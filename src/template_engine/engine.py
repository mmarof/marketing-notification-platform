"""
Jinja2 template engine for notification rendering.
Supports email templates with layouts and SMS templates.
"""

import re
from pathlib import Path
from typing import Any

import structlog
from jinja2 import (
    BaseLoader,
    Environment,
    TemplateNotFound,
    Undefined,
)

from src.config.settings import get_settings
from src.core.exceptions import TemplateError

logger = structlog.get_logger(__name__)
settings = get_settings()


class SilentUndefined(Undefined):
    """Undefined that returns empty string instead of raising error."""

    def __str__(self) -> str:
        return ""

    def __iter__(self):
        return iter([])

    def __bool__(self) -> bool:
        return False


class DatabaseTemplateLoader(BaseLoader):
    """
    Template loader that loads templates from Elasticsearch.
    Falls back to file system for built-in templates.
    """

    def __init__(self) -> None:
        self._file_templates_path = Path(__file__).parent / "email"
        self._cache: dict[str, str] = {}

    async def load_from_database(self, template_id: str, user_id: str) -> str | None:
        """Load template content from Elasticsearch."""
        from src.repositories.base import get_elasticsearch_client

        client = get_elasticsearch_client()
        if not client:
            return None

        try:
            response = await client.get(
                index=f"{settings.elasticsearch.index_prefix}templates",
                id=template_id,
            )
            doc = response.get("_source", {})
            if doc.get("user_id") == user_id:
                return doc.get("content")
        except Exception:
            pass
        return None

    def get_source(self, environment: Environment, template: str) -> tuple[str, str, callable]:
        """Jinja2 loader interface - loads from file system."""
        # Try file system first
        template_path = self._file_templates_path / template
        if template_path.exists():
            with open(template_path, "r", encoding="utf-8") as f:
                source = f.read()
            return source, str(template_path), lambda: source

        raise TemplateNotFound(template)


class TemplateEngine:
    """
    Template rendering engine.
    Supports email (HTML with layouts) and SMS templates.
    """

    def __init__(self) -> None:
        self._env = Environment(
            loader=DatabaseTemplateLoader(),
            undefined=SilentUndefined,
            autoescape=False,  # HTML is pre-sanitized
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=False,
        )

        # Add custom filters
        self._env.filters["default"] = self._default_filter
        self._env.filters["truncate_html"] = self._truncate_html_filter
        self._env.filters["format_currency"] = self._format_currency_filter
        self._env.filters["format_date"] = self._format_date_filter

    @staticmethod
    def _default_filter(value: Any, default_value: str = "") -> str:
        """Default filter that handles None gracefully."""
        if value is None:
            return default_value
        return str(value)

    @staticmethod
    def _truncate_html_filter(html: str, length: int = 100) -> str:
        """Truncate HTML to specified length, preserving tags."""
        # Simple implementation - strip tags for truncation
        text = re.sub(r"<[^>]+>", "", html)
        if len(text) <= length:
            return html
        return text[:length] + "..."

    @staticmethod
    def _format_currency_filter(value: Any, currency: str = "USD") -> str:
        """Format a number as currency."""
        try:
            amount = float(value)
            symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
            symbol = symbols.get(currency, currency)
            return f"{symbol}{amount:,.2f}"
        except (ValueError, TypeError):
            return str(value)

    @staticmethod
    def _format_date_filter(value: Any, format_str: str = "%Y-%m-%d") -> str:
        """Format a datetime value."""
        if value is None:
            return ""
        from datetime import datetime

        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        if isinstance(value, datetime):
            return value.strftime(format_str)
        return str(value)

    def render_email(
        self,
        template_content: str,
        variables: dict[str, Any],
        layout: str | None = None,
    ) -> str:
        """
        Render an email template with variables.
        Optionally wraps in a layout template.
        """
        try:
            # Render the inner template
            inner_template = self._env.from_string(template_content)
            rendered_content = inner_template.render(**variables)

            # Wrap in layout if specified
            if layout:
                layout_template = self._env.from_string(layout)
                rendered_content = layout_template.render(
                    content=rendered_content,
                    **variables,
                )

            return rendered_content

        except Exception as e:
            logger.error(
                "email_render_failed",
                error=str(e),
                template_length=len(template_content),
            )
            raise TemplateError(f"Failed to render email template: {str(e)}")

    def render_sms(self, template_content: str, variables: dict[str, Any]) -> str:
        """Render an SMS template with variable substitution."""
        try:
            # SMS uses simple {{ variable }} syntax
            template = self._env.from_string(template_content)
            rendered = template.render(**variables)

            # Truncate to SMS length limit (160 for standard, 70 for Unicode)
            if len(rendered) > 160:
                logger.warning(
                    "sms_truncated",
                    original_length=len(rendered),
                )
                rendered = rendered[:157] + "..."

            return rendered

        except Exception as e:
            logger.error("sms_render_failed", error=str(e))
            raise TemplateError(f"Failed to render SMS template: {str(e)}")

    def extract_variables(self, template_content: str) -> list[str]:
        """Extract variable names from a template."""
        pattern = r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}"
        variables = set(re.findall(pattern, template_content))
        return sorted(variables)

    def validate_template(self, template_content: str, variables: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate a template against provided variables.
        Returns (is_valid, missing_variables).
        """
        required_vars = self.extract_variables(template_content)
        provided_vars = set(variables.keys())
        missing = [v for v in required_vars if v not in provided_vars]
        return len(missing) == 0, missing


# Default email layout
DEFAULT_EMAIL_LAYOUT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ subject | default('Notification') }}</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 600px;
            margin: 0 auto;
            background-color: #ffffff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header {
            background-color: {{ brand_color | default('#2563eb') }};
            padding: 30px;
            text-align: center;
        }
        .header img {
            max-height: 60px;
            margin-bottom: 10px;
        }
        .header h1 {
            color: white;
            margin: 0;
            font-size: 24px;
        }
        .body {
            padding: 30px;
        }
        .footer {
            background-color: #f8f9fa;
            padding: 20px 30px;
            text-align: center;
            font-size: 12px;
            color: #666;
        }
        .btn {
            display: inline-block;
            padding: 12px 30px;
            background-color: {{ cta_color | default('#2563eb') }};
            color: white !important;
            text-decoration: none;
            border-radius: 6px;
            font-weight: 600;
            margin: 15px 0;
        }
        .btn:hover {
            background-color: {{ cta_color_hover | default('#1d4ed8') }};
        }
    </style>
</head>
<body>
    <div class="container">
        {% if logo_url %}
        <div class="header">
            <img src="{{ logo_url }}" alt="Logo">
        </div>
        {% endif %}
        <div class="body">
            {{ content | safe }}
        </div>
        <div class="footer">
            <p>© {{ year | default('2024') }} {{ company_name | default('Company') }}. All rights reserved.</p>
            <p>
                <a href="{{ unsubscribe_url | default('#') }}" style="color: #666;">Unsubscribe</a> |
                <a href="{{ preferences_url | default('#') }}" style="color: #666;">Email Preferences</a>
            </p>
        </div>
    </div>
</body>
</html>
"""


# Singleton instance
template_engine = TemplateEngine()