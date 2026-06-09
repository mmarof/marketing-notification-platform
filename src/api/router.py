"""
Main API router that combines all route modules.
"""

from fastapi import APIRouter

from src.api.auth.api_keys import router as api_keys_router
from src.api.v1.campaigns import router as campaigns_router
from src.api.v1.notifications import router as notifications_router
from src.api.v1.templates import router as templates_router

api_router = APIRouter()

# Auth routes
api_router.include_router(api_keys_router, prefix="/auth", tags=["Authentication"])

# V1 API routes
api_router.include_router(notifications_router, prefix="/v1", tags=["Notifications"])
api_router.include_router(templates_router, prefix="/v1", tags=["Templates"])
api_router.include_router(campaigns_router, prefix="/v1", tags=["Campaigns"])
