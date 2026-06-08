"""
Notification sending and retrieval endpoints.
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.dependencies import TenantContext
from src.models.notifications import NotificationStatus
from src.schemas.notifications import (
    NotificationDetailResponse,
    NotificationRequest,
    NotificationResponse,
)
from src.services.notification_service import notification_service

router = APIRouter()


@router.post(
    "/notify",
    response_model=NotificationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send Notification",
    description="""
    Send a notification through one or more channels.
    
    Supports three modes:
    - **Raw HTML**: Provide `html` field directly
    - **Template**: Provide `template_id` to use a stored template
    - **Hybrid**: Provide both for template with overrides
    
    ## Example - Send email with template:
    ```json
    {
        "type": "email",
        "recipients": ["user@example.com"],
        "template_id": "550e8400-e29b-41d4-a716-446655440000",
        "variables": {"name": "John", "code": "123456"}
    }
    ```
    
    ## Example - Send SMS:
    ```json
    {
        "type": "sms",
        "recipients": ["+1234567890"],
        "sms_content": "Hi {{ name }}, your code is {{ code }}",
        "variables": {"name": "John", "code": "123456"}
    }
    ```
    """,
)
async def send_notification(
    request: NotificationRequest,
    tenant: TenantContext,
) -> NotificationResponse:
    """Send a notification."""
    notification = await notification_service.send_notification(
        request=request,
        user_id=tenant.user_id,
        api_key_id=str(tenant.api_key_id),
        workspace_id=tenant.workspace_id,
    )

    return NotificationResponse(
        notification_id=notification.notification_id,
        status=notification.status.value,
        channel=notification.channel.value,
        recipient_count=len(notification.recipients),
        created_at=notification.created_at,
        message="Notification queued for delivery",
    )


@router.get(
    "/notify/{notification_id}",
    response_model=NotificationDetailResponse,
    summary="Get Notification Details",
    description="Retrieve detailed information about a specific notification.",
)
async def get_notification(
    notification_id: UUID,
    tenant: TenantContext,
) -> NotificationDetailResponse:
    """Get notification details."""
    notification = await notification_service.get_notification(notification_id)

    if not notification or notification.user_id != tenant.user_id:
        from src.core.exceptions import NotFoundError

        raise NotFoundError("Notification not found")

    return NotificationDetailResponse(
        notification_id=notification.notification_id,
        campaign_id=notification.campaign_id,
        channel=notification.channel.value,
        status=notification.status.value,
        recipients=[r.to_dict() for r in notification.recipients],
        template_id=UUID(notification.template_id) if notification.template_id else None,
        subject=notification.subject,
        html_content=notification.html_content,
        sms_content=notification.sms_content,
        provider_responses=notification.provider_responses,
        error_message=notification.error_message,
        retry_count=notification.retry_count,
        metadata=notification.metadata,
        created_at=notification.created_at,
        updated_at=notification.created_at,  # Would need to track separately
    )


@router.post(
    "/notify/{notification_id}/retry",
    response_model=NotificationResponse,
    summary="Retry Failed Notification",
    description="Retry a failed notification.",
)
async def retry_notification(
    notification_id: UUID,
    tenant: TenantContext,
) -> NotificationResponse:
    """Retry a failed notification."""
    notification = await notification_service.retry_notification(notification_id)

    if not notification or notification.user_id != tenant.user_id:
        from src.core.exceptions import NotFoundError

        raise NotFoundError("Notification not found")

    return NotificationResponse(
        notification_id=notification.notification_id,
        status=notification.status.value,
        channel=notification.channel.value,
        recipient_count=len(notification.recipients),
        created_at=notification.created_at,
        message="Notification queued for retry",
    )


@router.get(
    "/notifications",
    response_model=dict,
    summary="List Notifications",
    description="List notifications with filtering and pagination.",
)
async def list_notifications(
    tenant: TenantContext,
    channel: str | None = Query(default=None, description="Filter by channel: email, sms, both"),
    status: str | None = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
) -> dict:
    """List notifications for the authenticated user."""
    from src.repositories.notification_repository import NotificationRepository

    repo = NotificationRepository()
    notifications, total = await repo.get_notifications_by_user(
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
        channel=channel,
        status=status,
        page=page,
        page_size=page_size,
    )

    total_pages = (total + page_size - 1) // page_size

    return {
        "notifications": [
            {
                "notification_id": str(n.notification_id),
                "channel": n.channel.value,
                "status": n.status.value,
                "recipient_count": len(n.recipients),
                "subject": n.subject,
                "template_id": n.template_id,
                "error_message": n.error_message,
                "created_at": n.created_at.isoformat(),
            }
            for n in notifications
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }