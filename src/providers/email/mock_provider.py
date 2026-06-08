"""
Mock email provider for development and testing.
Stores sent emails in memory for inspection.
"""

import asyncio
from typing import Any

import structlog

from src.providers.base import BaseEmailProvider, EmailMessage, ProviderResponse

logger = structlog.get_logger(__name__)


class MockEmailProvider(BaseEmailProvider):
    """Mock email provider that logs and stores sent emails."""

    def __init__(self) -> None:
        self._sent_emails: list[dict[str, Any]] = []
        self._should_fail: bool = False
        self._fail_rate: float = 0.0  # 0.0 to 1.0

    def configure_failure(self, should_fail: bool = True, fail_rate: float = 0.0) -> None:
        """Configure failure behavior for testing."""
        self._should_fail = should_fail
        self._fail_rate = fail_rate

    def get_sent_emails(self) -> list[dict[str, Any]]:
        """Get all sent emails (for test assertions)."""
        return self._sent_emails.copy()

    def clear_sent_emails(self) -> None:
        """Clear stored emails."""
        self._sent_emails.clear()

    async def send(self, message: EmailMessage) -> ProviderResponse:
        """Simulate sending an email."""
        import random

        # Simulate failure if configured
        if self._should_fail or (self._fail_rate > 0 and random.random() < self._fail_rate):
            logger.info("email_mock_failed", to=message.to, subject=message.subject)
            return ProviderResponse(
                success=False,
                error_message="Mock failure",
                provider_code="MOCK_FAILURE",
                retryable=True,
                metadata={"provider": "mock"},
            )

        # Store email for inspection
        email_record = {
            "to": message.to,
            "subject": message.subject,
            "html_content": message.html_content,
            "text_content": message.text_content,
            "from_email": message.from_email,
            "from_name": message.from_name,
            "cc": message.cc,
            "bcc": message.bcc,
            "headers": message.headers,
            "metadata": message.metadata,
            "sent_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        self._sent_emails.append(email_record)

        logger.info(
            "email_mock_sent",
            to=message.to,
            subject=message.subject,
            total_sent=len(self._sent_emails),
        )

        # Simulate network latency
        await asyncio.sleep(0.01)

        return ProviderResponse(
            success=True,
            provider_message_id=f"mock-{len(self._sent_emails)}",
            metadata={"provider": "mock", "stored_index": len(self._sent_emails) - 1},
        )

    async def send_bulk(self, messages: list[EmailMessage]) -> list[ProviderResponse]:
        """Simulate bulk email sending."""
        return await asyncio.gather(*[self.send(msg) for msg in messages])

    async def health_check(self) -> bool:
        """Mock provider is always healthy."""
        return True