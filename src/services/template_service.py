"""
Template management service.
Handles CRUD operations for notification templates.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from src.config.settings import get_settings
from src.core.exceptions import NotFoundError, ValidationError
from src.models.templates import Template, TemplateStatus, TemplateType
from src.repositories.base import get_elasticsearch_client
from src.schemas.templates import CreateTemplateRequest, UpdateTemplateRequest, VariableDefinition
from src.template_engine.engine import template_engine

logger = structlog.get_logger(__name__)
settings = get_settings()


class TemplateService:
    """Service for template management."""

    async def create_template(
        self,
        request: CreateTemplateRequest,
        user_id: str,
        workspace_id: str | None = None,
    ) -> Template:
        """Create a new template."""
        # Validate template syntax
        try:
            if request.template_type == TemplateType.EMAIL:
                template_engine.render_email(request.content, {})
            else:
                template_engine.render_sms(request.content, {})
        except Exception as e:
            raise ValidationError(f"Invalid template syntax: {str(e)}")

        # Extract variables for documentation
        extracted_vars = template_engine.extract_variables(request.content)
        variable_defs = request.variables or []

        # Ensure all defined variables match extracted
        defined_names = {v.name for v in variable_defs}
        for var_name in extracted_vars:
            if var_name not in defined_names:
                variable_defs.append(
                    VariableDefinition(name=var_name, type="string", required=False)
                )

        template = Template(
            name=request.name,
            template_type=request.template_type,
            user_id=user_id,
            content=request.content,
            subject=request.subject,
            text_content=request.text_content,
            workspace_id=workspace_id,
            description=request.description,
            variables=[v.model_dump() for v in variable_defs],
            metadata=request.metadata,
        )

        # Save to Elasticsearch
        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch not available")

        doc = template.to_elasticsearch_document()
        await client.index(
            index=f"{settings.elasticsearch.index_prefix}templates",
            id=str(template.template_id),
            document=doc,
            refresh="wait_for",
        )

        logger.info(
            "template_created",
            template_id=str(template.template_id),
            name=request.name,
            user_id=user_id,
        )

        return template

    async def get_template(self, template_id: UUID, user_id: str) -> Template:
        """Get a template by ID."""
        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch not available")

        try:
            response = await client.get(
                index=f"{settings.elasticsearch.index_prefix}templates",
                id=str(template_id),
            )
            doc = response.get("_source", {})
            if doc.get("user_id") != user_id:
                raise NotFoundError("Template not found")
            return Template.from_elasticsearch_document(doc)
        except Exception as e:
            if "not_found" in str(e).lower():
                raise NotFoundError("Template not found")
            raise

    async def list_templates(
        self,
        user_id: str,
        workspace_id: str | None = None,
        template_type: TemplateType | None = None,
        status: TemplateStatus | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Template], int]:
        """List templates with filtering."""
        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch not available")

        must_conditions: list[dict] = [{"term": {"user_id": user_id}}]
        if workspace_id:
            must_conditions.append({"term": {"workspace_id": workspace_id}})
        if template_type:
            must_conditions.append({"term": {"template_type": template_type.value}})
        if status:
            must_conditions.append({"term": {"status": status.value}})

        from_ = (page - 1) * page_size

        try:
            response = await client.search(
                index=f"{settings.elasticsearch.index_prefix}templates",
                body={
                    "query": {"bool": {"must": must_conditions}},
                    "sort": [{"updated_at": {"order": "desc"}}],
                    "from": from_,
                    "size": page_size,
                },
            )

            hits = response.get("hits", {})
            documents = [hit["_source"] for hit in hits.get("hits", [])]
            total = hits.get("total", {}).get("value", 0)

            templates = [Template.from_elasticsearch_document(doc) for doc in documents]
            return templates, total

        except Exception as e:
            logger.error("list_templates_failed", error=str(e))
            raise

    async def update_template(
        self,
        template_id: UUID,
        request: UpdateTemplateRequest,
        user_id: str,
    ) -> Template:
        """Update a template."""
        # Verify ownership
        existing = await self.get_template(template_id, user_id)

        # Build update document
        update_doc: dict[str, Any] = {"updated_at": datetime.utcnow().isoformat()}

        if request.name is not None:
            update_doc["name"] = request.name
        if request.content is not None:
            # Validate new content
            try:
                if existing.template_type == TemplateType.EMAIL:
                    template_engine.render_email(request.content, {})
                else:
                    template_engine.render_sms(request.content, {})
            except Exception as e:
                raise ValidationError(f"Invalid template syntax: {str(e)}")
            update_doc["content"] = request.content
        if request.subject is not None:
            update_doc["subject"] = request.subject
        if request.text_content is not None:
            update_doc["text_content"] = request.text_content
        if request.description is not None:
            update_doc["description"] = request.description
        if request.variables is not None:
            update_doc["variables"] = [v.model_dump() for v in request.variables]
        if request.status is not None:
            update_doc["status"] = request.status.value
        if request.metadata is not None:
            update_doc["metadata"] = request.metadata

        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch not available")

        await client.update(
            index=f"{settings.elasticsearch.index_prefix}templates",
            id=str(template_id),
            doc=update_doc,
            refresh="wait_for",
        )

        # Return updated template
        return await self.get_template(template_id, user_id)

    async def delete_template(self, template_id: UUID, user_id: str) -> bool:
        """Delete a template."""
        await self.get_template(template_id, user_id)  # Verify ownership

        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch not available")

        await client.delete(
            index=f"{settings.elasticsearch.index_prefix}templates",
            id=str(template_id),
            refresh="wait_for",
        )

        logger.info("template_deleted", template_id=str(template_id), user_id=user_id)
        return True

    async def render_template_preview(
        self,
        template_id: UUID,
        variables: dict[str, Any],
        user_id: str,
    ) -> dict[str, Any]:
        """Render a template preview with given variables."""
        template = await self.get_template(template_id, user_id)

        is_valid, missing = template_engine.validate_template(template.content, variables)

        if template.template_type == TemplateType.EMAIL:
            rendered = template_engine.render_email(
                template.content, variables, layout=None
            )
            return {
                "template_id": template.template_id,
                "rendered_content": rendered,
                "rendered_subject": (
                    template_engine._env.from_string(template.subject or "").render(**variables)
                    if template.subject
                    else None
                ),
                "used_variables": template_engine.extract_variables(template.content),
                "missing_variables": missing,
                "is_valid": is_valid,
            }
        else:
            rendered = template_engine.render_sms(template.content, variables)
            return {
                "template_id": template.template_id,
                "rendered_content": rendered,
                "used_variables": template_engine.extract_variables(template.content),
                "missing_variables": missing,
                "is_valid": is_valid,
            }


# Singleton instance
template_service = TemplateService()