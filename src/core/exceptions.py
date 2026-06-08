"""
Custom exception classes for the application.
Provides structured error handling across all layers.
"""

from typing import Any


class BaseApplicationError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str, details: Any = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class AuthenticationError(BaseApplicationError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(BaseApplicationError):
    """Raised when user lacks permission for an action."""

    pass


class NotFoundError(BaseApplicationError):
    """Raised when a requested resource is not found."""

    pass


class ValidationError(BaseApplicationError):
    """Raised when input validation fails."""

    pass


class RateLimitError(BaseApplicationError):
    """Raised when rate limit is exceeded."""

    def __init__(self, message: str, retry_after: int | None = None, details: Any = None):
        self.retry_after = retry_after
        super().__init__(message, details)


class ProviderError(BaseApplicationError):
    """Raised when an external provider (email/SMS) fails."""

    def __init__(
        self,
        message: str,
        provider: str,
        provider_code: str | None = None,
        retryable: bool = False,
        details: Any = None,
    ):
        self.provider = provider
        self.provider_code = provider_code
        self.retryable = retryable
        super().__init__(message, details)


class TemplateError(BaseApplicationError):
    """Raised when template rendering fails."""

    pass


class ElasticsearchError(BaseApplicationError):
    """Raised when Elasticsearch operations fail."""

    pass