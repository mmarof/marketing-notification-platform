"""
FastAPI dependency injection functions.
Provides common dependencies for request handling.
"""

from typing import Annotated

from fastapi import Depends, Header

from src.config.settings import get_settings
from src.core.exceptions import AuthenticationError, RateLimitError
from src.core.middleware import get_request_id
from src.core.rate_limiter import RateLimiter
from src.repositories.api_key_repository import ApiKeyRepository
from src.schemas.api_keys import ApiKeyContext

settings = get_settings()
rate_limiter = RateLimiter()


async def verify_api_key(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> ApiKeyContext:
    """
    Verify API key from Authorization header or X-API-Key header.
    Supports both 'Bearer <key>' and raw key formats.
    """
    api_key = None

    if authorization:
        if authorization.startswith("Bearer "):
            api_key = authorization[7:]
        else:
            api_key = authorization
    elif x_api_key:
        api_key = x_api_key

    if not api_key:
        raise AuthenticationError("API key is required. Provide via Authorization or X-API-Key header.")

    # Validate rate limit before expensive operations
    if settings.rate_limit.enabled:
        is_allowed, retry_after = await rate_limiter.check_rate_limit(api_key)
        if not is_allowed:
            raise RateLimitError(
                f"Rate limit exceeded. Try again in {retry_after} seconds.",
                retry_after=retry_after,
            )

    # Look up API key in Elasticsearch
    repository = ApiKeyRepository()
    key_context = await repository.validate_api_key(api_key)

    if not key_context:
        raise AuthenticationError("Invalid or expired API key.")

    if not key_context.is_active:
        raise AuthenticationError("API key has been deactivated.")

    return key_context


async def get_tenant_context(
    api_key_context: Annotated[ApiKeyContext, Depends(verify_api_key)],
) -> ApiKeyContext:
    """Get tenant context from authenticated API key."""
    return api_key_context


def get_request_id_header(
    x_request_id: Annotated[str | None, Header(alias="X-Request-ID")] = None,
) -> str:
    """Get or generate request ID."""
    return x_request_id or get_request_id()


# Type aliases for cleaner dependency injection
TenantContext = Annotated[ApiKeyContext, Depends(get_tenant_context)]
RequestId = Annotated[str, Depends(get_request_id_header)]