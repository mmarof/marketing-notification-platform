"""
Unique ID generation utilities.
"""

import secrets
import string
from datetime import datetime
from uuid import UUID, uuid4


def generate_notification_id() -> UUID:
    """Generate a unique notification ID."""
    return uuid4()


def generate_campaign_id() -> str:
    """Generate a human-readable campaign ID."""
    timestamp = datetime.utcnow().strftime("%Y%m%d")
    random_suffix = secrets.token_hex(4).upper()
    return f"cmp_{timestamp}_{random_suffix}"


def generate_api_key() -> str:
    """Generate a secure API key."""
    prefix = "mnp"
    random_part = secrets.token_urlsafe(32)
    return f"{prefix}_{random_part}"


def generate_short_id(length: int = 8) -> str:
    """Generate a short random ID for URLs."""
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_message_id() -> str:
    """Generate a unique message ID for provider tracking."""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_part = secrets.token_hex(8)
    return f"msg_{timestamp}_{random_part}"
