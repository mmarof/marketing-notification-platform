"""
Template domain models.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class TemplateType(StrEnum):
    """Template channel types."""

    EMAIL = "email"
    SMS = "sms"


class TemplateStatus(StrEnum):
    """Template lifecycle states."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class Template:
    """Represents a notification template."""

    def __init__(
        self,
        name: str,
        template_type: TemplateType,
        user_id: str,
        content: str,
        subject: str | None = None,
        text_content: str | None = None,
        workspace_id: str | None = None,
        template_id: UUID | None = None,
        status: TemplateStatus = TemplateStatus.DRAFT,
        description: str | None = None,
        variables: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.template_id = template_id or uuid4()
        self.name = name
        self.template_type = template_type
        self.user_id = user_id
        self.content = content
        self.subject = subject
        self.text_content = text_content
        self.workspace_id = workspace_id
        self.status = status
        self.description = description
        self.variables = variables or []
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def to_elasticsearch_document(self) -> dict[str, Any]:
        return {
            "template_id": str(self.template_id),
            "name": self.name,
            "template_type": self.template_type.value,
            "user_id": self.user_id,
            "content": self.content,
            "subject": self.subject,
            "text_content": self.text_content,
            "workspace_id": self.workspace_id,
            "status": self.status.value,
            "description": self.description,
            "variables": self.variables,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_elasticsearch_document(cls, doc: dict[str, Any]) -> "Template":
        return cls(
            template_id=UUID(doc["template_id"]),
            name=doc["name"],
            template_type=TemplateType(doc["template_type"]),
            user_id=doc["user_id"],
            content=doc["content"],
            subject=doc.get("subject"),
            text_content=doc.get("text_content"),
            workspace_id=doc.get("workspace_id"),
            status=TemplateStatus(doc.get("status", "draft")),
            description=doc.get("description"),
            variables=doc.get("variables"),
            metadata=doc.get("metadata"),
            created_at=datetime.fromisoformat(doc["created_at"]),
            updated_at=datetime.fromisoformat(doc["updated_at"]),
        )
