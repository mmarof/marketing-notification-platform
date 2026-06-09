"""
Campaign and analytics endpoints.
"""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from src.core.dependencies import TenantContext
from src.schemas.analytics import (
    AnalyticsEventFilter,
    AnalyticsEventResponse,
    AnalyticsSummaryResponse,
    CampaignDetailResponse,
)
from src.services.analytics_service import analytics_service

router = APIRouter()


@router.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    summary="Get Analytics Summary",
    description="""
    Get aggregated analytics summary for the authenticated user.

    Returns metrics including:
    - Total emails/SMS sent
    - Delivery rates
    - Failure rates
    - Bounce and complaint counts
    - Campaign statistics
    """,
)
async def get_analytics_summary(
    tenant: TenantContext,
    start_date: datetime | None = Query(
        default=None,
        description="Start of date range (ISO 8601)",
    ),
    end_date: datetime | None = Query(
        default=None,
        description="End of date range (ISO 8601)",
    ),
) -> AnalyticsSummaryResponse:
    """Get analytics summary."""
    return await analytics_service.get_summary(
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get(
    "/analytics/events",
    response_model=AnalyticsEventResponse,
    summary="Get Notification Events",
    description="Get paginated list of notification events with filtering.",
)
async def get_analytics_events(
    tenant: TenantContext,
    channel: str | None = Query(default=None, description="Filter: email, sms"),
    status: str | None = Query(default=None, description="Filter: sent, failed, bounced, etc."),
    template_id: UUID | None = Query(default=None, description="Filter by template"),
    campaign_id: UUID | None = Query(default=None, description="Filter by campaign"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort_by: str = Query(default="created_at", description="Sort field"),
    sort_order: str = Query(default="desc", description="asc or desc"),
) -> AnalyticsEventResponse:
    """Get notification events."""
    filters = AnalyticsEventFilter(
        channel=channel,  # type: ignore
        status=status,
        template_id=template_id,
        campaign_id=campaign_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,  # type: ignore
    )

    return await analytics_service.get_events(
        user_id=tenant.user_id,
        filters=filters,
        workspace_id=tenant.workspace_id,
    )


@router.get(
    "/analytics/campaign/{campaign_id}",
    response_model=CampaignDetailResponse,
    summary="Get Campaign Details",
    description="Get detailed analytics for a specific campaign.",
)
async def get_campaign_detail(
    campaign_id: UUID,
    tenant: TenantContext,
) -> CampaignDetailResponse:
    """Get campaign details."""
    return await analytics_service.get_campaign_detail(
        campaign_id=campaign_id,
        user_id=tenant.user_id,
    )


@router.get(
    "/analytics/delivery-stats",
    summary="Get Delivery Statistics",
    description="Get delivery statistics broken down by channel.",
)
async def get_delivery_stats(
    tenant: TenantContext,
    days: int = Query(default=30, ge=1, le=365, description="Number of days to include"),
) -> dict:
    """Get delivery statistics."""
    return await analytics_service.get_delivery_stats_by_channel(
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
        days=days,
    )
