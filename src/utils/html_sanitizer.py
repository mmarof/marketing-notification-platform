"""
HTML sanitization utilities for email content.
Prevents XSS and ensures email client compatibility.
"""

import re
from typing import Any

import bleach
from bleach.sanitizer import ALLOWED_TAGS, ALLOWED_ATTRIBUTES

# Extended allowed tags for email HTML
EMAIL_ALLOWED_TAGS = set(ALLOWED_TAGS) | {
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "style",
    "font",
    "center",
    "hr",
    "br",
    "span",
    "div",
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    "a",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "blockquote",
    "pre",
    "code",
}

EMAIL_ALLOWED_ATTRIBUTES = dict(ALLOWED_ATTRIBUTES)
EMAIL_ALLOWED_ATTRIBUTES.update({
    "img": ["src", "alt", "width", "height", "style", "border"],
    "td": ["colspan", "rowspan", "width", "height", "style", "align", "valign"],
    "th": ["colspan", "rowspan", "width", "height", "style", "align", "valign"],
    "table": ["width", "height", "style", "cellpadding", "cellspacing", "border", "align"],
    "tr": ["style", "align", "valign"],
    "a": ["href", "style", "target", "rel"],
    "font": ["face", "size", "color", "style"],
    "div": ["style", "class", "align"],
    "p": ["style", "class", "align"],
    "span": ["style", "class"],
    "h1": ["style", "class", "align"],
    "h2": ["style", "class", "align"],
    "h3": ["style", "class", "align"],
    "h4": ["style", "class", "align"],
    "h5": ["style", "class", "align"],
    "h6": ["style", "class", "align"],
    "ul": ["style", "class", "type"],
    "ol": ["style", "class", "type", "start"],
    "li": ["style", "class"],
    "blockquote": ["style", "cite"],
    "pre": ["style"],
    "code": ["style", "class"],
    "hr": ["style", "size", "width", "noshade", "color"],
})


def sanitize_html(html_content: str) -> str:
    """
    Sanitize HTML content for email use.
    Removes dangerous elements while preserving email-safe formatting.
    """
    if not html_content:
        return ""

    # Sanitize with bleach
    sanitized = bleach.clean(
        html_content,
        tags=EMAIL_ALLOWED_TAGS,
        attributes=EMAIL_ALLOWED_ATTRIBUTES,
        styles=True,
        strip=False,
    )

    # Additional security: remove javascript: URLs
    sanitized = re.sub(
        r'href\s*=\s*["\']javascript:[^"\']*["\']',
        'href="#"',
        sanitized,
        flags=re.IGNORECASE,
    )

    # Remove data: URLs in src attributes
    sanitized = re.sub(
        r'src\s*=\s*["\']data:[^"\']*["\']',
        'src=""',
        sanitized,
        flags=re.IGNORECASE,
    )

    # Remove on* event handlers
    sanitized = re.sub(
        r'\bon\w+\s*=\s*["\'][^"\']*["\']',
        '',
        sanitized,
        flags=re.IGNORECASE,
    )

    return sanitized


def extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML content."""
    if not html_content:
        return ""

    # Remove style blocks
    text = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL | re.IGNORECASE)

    # Remove script blocks
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # Replace common block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|h[1-6]|li|tr|blockquote)[^>]*>", "\n", text, flags=re.IGNORECASE)

    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)

    # Decode HTML entities
    import html as html_module
    text = html_module.unescape(text)

    # Clean up whitespace
    text = re.sub(r"\n\s*\n", "\n\n", text)
    text = text.strip()

    return text


def validate_email_html(html_content: str) -> dict[str, Any]:
    """
    Validate HTML content for email compatibility.
    Returns a dict with validation results.
    """
    issues: list[str] = []
    warnings: list[str] = []

    if not html_content:
        return {"valid": False, "issues": ["Empty content"], "warnings": warnings}

    # Check for DOCTYPE
    if "<!DOCTYPE" not in html_content.upper():
        warnings.append("Missing DOCTYPE declaration")

    # Check for html/body tags
    if "<html" not in html_content.lower():
        warnings.append("Missing <html> tag")

    if "<body" not in html_content.lower():
        warnings.append("Missing <body> tag")

    # Check for potentially unsupported CSS
    unsupported_css = [
        "position:", "float:", "display:flex", "display:grid",
        "box-shadow", "border-radius", "transform:",
    ]
    for css_prop in unsupported_css:
        if css_prop.lower() in html_content.lower():
            warnings.append(f"CSS property '{css_prop}' may not be supported in all email clients")

    # Check for external resources
    external_urls = re.findall(r'(?:src|href)=["\']https?://[^"\']+["\']', html_content)
    if len(external_urls) > 10:
        warnings.append(f"Many external resources ({len(external_urls)}). Some may be blocked.")

    # Check for very large content
    if len(html_content) > 100000:
        issues.append("HTML content exceeds 100KB limit")

    # Check for unclosed tags (simple check)
    open_tags = len(re.findall(r"<([a-z][a-z0-9]*)[^>]*>(?!</)", html_content, re.IGNORECASE))
    close_tags = len(re.findall(r"</([a-z][a-z0-9]*)>", html_content, re.IGNORECASE))
    # Self-closing tags don't need closing
    self_closing = len(re.findall(r"<(img|br|hr|input|meta|link)[^>]*/?>", html_content, re.IGNORECASE))
    if abs(open_tags - close_tags - self_closing) > 2:  # Allow some margin
        warnings.append("Possible unclosed HTML tags")

    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "size_bytes": len(html_content.encode("utf-8")),
        "external_resources": len(external_urls),
    }