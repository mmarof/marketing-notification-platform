"""
Integration tests for analytics API endpoints.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.schemas.api_keys import CreateApiKeyRequest
from src.services.api_key_service import ApiKeyService


@pytest.mark.asyncio
class TestAnalyticsAPI:
    """Integration tests for /v1/analytics endpoints."""

    @pytest.fixture
    async def client(self, mock_elasticsearch_client):
        """Create test client with globally patched ES client."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.fixture
    async def auth_headers(self, mock_elasticsearch_client, sample_user_id):
        """Create valid authentication headers using the real ApiKeyService."""
        service = ApiKeyService()
        create_request = CreateApiKeyRequest(
            name="Analytics Test Key",
            permissions=["view_analytics"],
        )
        _, raw_key = await service.create_api_key(create_request, sample_user_id)
        return {"X-API-Key": raw_key}

    async def test_get_analytics_summary(self, client, auth_headers, es_index):
        response = await client.get("/api/v1/analytics/summary", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "sms" in data
        assert "overall" in data
        assert "total_sent" in data["overall"]
        assert "success_rate" in data["overall"]

    async def test_get_analytics_summary_with_date_range(self, client, auth_headers, es_index):
        response = await client.get(
            "/api/v1/analytics/summary",
            headers=auth_headers,
            params={"start_date": "2024-01-01T00:00:00", "end_date": "2024-12-31T23:59:59"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period"]["start"] == "2024-01-01T00:00:00"
        assert data["period"]["end"] == "2024-12-31T23:59:59"

    async def test_get_analytics_events(self, client, auth_headers, es_index):
        response = await client.get("/api/v1/analytics/events", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "page" in data
        assert "total_pages" in data

    async def test_get_analytics_events_with_filters(self, client, auth_headers, es_index):
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

    async def test_get_delivery_stats(self, client, auth_headers, es_index):
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
