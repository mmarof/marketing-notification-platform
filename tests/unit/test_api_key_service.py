"""
Unit tests for API key service.
"""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from src.models.api_keys import ApiKeyPermission
from src.schemas.api_keys import CreateApiKeyRequest
from src.services.api_key_service import ApiKeyService


class TestApiKeyService:
    """Tests for ApiKeyService."""

    @pytest.fixture
    def service(self) -> ApiKeyService:
        """Create API key service."""
        return ApiKeyService()

    @pytest.fixture
    def create_request(self) -> CreateApiKeyRequest:
        """Sample create request."""
        return CreateApiKeyRequest(
            name="Test Key",
            permissions=[ApiKeyPermission.SEND_NOTIFICATIONS, ApiKeyPermission.VIEW_ANALYTICS],
        )

    @pytest.mark.asyncio
    async def test_create_api_key(
        self,
        service: ApiKeyService,
        create_request: CreateApiKeyRequest,
        sample_user_id,
    ):
        """Test API key creation."""
        with patch.object(service._repository, "create_api_key", new_callable=AsyncMock) as mock_create:
            from src.models.api_keys import ApiKey
            from datetime import datetime

            mock_api_key = ApiKey(
                user_id=sample_user_id,
                name="Test Key",
                permissions=[ApiKeyPermission.SEND_NOTIFICATIONS, ApiKeyPermission.VIEW_ANALYTICS],
                key_hash="hashed",
                key_prefix="mnp_abc...",
            )
            mock_create.return_value = (mock_api_key, "mnp_raw_key_here")

            response, raw_key = await service.create_api_key(create_request, sample_user_id)

            assert raw_key == "mnp_raw_key_here"
            assert response.name == "Test Key"
            assert len(response.permissions) == 2
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_api_keys(
        self,
        service: ApiKeyService,
        sample_user_id,
    ):
        """Test listing API keys."""
        with patch.object(service._repository, "list_api_keys", new_callable=AsyncMock) as mock_list:
            from src.models.api_keys import ApiKey
            from datetime import datetime

            mock_keys = [
                ApiKey(
                    user_id=sample_user_id,
                    name="Key 1",
                    permissions=[ApiKeyPermission.SEND_NOTIFICATIONS],
                    key_hash="hash1",
                    key_prefix="mnp_111...",
                    api_key_id=uuid4(),
                    created_at=datetime.utcnow(),
                ),
                ApiKey(
                    user_id=sample_user_id,
                    name="Key 2",
                    permissions=[ApiKeyPermission.ADMIN],
                    key_hash="hash2",
                    key_prefix="mnp_222...",
                    api_key_id=uuid4(),
                    created_at=datetime.utcnow(),
                ),
            ]
            mock_list.return_value = (mock_keys, 2)

            result = await service.list_api_keys(sample_user_id)

            assert result.total == 2
            assert len(result.keys) == 2
            mock_list.assert_called_once_with(sample_user_id, None)

    @pytest.mark.asyncio
    async def test_list_api_keys_with_workspace(
        self,
        service: ApiKeyService,
        sample_user_id,
        sample_workspace_id,
    ):
        """Test listing API keys filtered by workspace."""
        with patch.object(service._repository, "list_api_keys", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = ([], 0)

            await service.list_api_keys(sample_user_id, sample_workspace_id)

            mock_list.assert_called_once_with(sample_user_id, sample_workspace_id)

    @pytest.mark.asyncio
    async def test_delete_api_key(
        self,
        service: ApiKeyService,
        sample_user_id,
    ):
        """Test deleting an API key."""
        key_id = uuid4()

        with patch.object(service._repository, "delete_api_key", new_callable=AsyncMock) as mock_delete:
            mock_delete.return_value = True

            result = await service.delete_api_key(key_id, sample_user_id)

            assert result is True
            mock_delete.assert_called_once_with(key_id, sample_user_id)

    @pytest.mark.asyncio
    async def test_deactivate_api_key(
        self,
        service: ApiKeyService,
        sample_user_id,
    ):
        """Test deactivating an API key."""
        key_id = uuid4()

        with patch.object(service._repository, "deactivate_api_key", new_callable=AsyncMock) as mock_deactivate:
            mock_deactivate.return_value = True

            result = await service.deactivate_api_key(key_id, sample_user_id)

            assert result is True
            mock_deactivate.assert_called_once_with(key_id, sample_user_id)