"""
Base Elasticsearch repository with connection management.
Provides shared functionality for all repositories.
"""

from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch

from src.config.settings import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_elasticsearch_client: AsyncElasticsearch | None = None


async def initialize_elasticsearch() -> None:
    """Initialize Elasticsearch client and ensure indices exist."""
    global _elasticsearch_client

    _elasticsearch_client = AsyncElasticsearch(
        hosts=[settings.elasticsearch.host],
        basic_auth=(
            settings.elasticsearch.username,
            settings.elasticsearch.password.get_secret_value(),
        ),
        request_timeout=settings.elasticsearch.request_timeout,
        max_retries=settings.elasticsearch.max_retries,
        verify_certs=settings.elasticsearch.verify_certs,
        retry_on_timeout=True,
    )

    # Ensure indices exist with proper mappings
    await _ensure_indices_exist()


async def _ensure_indices_exist() -> None:
    """Create Elasticsearch indices with mappings if they don't exist."""
    if not _elasticsearch_client:
        return

    prefix = settings.elasticsearch.index_prefix

    indices_config = {
        f"{prefix}notifications": NOTIFICATION_INDEX_MAPPING,
        f"{prefix}api_keys": API_KEY_INDEX_MAPPING,
        f"{prefix}templates": TEMPLATE_INDEX_MAPPING,
        f"{prefix}audit_logs": AUDIT_LOG_INDEX_MAPPING,
    }

    for index_name, mapping in indices_config.items():
        exists = await _elasticsearch_client.indices.exists(index=index_name)
        if not exists:
            await _elasticsearch_client.indices.create(
                index=index_name,
                body={"mappings": mapping, "settings": {"number_of_shards": 1, "number_of_replicas": 0}},
            )
            logger.info("index_created", index=index_name)


async def close_elasticsearch() -> None:
    """Close Elasticsearch connection."""
    global _elasticsearch_client
    if _elasticsearch_client:
        await _elasticsearch_client.close()
        _elasticsearch_client = None


def get_elasticsearch_client() -> AsyncElasticsearch | None:
    """Get current Elasticsearch client."""
    return _elasticsearch_client


# Elasticsearch index mappings
NOTIFICATION_INDEX_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "notification_id": {"type": "keyword"},
        "campaign_id": {"type": "keyword"},
        "channel": {"type": "keyword"},
        "status": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "api_key_id": {"type": "keyword"},
        "workspace_id": {"type": "keyword"},
        "template_id": {"type": "keyword"},
        "subject": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "html_content": {"type": "text", "index": False},
        "text_content": {"type": "text", "index": False},
        "sms_content": {"type": "text", "index": False},
        "email_mode": {"type": "keyword"},
        "recipients": {
            "type": "nested",
            "properties": {
                "email": {"type": "keyword"},
                "phone": {"type": "keyword"},
                "variables": {"type": "object", "enabled": False},
                "metadata": {"type": "object", "enabled": False},
            },
        },
        "recipient_count": {"type": "integer"},
        "global_variables": {"type": "object", "enabled": False},
        "provider_responses": {"type": "object", "enabled": False},
        "error_message": {"type": "text"},
        "retry_count": {"type": "integer"},
        "metadata": {"type": "object", "enabled": True},
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
    },
}

API_KEY_INDEX_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "api_key_id": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "permissions": {"type": "keyword"},
        "key_hash": {"type": "keyword"},
        "key_prefix": {"type": "keyword"},
        "workspace_id": {"type": "keyword"},
        "is_active": {"type": "boolean"},
        "expires_at": {"type": "date"},
        "last_used_at": {"type": "date"},
        "created_at": {"type": "date"},
        "metadata": {"type": "object", "enabled": True},
    },
}

TEMPLATE_INDEX_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "template_id": {"type": "keyword"},
        "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "template_type": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "content": {"type": "text", "index": False},
        "subject": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
        "text_content": {"type": "text", "index": False},
        "workspace_id": {"type": "keyword"},
        "status": {"type": "keyword"},
        "description": {"type": "text"},
        "variables": {
            "type": "nested",
            "properties": {
                "name": {"type": "keyword"},
                "type": {"type": "keyword"},
                "required": {"type": "boolean"},
                "default": {"type": "keyword"},
                "description": {"type": "text"},
            },
        },
        "metadata": {"type": "object", "enabled": True},
        "created_at": {"type": "date"},
        "updated_at": {"type": "date"},
    },
}

AUDIT_LOG_INDEX_MAPPING = {
    "dynamic": "strict",
    "properties": {
        "event_id": {"type": "keyword"},
        "event_type": {"type": "keyword"},
        "user_id": {"type": "keyword"},
        "api_key_id": {"type": "keyword"},
        "workspace_id": {"type": "keyword"},
        "resource_type": {"type": "keyword"},
        "resource_id": {"type": "keyword"},
        "action": {"type": "keyword"},
        "changes": {"type": "object", "enabled": False},
        "ip_address": {"type": "ip"},
        "user_agent": {"type": "text", "index": False},
        "request_id": {"type": "keyword"},
        "timestamp": {"type": "date"},
    },
}


class BaseRepository:
    """Base repository with common Elasticsearch operations."""

    def __init__(self, index_name: str | None = None):
        self._index_name = index_name
        self._logger = structlog.get_logger(self.__class__.__name__)

    @property
    def index_name(self) -> str:
        if self._index_name:
            return self._index_name
        return f"{settings.elasticsearch.index_prefix}{self._get_index_suffix()}"

    def _get_index_suffix(self) -> str:
        """Override to provide index suffix."""
        raise NotImplementedError

    def _get_client(self) -> AsyncElasticsearch:
        client = get_elasticsearch_client()
        if not client:
            raise RuntimeError("Elasticsearch client not initialized")
        return client

    async def index_document(self, doc_id: str, document: dict[str, Any]) -> bool:
        """Index a document."""
        client = self._get_client()
        try:
            response = await client.index(
                index=self.index_name,
                id=doc_id,
                document=document,
                refresh="wait_for",
            )
            return response.get("result") in ("created", "updated")
        except Exception as e:
            self._logger.error("index_document_failed", error=str(e), doc_id=doc_id)
            raise

    async def get_document(self, doc_id: str) -> dict[str, Any] | None:
        """Get a document by ID."""
        client = self._get_client()
        try:
            response = await client.get(index=self.index_name, id=doc_id)
            return response.get("_source")
        except Exception as e:
            if "not_found" in str(e).lower():
                return None
            self._logger.error("get_document_failed", error=str(e), doc_id=doc_id)
            raise

    async def update_document(self, doc_id: str, document: dict[str, Any]) -> bool:
        """Update a document."""
        client = self._get_client()
        try:
            response = await client.update(
                index=self.index_name,
                id=doc_id,
                doc=document,
                refresh="wait_for",
            )
            return response.get("result") == "updated"
        except Exception as e:
            self._logger.error("update_document_failed", error=str(e), doc_id=doc_id)
            raise

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        client = self._get_client()
        try:
            response = await client.delete(
                index=self.index_name,
                id=doc_id,
                refresh="wait_for",
            )
            return response.get("result") == "deleted"
        except Exception as e:
            if "not_found" in str(e).lower():
                return False
            self._logger.error("delete_document_failed", error=str(e), doc_id=doc_id)
            raise

    async def search(
        self,
        query: dict[str, Any],
        size: int = 50,
        from_: int = 0,
        sort: list[dict] | None = None,
        source_includes: list[str] | None = None,
    ) -> tuple[list[dict], int]:
        """Execute a search query."""
        client = self._get_client()
        try:
            body: dict[str, Any] = {"query": query, "size": size, "from": from_}
            if sort:
                body["sort"] = sort
            if source_includes:
                body["_source"] = source_includes

            response = await client.search(index=self.index_name, body=body)
            hits = response.get("hits", {})
            documents = [hit["_source"] for hit in hits.get("hits", [])]
            total = hits.get("total", {}).get("value", 0)
            return documents, total
        except Exception as e:
            self._logger.error("search_failed", error=str(e))
            raise

    async def count(self, query: dict[str, Any]) -> int:
        """Count documents matching query."""
        client = self._get_client()
        try:
            response = await client.count(index=self.index_name, body={"query": query})
            return response.get("count", 0)
        except Exception as e:
            self._logger.error("count_failed", error=str(e))
            raise
