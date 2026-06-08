"""
Custom middleware for request processing.
Handles request IDs, tenant context, and timing.
"""

import time
import uuid
from contextvars import ContextVar
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Context variables for request-scoped data
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
user_id_ctx: ContextVar[str] = ContextVar("user_id", default="")
api_key_id_ctx: ContextVar[str] = ContextVar("api_key_id", default="")
workspace_id_ctx: ContextVar[str | None] = ContextVar("workspace_id", default=None)

logger = structlog.get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Adds unique request ID to each request for tracing."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_ctx.set(request_id)
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Extracts and sets tenant context from request.
    Context is populated by auth dependency after this middleware runs.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Initialize context (will be populated by auth dependency)
        request.state.user_id = None
        request.state.api_key_id = None
        request.state.workspace_id = None

        response = await call_next(request)

        # After request processing, sync context vars
        if hasattr(request.state, "user_id") and request.state.user_id:
            user_id_ctx.set(request.state.user_id)
        if hasattr(request.state, "api_key_id") and request.state.api_key_id:
            api_key_id_ctx.set(request.state.api_key_id)
        if hasattr(request.state, "workspace_id"):
            workspace_id_ctx.set(request.state.workspace_id)

        return response


class TimingMiddleware(BaseHTTPMiddleware):
    """Tracks request processing time for monitoring."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "request_completed",
                method=method,
                path=path,
                duration_ms=round(duration_ms, 2),
                status_code=getattr(response, "status_code", "unknown"),
            )


def get_request_id() -> str:
    """Get current request ID from context."""
    return request_id_ctx.get("")


def get_current_user_id() -> str:
    """Get current authenticated user ID from context."""
    user_id = user_id_ctx.get("")
    if not user_id:
        raise AuthenticationError("No authenticated user in context")
    return user_id


def get_current_api_key_id() -> str:
    """Get current API key ID from context."""
    return api_key_id_ctx.get("")


def get_current_workspace_id() -> str | None:
    """Get current workspace ID from context (optional)."""
    return workspace_id_ctx.get(None)