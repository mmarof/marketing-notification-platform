"""
Unit tests for notification service.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from src.models.notifications import NotificationChannel, NotificationStatus
from src.schemas.notifications import NotificationRequest, RecipientInput
from src.services.notification_service import NotificationService


class TestNotificationService:
    """Tests for NotificationService."""

    @pytest.fixture
    def service(self) -> NotificationService:
        """Create notification service with mocked providers."""
        with patch("src.services.notification_service.settings") as mock_settings:
            mock_settings.use_mock_providers = True
            mock_settings.smtp.host = ""
            mock_settings.twilio.is_configured = False
            svc = NotificationService()
            return svc

    @pytest.fixture
    def mock_notification_repo(self, service: NotificationService):
        """Mock the notification repository."""
        service._notification_repo.save_notification = AsyncMock()
        service._notification_repo.update_notification_status = AsyncMock()
        return service._notification_repo

    def test_parse_recipients_strings(self, service: NotificationService):
        """Test parsing string recipients."""
        recipients = ["user1@example.com", "+1234567890", "user2@example.com"]
        parsed = service._parse_recipients(recipients)

        assert len(parsed) == 3
        assert parsed[0].email == "user1@example.com"
        assert parsed[0].phone is None
        assert parsed[1].phone == "+1234567890"
        assert parsed[1].email is None
        assert parsed[2].email == "user2@example.com"

    def test_parse_recipients_objects(self, service: NotificationService):
        """Test parsing RecipientInput objects."""
        recipients = [
            RecipientInput(
                email="user@example.com",
                phone="+1234567890",
                variables={"name": "John"},
                metadata={"source": "signup"},
            )
        ]
        parsed = service._parse_recipients(recipients)

        assert len(parsed) == 1
        assert parsed[0].email == "user@example.com"
        assert parsed[0].phone == "+1234567890"
        assert parsed[0].variables == {"name": "John"}
        assert parsed[0].metadata == {"source": "signup"}

    def test_parse_recipients_mixed(self, service: NotificationService):
        """Test parsing mixed string and object recipients."""
        recipients = [
            "user1@example.com",
            RecipientInput(email="user2@example.com", variables={"name": "Jane"}),
        ]
        parsed = service._parse_recipients(recipients)

        assert len(parsed) == 2
        assert parsed[0].email == "user1@example.com"
        assert parsed[1].email == "user2@example.com"
        assert parsed[1].variables == {"name": "Jane"}

    def test_determine_channel_from_type(self, service: NotificationService):
        """Test channel determination from type field."""
        request_email = NotificationRequest(type="email", recipients=["user@example.com"])
        request_sms = NotificationRequest(type="sms", recipients=["+1234567890"])
        request_both = NotificationRequest(type="both", recipients=["user@example.com"])

        assert service._determine_channel(request_email, []) == NotificationChannel.EMAIL
        assert service._determine_channel(request_sms, []) == NotificationChannel.SMS
        assert service._determine_channel(request_both, []) == NotificationChannel.BOTH

    def test_determine_channel_from_override(self, service: NotificationService):
        """Test channel determination from channels override."""
        request = NotificationRequest(
            type="both",
            recipients=["user@example.com"],
            channels={"email": True, "sms": False},
        )
        assert service._determine_channel(request, []) == NotificationChannel.EMAIL

    def test_determine_email_mode_raw(self, service: NotificationService):
        """Test email mode determination for raw HTML."""
        request = NotificationRequest(
            type="email",
            recipients=["user@example.com"],
            html="<h1>Test</h1>",
        )
        assert service._determine_email_mode(request).value == "raw_html"

    def test_determine_email_mode_template(self, service: NotificationService):
        """Test email mode determination for template."""
        request = NotificationRequest(
            type="email",
            recipients=["user@example.com"],
            template_id=uuid4(),
        )
        assert service._determine_email_mode(request).value == "template"

    def test_determine_email_mode_hybrid(self, service: NotificationService):
        """Test email mode determination for hybrid."""
        request = NotificationRequest(
            type="email",
            recipients=["user@example.com"],
            template_id=uuid4(),
            html="<h1>Override</h1>",
        )
        assert service._determine_email_mode(request).value == "hybrid"

    @pytest.mark.asyncio
    async def test_send_notification_email_success(
        self,
        service: NotificationService,
        mock_notification_repo,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test successful email notification sending."""
        request = NotificationRequest(
            type="email",
            recipients=["user@example.com"],
            html="<h1>Hello</h1>",
            subject="Test Email",
        )

        notification = await service.send_notification(
            request=request,
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
        )

        assert notification is not None
        assert notification.status == NotificationStatus.SENT
        assert len(notification.recipients) == 1
        assert mock_notification_repo.save_notification.called
        assert mock_notification_repo.update_notification_status.called

    @pytest.mark.asyncio
    async def test_send_notification_sms_success(
        self,
        service: NotificationService,
        mock_notification_repo,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test successful SMS notification sending."""
        request = NotificationRequest(
            type="sms",
            recipients=["+1234567890"],
            sms_content="Test message",
        )

        notification = await service.send_notification(
            request=request,
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
        )

        assert notification is not None
        assert notification.status == NotificationStatus.SENT

    @pytest.mark.asyncio
    async def test_send_notification_both_channels(
        self,
        service: NotificationService,
        mock_notification_repo,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test notification sending to both channels."""
        request = NotificationRequest(
            type="both",
            recipients=[RecipientInput(email="user@example.com", phone="+1234567890")],
            html="<h1>Hello</h1>",
            sms_content="Hello SMS",
            subject="Test",
        )

        notification = await service.send_notification(
            request=request,
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
        )

        assert notification is not None
        assert notification.channel == NotificationChannel.BOTH
        assert "email" in notification.provider_responses
        assert "sms" in notification.provider_responses

    @pytest.mark.asyncio
    async def test_send_notification_with_template(
        self,
        service: NotificationService,
        mock_notification_repo,
        sample_user_id,
        sample_api_key_id,
        sample_template_id,
        es_client,
    ):
        """Test notification sending with template."""
        # First, create a template in ES
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

        request = NotificationRequest(
            type="email",
            recipients=["user@example.com"],
            template_id=sample_template_id,
            variables={"name": "John"},
        )

        with patch("src.repositories.base.get_elasticsearch_client", return_value=es_client):
            notification = await service.send_notification(
                request=request,
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )

        assert notification is not None
        assert notification.status == NotificationStatus.SENT
