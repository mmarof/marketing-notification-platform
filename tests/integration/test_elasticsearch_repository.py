"""
Integration tests for Elasticsearch repository operations.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from src.models.notifications import Notification, NotificationChannel, NotificationStatus, Recipient
from src.repositories.notification_repository import NotificationRepository


@pytest.mark.asyncio
class TestNotificationRepository:
    """Integration tests for NotificationRepository."""

    @pytest.fixture
    def repository(self, es_client) -> NotificationRepository:
        """Create repository with patched client."""
        from unittest.mock import patch

        with patch("src.repositories.base.get_elasticsearch_client", return_value=es_client):
            repo = NotificationRepository()
            repo._index_name = "test_mnp_notifications"
            return repo

    @pytest.fixture
    def sample_notification(self, sample_user_id, sample_api_key_id) -> Notification:
        """Create a sample notification."""
        return Notification(
            channel=NotificationChannel.EMAIL,
            recipients=[Recipient(email="user@example.com")],
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
            subject="Test Subject",
            html_content="<h1>Test</h1>",
        )

    @pytest.mark.asyncio
    async def test_save_and_get_notification(
        self,
        repository: NotificationRepository,
        sample_notification: Notification,
    ):
        """Test saving and retrieving a notification."""
        # Save
        saved = await repository.save_notification(sample_notification)
        assert saved.notification_id == sample_notification.notification_id

        # Get
        retrieved = await repository.get_notification(sample_notification.notification_id)
        assert retrieved is not None
        assert retrieved.notification_id == sample_notification.notification_id
        assert retrieved.channel == NotificationChannel.EMAIL
        assert retrieved.subject == "Test Subject"
        assert len(retrieved.recipients) == 1

    @pytest.mark.asyncio
    async def test_update_notification_status(
        self,
        repository: NotificationRepository,
        sample_notification: Notification,
    ):
        """Test updating notification status."""
        await repository.save_notification(sample_notification)

        # Update status
        await repository.update_notification_status(
            sample_notification.notification_id,
            NotificationStatus.SENT,
            provider_response={"message_id": "msg_123"},
        )

        # Verify update
        updated = await repository.get_notification(sample_notification.notification_id)
        assert updated is not None
        assert updated.status == NotificationStatus.SENT
        assert updated.provider_responses == {"message_id": "msg_123"}

    @pytest.mark.asyncio
    async def test_get_notifications_by_user(
        self,
        repository: NotificationRepository,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test getting notifications by user."""
        # Create multiple notifications
        for i in range(5):
            notif = Notification(
                channel=NotificationChannel.EMAIL if i % 2 == 0 else NotificationChannel.SMS,
                recipients=[Recipient(email=f"user{i}@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            await repository.save_notification(notif)

        # Get all for user
        notifications, total = await repository.get_notifications_by_user(sample_user_id)
        assert total == 5
        assert len(notifications) == 5

        # Filter by channel
        email_notifs, email_total = await repository.get_notifications_by_user(
            sample_user_id, channel="email"
        )
        assert email_total == 3  # 0, 2, 4

    @pytest.mark.asyncio
    async def test_get_status_counts(
        self,
        repository: NotificationRepository,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test getting status counts for analytics."""
        # Create notifications with different statuses
        for status in [NotificationStatus.SENT, NotificationStatus.SENT, NotificationStatus.FAILED]:
            notif = Notification(
                channel=NotificationChannel.EMAIL,
                recipients=[Recipient(email="user@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            notif.status = status
            await repository.save_notification(notif)
            await repository.update_notification_status(
                notif.notification_id, status
            )

        counts = await repository.get_status_counts(sample_user_id)
        assert "sent" in counts
        assert counts["sent"] == 2
        assert "failed" in counts
        assert counts["failed"] == 1

    @pytest.mark.asyncio
    async def test_get_channel_counts(
        self,
        repository: NotificationRepository,
        sample_user_id,
        sample_api_key_id,
    ):
        """Test getting channel counts."""
        for _ in range(3):
            notif = Notification(
                channel=NotificationChannel.EMAIL,
                recipients=[Recipient(email="user@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            await repository.save_notification(notif)

        for _ in range(2):
            notif = Notification(
                channel=NotificationChannel.SMS,
                recipients=[Recipient(phone="+1234567890")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            await repository.save_notification(notif)

        counts = await repository.get_channel_counts(sample_user_id)
        assert counts.get("email") == 3
        assert counts.get("sms") == 2

    @pytest.mark.asyncio
    async def test_delete_notification(
        self,
        repository: NotificationRepository,
        sample_notification: Notification,
    ):
        """Test deleting a notification."""
        await repository.save_notification(sample_notification)

        # Delete
        result = await repository.delete_notification(sample_notification.notification_id)
        assert result is True

        # Verify deleted
        retrieved = await repository.get_notification(sample_notification.notification_id)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_nonexistent_notification(
        self,
        repository: NotificationRepository,
    ):
        """Test getting a non-existent notification."""
        retrieved = await repository.get_notification(uuid4())
        assert retrieved is None