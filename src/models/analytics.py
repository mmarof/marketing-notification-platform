"""
Analytics domain models.
"""

from datetime import datetime
from typing import Any


class AnalyticsSummary:
    """Aggregated analytics summary."""

    def __init__(
        self,
        user_id: str,
        workspace_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ):
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.start_date = start_date
        self.end_date = end_date

        # Email metrics
        self.total_emails_sent: int = 0
        self.emails_delivered: int = 0
        self.emails_failed: int = 0
        self.emails_bounced: int = 0
        self.emails_complained: int = 0

        # SMS metrics
        self.total_sms_sent: int = 0
        self.sms_delivered: int = 0
        self.sms_failed: int = 0

        # Computed rates
        self.email_delivery_rate: float = 0.0
        self.email_failure_rate: float = 0.0
        self.sms_delivery_rate: float = 0.0
        self.sms_failure_rate: float = 0.0
        self.overall_success_rate: float = 0.0

        # Campaign metrics
        self.total_campaigns: int = 0
        self.total_recipients: int = 0

    def compute_rates(self) -> None:
        """Compute delivery and failure rates."""
        if self.total_emails_sent > 0:
            self.email_delivery_rate = round(
                (self.emails_delivered / self.total_emails_sent) * 100, 2
            )
            self.email_failure_rate = round(
                (self.emails_failed / self.total_emails_sent) * 100, 2
            )

        if self.total_sms_sent > 0:
            self.sms_delivery_rate = round(
                (self.sms_delivered / self.total_sms_sent) * 100, 2
            )
            self.sms_failure_rate = round(
                (self.sms_failed / self.total_sms_sent) * 100, 2
            )

        total_sent = self.total_emails_sent + self.total_sms_sent
        total_success = self.emails_delivered + self.sms_delivered
        if total_sent > 0:
            self.overall_success_rate = round((total_success / total_sent) * 100, 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "period": {
                "start": self.start_date.isoformat() if self.start_date else None,
                "end": self.end_date.isoformat() if self.end_date else None,
            },
            "email": {
                "total_sent": self.total_emails_sent,
                "delivered": self.emails_delivered,
                "failed": self.emails_failed,
                "bounced": self.emails_bounced,
                "complained": self.emails_complained,
                "delivery_rate": self.email_delivery_rate,
                "failure_rate": self.email_failure_rate,
            },
            "sms": {
                "total_sent": self.total_sms_sent,
                "delivered": self.sms_delivered,
                "failed": self.sms_failed,
                "delivery_rate": self.sms_delivery_rate,
                "failure_rate": self.sms_failure_rate,
            },
            "overall": {
                "total_sent": self.total_emails_sent + self.total_sms_sent,
                "total_campaigns": self.total_campaigns,
                "total_recipients": self.total_recipients,
                "success_rate": self.overall_success_rate,
            },
        }


class AnalyticsEvent:
    """Individual event for analytics timeline."""

    def __init__(
        self,
        notification_id: str,
        event_type: str,
        timestamp: datetime,
        channel: str,
        recipient: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.notification_id = notification_id
        self.event_type = event_type
        self.timestamp = timestamp
        self.channel = channel
        self.recipient = recipient
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "notification_id": self.notification_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "channel": self.channel,
            "recipient": self.recipient,
            "details": self.details,
        }