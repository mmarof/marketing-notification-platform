"""
Notification request and response schemas.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class RecipientInput(BaseModel):
    """Schema for a single recipient."""

    email: str | None = Field(default=None, description="Recipient email address")
    phone: str | None = Field(default=None, description="Recipient phone number (E.164 format)")
    variables: dict[str, Any] = Field(default_factory=dict, description="Per-recipient template variables")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional recipient metadata")

    @model_validator(mode="after")
    def validate_has_contact(self) -> "RecipientInput":
        if not self.email and not self.phone:
            raise ValueError("Recipient must have either email or phone")
        return self


class NotificationRequest(BaseModel):
    """Schema for sending a notification."""

    type: Literal["email", "sms", "both"] = Field(
        default="both",
        description="Notification type",
    )
    recipients: list[str | RecipientInput] = Field(
        min_length=1,
        max_length=10000,
        description="List of recipient emails/phones or recipient objects",
    )
    template_id: UUID | None = Field(
        default=None,
        description="Template ID to use for rendering",
    )
    subject: str | None = Field(
        default=None,
        max_length=500,
        description="Email subject line (overrides template subject)",
    )
    html: str | None = Field(
        default=None,
        description="Raw HTML content (bypasses template)",
    )
    text: str | None = Field(
        default=None,
        description="Plain text fallback content",
    )
    sms_content: str | None = Field(
        default=None,
        description="SMS message content (bypasses template)",
    )
    variables: dict[str, Any] = Field(
        default_factory=dict,
        description="Global template variables",
    )
    channels: dict[str, bool] | None = Field(
        default=None,
        description="Channel overrides: {email: true, sms: false}",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional notification metadata",
    )
    campaign_id: UUID | None = Field(
        default=None,
        description="Associate with a campaign for grouping",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description="Schedule for future delivery (ISO 8601)",
    )

    @field_validator("recipients")
    @classmethod
    def validate_recipients_list(cls, v: list) -> list:
        if len(v) > 10000:
            raise ValueError("Maximum 10,000 recipients per request")
        return v


class NotificationResponse(BaseModel):
    """Schema for notification response."""

    notification_id: UUID
    status: str
    channel: str
    recipient_count: int
    created_at: datetime
    message: str


class BulkNotificationResponse(BaseModel):
    """Schema for bulk notification response."""

    notification_ids: list[UUID]
    total_sent: int
    status: str
    message: str


class NotificationDetailResponse(BaseModel):
    """Detailed notification information."""

    notification_id: UUID
    campaign_id: UUID | None
    channel: str
    status: str
    recipients: list[dict[str, Any]]
    template_id: UUID | None
    subject: str | None
    html_content: str | None
    sms_content: str | None
    provider_responses: dict[str, Any]
    error_message: str | None
    retry_count: int
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime