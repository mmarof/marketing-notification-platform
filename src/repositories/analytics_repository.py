"""
Analytics repository for aggregated queries.
"""

from datetime import datetime
from typing import Any

from src.models.analytics import AnalyticsSummary
from src.repositories.base import BaseRepository, get_elasticsearch_client


class AnalyticsRepository(BaseRepository):
    """Repository for analytics aggregations."""

    def _get_index_suffix(self) -> str:
        return "notifications"

    async def get_summary(
        self,
        user_id: str,
        workspace_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> AnalyticsSummary:
        """Get aggregated analytics summary."""
        summary = AnalyticsSummary(
            user_id=user_id,
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
        )

        client = get_elasticsearch_client()
        if not client:
            return summary

        # Build base query
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

        base_query = {"bool": {"must": must_conditions}}

        try:
            # Multi-aggregation query
            response = await client.search(
                index=self.index_name,
                body={
                    "query": base_query,
                    "size": 0,
                    "aggs": {
                        "by_channel": {
                            "terms": {"field": "channel"},
                            "aggs": {
                                "by_status": {
                                    "terms": {"field": "status"},
                                },
                                "total_recipients": {
                                    "sum": {"field": "recipient_count"},
                                },
                            },
                        },
                        "total_campaigns": {
                            "cardinality": {"field": "campaign_id"},
                        },
                        "total_recipients": {
                            "sum": {"field": "recipient_count"},
                        },
                    },
                },
            )

            aggs = response.get("aggregations", {})

            # Process channel breakdown
            for bucket in aggs.get("by_channel", {}).get("buckets", []):
                channel = bucket["key"]
                for status_bucket in bucket.get("by_status", {}).get("buckets", []):
                    status = status_bucket["key"]
                    count = status_bucket["doc_count"]

                    if channel == "email" or channel == "both":
                        if status == "sent" or status == "delivered":
                            summary.emails_delivered += count
                        elif status == "failed":
                            summary.emails_failed += count
                        elif status == "bounced":
                            summary.emails_bounced += count
                        elif status == "complained":
                            summary.emails_complained += count

                    if channel == "sms" or channel == "both":
                        if status == "sent" or status == "delivered":
                            summary.sms_delivered += count
                        elif status == "failed":
                            summary.sms_failed += count

                # Calculate total sent per channel
                channel_total = sum(
                    b["doc_count"] for b in bucket.get("by_status", {}).get("buckets", [])
                )
                if channel == "email" or channel == "both":
                    summary.total_emails_sent += channel_total
                if channel == "sms" or channel == "both":
                    summary.total_sms_sent += channel_total

            summary.total_campaigns = aggs.get("total_campaigns", {}).get("value", 0)
            summary.total_recipients = aggs.get("total_recipients", {}).get("value", 0)

            summary.compute_rates()

        except Exception as e:
            self._logger.error("analytics_summary_failed", error=str(e))

        return summary

    async def get_events(
        self,
        user_id: str,
        workspace_id: str | None = None,
        channel: str | None = None,
        status: str | None = None,
        template_id: str | None = None,
        campaign_id: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        """Get notification events with filtering and pagination."""
        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]

        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})
        if channel:
            must_conditions.append({"term": {"channel": channel}})
        if status:
            must_conditions.append({"term": {"status": status}})
        if template_id:
            must_conditions.append({"term": {"template_id": template_id}})
        if campaign_id:
            must_conditions.append({"term": {"campaign_id": campaign_id}})

        if start_date or end_date:
            range_condition: dict[str, Any] = {}
            if start_date:
                range_condition["gte"] = start_date.isoformat()
            if end_date:
                range_condition["lte"] = end_date.isoformat()
            must_conditions.append({"range": {"created_at": range_condition}})

        sort = [{sort_by: {"order": sort_order}}]
        from_ = (page - 1) * page_size

        source_includes = [
            "notification_id",
            "campaign_id",
            "channel",
            "status",
            "subject",
            "recipient_count",
            "template_id",
            "error_message",
            "created_at",
            "updated_at",
        ]

        documents, total = await self.search(
            query={"bool": {"must": must_conditions}},
            size=page_size,
            from_=from_,
            sort=sort,
            source_includes=source_includes,
        )

        return documents, total

    async def get_campaign_detail(self, campaign_id: str, user_id: str) -> dict[str, Any] | None:
        """Get detailed campaign information."""
        must_conditions = [
            {"term": {"campaign_id": campaign_id}},
            {"term": {"user_id": user_id}},
        ]

        client = get_elasticsearch_client()
        if not client:
            return None

        try:
            response = await client.search(
                index=self.index_name,
                body={
                    "query": {"bool": {"must": must_conditions}},
                    "size": 0,
                    "aggs": {
                        "status_breakdown": {
                            "terms": {"field": "status"},
                        },
                        "total_recipients": {
                            "sum": {"field": "recipient_count"},
                        },
                        "date_range": {
                            "range": {"field": "created_at", "ranges": [{"from": "now-1y"}]},
                            "aggs": {
                                "min_date": {"min": {"field": "created_at"}},
                                "max_date": {"max": {"field": "created_at"}},
                            },
                        },
                    },
                },
            )

            aggs = response.get("aggregations", {})
            status_breakdown = {
                b["key"]: b["doc_count"]
                for b in aggs.get("status_breakdown", {}).get("buckets", [])
            }

            date_range = aggs.get("date_range", {}).get("buckets", [{}])[0]
            created_range = {
                "start": date_range.get("min_date", {}).get("value_as_string"),
                "end": date_range.get("max_date", {}).get("value_as_string"),
            }

            return {
                "campaign_id": campaign_id,
                "notification_count": sum(status_breakdown.values()),
                "total_recipients": aggs.get("total_recipients", {}).get("value", 0),
                "status_breakdown": status_breakdown,
                "created_range": created_range,
            }

        except Exception as e:
            self._logger.error("campaign_detail_failed", error=str(e), campaign_id=campaign_id)
            return None
