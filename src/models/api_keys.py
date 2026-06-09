"""
API Key domain models.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class ApiKeyPermission(StrEnum):
    """API key permission levels."""

    READ_ONLY = "read_only"
    SEND_NOTIFICATIONS = "send_notifications"
    MANAGE_TEMPLATES = "manage_templates"
    VIEW_ANALYTICS = "view_analytics"
    ADMIN = "admin"


class ApiKey:
    """Represents an API key for authentication."""

    def __init__(
        self,
        user_id: str,
        name: str,
        permissions: list[ApiKeyPermission],
        key_hash: str,
        key_prefix: str,
        workspace_id: str | None = None,
        api_key_id: UUID | None = None,
        is_active: bool = True,
        expires_at: datetime | None = None,
        last_used_at: datetime | None = None,
        created_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        self.api_key_id = api_key_id or uuid4()
        self.user_id = user_id
        self.name = name
        self.permissions = permissions
        self.key_hash = key_hash
        self.key_prefix = key_prefix
        self.workspace_id = workspace_id
        self.is_active = is_active
        self.expires_at = expires_at
        self.last_used_at = last_used_at
        self.created_at = created_at or datetime.utcnow()
        self.metadata = metadata or {}

    def to_elasticsearch_document(self) -> dict[str, Any]:
        return {
            "api_key_id": str(self.api_key_id),
            "user_id": self.user_id,
            "name": self.name,
            "permissions": [p.value for p in self.permissions],
            "key_hash": self.key_hash,
            "key_prefix": self.key_prefix,
            "workspace_id": self.workspace_id,
            "is_active": self.is_active,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_elasticsearch_document(cls, doc: dict[str, Any]) -> "ApiKey":
        permissions = [ApiKeyPermission(p) for p in doc.get("permissions", [])]
        return cls(
            api_key_id=UUID(doc["api_key_id"]),
            user_id=doc["user_id"],
            name=doc["name"],
            permissions=permissions,
            key_hash=doc["key_hash"],
            key_prefix=doc["key_prefix"],
            workspace_id=doc.get("workspace_id"),
            is_active=doc.get("is_active", True),
            expires_at=datetime.fromisoformat(doc["expires_at"]) if doc.get("expires_at") else None,
            last_used_at=(
                datetime.fromisoformat(doc["last_used_at"]) if doc.get("last_used_at") else None
            ),
            created_at=datetime.fromisoformat(doc["created_at"]),
            metadata=doc.get("metadata"),
        )
