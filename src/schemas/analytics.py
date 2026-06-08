"""
Analytics request and response schemas.
"""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AnalyticsSummaryResponse(BaseModel):
    """Response schema for analytics summary."""

    period: dict[str, str | None]
    email: dict[str, Any]
    sms: dict[str, Any]
    overall: dict[str, Any]


class AnalyticsEventFilter(BaseModel):
    """Filter parameters for analytics events."""

    channel: Literal["email", "sms"] | None = None
    status: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    template_id: UUID | None = None
    campaign_id: UUID | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    sort_by: str = Field(default="created_at")
    sort_order: Literal["asc", "desc"] = Field(default="desc")


class AnalyticsEventResponse(BaseModel):
    """Response schema for analytics events list."""

    events: list[dict[str, Any]]
    total: int
    page: int
    page_size: int
    total_pages: int


class CampaignDetailResponse(BaseModel):
    """Response schema for campaign detail."""

    campaign_id: UUID
    notification_count: int
    total_recipients: int
    channel: str
    status_breakdown: dict[str, int]
    notifications: list[dict[str, Any]]
    created_range: dict[str, str]