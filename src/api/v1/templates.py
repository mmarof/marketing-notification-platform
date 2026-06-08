"""
Template management endpoints.
"""

from uuid import UUID

from fastapi import APIRouter, Query, status

from src.core.dependencies import TenantContext
from src.models.templates import TemplateStatus, TemplateType
from src.schemas.templates import (
    CreateTemplateRequest,
    TemplateListResponse,
    TemplateRenderResponse,
    TemplateResponse,
    UpdateTemplateRequest,
)
from src.services.template_service import template_service

router = APIRouter()


@router.post(
    "/templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Template",
    description="""
    Create a new notification template.

    Templates use Jinja2 syntax for variable substitution:
    - `{{ variable_name }}` for variable output
    - `{% if condition %}...{% endif %}` for conditionals
    - `{% for item in list %}...{% endfor %}` for loops

    ## Example Email Template:
    ```html
    <h1>Hello {{ name }}</h1>
    <p>Your order {{ order_id }} has been confirmed.</p>
    <a href="{{ tracking_url }}">Track your order</a>
    ```

    ## Example SMS Template:
    ```
    Hi {{ name }}, your code is {{ code }}. Valid for {{ validity_minutes }} minutes.
    ```
    """,
)
async def create_template(
    request: CreateTemplateRequest,
    tenant: TenantContext,
) -> TemplateResponse:
    """Create a new template."""
    template = await template_service.create_template(
        request=request,
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
    )

    return _to_response(template)


@router.get(
    "/templates",
    response_model=TemplateListResponse,
    summary="List Templates",
    description="List all templates with optional filtering.",
)
async def list_templates(
    tenant: TenantContext,
    template_type: TemplateType | None = Query(default=None, description="Filter by type"),
    status: TemplateStatus | None = Query(default=None, description="Filter by status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> TemplateListResponse:
    """List templates."""
    templates, total = await template_service.list_templates(
        user_id=tenant.user_id,
        workspace_id=tenant.workspace_id,
        template_type=template_type,
        status=status,
        page=page,
        page_size=page_size,
    )

    return TemplateListResponse(
        templates=[_to_response(t) for t in templates],
        total=total,
    )


@router.get(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Get Template",
    description="Get a specific template by ID.",
)
async def get_template(
    template_id: UUID,
    tenant: TenantContext,
) -> TemplateResponse:
    """Get template details."""
    template = await template_service.get_template(template_id, tenant.user_id)
    return _to_response(template)


@router.put(
    "/templates/{template_id}",
    response_model=TemplateResponse,
    summary="Update Template",
    description="Update a template's content or metadata.",
)
async def update_template(
    template_id: UUID,
    request: UpdateTemplateRequest,
    tenant: TenantContext,
) -> TemplateResponse:
    """Update a template."""
    template = await template_service.update_template(
        template_id=template_id,
        request=request,
        user_id=tenant.user_id,
    )
    return _to_response(template)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Template",
    description="Permanently delete a template.",
)
async def delete_template(
    template_id: UUID,
    tenant: TenantContext,
) -> None:
    """Delete a template."""
    await template_service.delete_template(template_id, tenant.user_id)


@router.post(
    "/templates/{template_id}/render",
    response_model=TemplateRenderResponse,
    summary="Render Template Preview",
    description="Render a template with sample variables for preview.",
)
async def render_template_preview(
    template_id: UUID,
    tenant: TenantContext,
    variables: dict | None = None,
) -> TemplateRenderResponse:
    """Render template preview."""
    if variables is None:
        variables = {}
    result = await template_service.render_template_preview(
        template_id=template_id,
        variables=variables,
        user_id=tenant.user_id,
    )

    return TemplateRenderResponse(**result)


@router.post(
    "/templates/validate",
    summary="Validate Template Syntax",
    description="Validate Jinja2 template syntax without saving.",
)
async def validate_template_syntax(
    content: str,
    template_type: TemplateType = Query(default=TemplateType.EMAIL),
) -> dict:
    """Validate template syntax."""
    from src.core.exceptions import TemplateError
    from src.template_engine.engine import template_engine

    try:
        if template_type == TemplateType.EMAIL:
            template_engine.render_email(content, {})
        else:
            template_engine.render_sms(content, {})

        variables = template_engine.extract_variables(content)

        return {
            "valid": True,
            "variables": variables,
            "message": "Template syntax is valid",
        }
    except TemplateError as e:
        return {
            "valid": False,
            "variables": [],
            "message": str(e),
        }


def _to_response(template) -> TemplateResponse:
    """Convert Template model to response schema."""
    from src.schemas.templates import VariableDefinition

    return TemplateResponse(
        template_id=template.template_id,
        name=template.name,
        template_type=template.template_type.value,
        content=template.content,
        subject=template.subject,
        text_content=template.text_content,
        status=template.status.value,
        description=template.description,
        variables=[VariableDefinition(**v) for v in template.variables] if template.variables else [],
        workspace_id=template.workspace_id,
        metadata=template.metadata,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )
