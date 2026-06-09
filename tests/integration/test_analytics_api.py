"""
Integration tests for analytics API endpoints.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
class TestAnalyticsAPI:
    """Integration tests for /v1/analytics endpoints."""

    @pytest.fixture
    async def client(self, es_client, test_settings):
        """Create test client with patched ES client and settings."""

        with (
            patch("src.repositories.base.get_elasticsearch_client", return_value=es_client),
            patch("src.repositories.base._elasticsearch_client", es_client),
            patch("src.config.settings.get_settings", return_value=test_settings),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    @pytest.fixture
    async def auth_headers(self, es_client, sample_user_id, sample_api_key_id):
        """Create valid authentication."""
        import bcrypt

        raw_key = "mnp_analytics_test_key"
        key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

        await es_client.index(
            index="test_mnp_api_keys",
            id=str(sample_api_key_id),
            document={
                "api_key_id": str(sample_api_key_id),
                "user_id": sample_user_id,
                "name": "Analytics Key",
                "permissions": ["view_analytics"],
                "key_hash": key_hash,
                "key_prefix": "mnp_ana...",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00",
                "metadata": {},
            },
            refresh="wait_for",
        )

        return {"X-API-Key": raw_key}

    @pytest.mark.asyncio
    async def test_get_analytics_summary(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test getting analytics summary."""
        response = await client.get(
            "/api/v1/analytics/summary",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "sms" in data
        assert "overall" in data
        assert "total_sent" in data["overall"]
        assert "success_rate" in data["overall"]

    @pytest.mark.asyncio
    async def test_get_analytics_summary_with_date_range(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test analytics summary with date range."""
        response = await client.get(
            "/api/v1/analytics/summary",
            headers=auth_headers,
            params={
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T23:59:59",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"]["start"] == "2024-01-01T00:00:00"
        assert data["period"]["end"] == "2024-12-31T23:59:59"

    @pytest.mark.asyncio
    async def test_get_analytics_events(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test getting analytics events."""
        response = await client.get(
            "/api/v1/analytics/events",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data

    @pytest.mark.asyncio
    async def test_get_analytics_events_with_filters(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test analytics events with filters."""
        response = await client.get(
            "/api/v1/analytics/events",
            headers=auth_headers,
            params={
                "channel": "email",
                "status": "sent",
                "page": 1,
                "page_size": 10,
                "sort_order": "desc",
            },
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_delivery_stats(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test getting delivery statistics."""
        response = await client.get(
            "/api/v1/analytics/delivery-stats",
            headers=auth_headers,
            params={"days": 30},
        )
        assert response.status_code == 200
        data = response.json()
        assert "period_days" in data
        assert data["period_days"] == 30
        assert "channels" in data
        assert "total" in data
