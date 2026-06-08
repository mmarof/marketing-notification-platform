"""
Template request and response schemas.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.templates import TemplateStatus, TemplateType


class VariableDefinition(BaseModel):
    """Definition of a template variable."""

    name: str
    type: str = Field(default="string", description="Variable type: string, number, boolean, date")
    required: bool = Field(default=False)
    default: Any = Field(default=None)
    description: str | None = Field(default=None)


class CreateTemplateRequest(BaseModel):
    """Schema for creating a new template."""

    name: str = Field(
        min_length=1,
        max_length=200,
        description="Template name",
    )
    template_type: TemplateType = Field(description="Template channel type")
    content: str = Field(
        min_length=1,
        description="Template content (Jinja2 for email, text with {{ }} for SMS)",
    )
    subject: str | None = Field(
        default=None,
        max_length=500,
        description="Email subject (for email templates)",
    )
    text_content: str | None = Field(
        default=None,
        description="Plain text fallback for email templates",
    )
    description: str | None = Field(
        default=None,
        max_length=1000,
        description="Template description",
    )
    variables: list[VariableDefinition] = Field(
        default_factory=list,
        description="Variable definitions for documentation/validation",
    )
    workspace_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdateTemplateRequest(BaseModel):
    """Schema for updating a template."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, max_length=500)
    text_content: str | None = Field(default=None)
    description: str | None = Field(default=None, max_length=1000)
    variables: list[VariableDefinition] | None = None
    status: TemplateStatus | None = None
    metadata: dict[str, Any] | None = None


class TemplateResponse(BaseModel):
    """Schema for template response."""

    template_id: UUID
    name: str
    template_type: str
    content: str
    subject: str | None
    text_content: str | None
    status: str
    description: str | None
    variables: list[VariableDefinition]
    workspace_id: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    """Schema for listing templates."""

    templates: list[TemplateResponse]
    total: int


class TemplateRenderRequest(BaseModel):
    """Schema for preview/template rendering."""

    template_id: UUID
    variables: dict[str, Any] = Field(default_factory=dict)
    recipient_variables: dict[str, dict[str, Any]] | None = None


class TemplateRenderResponse(BaseModel):
    """Schema for rendered template output."""

    template_id: UUID
    rendered_content: str
    rendered_subject: str | None
    rendered_text: str | None
    used_variables: list[str]
    missing_variables: list[str]
