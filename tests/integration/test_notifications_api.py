"""
Integration tests for notification API endpoints.
"""


import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest.mark.asyncio
class TestNotificationsAPI:
    """Integration tests for /v1/notify endpoints."""

    @pytest.fixture
    async def client(self, es_client):
        """Create test client with ES patched."""
        from unittest.mock import patch

        with (
            patch("src.repositories.base.get_elasticsearch_client", return_value=es_client),
            patch("src.repositories.base._elasticsearch_client", es_client),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    @pytest.fixture
    async def auth_headers(self, es_client, sample_user_id, sample_api_key_id):
        """Create valid authentication headers."""
        import bcrypt

        raw_key = "mnp_test_api_key_for_integration_testing"
        key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

        # Create API key in ES
        api_key_doc = {
            "api_key_id": str(sample_api_key_id),
            "user_id": sample_user_id,
            "name": "Test Key",
            "permissions": ["send_notifications", "view_analytics", "manage_templates"],
            "key_hash": key_hash,
            "key_prefix": "mnp_test...",
            "workspace_id": None,
            "is_active": True,
            "expires_at": None,
            "last_used_at": None,
            "created_at": "2024-01-01T00:00:00",
            "metadata": {},
        }
        await es_client.index(
            index="test_mnp_api_keys",
            id=str(sample_api_key_id),
            document=api_key_doc,
            refresh="wait_for",
        )

        return {"X-API-Key": raw_key}

    @pytest.mark.asyncio
    async def test_send_email_notification_no_auth(self, client: AsyncClient):
        """Test that sending without auth fails."""
        response = await client.post(
            "/api/v1/notify",
            json={
                "type": "email",
                "recipients": ["user@example.com"],
                "html": "<h1>Test</h1>",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_email_notification_raw_html(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test sending email with raw HTML."""
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": ["user1@example.com", "user2@example.com"],
                "html": "<h1>Hello World</h1><p>This is a test email.</p>",
                "subject": "Test Email",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "notification_id" in data
        assert data["status"] == "sent"
        assert data["channel"] == "email"
        assert data["recipient_count"] == 2

    @pytest.mark.asyncio
    async def test_send_sms_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test sending SMS notification."""
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "sms",
                "recipients": ["+1234567890"],
                "sms_content": "Test SMS message",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["channel"] == "sms"
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_both_channels(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test sending to both email and SMS."""
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "both",
                "recipients": [
                    {"email": "user@example.com", "phone": "+1234567890"}
                ],
                "html": "<p>Email content</p>",
                "sms_content": "SMS content",
                "subject": "Multi-channel",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["channel"] == "both"

    @pytest.mark.asyncio
    async def test_send_with_template(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
        es_client,
        sample_user_id,
        sample_template_id,
    ):
        """Test sending with a template."""
        # Create template first
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
        await es_client.index(
            index="test_mnp_templates",
            id=str(sample_template_id),
            document=template_doc,
            refresh="wait_for",
        )

        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": ["user@example.com"],
                "template_id": str(sample_template_id),
                "variables": {"name": "John"},
            },
        )
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_send_without_recipients_fails(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Test that sending without recipients fails validation."""
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": [],
                "html": "<h1>Test</h1>",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_notification(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test retrieving a notification."""
        # First send a notification
        send_response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": ["user@example.com"],
                "html": "<h1>Test</h1>",
                "subject": "Test",
            },
        )
        notification_id = send_response.json()["notification_id"]

        # Then retrieve it
        get_response = await client.get(
            f"/api/v1/notify/{notification_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["notification_id"] == notification_id
        assert data["channel"] == "email"

    @pytest.mark.asyncio
    async def test_list_notifications(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test listing notifications."""
        # Send a few notifications first
        for i in range(3):
            await client.post(
                "/api/v1/notify",
                headers=auth_headers,
                json={
                    "type": "email",
                    "recipients": [f"user{i}@example.com"],
                    "html": f"<h1>Test {i}</h1>",
                    "subject": f"Test {i}",
                },
            )

        response = await client.get(
            "/api/v1/notifications",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["notifications"]) >= 3

    @pytest.mark.asyncio
    async def test_list_notifications_with_filters(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test listing notifications with filters."""
        response = await client.get(
            "/api/v1/notifications",
            headers=auth_headers,
            params={"channel": "email", "status": "sent", "page_size": 10},
        )
        assert response.status_code == 200
