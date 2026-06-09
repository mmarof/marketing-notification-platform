"""
Integration tests for Elasticsearch repository operations.
Fixed version with proper client and index handling.
"""

import asyncio
from uuid import uuid4

import pytest

from src.config.settings import get_settings
from src.models.notifications import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    Recipient,
)
from src.repositories.notification_repository import NotificationRepository

TEST_SETTINGS = get_settings()
TEST_SETTINGS.elasticsearch.index_prefix = "test_mnp_"


@pytest.mark.asyncio
class TestNotificationRepository:
    """Integration tests for NotificationRepository."""

    @pytest.fixture
    def repository(self, es_index, patch_elasticsearch) -> NotificationRepository:
        """
        Create repository with patched ES client.
        es_index ensures indices exist and cleans up after.
        """
        repo = NotificationRepository()
        # Explicitly set index name to match our test prefix
        repo._index_name = "test_mnp_notifications"
        return repo

    @pytest.fixture
    def sample_notification(
        self,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ) -> Notification:
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
        assert retrieved.recipients[0].email == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_nonexistent_notification(
        self,
        repository: NotificationRepository,
    ):
        """Test getting a non-existent notification returns None."""
        retrieved = await repository.get_notification(uuid4())
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_update_notification_status(
        self,
        repository: NotificationRepository,
        sample_notification: Notification,
    ):
        """Test updating notification status."""
        await repository.save_notification(sample_notification)

        # Update status
        success = await repository.update_notification_status(
            sample_notification.notification_id,
            NotificationStatus.SENT,
            provider_response={"message_id": "msg_123", "provider": "mock"},
        )
        assert success is True

        # Verify update
        updated = await repository.get_notification(sample_notification.notification_id)
        assert updated is not None
        assert updated.status == NotificationStatus.SENT
        assert updated.provider_responses == {"message_id": "msg_123", "provider": "mock"}

    @pytest.mark.asyncio
    async def test_update_status_with_error(
        self,
        repository: NotificationRepository,
        sample_notification: Notification,
    ):
        """Test updating notification status with error message."""
        await repository.save_notification(sample_notification)

        await repository.update_notification_status(
            sample_notification.notification_id,
            NotificationStatus.FAILED,
            error_message="Connection timeout",
        )

        updated = await repository.get_notification(sample_notification.notification_id)
        assert updated.status == NotificationStatus.FAILED
        assert updated.error_message == "Connection timeout"

    @pytest.mark.asyncio
    async def test_get_notifications_by_user(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ):
        """Test getting notifications filtered by user."""
        # Create multiple notifications for the same user
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

        # Filter by channel - email
        _email_notifs, email_total = await repository.get_notifications_by_user(
            sample_user_id, channel="email"
        )
        assert email_total == 3  # indices 0, 2, 4

        # Filter by channel - sms
        _sms_notifs, sms_total = await repository.get_notifications_by_user(
            sample_user_id, channel="sms"
        )
        assert sms_total == 2  # indices 1, 3

    @pytest.mark.asyncio
    async def test_get_notifications_by_user_with_workspace(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
        sample_workspace_id: str,
    ):
        """Test filtering notifications by workspace."""
        # Create notifications in different workspaces
        notif1 = Notification(
            channel=NotificationChannel.EMAIL,
            recipients=[Recipient(email="user1@example.com")],
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
            workspace_id=sample_workspace_id,
        )
        notif2 = Notification(
            channel=NotificationChannel.EMAIL,
            recipients=[Recipient(email="user2@example.com")],
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
            workspace_id="other_workspace",
        )

        await repository.save_notification(notif1)
        await repository.save_notification(notif2)

        # Filter by workspace
        ws_notifs, ws_total = await repository.get_notifications_by_user(
            sample_user_id, workspace_id=sample_workspace_id
        )
        assert ws_total == 1
        assert ws_notifs[0].workspace_id == sample_workspace_id

    @pytest.mark.asyncio
    async def test_get_notifications_pagination(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ):
        """Test notification list pagination."""
        # Create 10 notifications
        for i in range(10):
            notif = Notification(
                channel=NotificationChannel.EMAIL,
                recipients=[Recipient(email=f"user{i}@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            await repository.save_notification(notif)

        # Page 1
        page1, total = await repository.get_notifications_by_user(
            sample_user_id, page=1, page_size=3
        )
        assert total == 10
        assert len(page1) == 3

        # Page 2
        page2, _ = await repository.get_notifications_by_user(
            sample_user_id, page=2, page_size=3
        )
        assert len(page2) == 3

        # Last page
        last_page, _ = await repository.get_notifications_by_user(
            sample_user_id, page=4, page_size=3
        )
        assert len(last_page) == 1

    @pytest.mark.asyncio
    async def test_get_status_counts(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
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
            await repository.save_notification(notif)
            await repository.update_notification_status(notif.notification_id, status)

        counts = await repository.get_status_counts(sample_user_id)
        assert "sent" in counts
        assert counts["sent"] == 2
        assert "failed" in counts
        assert counts["failed"] == 1

    @pytest.mark.asyncio
    async def test_get_channel_counts(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ):
        """Test getting channel counts."""
        # Create email notifications
        for _ in range(3):
            notif = Notification(
                channel=NotificationChannel.EMAIL,
                recipients=[Recipient(email="user@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            await repository.save_notification(notif)

        # Create SMS notifications
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
    async def test_delete_nonexistent_notification(
        self,
        repository: NotificationRepository,
    ):
        """Test deleting a non-existent notification returns False."""
        result = await repository.delete_notification(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_notifications_isolated_by_user(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ):
        """Test that notifications are isolated by user (multi-tenancy)."""
        other_user_id = "other_user_xyz"

        # Create notification for sample user
        notif1 = Notification(
            channel=NotificationChannel.EMAIL,
            recipients=[Recipient(email="user1@example.com")],
            user_id=sample_user_id,
            api_key_id=str(sample_api_key_id),
        )
        await repository.save_notification(notif1)

        # Create notification for other user
        notif2 = Notification(
            channel=NotificationChannel.EMAIL,
            recipients=[Recipient(email="user2@example.com")],
            user_id=other_user_id,
            api_key_id=str(sample_api_key_id),
        )
        await repository.save_notification(notif2)

        # Sample user should only see their notification
        user_notifs, user_total = await repository.get_notifications_by_user(sample_user_id)
        assert user_total == 1
        assert user_notifs[0].user_id == sample_user_id

        # Other user should only see their notification
        other_notifs, other_total = await repository.get_notifications_by_user(other_user_id)
        assert other_total == 1
        assert other_notifs[0].user_id == other_user_id

    @pytest.mark.asyncio
    async def test_bulk_notification_creation(
        self,
        repository: NotificationRepository,
        sample_user_id: str,
        sample_api_key_id: uuid4,
    ):
        """Test creating many notifications efficiently."""
        # Create 100 notifications
        tasks = []
        for i in range(100):
            notif = Notification(
                channel=NotificationChannel.EMAIL,
                recipients=[Recipient(email=f"bulk{i}@example.com")],
                user_id=sample_user_id,
                api_key_id=str(sample_api_key_id),
            )
            tasks.append(repository.save_notification(notif))

        await asyncio.gather(*tasks)

        # Verify count
        _, total = await repository.get_notifications_by_user(sample_user_id, page_size=200)
        assert total == 100
