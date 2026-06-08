"""
Common response schemas.
"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: dict[str, Any]


class SuccessResponse(BaseModel):
    """Simple success response."""

    message: str
    data: dict[str, Any] | None = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    items: list[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    elasticsearch: str | None = None
    redis: str | None = None