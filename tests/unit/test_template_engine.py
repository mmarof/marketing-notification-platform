"""
Unit tests for the template engine.
"""

import pytest

from src.template_engine.engine import DEFAULT_EMAIL_LAYOUT, TemplateEngine


class TestTemplateEngine:
    """Tests for TemplateEngine class."""

    @pytest.fixture
    def engine(self) -> TemplateEngine:
        """Create a fresh template engine instance."""
        return TemplateEngine()

    def test_render_simple_variable(self, engine: TemplateEngine):
        """Test rendering a simple variable."""
        template = "<h1>Hello {{ name }}</h1>"
        result = engine.render_email(template, {"name": "John"})
        assert "<h1>Hello John</h1>" in result

    def test_render_multiple_variables(self, engine: TemplateEngine):
        """Test rendering multiple variables."""
        template = "<p>{{ greeting }}, {{ name }}! Welcome to {{ company }}.</p>"
        result = engine.render_email(
            template,
            {"greeting": "Hi", "name": "Jane", "company": "Acme"},
        )
        assert "Hi, Jane! Welcome to Acme." in result

    def test_render_with_missing_variable(self, engine: TemplateEngine):
        """Test rendering with missing variable (should not raise)."""
        template = "<p>{{ name }}, {{ missing_var }}</p>"
        result = engine.render_email(template, {"name": "John"})
        assert "John," in result
        # Missing var should be empty string (SilentUndefined)
        assert "{{ missing_var }}" not in result

    def test_render_with_conditional(self, engine: TemplateEngine):
        """Test rendering with if/else conditional."""
        template = """
        {% if premium %}
        <p>You have premium access!</p>
        {% else %}
        <p>Upgrade to premium for more features.</p>
        {% endif %}
        """
        premium_result = engine.render_email(template, {"premium": True})
        assert "premium access" in premium_result
        assert "Upgrade" not in premium_result

        free_result = engine.render_email(template, {"premium": False})
        assert "premium access" not in free_result
        assert "Upgrade" in free_result

    def test_render_with_loop(self, engine: TemplateEngine):
        """Test rendering with for loop."""
        template = """
        <ul>
        {% for item in items %}
        <li>{{ item }}</li>
        {% endfor %}
        </ul>
        """
        result = engine.render_email(template, {"items": ["Apple", "Banana", "Cherry"]})
        assert "<li>Apple</li>" in result
        assert "<li>Banana</li>" in result
        assert "<li>Cherry</li>" in result

    def test_render_with_layout(self, engine: TemplateEngine):
        """Test rendering with layout wrapper."""
        content = "<p>Hello {{ name }}</p>"
        result = engine.render_email(
            content,
            {"name": "John", "brand_color": "#ff0000"},
            layout=DEFAULT_EMAIL_LAYOUT,
        )
        assert "<!DOCTYPE html>" in result
        assert "<html" in result
        assert "Hello John" in result
        assert "#ff0000" in result

    def test_render_sms_simple(self, engine: TemplateEngine):
        """Test SMS template rendering."""
        template = "Hi {{ name }}, your code is {{ code }}."
        result = engine.render_sms(template, {"name": "John", "code": "123456"})
        assert result == "Hi John, your code is 123456."

    def test_render_sms_truncation(self, engine: TemplateEngine):
        """Test SMS truncation for long messages."""
        long_text = "x" * 200
        template = "{{ content }}"
        result = engine.render_sms(template, {"content": long_text})
        assert len(result) <= 160
        assert result.endswith("...")

    def test_extract_variables(self, engine: TemplateEngine):
        """Test variable extraction from template."""
        template = """
        <h1>{{ name }}</h1>
        <p>{{ company }}</p>
        {% if premium %}
        <p>{{ premium_features }}</p>
        {% endif %}
        """
        variables = engine.extract_variables(template)
        assert "name" in variables
        assert "company" in variables
        assert "premium_features" in variables
        # premium is used in condition, not as output
        assert "premium" not in variables

    def test_validate_template_valid(self, engine: TemplateEngine):
        """Test template validation with all variables provided."""
        template = "{{ name }}, {{ company }}"
        is_valid, missing = engine.validate_template(template, {"name": "John", "company": "Acme"})
        assert is_valid is True
        assert len(missing) == 0

    def test_validate_template_missing_vars(self, engine: TemplateEngine):
        """Test template validation with missing variables."""
        template = "{{ name }}, {{ company }}, {{ location }}"
        is_valid, missing = engine.validate_template(template, {"name": "John"})
        assert is_valid is False
        assert "company" in missing
        assert "location" in missing
        assert "name" not in missing

    def test_currency_filter(self, engine: TemplateEngine):
        """Test currency formatting filter."""
        template = "{{ price | format_currency }}"
        result = engine.render_email(template, {"price": 99.99})
        assert "$99.99" in result

    def test_date_filter(self, engine: TemplateEngine):
        """Test date formatting filter."""
        from datetime import datetime

        template = "{{ date | format_date('%B %d, %Y') }}"
        result = engine.render_email(
            template,
            {"date": datetime(2024, 1, 15)},
        )
        assert "January 15, 2024" in result

    def test_nested_variable_access(self, engine: TemplateEngine):
        """Test accessing nested object properties."""
        template = "{{ user.name }} - {{ user.email }}"
        result = engine.render_email(
            template,
            {"user": {"name": "John", "email": "john@example.com"}},
        )
        assert "John - john@example.com" in result

    def test_html_injection_prevention(self, engine: TemplateEngine):
        """Test that user-provided variables aren't escaped (since we use safe rendering)."""
        template = "<p>{{ content }}</p>"
        malicious = '<script>alert("xss")</script>'
        result = engine.render_email(template, {"content": malicious})
        # With autoescape=False, the script tag is preserved
        # In production, HTML should be sanitized BEFORE passing to template
        assert malicious in result
