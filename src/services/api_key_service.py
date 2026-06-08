"""
API Key management service.
"""

from uuid import UUID

import structlog

from src.core.exceptions import NotFoundError
from src.models.api_keys import ApiKey, ApiKeyPermission
from src.repositories.api_key_repository import ApiKeyRepository
from src.schemas.api_keys import ApiKeyResponse, ApiKeyListResponse, CreateApiKeyRequest

logger = structlog.get_logger(__name__)


class ApiKeyService:
    """Service for API key management."""

    def __init__(self) -> None:
        self._repository = ApiKeyRepository()

    async def create_api_key(
        self,
        request: CreateApiKeyRequest,
        user_id: str,
    ) -> tuple[ApiKeyResponse, str]:
        """Create a new API key. Returns (response, raw_key)."""
        api_key, raw_key = await self._repository.create_api_key(
            user_id=user_id,
            name=request.name,
            permissions=request.permissions,
            workspace_id=request.workspace_id,
            expires_in_days=request.expires_in_days,
            metadata=request.metadata,
        )

        response = self._to_response(api_key)
        return response, raw_key

    async def list_api_keys(
        self,
        user_id: str,
        workspace_id: str | None = None,
    ) -> ApiKeyListResponse:
        """List all API keys for a user."""
        keys, total = await self._repository.list_api_keys(user_id, workspace_id)
        return ApiKeyListResponse(
            keys=[self._to_response(key) for key in keys],
            total=total,
        )

    async def delete_api_key(self, api_key_id: UUID, user_id: str) -> bool:
        """Delete an API key."""
        return await self._repository.delete_api_key(api_key_id, user_id)

    async def deactivate_api_key(self, api_key_id: UUID, user_id: str) -> bool:
        """Deactivate an API key (soft delete)."""
        return await self._repository.deactivate_api_key(api_key_id, user_id)

    def _to_response(self, api_key: ApiKey) -> ApiKeyResponse:
        """Convert ApiKey model to response schema."""
        return ApiKeyResponse(
            api_key_id=api_key.api_key_id,
            name=api_key.name,
            key_prefix=api_key.key_prefix,
            permissions=[p.value for p in api_key.permissions],
            workspace_id=api_key.workspace_id,
            is_active=api_key.is_active,
            expires_at=api_key.expires_at,
            last_used_at=api_key.last_used_at,
            created_at=api_key.created_at,
            metadata=api_key.metadata,
        )


# Singleton instance
api_key_service = ApiKeyService()