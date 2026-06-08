"""
Mock SMS provider for development and testing.
"""

import asyncio
from typing import Any

import structlog

from src.providers.base import BaseSMSProvider, ProviderResponse, SMSMessage

logger = structlog.get_logger(__name__)


class MockSMSProvider(BaseSMSProvider):
    """Mock SMS provider that logs and stores sent messages."""

    def __init__(self) -> None:
        self._sent_messages: list[dict[str, Any]] = []
        self._should_fail: bool = False
        self._fail_rate: float = 0.0

    def configure_failure(self, should_fail: bool = True, fail_rate: float = 0.0) -> None:
        """Configure failure behavior for testing."""
        self._should_fail = should_fail
        self._fail_rate = fail_rate

    def get_sent_messages(self) -> list[dict[str, Any]]:
        """Get all sent messages (for test assertions)."""
        return self._sent_messages.copy()

    def clear_sent_messages(self) -> None:
        """Clear stored messages."""
        self._sent_messages.clear()

    async def send(self, message: SMSMessage) -> ProviderResponse:
        """Simulate sending an SMS."""
        import random

        if self._should_fail or (self._fail_rate > 0 and random.random() < self._fail_rate):
            logger.info("sms_mock_failed", to=message.to)
            return ProviderResponse(
                success=False,
                error_message="Mock failure",
                provider_code="MOCK_FAILURE",
                retryable=True,
                metadata={"provider": "mock"},
            )

        message_record = {
            "to": message.to,
            "content": message.content,
            "from_number": message.from_number,
            "metadata": message.metadata,
            "sent_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        self._sent_messages.append(message_record)

        logger.info(
            "sms_mock_sent",
            to=message.to,
            total_sent=len(self._sent_messages),
        )

        await asyncio.sleep(0.005)

        return ProviderResponse(
            success=True,
            provider_message_id=f"mock-sms-{len(self._sent_messages)}",
            metadata={
                "provider": "mock",
                "recipients": len(message.to),
            },
        )

    async def send_bulk(self, messages: list[SMSMessage]) -> list[ProviderResponse]:
        """Simulate bulk SMS sending."""
        return await asyncio.gather(*[self.send(msg) for msg in messages])

    async def health_check(self) -> bool:
        """Mock provider is always healthy."""
        return True