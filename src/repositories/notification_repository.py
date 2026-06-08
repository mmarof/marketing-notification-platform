"""
Notification repository for Elasticsearch operations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from src.models.notifications import Notification, NotificationStatus
from src.repositories.base import BaseRepository, get_elasticsearch_client


class NotificationRepository(BaseRepository):
    """Repository for notification persistence."""

    def _get_index_suffix(self) -> str:
        return "notifications"

    async def save_notification(self, notification: Notification) -> Notification:
        """Save a notification to Elasticsearch."""
        doc = notification.to_elasticsearch_document()
        await self.index_document(str(notification.notification_id), doc)
        return notification

    async def get_notification(self, notification_id: UUID) -> Notification | None:
        """Get a notification by ID."""
        doc = await self.get_document(str(notification_id))
        if doc:
            return Notification.from_elasticsearch_document(doc)
        return None

    async def update_notification_status(
        self,
        notification_id: UUID,
        status: NotificationStatus,
        provider_response: dict[str, Any] | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update notification status."""
        update_doc: dict[str, Any] = {
            "status": status.value,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if provider_response:
            update_doc["provider_responses"] = provider_response
        if error_message:
            update_doc["error_message"] = error_message

        return await self.update_document(str(notification_id), update_doc)

    async def get_notifications_by_user(
        self,
        user_id: str,
        workspace_id: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Notification], int]:
        """Get notifications for a user with filtering."""
        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]

        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})
        if channel:
            must_conditions.append({"term": {"channel": channel}})
        if status:
            must_conditions.append({"term": {"status": status}})

        query = {"bool": {"must": must_conditions}}

        sort = [{"created_at": {"order": "desc"}}]
        from_ = (page - 1) * page_size

        documents, total = await self.search(
            query=query, size=page_size, from_=from_, sort=sort
        )

        notifications = [Notification.from_elasticsearch_document(doc) for doc in documents]
        return notifications, total

    async def get_notifications_by_campaign(
        self, campaign_id: UUID, page: int = 1, page_size: int = 50
    ) -> tuple[list[Notification], int]:
        """Get all notifications for a campaign."""
        query = {"term": {"campaign_id": str(campaign_id)}}
        sort = [{"created_at": {"order": "asc"}}]
        from_ = (page - 1) * page_size

        documents, total = await self.search(
            query=query, size=page_size, from_=from_, sort=sort
        )

        notifications = [Notification.from_elasticsearch_document(doc) for doc in documents]
        return notifications, total

    async def get_status_counts(
        self,
        user_id: str,
        workspace_id: str | None = None,
        channel: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, int]:
        """Get notification counts by status for analytics."""
        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]

        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})
        if channel:
            must_conditions.append({"term": {"channel": channel}})

        if start_date or end_date:
            range_condition: dict[str, Any] = {}
            if start_date:
                range_condition["gte"] = start_date.isoformat()
            if end_date:
                range_condition["lte"] = end_date.isoformat()
            must_conditions.append({"range": {"created_at": range_condition}})

        client = get_elasticsearch_client()
        if not client:
            return {}

        aggregation = {
            "status_counts": {
                "terms": {"field": "status", "size": 20},
            }
        }

        try:
            response = await client.search(
                index=self.index_name,
                body={
                    "query": {"bool": {"must": must_conditions}},
                    "size": 0,
                    "aggs": aggregation,
                },
            )
            buckets = response.get("aggregations", {}).get("status_counts", {}).get("buckets", [])
            return {bucket["key"]: bucket["doc_count"] for bucket in buckets}
        except Exception as e:
            self._logger.error("status_counts_failed", error=str(e))
            return {}

    async def get_channel_counts(
        self,
        user_id: str,
        workspace_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, int]:
        """Get notification counts by channel."""
        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]

        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})

        if start_date or end_date:
            range_condition: dict[str, Any] = {}
            if start_date:
                range_condition["gte"] = start_date.isoformat()
            if end_date:
                range_condition["lte"] = end_date.isoformat()
            must_conditions.append({"range": {"created_at": range_condition}})

        client = get_elasticsearch_client()
        if not client:
            return {}

        try:
            response = await client.search(
                index=self.index_name,
                body={
                    "query": {"bool": {"must": must_conditions}},
                    "size": 0,
                    "aggs": {
                        "channel_counts": {
                            "terms": {"field": "channel", "size": 10},
                        }
                    },
                },
            )
            buckets = response.get("aggregations", {}).get("channel_counts", {}).get("buckets", [])
            return {bucket["key"]: bucket["doc_count"] for bucket in buckets}
        except Exception as e:
            self._logger.error("channel_counts_failed", error=str(e))
            return {}
