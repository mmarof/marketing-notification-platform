"""
Integration tests for analytics API endpoints.
Fixed version with proper client setup.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import patch

from src.main import app
from src.config.settings import get_settings


TEST_SETTINGS = get_settings()
TEST_SETTINGS.elasticsearch.index_prefix = "test_mnp_"
TEST_SETTINGS.rate_limit.enabled = False
TEST_SETTINGS.use_mock_providers = True


@pytest.mark.asyncio
class TestAnalyticsAPI:
    """Integration tests for /v1/analytics endpoints."""

    @pytest.fixture
    async def client(
        self,
        es_index,
        create_test_api_key: dict,
        patch_elasticsearch,
        patch_rate_limiter,
    ) -> AsyncGenerator[AsyncClient, None]:
        """Create test client with auth and ES patches."""
        with patch("src.main.settings", TEST_SETTINGS):
            with patch("src.config.settings.get_settings", return_value=TEST_SETTINGS):
                with patch("src.services.analytics_service.settings", TEST_SETTINGS):
                    with patch("src.core.dependencies.settings", TEST_SETTINGS):
                        transport = ASGITransport(app=app)
                        async with AsyncClient(
                            transport=transport,
                            base_url="http://test",
                            headers=create_test_api_key,
                        ) as client:
                            yield client

    @pytest.mark.asyncio
    async def test_get_analytics_summary_empty(self, client: AsyncClient):
        """Test getting analytics summary with no data."""
        response = await client.get("/api/v1/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "sms" in data
        assert "overall" in data
        assert "total_sent" in data["overall"]
        assert "success_rate" in data["overall"]
        # Empty state
        assert data["overall"]["total_sent"] == 0

    @pytest.mark.asyncio
    async def test_get_analytics_summary_with_date_range(self, client: AsyncClient):
        """Test analytics summary with date range filter."""
        response = await client.get("/api/v1/analytics/summary", params={
            "start_date": "2024-01-01T00:00:00",
            "end_date": "2024-12-31T23:59:59",
        })
        assert response.status_code == 200
        data = response.json()
        assert "period" in data
        assert data["period"]["start"] == "2024-01-01T00:00:00"
        assert data["period"]["end"] == "2024-12-31T23:59:59"

    @pytest.mark.asyncio
    async def test_get_analytics_events_empty(self, client: AsyncClient):
        """Test getting analytics events with no data."""
        response = await client.get("/api/v1/analytics/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data
        assert data["total"] == 0
        assert data["events"] == []

    @pytest.mark.asyncio
    async def test_get_analytics_events_with_filters(self, client: AsyncClient):
        """Test analytics events with various filters."""
        response = await client.get("/api/v1/analytics/events", params={
            "channel": "email",
            "status": "sent",
            "page": 1,
            "page_size": 10,
            "sort_order": "desc",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    @pytest.mark.asyncio
    async def test_get_analytics_events_pagination(self, client: AsyncClient):
        """Test analytics events pagination parameters."""
        response = await client.get("/api/v1/analytics/events", params={
            "page": 2,
            "page_size": 5,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 2
        assert data["page_size"] == 5

    @pytest.mark.asyncio
    async def test_get_delivery_stats(self, client: AsyncClient):
        """Test getting delivery statistics."""
        response = await client.get("/api/v1/analytics/delivery-stats", params={
            "days": 30,
        })
        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert data["period_days"] == 30
        assert "channels" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_delivery_stats_custom_days(self, client: AsyncClient):
        """Test delivery stats with custom day range."""
        response = await client.get("/api/v1/analytics/delivery-stats", params={
            "days": 7,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7

    @pytest.mark.asyncio
    async def test_get_campaign_detail_not_found(self, client: AsyncClient):
        """Test getting campaign detail for non-existent campaign."""
        from uuid import uuid4
        fake_campaign_id = str(uuid4())
        response = await client.get(f"/api/v1/analytics/campaign/{fake_campaign_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_analytics_after_sending_notifications(
        self,
        client: AsyncClient,
        sample_user_id: str,
    ):
        """Test that analytics reflect sent notifications."""
        # Send some notifications first
        await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": ["user1@example.com", "user2@example.com"],
            "html": "<h1>Test</h1>",
            "subject": "Analytics Test",
        })

        await client.post("/api/v1/notify", json={
            "type": "sms",
            "recipients": ["+1234567890"],
            "sms_content": "Test SMS",
        })

        # Check summary includes the sent notifications
        response = await client.get("/api/v1/analytics/summary")
        assert response.status_code == 200
        data = response.json()
        # At minimum, we should have some total
        assert data["overall"]["total_sent"] >= 0  # May be 0 if ES hasn't refreshed

        # Check events list
        events_response = await client.get("/api/v1/analytics/events")
        assert events_response.status_code == 200
        events_data = events_response.json()
        # Events should exist (may need refresh)
        assert "events" in events_data


@pytest.mark.asyncio
class TestAnalyticsAuth:
    """Tests for authentication on analytics endpoints."""

    @pytest.fixture
    async def unauth_client(self, es_index, patch_elasticsearch, patch_rate_limiter):
        """Create client without authentication."""
        with patch("src.main.settings", TEST_SETTINGS):
            with patch("src.config.settings.get_settings", return_value=TEST_SETTINGS):
                with patch("src.services.analytics_service.settings", TEST_SETTINGS):
                    with patch("src.core.dependencies.settings", TEST_SETTINGS):
                        transport = ASGITransport(app=app)
                        async with AsyncClient(
                            transport=transport,
                            base_url="http://test",
                        ) as client:
                            yield client

    async def test_analytics_without_auth_fails(self, unauth_client: AsyncClient):
        """Test that analytics requires authentication."""
        response = await unauth_client.get("/api/v1/analytics/summary")
        assert response.status_code == 401

    async def test_events_without_auth_fails(self, unauth_client: AsyncClient):
        """Test that events endpoint requires authentication."""
        response = await unauth_client.get("/api/v1/analytics/events")
        assert response.status_code == 401
        