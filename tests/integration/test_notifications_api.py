"""
Integration tests for notification API endpoints.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app
from src.repositories.base import get_elasticsearch_client
from src.schemas.api_keys import CreateApiKeyRequest
from src.services.api_key_service import ApiKeyService


@pytest.mark.asyncio
class TestNotificationsAPI:
    """Integration tests for /v1/notify endpoints."""

    @pytest.fixture
    async def client(self, mock_elasticsearch_client):
        """Create test client with globally patched ES client."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

    @pytest.fixture
    async def auth_headers(self, mock_elasticsearch_client, sample_user_id):
        """Create valid authentication headers using the real ApiKeyService."""
        es_client = get_elasticsearch_client()
        service = ApiKeyService()
        with patch.object(service._repository, '_client', es_client):
            create_request = CreateApiKeyRequest(
                name="Notification Test Key",
                permissions=["send_notifications", "view_analytics", "manage_templates"],
            )
            _, raw_key = await service.create_api_key(create_request, sample_user_id)
        return {"X-API-Key": raw_key}

    async def test_send_email_notification_no_auth(self, client):
        response = await client.post(
            "/api/v1/notify",
            json={"type": "email", "recipients": ["user@example.com"], "html": "<h1>Test</h1>"},
        )
        assert response.status_code == 401

    async def test_send_email_notification_raw_html(self, client, auth_headers, es_index):
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

    async def test_send_sms_notification(self, client, auth_headers, es_index):
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={"type": "sms", "recipients": ["+1234567890"], "sms_content": "Test SMS message"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["channel"] == "sms"
        assert data["status"] == "sent"

    async def test_send_both_channels(self, client, auth_headers, es_index):
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "both",
                "recipients": [{"email": "user@example.com", "phone": "+1234567890"}],
                "html": "<p>Email content</p>",
                "sms_content": "SMS content",
                "subject": "Multi-channel",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert data["channel"] == "both"

    async def test_send_with_template(
        self, client, auth_headers, es_index, es_client, sample_user_id, sample_template_id
    ):
        # Create template using the patched ES client
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

    async def test_send_without_recipients_fails(self, client, auth_headers):
        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={"type": "email", "recipients": [], "html": "<h1>Test</h1>"},
        )
        assert response.status_code == 422

    async def test_get_notification(self, client, auth_headers, es_index):
        send_resp = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": ["user@example.com"],
                "html": "<h1>Test</h1>",
                "subject": "Test",
            },
        )
        notification_id = send_resp.json()["notification_id"]

        get_resp = await client.get(f"/api/v1/notify/{notification_id}", headers=auth_headers)
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["notification_id"] == notification_id
        assert data["channel"] == "email"

    async def test_list_notifications(self, client, auth_headers, es_index):
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

        response = await client.get("/api/v1/notifications", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 3
        assert len(data["notifications"]) >= 3

    async def test_list_notifications_with_filters(self, client, auth_headers, es_index):
        response = await client.get(
            "/api/v1/notifications",
            headers=auth_headers,
            params={"channel": "email", "status": "sent", "page_size": 10},
        )
        assert response.status_code == 200
