"""
Base provider interfaces for notification delivery.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResponse:
    """Standardized response from a notification provider."""

    success: bool
    provider_message_id: str | None = None
    provider_code: str | None = None
    raw_response: dict[str, Any] = field(default_factory=dict)
    error_message: str | None = None
    retryable: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EmailMessage:
    """Email message to be sent."""

    to: list[str]
    subject: str
    html_content: str | None = None
    text_content: str | None = None
    from_email: str | None = None
    from_name: str | None = None
    reply_to: str | None = None
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SMSMessage:
    """SMS message to be sent."""

    to: list[str]
    content: str
    from_number: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseEmailProvider(ABC):
    """Abstract base class for email providers."""

    @abstractmethod
    async def send(self, message: EmailMessage) -> ProviderResponse:
        """Send an email message."""
        ...

    @abstractmethod
    async def send_bulk(self, messages: list[EmailMessage]) -> list[ProviderResponse]:
        """Send multiple email messages."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy."""
        ...


class BaseSMSProvider(ABC):
    """Abstract base class for SMS providers."""

    @abstractmethod
    async def send(self, message: SMSMessage) -> ProviderResponse:
        """Send an SMS message."""
        ...

    @abstractmethod
    async def send_bulk(self, messages: list[SMSMessage]) -> list[ProviderResponse]:
        """Send multiple SMS messages."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the provider is healthy."""
        ...