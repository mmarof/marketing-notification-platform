"""
Notification service - core business logic for sending notifications.
Orchestrates template rendering, provider selection, and event logging.
"""

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from src.config.settings import get_settings
from src.core.exceptions import ProviderError, ValidationError
from src.models.notifications import (
    EmailMode,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Recipient,
)
from src.providers.base import EmailMessage, SMSMessage
from src.repositories.notification_repository import NotificationRepository
from src.schemas.notifications import NotificationRequest, RecipientInput
from src.template_engine.engine import DEFAULT_EMAIL_LAYOUT, template_engine

logger = structlog.get_logger(__name__)
settings = get_settings()


class NotificationService:
    """
    Core notification service.
    Handles notification creation, rendering, and delivery.
    """

    def __init__(self) -> None:
        self._notification_repo = NotificationRepository()
        self._email_provider = self._create_email_provider()
        self._sms_provider = self._create_sms_provider()

    def _create_email_provider(self):
        """Create appropriate email provider based on configuration."""
        if settings.use_mock_providers:
            from src.providers.email.mock_provider import MockEmailProvider

            return MockEmailProvider()
        else:
            from src.providers.email.smtp_provider import SMTPEmailProvider

            return SMTPEmailProvider()

    def _create_sms_provider(self):
        """Create appropriate SMS provider based on configuration."""
        if settings.use_mock_providers or not settings.twilio.is_configured:
            from src.providers.sms.mock_provider import MockSMSProvider

            return MockSMSProvider()
        else:
            from src.providers.sms.twilio_provider import TwilioSMSProvider

            return TwilioSMSProvider()

    def _parse_recipients(
        self, recipients: list[str | RecipientInput]
    ) -> list[Recipient]:
        """Parse recipient input into Recipient objects."""
        parsed = []
        for r in recipients:
            if isinstance(r, str):
                parsed.append(Recipient.from_string(r))
            else:
                parsed.append(
                    Recipient(
                        email=r.email,
                        phone=r.phone,
                        variables=r.variables,
                        metadata=r.metadata,
                    )
                )
        return parsed

    def _determine_channel(
        self, request: NotificationRequest, recipients: list[Recipient]
    ) -> NotificationChannel:
        """Determine notification channel based on request and recipients."""
        # Check channel overrides
        if request.channels:
            email_enabled = request.channels.get("email", False)
            sms_enabled = request.channels.get("sms", False)
            if email_enabled and sms_enabled:
                return NotificationChannel.BOTH
            elif email_enabled:
                return NotificationChannel.EMAIL
            elif sms_enabled:
                return NotificationChannel.SMS

        # Use type field
        channel_map = {
            "email": NotificationChannel.EMAIL,
            "sms": NotificationChannel.SMS,
            "both": NotificationChannel.BOTH,
        }
        return channel_map.get(request.type, NotificationChannel.BOTH)

    def _determine_email_mode(self, request: NotificationRequest) -> EmailMode:
        """Determine email rendering mode."""
        if request.html and request.template_id:
            return EmailMode.HYBRID
        elif request.html:
            return EmailMode.RAW_HTML
        else:
            return EmailMode.TEMPLATE

    async def _get_template_content(
        self, template_id: UUID, user_id: str
    ) -> dict[str, str] | None:
        """Load template content from database."""
        from src.repositories.base import get_elasticsearch_client

        client = get_elasticsearch_client()
        if not client:
            return None

        try:
            response = await client.get(
                index=f"{settings.elasticsearch.index_prefix}templates",
                id=str(template_id),
            )
            doc = response.get("_source", {})
            if doc.get("user_id") == user_id and doc.get("status") == "active":
                return {
                    "content": doc.get("content", ""),
                    "subject": doc.get("subject"),
                    "text_content": doc.get("text_content"),
                }
        except Exception as e:
            logger.warning("template_load_failed", template_id=template_id, error=str(e))

        return None

    def _render_email_content(
        self,
        request: NotificationRequest,
        template_content: dict[str, str] | None,
        variables: dict[str, Any],
    ) -> tuple[str, str | None, str | None]:
        """Render email content based on mode. Returns (html, subject, text)."""
        mode = self._determine_email_mode(request)

        if mode == EmailMode.RAW_HTML:
            return request.html, request.subject, request.text

        elif mode == EmailMode.TEMPLATE:
            if not template_content:
                raise ValidationError("Template ID required for template mode")
            html = template_engine.render_email(
                template_content["content"],
                variables,
                layout=DEFAULT_EMAIL_LAYOUT,
            )
            subject = request.subject or template_content.get("subject")
            text = template_content.get("text_content")
            return html, subject, text

        else:  # HYBRID
            if not template_content:
                raise ValidationError("Template ID required for hybrid mode")
            # Render template first, then override with provided HTML
            base_html = template_engine.render_email(
                template_content["content"],
                variables,
                layout=DEFAULT_EMAIL_LAYOUT,
            )
            # In hybrid mode, use provided HTML as the content block
            html = template_engine.render_email(
                request.html,
                variables,
                layout=DEFAULT_EMAIL_LAYOUT,
            )
            subject = request.subject or template_content.get("subject")
            text = request.text or template_content.get("text_content")
            return html, subject, text

    def _render_sms_content(
        self,
        request: NotificationRequest,
        template_content: dict[str, str] | None,
        variables: dict[str, Any],
    ) -> str:
        """Render SMS content."""
        if request.sms_content:
            return template_engine.render_sms(request.sms_content, variables)
        elif template_content and template_content.get("content"):
            return template_engine.render_sms(template_content["content"], variables)
        else:
            raise ValidationError("SMS content or template required for SMS notifications")

    async def send_notification(
        self,
        request: NotificationRequest,
        user_id: str,
        api_key_id: str,
        workspace_id: str | None = None,
    ) -> Notification:
        """Send a single notification (may be to multiple recipients)."""
        # Parse recipients
        recipients = self._parse_recipients(request.recipients)

        # Determine channel and mode
        channel = self._determine_channel(request, recipients)

        # Load template if specified
        template_content = None
        if request.template_id:
            template_content = await self._get_template_content(
                request.template_id, user_id
            )
            if not template_content:
                raise ValidationError(
                    f"Template not found or inactive: {request.template_id}"
                )

        # Create notification record
        notification = Notification(
            channel=channel,
            recipients=recipients,
            user_id=user_id,
            api_key_id=api_key_id,
            workspace_id=workspace_id,
            template_id=str(request.template_id) if request.template_id else None,
            subject=request.subject,
            email_mode=self._determine_email_mode(request),
            global_variables=request.variables,
            metadata=request.metadata,
            campaign_id=request.campaign_id,
        )

        # Save initial notification
        await self._notification_repo.save_notification(notification)

        # Update status to processing
        await self._notification_repo.update_notification_status(
            notification.notification_id, NotificationStatus.PROCESSING
        )
        notification.status = NotificationStatus.PROCESSING

        # Send based on channel
        try:
            provider_responses = {}

            if channel in (NotificationChannel.EMAIL, NotificationChannel.BOTH):
                email_response = await self._send_email_notification(
                    notification, request, template_content
                )
                provider_responses["email"] = {
                    "success": email_response.success,
                    "message_id": email_response.provider_message_id,
                    "error": email_response.error_message,
                }

            if channel in (NotificationChannel.SMS, NotificationChannel.BOTH):
                sms_response = await self._send_sms_notification(
                    notification, request, template_content
                )
                provider_responses["sms"] = {
                    "success": sms_response.success,
                    "message_id": sms_response.provider_message_id,
                    "error": sms_response.error_message,
                }

            # Determine final status
            all_success = all(
                r.get("success", False) for r in provider_responses.values()
            )
            any_success = any(
                r.get("success", False) for r in provider_responses.values()
            )

            if all_success:
                final_status = NotificationStatus.SENT
            elif any_success:
                final_status = NotificationStatus.SENT  # Partial success
            else:
                final_status = NotificationStatus.FAILED

            # Update notification
            await self._notification_repo.update_notification_status(
                notification.notification_id,
                final_status,
                provider_response=provider_responses,
                error_message=None if all_success else "Partial or complete failure",
            )
            notification.status = final_status
            notification.provider_responses = provider_responses

        except Exception as e:
            logger.error(
                "notification_processing_error",
                notification_id=str(notification.notification_id),
                error=str(e),
            )
            await self._notification_repo.update_notification_status(
                notification.notification_id,
                NotificationStatus.FAILED,
                error_message=str(e),
            )
            notification.status = NotificationStatus.FAILED
            notification.error_message = str(e)

        return notification

    async def _send_email_notification(
        self,
        notification: Notification,
        request: NotificationRequest,
        template_content: dict[str, str] | None,
    ) -> Any:
        """Send email portion of notification."""
        # Merge global and per-recipient variables
        all_variables = {**request.variables}

        # Render content
        html, subject, text = self._render_email_content(
            request, template_content, all_variables
        )

        # Build email message
        emails = [r.email for r in notification.recipients if r.email]
        if not emails:
            return type("Response", (), {"success": True, "provider_message_id": None, "error_message": None, "metadata": {}})()

        email_message = EmailMessage(
            to=emails,
            subject=subject or "Notification",
            html_content=html,
            text_content=text,
            metadata={"notification_id": str(notification.notification_id)},
        )

        return await self._email_provider.send(email_message)

    async def _send_sms_notification(
        self,
        notification: Notification,
        request: NotificationRequest,
        template_content: dict[str, str] | None,
    ) -> Any:
        """Send SMS portion of notification."""
        all_variables = {**request.variables}

        content = self._render_sms_content(request, template_content, all_variables)

        phones = [r.phone for r in notification.recipients if r.phone]
        if not phones:
            return type("Response", (), {"success": True, "provider_message_id": None, "error_message": None, "metadata": {}})()

        sms_message = SMSMessage(
            to=phones,
            content=content,
            metadata={"notification_id": str(notification.notification_id)},
        )

        return await self._sms_provider.send(sms_message)

    async def send_bulk_notifications(
        self,
        requests: list[tuple[NotificationRequest, str, str, str | None]],
    ) -> list[Notification]:
        """Send multiple notifications with concurrency control."""
        semaphore = asyncio.Semaphore(20)  # Max 20 concurrent notifications

        async def send_with_limit(
            args: tuple[NotificationRequest, str, str, str | None]
        ) -> Notification:
            async with semaphore:
                return await self.send_notification(*args)

        tasks = [send_with_limit(args) for args in requests]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def get_notification(self, notification_id: UUID) -> Notification | None:
        """Get notification by ID."""
        return await self._notification_repo.get_notification(notification_id)

    async def retry_notification(self, notification_id: UUID) -> Notification | None:
        """Retry a failed notification."""
        notification = await self._notification_repo.get_notification(notification_id)
        if not notification:
            return None

        if notification.status not in (NotificationStatus.FAILED,):
            raise ValidationError("Only failed notifications can be retried")

        if notification.retry_count >= notification.max_retries:
            raise ValidationError("Maximum retry count exceeded")

        # Increment retry count
        await self._notification_repo.update_document(
            str(notification_id),
            {
                "retry_count": notification.retry_count + 1,
                "status": NotificationStatus.QUEUED.value,
                "updated_at": datetime.utcnow().isoformat(),
            },
        )

        # Re-process (simplified - in production, queue this)
        notification.retry_count += 1
        notification.status = NotificationStatus.QUEUED
        return notification


# Singleton instance
notification_service = NotificationService()