"""
Notification domain models.
Represents the core business entities for notifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field, field_validator


class NotificationChannel(str, Enum):
    """Supported notification channels."""

    EMAIL = "email"
    SMS = "sms"
    BOTH = "both"


class NotificationStatus(str, Enum):
    """Notification lifecycle states."""

    QUEUED = "queued"
    PROCESSING = "processing"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"
    COMPLAINED = "complained"
    UNSUBSCRIBED = "unsubscribed"


class EmailMode(str, Enum):
    """Email content rendering modes."""

    RAW_HTML = "raw_html"
    TEMPLATE = "template"
    HYBRID = "hybrid"


class Recipient:
    """Represents a notification recipient."""

    def __init__(
        self,
        email: str | None = None,
        phone: str | None = None,
        variables: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.email = email
        self.phone = phone
        self.variables = variables or {}
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "phone": self.phone,
            "variables": self.variables,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Recipient":
        return cls(
            email=data.get("email"),
            phone=data.get("phone"),
            variables=data.get("variables"),
            metadata=data.get("metadata"),
        )

    @classmethod
    def from_string(cls, value: str) -> "Recipient":
        """Create recipient from email or phone string."""
        if "@" in value:
            return cls(email=value)
        return cls(phone=value)


class Notification:
    """
    Core notification entity.
    Represents a single notification that may span multiple channels.
    """

    def __init__(
        self,
        channel: NotificationChannel,
        recipients: list[Recipient],
        user_id: str,
        api_key_id: str,
        workspace_id: str | None = None,
        template_id: str | None = None,
        subject: str | None = None,
        html_content: str | None = None,
        text_content: str | None = None,
        sms_content: str | None = None,
        email_mode: EmailMode = EmailMode.TEMPLATE,
        global_variables: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        notification_id: UUID | None = None,
        campaign_id: UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.notification_id = notification_id or uuid4()
        self.campaign_id = campaign_id
        self.channel = channel
        self.recipients = recipients
        self.user_id = user_id
        self.api_key_id = api_key_id
        self.workspace_id = workspace_id
        self.template_id = template_id
        self.subject = subject
        self.html_content = html_content
        self.text_content = text_content
        self.sms_content = sms_content
        self.email_mode = email_mode
        self.global_variables = global_variables or {}
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.utcnow()
        self.status = NotificationStatus.QUEUED

        # Provider response tracking
        self.provider_responses: dict[str, Any] = {}
        self.error_message: str | None = None
        self.retry_count: int = 0
        self.max_retries: int = 3

    def to_elasticsearch_document(self) -> dict[str, Any]:
        """Convert to Elasticsearch document format."""
        return {
            "notification_id": str(self.notification_id),
            "campaign_id": str(self.campaign_id) if self.campaign_id else None,
            "channel": self.channel.value,
            "status": self.status.value,
            "user_id": self.user_id,
            "api_key_id": self.api_key_id,
            "workspace_id": self.workspace_id,
            "template_id": self.template_id,
            "subject": self.subject,
            "html_content": self.html_content,
            "text_content": self.text_content,
            "sms_content": self.sms_content,
            "email_mode": self.email_mode.value,
            "recipients": [r.to_dict() for r in self.recipients],
            "recipient_count": len(self.recipients),
            "global_variables": self.global_variables,
            "provider_responses": self.provider_responses,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

    @classmethod
    def from_elasticsearch_document(cls, doc: dict[str, Any]) -> "Notification":
        """Create Notification from Elasticsearch document."""
        recipients = [Recipient.from_dict(r) for r in doc.get("recipients", [])]
        notification = cls(
            notification_id=UUID(doc["notification_id"]),
            campaign_id=UUID(doc["campaign_id"]) if doc.get("campaign_id") else None,
            channel=NotificationChannel(doc["channel"]),
            recipients=recipients,
            user_id=doc["user_id"],
            api_key_id=doc["api_key_id"],
            workspace_id=doc.get("workspace_id"),
            template_id=doc.get("template_id"),
            subject=doc.get("subject"),
            html_content=doc.get("html_content"),
            text_content=doc.get("text_content"),
            sms_content=doc.get("sms_content"),
            email_mode=EmailMode(doc.get("email_mode", "template")),
            global_variables=doc.get("global_variables"),
            metadata=doc.get("metadata"),
        )
        notification.status = NotificationStatus(doc.get("status", "queued"))
        notification.provider_responses = doc.get("provider_responses", {})
        notification.error_message = doc.get("error_message")
        notification.retry_count = doc.get("retry_count", 0)
        return notification