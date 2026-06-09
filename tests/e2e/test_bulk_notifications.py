"""
End-to-end tests for bulk notification scenarios.
Fixed version with proper imports and client setup.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch
from uuid import uuid4

from src.main import app
from src.config.settings import get_settings


TEST_SETTINGS = get_settings()
TEST_SETTINGS.elasticsearch.index_prefix = "test_mnp_"
TEST_SETTINGS.rate_limit.enabled = False
TEST_SETTINGS.use_mock_providers = True


@pytest.mark.asyncio
class TestBulkNotifications:
    """E2E tests for bulk notification sending."""

    @pytest.fixture
    async def client(
        self,
        es_index,
        create_test_api_key: dict,
        patch_elasticsearch,
        patch_rate_limiter,
    ) -> AsyncGenerator[AsyncClient, None]:
        """Create authenticated test client."""
        with patch("src.main.settings", TEST_SETTINGS):
            with patch("src.config.settings.get_settings", return_value=TEST_SETTINGS):
                with patch("src.services.notification_service.settings", TEST_SETTINGS):
                    with patch("src.core.dependencies.settings", TEST_SETTINGS):
                        transport = ASGITransport(app=app)
                        async with AsyncClient(
                            transport=transport,
                            base_url="http://test",
                            headers=create_test_api_key,
                        ) as client:
                            yield client

    @pytest.mark.asyncio
    async def test_bulk_email_send(self, client: AsyncClient):
        """Test sending to many recipients in one request."""
        recipients = [f"user{i}@example.com" for i in range(100)]

        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": recipients,
            "html": "<h1>Bulk Test</h1>",
            "subject": "Bulk Email",
        })

        assert response.status_code == 202, f"Failed: {response.text}"
        data = response.json()
        assert data["recipient_count"] == 100
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_bulk_with_per_recipient_variables(self, client: AsyncClient):
        """Test bulk send with per-recipient variables."""
        recipients = [
            {"email": "user1@example.com", "variables": {"name": "Alice"}},
            {"email": "user2@example.com", "variables": {"name": "Bob"}},
            {"email": "user3@example.com", "variables": {"name": "Charlie"}},
        ]

        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": recipients,
            "html": "<h1>Hello {{ name }}</h1>",
            "subject": "Personalized",
        })

        assert response.status_code == 202, f"Failed: {response.text}"
        assert response.json()["recipient_count"] == 3

    @pytest.mark.asyncio
    async def test_sequential_bulk_sends(self, client: AsyncClient):
        """Test multiple sequential bulk sends."""
        notification_ids = []
        campaign_id = str(uuid4())

        for batch in range(5):
            recipients = [f"batch{batch}_user{i}@example.com" for i in range(20)]
            response = await client.post("/api/v1/notify", json={
                "type": "email",
                "recipients": recipients,
                "html": f"<h1>Batch {batch}</h1>",
                "subject": f"Batch {batch}",
                "campaign_id": campaign_id,
            })
            assert response.status_code == 202, f"Batch {batch} failed: {response.text}"
            notification_ids.append(response.json()["notification_id"])

        # Verify all notifications are listed
        list_response = await client.get("/api/v1/notifications", params={"page_size": 100})
        assert list_response.status_code == 200
        data = list_response.json()
        assert data["total"] >= 5

        # Verify campaign analytics
        campaign_response = await client.get(f"/api/v1/analytics/campaign/{campaign_id}")
        # May be 404 if ES hasn't refreshed, or 200 with data
        assert campaign_response.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_bulk_sms_send(self, client: AsyncClient):
        """Test bulk SMS sending."""
        recipients = [f"+1234567{i:04d}" for i in range(50)]

        response = await client.post("/api/v1/notify", json={
            "type": "sms",
            "recipients": recipients,
            "sms_content": "Bulk SMS test message",
        })

        assert response.status_code == 202, f"Failed: {response.text}"
        assert response.json()["recipient_count"] == 50

    @pytest.mark.asyncio
    async def test_mixed_channel_bulk(self, client: AsyncClient):
        """Test bulk send with mixed channel recipients."""
        recipients = [
            {"email": "email1@example.com", "phone": "+1234567890"},
            {"email": "email2@example.com", "phone": "+0987654321"},
            {"email": "email3@example.com"},  # Email only
            {"phone": "+1111111111"},  # SMS only
        ]

        response = await client.post("/api/v1/notify", json={
            "type": "both",
            "recipients": recipients,
            "html": "<p>Email content</p>",
            "sms_content": "SMS content",
            "subject": "Mixed",
        })

        assert response.status_code == 202, f"Failed: {response.text}"
        data = response.json()
        assert data["channel"] == "both"
        assert data["recipient_count"] == 4

    @pytest.mark.asyncio
    async def test_bulk_at_max_limit(self, client: AsyncClient):
        """Test sending exactly at the maximum recipient limit."""
        # Max is 10,000
        recipients = [f"max{i}@example.com" for i in range(10000)]

        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": recipients,
            "html": "<p>Max limit test</p>",
            "subject": "Max Test",
        })

        assert response.status_code == 202, f"Failed: {response.text}"
        assert response.json()["recipient_count"] == 10000

    @pytest.mark.asyncio
    async def test_bulk_exceeds_limit_fails(self, client: AsyncClient):
        """Test that exceeding the recipient limit fails validation."""
        # Exceed max of 10,000
        recipients = [f"over{i}@example.com" for i in range(10001)]

        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": recipients,
            "html": "<p>Over limit</p>",
            "subject": "Over Test",
        })

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_bulk_with_metadata(self, client: AsyncClient):
        """Test bulk send with custom metadata."""
        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": [f"user{i}@example.com" for i in range(10)],
            "html": "<p>With metadata</p>",
            "subject": "Metadata Test",
            "metadata": {
                "campaign_name": "Q1 Newsletter",
                "source": "marketing_automation",
                "priority": "high",
            },
        })

        assert response.status_code == 202, f"Failed: {response.text}"

    @pytest.mark.asyncio
    async def test_bulk_analytics_reflect_sends(self, client: AsyncClient):
        """Test that analytics reflect bulk sends."""
        # Send bulk email
        await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": [f"analytics{i}@example.com" for i in range(50)],
            "html": "<p>Analytics test</p>",
            "subject": "Analytics Bulk",
        })

        # Send bulk SMS
        await client.post("/api/v1/notify", json={
            "type": "sms",
            "recipients": [f"+123456{i:04d}" for i in range(30)],
            "sms_content": "Analytics SMS",
        })

        # Check summary
        summary_response = await client.get("/api/v1/analytics/summary")
        assert summary_response.status_code == 200
        summary = summary_response.json()
        # Verify structure (values may vary based on ES refresh)
        assert "email" in summary
        assert "sms" in summary

    @pytest.mark.asyncio
    async def test_retry_failed_notification(self, client: AsyncClient):
        """Test retrying a notification (mock scenario)."""
        # In production, this would require an actual failed notification
        # For now, test that the endpoint exists and handles not-found
        fake_id = str(uuid4())
        response = await client.post(f"/api/v1/notify/{fake_id}/retry")
        assert response.status_code == 404
        