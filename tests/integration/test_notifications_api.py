"""
Integration tests for notification API endpoints.
Fixed version with proper client setup and auth handling.
"""

from collections.abc import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from src.config.settings import get_settings
from src.main import app

# Ensure test settings are used
TEST_SETTINGS = get_settings()
TEST_SETTINGS.elasticsearch.index_prefix = "test_mnp_"
TEST_SETTINGS.rate_limit.enabled = False


@pytest.mark.asyncio
class TestNotificationsAPI:
    """Integration tests for /v1/notify endpoints."""

    @pytest.fixture
    async def auth_headers(
        self,
        es_index,
        create_test_api_key: dict,
    ) -> dict:
        """Get authentication headers - es_index ensures indices exist."""
        return create_test_api_key

    @pytest.fixture
    async def client(
        self,
        es_index,
        auth_headers: dict,
        patch_elasticsearch,
        patch_rate_limiter,
    ) -> AsyncGenerator[AsyncClient, None]:
        """
        Create test HTTP client with all patches applied.
        es_index dependency ensures ES indices are created.
        """
        with (
            patch("src.main.settings", TEST_SETTINGS),
            patch("src.config.settings.get_settings", return_value=TEST_SETTINGS),
            patch("src.services.notification_service.settings", TEST_SETTINGS),
            patch("src.core.dependencies.settings", TEST_SETTINGS),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
                headers=auth_headers,
            ) as client:
                yield client

    async def _send_notification(self, client: AsyncClient, payload: dict) -> tuple:
        """Helper to send notification and return response data."""
        response = await client.post("/api/v1/notify", json=payload)
        return response, response.json() if response.status_code != 422 else response.text

    @pytest.mark.asyncio
    async def test_send_email_notification_raw_html(self, client: AsyncClient):
        """Test sending email with raw HTML."""
        response, data = await self._send_notification(client, {
            "type": "email",
            "recipients": ["user1@example.com", "user2@example.com"],
            "html": "<h1>Hello World</h1><p>This is a test email.</p>",
            "subject": "Test Email",
        })

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {data}"
        assert "notification_id" in data
        assert data["status"] == "sent"
        assert data["channel"] == "email"
        assert data["recipient_count"] == 2

    @pytest.mark.asyncio
    async def test_send_sms_notification(self, client: AsyncClient):
        """Test sending SMS notification."""
        response, data = await self._send_notification(client, {
            "type": "sms",
            "recipients": ["+1234567890"],
            "sms_content": "Test SMS message",
        })

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {data}"
        assert data["channel"] == "sms"
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_both_channels(self, client: AsyncClient):
        """Test sending to both email and SMS."""
        response, data = await self._send_notification(client, {
            "type": "both",
            "recipients": [
                {"email": "user@example.com", "phone": "+1234567890"}
            ],
            "html": "<p>Email content</p>",
            "sms_content": "SMS content",
            "subject": "Multi-channel",
        })

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {data}"
        assert data["channel"] == "both"

    @pytest.mark.asyncio
    async def test_send_with_template(
        self,
        client: AsyncClient,
        es_index,
        sample_user_id: str,
        sample_template_id: uuid4,
    ):
        """Test sending with a template stored in ES."""
        # Create template in ES
        template_doc = {
            "template_id": str(sample_template_id),
            "name": "Test Template",
            "template_type": "email",
            "user_id": sample_user_id,
            "content": "<h1>Hello {{ name }}</h1>",
            "subject": "Hello {{ name }}",
            "status": "active",
            "variables": [],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        }

        from src.repositories.base import get_elasticsearch_client
        es_client = get_elasticsearch_client()
        await es_client.index(
            index="test_mnp_templates",
            id=str(sample_template_id),
            document=template_doc,
            refresh="wait_for",
        )

        response, data = await self._send_notification(client, {
            "type": "email",
            "recipients": ["user@example.com"],
            "template_id": str(sample_template_id),
            "variables": {"name": "John"},
        })

        assert response.status_code == 202, f"Expected 202, got {response.status_code}: {data}"

    @pytest.mark.asyncio
    async def test_send_without_recipients_fails(self, client: AsyncClient):
        """Test that sending without recipients fails validation."""
        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": [],
            "html": "<h1>Test</h1>",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_recipient_without_contact_fails(self, client: AsyncClient):
        """Test that recipient without email or phone fails."""
        response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": [{"variables": {"name": "Test"}}],
            "html": "<h1>Test</h1>",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_notification(self, client: AsyncClient):
        """Test retrieving a notification by ID."""
        send_response = await client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": ["user@example.com"],
            "html": "<h1>Test</h1>",
            "subject": "Test",
        })
        assert send_response.status_code == 202
        notification_id = send_response.json()["notification_id"]

        get_response = await client.get(f"/api/v1/notify/{notification_id}")
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["notification_id"] == notification_id
        assert data["channel"] == "email"
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_get_nonexistent_notification(self, client: AsyncClient):
        """Test retrieving a non-existent notification returns 404."""
        fake_id = str(uuid4())
        response = await client.get(f"/api/v1/notify/{fake_id}")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_notifications(self, client: AsyncClient):
        """Test listing notifications."""
        for i in range(3):
            response = await client.post("/api/v1/notify", json={
                "type": "email",
                "recipients": [f"user{i}@example.com"],
                "html": f"<h1>Test {i}</h1>",
                "subject": f"Test {i}",
            })
            assert response.status_code == 202

        response = await client.get("/api/v1/notifications")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["notifications"]) >= 3

    @pytest.mark.asyncio
    async def test_list_notifications_with_filters(self, client: AsyncClient):
        """Test listing notifications with channel and status filters."""
        response = await client.get("/api/v1/notifications", params={
            "channel": "email",
            "status": "sent",
            "page_size": 10,
        })
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "page" in data
        assert "notifications" in data

    @pytest.mark.asyncio
    async def test_list_notifications_pagination(self, client: AsyncClient):
        """Test notification list pagination."""
        response = await client.get("/api/v1/notifications", params={
            "page": 1,
            "page_size": 2,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 2
        assert len(data["notifications"]) <= 2


@pytest.mark.asyncio
class TestNotificationsAuth:
    """Tests for authentication on notification endpoints."""

    @pytest.fixture
    async def unauth_client(self, es_index, patch_elasticsearch, patch_rate_limiter):
        """Create client without authentication."""
        with (
            patch("src.main.settings", TEST_SETTINGS),
            patch("src.config.settings.get_settings", return_value=TEST_SETTINGS),
            patch("src.services.notification_service.settings", TEST_SETTINGS),
            patch("src.core.dependencies.settings", TEST_SETTINGS),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as client:
                yield client

    async def test_send_without_auth_fails(self, unauth_client: AsyncClient):
        """Test that sending without auth fails."""
        response = await unauth_client.post("/api/v1/notify", json={
            "type": "email",
            "recipients": ["user@example.com"],
            "html": "<h1>Test</h1>",
        })
        assert response.status_code == 401

    async def test_send_with_invalid_key_fails(self, unauth_client: AsyncClient):
        """Test that sending with invalid key fails."""
        response = await unauth_client.post(
            "/api/v1/notify",
            json={
                "type": "email",
                "recipients": ["user@example.com"],
                "html": "<h1>Test</h1>",
            },
            headers={"X-API-Key": "invalid_key"},
        )
        assert response.status_code == 401

    async def test_list_without_auth_fails(self, unauth_client: AsyncClient):
        """Test that listing without auth fails."""
        response = await unauth_client.get("/api/v1/notifications")
        assert response.status_code == 401
