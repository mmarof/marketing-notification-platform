"""
Analytics service for aggregated metrics and event tracking.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from src.repositories.analytics_repository import AnalyticsRepository
from src.schemas.analytics import (
    AnalyticsEventFilter,
    AnalyticsEventResponse,
    AnalyticsSummaryResponse,
    CampaignDetailResponse,
)

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """Service for analytics and reporting."""

    def __init__(self) -> None:
        self._repository = AnalyticsRepository()

    async def get_summary(
        self,
        user_id: str,
        workspace_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AnalyticsSummaryResponse:
        """Get analytics summary for a user."""
        summary = await self._repository.get_summary(
            user_id=user_id,
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
        )
        return AnalyticsSummaryResponse(**summary.to_dict())

    async def get_events(
        self,
        user_id: str,
        filters: AnalyticsEventFilter,
        workspace_id: str | None = None,
    ) -> AnalyticsEventResponse:
        """Get notification events with filtering."""
        events, total = await self._repository.get_events(
            user_id=user_id,
            workspace_id=workspace_id,
            channel=filters.channel,
            status=filters.status,
            template_id=str(filters.template_id) if filters.template_id else None,
            campaign_id=str(filters.campaign_id) if filters.campaign_id else None,
            start_date=filters.start_date,
            end_date=filters.end_date,
            page=filters.page,
            page_size=filters.page_size,
            sort_by=filters.sort_by,
            sort_order=filters.sort_order,
        )

        total_pages = (total + filters.page_size - 1) // filters.page_size

        return AnalyticsEventResponse(
            events=events,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            total_pages=total_pages,
        )

    async def get_campaign_detail(
        self,
        campaign_id: UUID,
        user_id: str,
    ) -> CampaignDetailResponse:
        """Get detailed campaign analytics."""
        detail = await self._repository.get_campaign_detail(
            campaign_id=str(campaign_id),
            user_id=user_id,
        )

        if not detail:
            from src.core.exceptions import NotFoundError

            raise NotFoundError(f"Campaign not found: {campaign_id}")

        # Fetch actual notifications for the campaign
        from src.repositories.notification_repository import NotificationRepository

        notif_repo = NotificationRepository()
        notifications, _ = await notif_repo.get_notifications_by_campaign(
            campaign_id=campaign_id, page=1, page_size=100
        )

        return CampaignDetailResponse(
            campaign_id=campaign_id,
            notification_count=detail["notification_count"],
            total_recipients=detail["total_recipients"],
            channel="both",  # Would need to determine from notifications
            status_breakdown=detail["status_breakdown"],
            notifications=[n.to_elasticsearch_document() for n in notifications],
            created_range=detail["created_range"],
        )

    async def get_delivery_stats_by_channel(
        self,
        user_id: str,
        workspace_id: str | None = None,
        days: int = 30,
    ) -> dict[str, Any]:
        """Get delivery statistics broken down by channel."""
        start_date = datetime.utcnow() - __import__("datetime").timedelta(days=days)

        channel_counts = await self._repository.get_channel_counts(
            user_id=user_id,
            workspace_id=workspace_id,
            start_date=start_date,
        )

        return {
            "period_days": days,
            "channels": channel_counts,
            "total": sum(channel_counts.values()),
        }


# Singleton instance
analytics_service = AnalyticsService()
