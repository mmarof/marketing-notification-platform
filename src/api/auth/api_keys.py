"""
API Key management endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, status

from src.core.dependencies import TenantContext
from src.schemas.api_keys import (
    ApiKeyCreatedResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
)
from src.services.api_key_service import api_key_service

router = APIRouter()


@router.post(
    "/api-key/create",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create API Key",
    description="Create a new API key for authentication. The full key is only shown once.",
)
async def create_api_key(
    request: CreateApiKeyRequest,
    tenant: TenantContext,
) -> ApiKeyCreatedResponse:
    """Create a new API key."""
    response, raw_key = await api_key_service.create_api_key(
        request=request,
        user_id=tenant.user_id,
    )

    return ApiKeyCreatedResponse(
        api_key_id=response.api_key_id,
        name=response.name,
        key=raw_key,
        key_prefix=response.key_prefix,
        permissions=response.permissions,
        workspace_id=response.workspace_id,
        expires_at=response.expires_at,
        created_at=response.created_at,
    )


@router.get(
    "/api-key/list",
    response_model=ApiKeyListResponse,
    summary="List API Keys",
    description="List all API keys for the authenticated user.",
)
async def list_api_keys(
    tenant: TenantContext,
    workspace_id: str | None = None,
) -> ApiKeyListResponse:
    """List all API keys."""
    return await api_key_service.list_api_keys(
        user_id=tenant.user_id,
        workspace_id=workspace_id or tenant.workspace_id,
    )


@router.delete(
    "/api-key/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete API Key",
    description="Permanently delete an API key.",
)
async def delete_api_key(
    api_key_id: UUID,
    tenant: TenantContext,
) -> None:
    """Delete an API key."""
    await api_key_service.delete_api_key(
        api_key_id=api_key_id,
        user_id=tenant.user_id,
    )


@router.post(
    "/api-key/{api_key_id}/deactivate",
    response_model=ApiKeyResponse,
    summary="Deactivate API Key",
    description="Deactivate an API key without deleting it.",
)
async def deactivate_api_key(
    api_key_id: UUID,
    tenant: TenantContext,
) -> ApiKeyResponse:
    """Deactivate an API key."""
    await api_key_service.deactivate_api_key(
        api_key_id=api_key_id,
        user_id=tenant.user_id,
    )
    # Return the updated key
    result = await api_key_service.list_api_keys(tenant.user_id)
    for key in result.keys:
        if key.api_key_id == api_key_id:
            return key
    from src.core.exceptions import NotFoundError

    raise NotFoundError("API key not found after deactivation")
