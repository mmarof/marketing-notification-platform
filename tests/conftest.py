"""
Pytest configuration and shared fixtures.
"""

import os

# Force test index prefix before any app imports
os.environ["ELASTICSEARCH_INDEX_PREFIX"] = "test_mnp_"
os.environ["SMTP_HOST"] = ""
os.environ["TWILIO_ACCOUNT_SID"] = ""
os.environ["TWILIO_AUTH_TOKEN"] = ""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch

from src.config.settings import Settings
from src.core.middleware import api_key_id_ctx, request_id_ctx, user_id_ctx, workspace_id_ctx

# Override settings for testing
TEST_SETTINGS = Settings(
    app_name="TestApp",
    app_env="development",
    app_debug=True,
    app_version="test",
    secret_key="test-secret-key-for-testing-purposes-only-min-32-chars",
    elasticsearch__host=os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200"),
    elasticsearch__username="elastic",
    elasticsearch__password="changeme",
    elasticsearch__index_prefix="test_mnp_",
    redis__host=os.getenv("REDIS_HOST", "localhost"),
    redis__port=6379,
    smtp__host="",  # Use mock provider
    twilio__account_sid="",
    twilio__auth_token="",
)


@pytest.fixture
def test_settings():
    """Return the test settings for patching."""
    return TEST_SETTINGS


@pytest.fixture(scope="session")
def settings():
    """Get test settings."""
    return TEST_SETTINGS


@pytest_asyncio.fixture(scope="function")
async def es_client() -> AsyncGenerator[AsyncElasticsearch, None]:
    """Create and yield Elasticsearch client for testing."""
    client = AsyncElasticsearch(
        hosts=[TEST_SETTINGS.elasticsearch.host],
        basic_auth=(
            TEST_SETTINGS.elasticsearch.username,
            TEST_SETTINGS.elasticsearch.password.get_secret_value(),
        ),
        request_timeout=30,
        verify_certs=False,
        # Force compatibility with Elasticsearch 8.x
        headers={"accept": "application/vnd.elasticsearch+json; compatible-with=8"},
    )

    # Wait for Elasticsearch to be ready
    for _ in range(30):
        try:
            await client.ping()
            break
        except Exception:
            await asyncio.sleep(1)
    else:
        pytest.skip("Elasticsearch not available")

    yield client

    # Cleanup test indices
    with contextlib.suppress(Exception):
        await client.indices.delete(index="test_mnp_*")

    await client.close()


@pytest_asyncio.fixture
async def es_index(es_client: AsyncElasticsearch):
    """Create test indices before each test and cleanup after."""
    prefix = "test_mnp_"

    # Create indices with same mappings as production
    from src.repositories.base import (
        API_KEY_INDEX_MAPPING,
        NOTIFICATION_INDEX_MAPPING,
        TEMPLATE_INDEX_MAPPING,
    )

    for suffix, mapping in [
        ("notifications", NOTIFICATION_INDEX_MAPPING),
        ("api_keys", API_KEY_INDEX_MAPPING),
        ("templates", TEMPLATE_INDEX_MAPPING),
    ]:
        index_name = f"{prefix}{suffix}"
        if await es_client.indices.exists(index=index_name):
            await es_client.indices.delete(index=index_name)
        await es_client.indices.create(
            index=index_name,
            body={"mappings": mapping, "settings": {"number_of_shards": 1, "number_of_replicas": 0}},
        )

    yield

    # Cleanup
    for suffix in ["notifications", "api_keys", "templates"]:
        with contextlib.suppress(Exception):
            await es_client.indices.delete(index=f"{prefix}{suffix}")


@pytest.fixture
def mock_elasticsearch_client(es_client: AsyncElasticsearch):
    """Patch the global Elasticsearch client."""
    with (
        patch("src.repositories.base.get_elasticsearch_client", return_value=es_client),
        patch("src.repositories.base._elasticsearch_client", es_client),
    ):
        yield es_client


@pytest.fixture
def sample_user_id() -> str:
    """Generate a sample user ID."""
    return "user_test_12345"


@pytest.fixture
def sample_workspace_id() -> str:
    """Generate a sample workspace ID."""
    return "workspace_test_12345"


@pytest.fixture
def sample_api_key_id() -> uuid4:
    """Generate a sample API key ID."""
    return uuid4()


@pytest.fixture
def sample_template_id() -> uuid4:
    """Generate a sample template ID."""
    return uuid4()


@pytest.fixture
def tenant_context(sample_user_id, sample_api_key_id, sample_workspace_id):
    """Create a sample tenant context."""
    from src.schemas.api_keys import ApiKeyContext

    return ApiKeyContext(
        api_key_id=sample_api_key_id,
        user_id=sample_user_id,
        name="Test Key",
        permissions=["send_notifications", "view_analytics"],
        workspace_id=sample_workspace_id,
        is_active=True,
    )


@pytest.fixture
def set_context_vars(sample_user_id, sample_api_key_id, sample_workspace_id):
    """Set context variables for testing."""
    request_id_ctx.set("test-request-123")
    user_id_ctx.set(sample_user_id)
    api_key_id_ctx.set(str(sample_api_key_id))
    workspace_id_ctx.set(sample_workspace_id)
    yield
    request_id_ctx.set("")
    user_id_ctx.set("")
    api_key_id_ctx.set("")
    workspace_id_ctx.set(None)


@pytest.fixture
def sample_email_template_content() -> str:
    """Sample email template content."""
    return """
    <h1>Hello {{ name }},</h1>
    <p>Welcome to {{ company }}!</p>
    <p>Your account has been created successfully.</p>
    {% if cta_url %}
    <a href="{{ cta_url }}" style="padding: 12px 24px; background: #2563eb; color: white; text-decoration: none; border-radius: 6px;">
        Get Started
    </a>
    {% endif %}
    <p>Thanks,<br>The {{ company }} Team</p>
    """


@pytest.fixture
def sample_sms_template_content() -> str:
    """Sample SMS template content."""
    return "Hi {{ name }}, your {{ company }} verification code is {{ code }}. Valid for {{ validity }} mins."


@pytest.fixture
def sample_notification_request(sample_template_id) -> dict:
    """Sample notification request payload."""
    return {
        "type": "email",
        "recipients": ["user1@example.com", "user2@example.com"],
        "template_id": str(sample_template_id),
        "variables": {
            "name": "John",
            "company": "Acme Inc",
            "cta_url": "https://example.com/get-started",
        },
    }


@pytest.fixture
def sample_sms_notification_request() -> dict:
    """Sample SMS notification request payload."""
    return {
        "type": "sms",
        "recipients": ["+1234567890", "+0987654321"],
        "sms_content": "Hi {{ name }}, your code is {{ code }}.",
        "variables": {
            "name": "John",
            "code": "123456",
        },
    }
