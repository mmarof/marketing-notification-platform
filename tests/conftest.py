"""
Pytest configuration and shared fixtures.
Fixed version with proper async handling and ES patching.
"""

import asyncio
import os
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch

# Set environment variables BEFORE importing settings
os.environ.setdefault("ELASTICSEARCH_HOST", os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200"))
os.environ.setdefault("ELASTICSEARCH_USERNAME", "elastic")
os.environ.setdefault("ELASTICSEARCH_PASSWORD", "changeme")
os.environ.setdefault("ELASTICSEARCH_INDEX_PREFIX", "test_mnp_")
os.environ.setdefault("REDIS_HOST", os.getenv("REDIS_HOST", "localhost"))
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("SMTP_HOST", "")
os.environ.setdefault("TWILIO_ACCOUNT_SID", "")
os.environ.setdefault("TWILIO_AUTH_TOKEN", "")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("APP_DEBUG", "true")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-purposes-only-minimum-32")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

from src.config.settings import get_settings, Settings

# Force reload settings with test values
get_settings.cache_clear()

# Now get the test settings
TEST_SETTINGS = get_settings()

# Ensure test index prefix
TEST_SETTINGS.elasticsearch.index_prefix = "test_mnp_"
TEST_SETTINGS.rate_limit.enabled = False

TEST_INDEX_PREFIX = "test_mnp_"


@pytest.fixture(scope="session")
def event_loop_policy():
    """Use default event loop policy."""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for the test session."""
    policy = asyncio.DefaultEventLoopPolicy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def settings():
    """Get test settings."""
    return TEST_SETTINGS


@pytest_asyncio.fixture(scope="session")
async def es_client() -> AsyncGenerator[AsyncElasticsearch, None]:
    """
    Create and yield Elasticsearch client for testing.
    Waits for ES to be ready before yielding.
    """
    es_host = os.environ.get("ELASTICSEARCH_HOST", "http://localhost:9200")
    es_user = os.environ.get("ELASTICSEARCH_USERNAME", "elastic")
    es_pass = os.environ.get("ELASTICSEARCH_PASSWORD", "changeme")

    client = AsyncElasticsearch(
        hosts=[es_host],
        basic_auth=(es_user, es_pass),
        request_timeout=30,
        verify_certs=False,
        ssl_show_warn=False,
    )

    # Wait for Elasticsearch to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            await client.ping()
            break
        except Exception:
            if i == max_retries - 1:
                pytest.skip(f"Elasticsearch not available at {es_host}")
            await asyncio.sleep(1)

    yield client

    # Cleanup all test indices at end of session
    try:
        await client.indices.delete(index=f"{TEST_INDEX_PREFIX}*", ignore_unavailable=True)
    except Exception:
        pass

    await client.close()


@pytest_asyncio.fixture
async def es_index(es_client: AsyncElasticsearch):
    """
    Create fresh test indices before each test and cleanup after.
    This fixture MUST be used by integration tests that write to ES.
    """
    from src.repositories.base import (
        API_KEY_INDEX_MAPPING,
        AUDIT_LOG_INDEX_MAPPING,
        NOTIFICATION_INDEX_MAPPING,
        TEMPLATE_INDEX_MAPPING,
    )

    indices_to_create = {
        f"{TEST_INDEX_PREFIX}notifications": NOTIFICATION_INDEX_MAPPING,
        f"{TEST_INDEX_PREFIX}api_keys": API_KEY_INDEX_MAPPING,
        f"{TEST_INDEX_PREFIX}templates": TEMPLATE_INDEX_MAPPING,
        f"{TEST_INDEX_PREFIX}audit_logs": AUDIT_LOG_INDEX_MAPPING,
    }

    # Delete existing indices first (clean slate)
    for index_name in indices_to_create:
        try:
            await es_client.indices.delete(index=index_name, ignore_unavailable=True)
        except Exception:
            pass

    # Create indices with mappings
    for index_name, mapping in indices_to_create.items():
        try:
            await es_client.indices.create(
                index=index_name,
                body={
                    "mappings": mapping,
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                        "refresh_interval": "1ms",
                    },
                },
            )
        except Exception as e:
            pytest.fail(f"Failed to create index {index_name}: {e}")

    # Wait for indices to be ready
    await es_client.indices.refresh(index=f"{TEST_INDEX_PREFIX}*")

    yield es_client

    # Cleanup after each test
    for index_name in indices_to_create:
        try:
            await es_client.indices.delete(index=index_name, ignore_unavailable=True)
        except Exception:
            pass


@pytest.fixture
def patch_elasticsearch(es_client: AsyncElasticsearch):
    """
    Properly patch all Elasticsearch client access points.
    Use this fixture in tests that need ES access through repositories.
    """
    patches = []

    # Patch the global client in base repository
    p1 = patch("src.repositories.base._elasticsearch_client", es_client)
    patches.append(p1)

    # Patch the getter function
    p2 = patch("src.repositories.base.get_elasticsearch_client", return_value=es_client)
    patches.append(p2)

    # Patch settings to use test index prefix
    p3 = patch("src.repositories.base.settings", TEST_SETTINGS)
    patches.append(p3)

    # Start all patches
    mocks = [p.start() for p in patches]

    yield es_client

    # Stop all patches in reverse order
    for m in reversed(mocks):
        m.stop()


@pytest.fixture
def patch_rate_limiter():
    """Patch rate limiter to always allow requests."""
    mock_limiter = MagicMock()
    mock_limiter.check_rate_limit = AsyncMock(return_value=(True, None))

    with patch("src.core.dependencies.rate_limiter", mock_limiter):
        with patch("src.core.rate_limiter.RateLimiter", return_value=mock_limiter):
            yield mock_limiter


@pytest.fixture
def sample_user_id() -> str:
    """Generate a consistent sample user ID."""
    return "test_user_abc123"


@pytest.fixture
def sample_workspace_id() -> str:
    """Generate a consistent sample workspace ID."""
    return "test_workspace_xyz789"


@pytest.fixture
def sample_api_key_id() -> uuid4:
    """Generate a sample API key ID."""
    return uuid4()


@pytest.fixture
def sample_template_id() -> uuid4:
    """Generate a sample template ID."""
    return uuid4()


@pytest.fixture
def sample_raw_api_key() -> str:
    """Generate a raw API key string for testing."""
    return "mnp_testapikey_abcd1234efgh5678ijkl9012mnop3456"


@pytest.fixture
def tenant_context(sample_user_id, sample_api_key_id, sample_workspace_id):
    """Create a sample tenant context for service-level tests."""
    from src.schemas.api_keys import ApiKeyContext

    return ApiKeyContext(
        api_key_id=sample_api_key_id,
        user_id=sample_user_id,
        name="Test Key",
        permissions=["send_notifications", "view_analytics", "manage_templates"],
        workspace_id=sample_workspace_id,
        is_active=True,
    )


@pytest_asyncio.fixture
async def create_test_api_key(
    es_client: AsyncElasticsearch,
    sample_user_id: str,
    sample_api_key_id: uuid4,
    sample_raw_api_key: str,
) -> dict:
    """
    Create a test API key in Elasticsearch.
    Returns headers dict ready for HTTP requests.
    """
    import bcrypt

    key_hash = bcrypt.hashpw(sample_raw_api_key.encode(), bcrypt.gensalt()).decode()
    key_prefix = sample_raw_api_key[:8] + "..."

    api_key_doc = {
        "api_key_id": str(sample_api_key_id),
        "user_id": sample_user_id,
        "name": "Test API Key",
        "permissions": ["send_notifications", "view_analytics", "manage_templates"],
        "key_hash": key_hash,
        "key_prefix": key_prefix,
        "workspace_id": None,
        "is_active": True,
        "expires_at": None,
        "last_used_at": None,
        "created_at": datetime.utcnow().isoformat(),
        "metadata": {},
    }

    await es_client.index(
        index=f"{TEST_INDEX_PREFIX}api_keys",
        id=str(sample_api_key_id),
        document=api_key_doc,
        refresh="wait_for",
    )

    return {"X-API-Key": sample_raw_api_key}


@pytest.fixture
def sample_email_template_content() -> str:
    """Sample email template content."""
    return """
    <h1>Hello {{ name }},</h1>
    <p>Welcome to {{ company }}!</p>
    <p>Your account has been created successfully.</p>
    {% if cta_url %}
    <a href="{{ cta_url }}" style="padding: 12px 24px; background: #2563eb; color: white;">
        Get Started
    </a>
    {% endif %}
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
