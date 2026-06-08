"""
API Key request and response schemas.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.api_keys import ApiKeyPermission


class CreateApiKeyRequest(BaseModel):
    """Schema for creating a new API key."""

    name: str = Field(
        min_length=1,
        max_length=100,
        description="Descriptive name for the API key",
    )
    permissions: list[ApiKeyPermission] = Field(
        min_length=1,
        description="Permissions granted to this key",
    )
    workspace_id: str | None = Field(
        default=None,
        description="Scope key to specific workspace",
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Key expiration in days (null = never expires)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional key metadata",
    )


class ApiKeyResponse(BaseModel):
    """Schema for API key response (excludes hash)."""

    api_key_id: UUID
    name: str
    key_prefix: str
    permissions: list[str]
    workspace_id: str | None
    is_active: bool
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime
    metadata: dict[str, Any]


class ApiKeyCreatedResponse(BaseModel):
    """Schema returned after key creation (includes full key once)."""

    api_key_id: UUID
    name: str
    key: str  # Full API key - only shown once
    key_prefix: str
    permissions: list[str]
    workspace_id: str | None
    expires_at: datetime | None
    created_at: datetime
    message: str = "Store this API key securely. It cannot be retrieved again."


class ApiKeyContext(BaseModel):
    """Internal context for authenticated API key."""

    api_key_id: UUID
    user_id: str
    name: str
    permissions: list[str]
    workspace_id: str | None
    is_active: bool


class ApiKeyListResponse(BaseModel):
    """Schema for listing API keys."""

    keys: list[ApiKeyResponse]
    total: int