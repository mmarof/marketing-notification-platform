"""
Token bucket rate limiter implementation.
Uses Redis for distributed rate limiting across multiple instances.
"""

import time
from dataclasses import dataclass

import structlog

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    retry_after: int | None = None


class RateLimiter:
    """
    Token bucket rate limiter with sliding window.
    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self) -> None:
        self._in_memory_buckets: dict[str, dict] = {}
        self._redis_client = None

    async def _get_redis(self):
        """Lazy-load Redis client."""
        if self._redis_client is None:
            try:
                import redis.asyncio as aioredis

                self._redis_client = aioredis.from_url(
                    settings.redis.url,
                    decode_responses=True,
                    socket_timeout=settings.redis.socket_timeout,
                    socket_connect_timeout=settings.redis.socket_connect_timeout,
                )
                await self._redis_client.ping()
            except Exception as e:
                logger.warning("redis_unavailable_falling_back_to_memory", error=str(e))
                self._redis_client = None
        return self._redis_client

    async def check_rate_limit(self, key: str) -> tuple[bool, int | None]:
        """
        Check if request is allowed under rate limit.
        Returns (allowed, retry_after_seconds).
        """
        if not settings.rate_limit.enabled:
            return True, None

        redis = await self._get_redis()

        if redis:
            return await self._check_redis(redis, key)
        return self._check_in_memory(key)

    async def _check_redis(self, redis, key: str) -> tuple[bool, int | None]:
        """Check rate limit using Redis sliding window."""
        now = time.time()
        minute_key = f"ratelimit:minute:{key}"
        hour_key = f"ratelimit:hour:{key}"

        pipe = redis.pipeline()

        # Minute window
        pipe.zadd(minute_key, {f"{now}": now})
        pipe.zremrangebyscore(minute_key, 0, now - 60)
        pipe.zcard(minute_key)
        pipe.expire(minute_key, 120)

        # Hour window
        pipe.zadd(hour_key, {f"{now}": now})
        pipe.zremrangebyscore(hour_key, 0, now - 3600)
        pipe.zcard(hour_key)
        pipe.expire(hour_key, 7200)

        results = await pipe.execute()

        minute_count = results[2]
        hour_count = results[5]

        if minute_count > settings.rate_limit.requests_per_minute:
            retry_after = 60 - int(now - float(redis.zrange(minute_key, 0, 0, withscores=True)[0][1]))
            return False, max(1, retry_after)

        if hour_count > settings.rate_limit.requests_per_hour:
            retry_after = 3600 - int(now - float(redis.zrange(hour_key, 0, 0, withscores=True)[0][1]))
            return False, max(1, retry_after)

        return True, None

    def _check_in_memory(self, key: str) -> tuple[bool, int | None]:
        """Check rate limit using in-memory storage (single instance only)."""
        now = time.time()

        if key not in self._in_memory_buckets:
            self._in_memory_buckets[key] = {
                "minute_requests": [],
                "hour_requests": [],
            }

        bucket = self._in_memory_buckets[key]

        # Clean old entries
        bucket["minute_requests"] = [t for t in bucket["minute_requests"] if now - t < 60]
        bucket["hour_requests"] = [t for t in bucket["hour_requests"] if now - t < 3600]

        # Check limits
        if len(bucket["minute_requests"]) >= settings.rate_limit.requests_per_minute:
            retry_after = 60 - int(now - bucket["minute_requests"][0])
            return False, max(1, retry_after)

        if len(bucket["hour_requests"]) >= settings.rate_limit.requests_per_hour:
            retry_after = 3600 - int(now - bucket["hour_requests"][0])
            return False, max(1, retry_after)

        # Record request
        bucket["minute_requests"].append(now)
        bucket["hour_requests"].append(now)

        return True, None

    async def close(self) -> None:
        """Cleanup Redis connection."""
        if self._redis_client:
            await self._redis_client.close()