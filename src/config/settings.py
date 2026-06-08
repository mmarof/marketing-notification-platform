"""
Application configuration using pydantic-settings.
Supports environment variables and .env file loading.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ElasticsearchSettings(BaseSettings):
    """Elasticsearch connection configuration."""

    host: str = Field(default="http://localhost:9200", alias="ELASTICSEARCH_HOST")
    username: str = Field(default="elastic", alias="ELASTICSEARCH_USERNAME")
    password: SecretStr = Field(default=SecretStr("changeme"), alias="ELASTICSEARCH_PASSWORD")
    index_prefix: str = Field(default="mnp_", alias="ELASTICSEARCH_INDEX_PREFIX")
    request_timeout: int = Field(default=30, alias="ELASTICSEARCH_REQUEST_TIMEOUT")
    max_retries: int = Field(default=3, alias="ELASTICSEARCH_MAX_RETRIES")
    verify_certs: bool = Field(default=False, alias="ELASTICSEARCH_VERIFY_CERTS")

    model_config = SettingsConfigDict(env_prefix="ELASTICSEARCH_")


class RedisSettings(BaseSettings):
    """Redis connection configuration."""

    host: str = Field(default="localhost", alias="REDIS_HOST")
    port: int = Field(default=6379, alias="REDIS_PORT")
    db: int = Field(default=0, alias="REDIS_DB")
    password: SecretStr | None = Field(default=None, alias="REDIS_PASSWORD")
    max_connections: int = Field(default=20, alias="REDIS_MAX_CONNECTIONS")
    socket_timeout: int = Field(default=5, alias="REDIS_SOCKET_TIMEOUT")
    socket_connect_timeout: int = Field(default=3, alias="REDIS_SOCKET_CONNECT_TIMEOUT")

    @property
    def url(self) -> str:
        pwd = f":{self.password.get_secret_value()}@" if self.password else ""
        return f"redis://{pwd}{self.host}:{self.port}/{self.db}"

    model_config = SettingsConfigDict(env_prefix="REDIS_")


class SMTPSettings(BaseSettings):
    """SMTP email provider configuration."""

    host: str = Field(default="localhost", alias="SMTP_HOST")
    port: int = Field(default=587, alias="SMTP_PORT")
    username: str | None = Field(default=None, alias="SMTP_USERNAME")
    password: SecretStr | None = Field(default=None, alias="SMTP_PASSWORD")
    use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    use_ssl: bool = Field(default=False, alias="SMTP_USE_SSL")
    from_email: str = Field(default="noreply@example.com", alias="SMTP_FROM_EMAIL")
    from_name: str = Field(default="Marketing Platform", alias="SMTP_FROM_NAME")
    timeout: int = Field(default=30, alias="SMTP_TIMEOUT")
    max_connections: int = Field(default=10, alias="SMTP_MAX_CONNECTIONS")

    model_config = SettingsConfigDict(env_prefix="SMTP_")


class TwilioSettings(BaseSettings):
    """Twilio SMS provider configuration."""

    account_sid: SecretStr = Field(default=SecretStr(""), alias="TWILIO_ACCOUNT_SID")
    auth_token: SecretStr = Field(default=SecretStr(""), alias="TWILIO_AUTH_TOKEN")
    phone_number: str = Field(default="", alias="TWILIO_PHONE_NUMBER")
    timeout: int = Field(default=30, alias="TWILIO_TIMEOUT")

    @property
    def is_configured(self) -> bool:
        return bool(self.account_sid.get_secret_value() and self.auth_token.get_secret_value())

    model_config = SettingsConfigDict(env_prefix="TWILIO_")


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""

    enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    requests_per_minute: int = Field(default=100, alias="RATE_LIMIT_REQUESTS_PER_MINUTE")
    requests_per_hour: int = Field(default=1000, alias="RATE_LIMIT_REQUESTS_PER_HOUR")
    burst_limit: int = Field(default=20, alias="RATE_LIMIT_BURST_LIMIT")

    model_config = SettingsConfigDict(env_prefix="RATE_LIMIT_")


class Settings(BaseSettings):
    """Main application settings."""

    # Application
    app_name: str = Field(default="MarketingNotificationPlatform", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    app_debug: bool = Field(default=True, alias="APP_DEBUG")
    app_version: str = Field(default="1.0.0", alias="APP_VERSION")
    secret_key: SecretStr = Field(
        default=SecretKey("change-me-in-production"), alias="SECRET_KEY"
    )

    # Server
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    workers: int = Field(default=4, alias="WORKERS")

    # Sub-configurations
    elasticsearch: ElasticsearchSettings = ElasticsearchSettings()
    redis: RedisSettings = RedisSettings()
    smtp: SMTPSettings = SMTPSettings()
    twilio: TwilioSettings = TwilioSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")

    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str | SecretStr) -> SecretStr:
        if isinstance(v, SecretStr):
            return v
        if len(v) < 32 and cls.app_env != "development":
            raise ValueError("SECRET_KEY must be at least 32 characters in production")
        return SecretStr(v)

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def use_mock_providers(self) -> bool:
        return self.is_development and not self.smtp.host

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()