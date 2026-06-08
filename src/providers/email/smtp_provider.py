"""
SMTP email provider implementation.
Uses aiosmtplib for async SMTP operations.
"""

import asyncio
from typing import Any

import structlog
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config.settings import get_settings
from src.providers.base import BaseEmailProvider, EmailMessage, ProviderResponse

logger = structlog.get_logger(__name__)
settings = get_settings()


class SMTPEmailProvider(BaseEmailProvider):
    """Email provider using SMTP protocol."""

    def __init__(self) -> None:
        self._host = settings.smtp.host
        self._port = settings.smtp.port
        self._username = settings.smtp.username
        self._password = (
            settings.smtp.password.get_secret_value() if settings.smtp.password else None
        )
        self._use_tls = settings.smtp.use_tls
        self._use_ssl = settings.smtp.use_ssl
        self._from_email = settings.smtp.from_email
        self._from_name = settings.smtp.from_name
        self._timeout = settings.smtp.timeout

    def _build_mime_message(self, message: EmailMessage) -> MIMEMultipart:
        """Build MIME message from EmailMessage."""
        msg = MIMEMultipart("alternative")

        from_email = message.from_email or self._from_email
        from_name = message.from_name or self._from_name

        if from_name:
            msg["From"] = f"{from_name} <{from_email}>"
        else:
            msg["From"] = from_email

        msg["To"] = ", ".join(message.to)
        msg["Subject"] = message.subject

        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        if message.cc:
            msg["Cc"] = ", ".join(message.cc)

        # Add custom headers
        for key, value in message.headers.items():
            msg[key] = value

        # Add text part
        if message.text_content:
            text_part = MIMEText(message.text_content, "plain", "utf-8")
            msg.attach(text_part)

        # Add HTML part
        if message.html_content:
            html_part = MIMEText(message.html_content, "html", "utf-8")
            msg.attach(html_part)

        return msg

    async def send(self, message: EmailMessage) -> ProviderResponse:
        """Send a single email via SMTP."""
        try:
            import aiosmtplib

            mime_msg = self._build_mime_message(message)

            recipients = list(set(message.to + message.cc + message.bcc))

            await aiosmtplib.send(
                mime_msg,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                use_tls=self._use_tls,
                start_tls=self._use_tls and not self._use_ssl,
                recipients=recipients,
                timeout=self._timeout,
            )

            logger.info(
                "email_sent",
                to=message.to,
                subject=message.subject,
            )

            return ProviderResponse(
                success=True,
                provider_message_id=f"smtp-{id(message)}",
                metadata={"provider": "smtp", "recipients": len(recipients)},
            )

        except Exception as e:
            error_str = str(e)
            retryable = "timeout" in error_str.lower() or "connection" in error_str.lower()

            logger.error(
                "email_send_failed",
                to=message.to,
                subject=message.subject,
                error=error_str,
                retryable=retryable,
            )

            return ProviderResponse(
                success=False,
                error_message=error_str,
                provider_code="SMTP_ERROR",
                retryable=retryable,
                metadata={"provider": "smtp"},
            )

    async def send_bulk(self, messages: list[EmailMessage]) -> list[ProviderResponse]:
        """Send multiple emails with concurrency control."""
        semaphore = asyncio.Semaphore(10)  # Max 10 concurrent sends

        async def send_with_limit(msg: EmailMessage) -> ProviderResponse:
            async with semaphore:
                return await self.send(msg)

        tasks = [send_with_limit(msg) for msg in messages]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def health_check(self) -> bool:
        """Check SMTP connectivity."""
        try:
            import aiosmtplib

            await aiosmtplib.connect(
                hostname=self._host,
                port=self._port,
                use_tls=self._use_ssl,
                timeout=5,
            )
            return True
        except Exception:
            return False