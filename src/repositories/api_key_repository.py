"""
API Key repository for Elasticsearch operations.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import bcrypt

from src.config.settings import get_settings
from src.core.exceptions import NotFoundError
from src.models.api_keys import ApiKey, ApiKeyPermission
from src.repositories.base import BaseRepository
from src.schemas.api_keys import ApiKeyContext

settings = get_settings()


class ApiKeyRepository(BaseRepository):
    """Repository for API key persistence and validation."""

    def _get_index_suffix(self) -> str:
        return "api_keys"

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash an API key using bcrypt."""
        return bcrypt.hashpw(api_key.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_api_key_hash(api_key: str, key_hash: str) -> bool:
        """Verify an API key against its hash."""
        try:
            return bcrypt.checkpw(api_key.encode(), key_hash.encode())
        except Exception:
            return False

    @staticmethod
    def generate_api_key() -> str:
        """Generate a new API key."""
        import secrets

        return f"mnp_{secrets.token_urlsafe(32)}"

    @staticmethod
    def get_key_prefix(api_key: str) -> str:
        """Get prefix of API key for display purposes."""
        return api_key[:8] + "..."

    async def create_api_key(
        self,
        user_id: str,
        name: str,
        permissions: list[ApiKeyPermission],
        workspace_id: str | None = None,
        expires_in_days: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[ApiKey, str]:
        """Create a new API key. Returns (ApiKey object, raw key string)."""
        raw_key = self.generate_api_key()
        key_hash = self.hash_api_key(raw_key)
        key_prefix = self.get_key_prefix(raw_key)

        expires_at = None
        if expires_in_days:
            from datetime import timedelta

            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        api_key = ApiKey(
            user_id=user_id,
            name=name,
            permissions=permissions,
            key_hash=key_hash,
            key_prefix=key_prefix,
            workspace_id=workspace_id,
            expires_at=expires_at,
            metadata=metadata,
        )

        doc = api_key.to_elasticsearch_document()
        await self.index_document(str(api_key.api_key_id), doc)

        return api_key, raw_key

    async def validate_api_key(self, raw_key: str) -> ApiKeyContext | None:
        """
        Validate an API key and return context if valid.
        Searches by key prefix first for efficiency, then verifies hash.
        """
        prefix = raw_key[:8]
        if not prefix:
            return None

        # Search by prefix (only first 8 chars for security)
        query = {
            "bool": {
                "must": [
                    {"term": {"key_prefix": prefix + "..."}},
                    {"term": {"is_active": True}},
                ]
            }
        }

        documents, _ = await self.search(query=query, size=10)

        for doc in documents:
            if self.verify_api_key_hash(raw_key, doc["key_hash"]):
                # Check expiration
                if doc.get("expires_at"):
                    expires_at = datetime.fromisoformat(doc["expires_at"])
                    if datetime.utcnow() > expires_at:
                        continue

                # Update last used
                await self.update_document(
                    doc["api_key_id"],
                    {"last_used_at": datetime.utcnow().isoformat()},
                )

                return ApiKeyContext(
                    api_key_id=UUID(doc["api_key_id"]),
                    user_id=doc["user_id"],
                    name=doc["name"],
                    permissions=doc["permissions"],
                    workspace_id=doc.get("workspace_id"),
                    is_active=doc["is_active"],
                )

        return None

    async def get_api_key(self, api_key_id: UUID, user_id: str) -> ApiKey | None:
        """Get an API key by ID (user-scoped for security)."""
        doc = await self.get_document(str(api_key_id))
        if doc and doc["user_id"] == user_id:
            return ApiKey.from_elasticsearch_document(doc)
        return None

    async def list_api_keys(
        self, user_id: str, workspace_id: str | None = None
    ) -> tuple[list[ApiKey], int]:
        """List all API keys for a user."""
        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]
        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})

        documents, total = await self.search(
            query={"bool": {"must": must_conditions}},
            sort=[{"created_at": {"order": "desc"}}],
            size=100,
        )

        api_keys = [ApiKey.from_elasticsearch_document(doc) for doc in documents]
        return api_keys, total

    async def deactivate_api_key(self, api_key_id: UUID, user_id: str) -> bool:
        """Deactivate an API key."""
        doc = await self.get_document(str(api_key_id))
        if not doc or doc["user_id"] != user_id:
            raise NotFoundError("API key not found")

        return await self.update_document(str(api_key_id), {"is_active": False})

    async def delete_api_key(self, api_key_id: UUID, user_id: str) -> bool:
        """Delete an API key permanently."""
        doc = await self.get_document(str(api_key_id))
        if not doc or doc["user_id"] != user_id:
            raise NotFoundError("API key not found")

        return await self.delete_document(str(api_key_id))
