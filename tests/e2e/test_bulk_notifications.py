"""
End-to-end tests for bulk notification scenarios.
"""

from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

# Need to import app for the fixture
from src.main import app


@pytest.mark.asyncio
class TestBulkNotifications:
    """E2E tests for bulk notification sending."""

    @pytest.fixture
    async def client(self, es_client):
        """Create test client."""
        with (
            patch("src.repositories.base.get_elasticsearch_client", return_value=es_client),
            patch("src.repositories.base._elasticsearch_client", es_client),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    @pytest.fixture
    async def auth_headers(self, es_client, sample_user_id, sample_api_key_id):
        """Create authenticated headers."""
        import bcrypt

        raw_key = "mnp_bulk_test_key"
        key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()

        await es_client.index(
            index="test_mnp_api_keys",
            id=str(sample_api_key_id),
            document={
                "api_key_id": str(sample_api_key_id),
                "user_id": sample_user_id,
                "name": "Bulk Test Key",
                "permissions": ["send_notifications"],
                "key_hash": key_hash,
                "key_prefix": "mnp_bulk...",
                "is_active": True,
                "created_at": "2024-01-01T00:00:00",
                "metadata": {},
            },
            refresh="wait_for",
        )

        return {"X-API-Key": raw_key}

    @pytest.mark.asyncio
    async def test_bulk_email_send(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test sending to many recipients in one request."""
        recipients = [f"user{i}@example.com" for i in range(100)]

        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": recipients,
                "html": "<h1>Bulk Test</h1>",
                "subject": "Bulk Email",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["recipient_count"] == 100

    @pytest.mark.asyncio
    async def test_bulk_with_per_recipient_variables(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test bulk send with per-recipient variables."""
        recipients = [
            {"email": "user1@example.com", "variables": {"name": "Alice"}},
            {"email": "user2@example.com", "variables": {"name": "Bob"}},
            {"email": "user3@example.com", "variables": {"name": "Charlie"}},
        ]

        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "email",
                "recipients": recipients,
                "html": "<h1>Hello {{ name }}</h1>",
                "subject": "Personalized",
            },
        )

        assert response.status_code == 202
        assert response.json()["recipient_count"] == 3

    @pytest.mark.asyncio
    async def test_sequential_bulk_sends(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test multiple sequential bulk sends."""
        notification_ids = []

        for batch in range(5):
            recipients = [f"batch{batch}_user{i}@example.com" for i in range(20)]
            response = await client.post(
                "/api/v1/notify",
                headers=auth_headers,
                json={
                    "type": "email",
                    "recipients": recipients,
                    "html": f"<h1>Batch {batch}</h1>",
                    "subject": f"Batch {batch}",
                    "campaign_id": str(__import__("uuid").uuid4()),
                },
            )
            assert response.status_code == 202
            notification_ids.append(response.json()["notification_id"])

        # Verify all notifications are listed
        list_response = await client.get(
            "/api/v1/notifications",
            headers=auth_headers,
            params={"page_size": 100},
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] >= 5

    @pytest.mark.asyncio
    async def test_bulk_sms_send(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test bulk SMS sending."""
        recipients = [f"+1234567{i:04d}" for i in range(50)]

        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "sms",
                "recipients": recipients,
                "sms_content": "Bulk SMS test message",
            },
        )

        assert response.status_code == 202
        assert response.json()["recipient_count"] == 50

    @pytest.mark.asyncio
    async def test_mixed_channel_bulk(
        self,
        client: AsyncClient,
        auth_headers: dict,
        es_index,
    ):
        """Test bulk send with mixed channel recipients."""
        recipients = [
            {"email": "email1@example.com", "phone": "+1234567890"},
            {"email": "email2@example.com", "phone": "+0987654321"},
            {"email": "email3@example.com"},  # Email only
            {"phone": "+1111111111"},  # SMS only
        ]

        response = await client.post(
            "/api/v1/notify",
            headers=auth_headers,
            json={
                "type": "both",
                "recipients": recipients,
                "html": "<p>Email content</p>",
                "sms_content": "SMS content",
                "subject": "Mixed",
            },
        )

        assert response.status_code == 202
        assert response.json()["channel"] == "both"


