"""
Input Sanitization
==================
Server-side sanitization for all string fields stored in the database.
Uses bleach (already installed) to strip disallowed HTML tags/attributes.
"""
import re
import bleach

# No HTML allowed in name/title/description fields
_SAFE_TAGS: list = []
_SAFE_ATTRS: dict = {}


def sanitize_text(value: str) -> str:
    """
    Strip all HTML tags and dangerous content from a plain-text string.
    Use for: title, name, description, label, username, etc.
    """
    if not value:
        return value
    return bleach.clean(value, tags=_SAFE_TAGS, attributes=_SAFE_ATTRS, strip=True).strip()


# Tags allowed in rich-text / markdown-rendered fields (e.g. QR description)
_RICH_TAGS = ['b', 'i', 'em', 'strong', 'u', 's', 'br', 'p', 'ul', 'ol', 'li', 'a']
_RICH_ATTRS = {'a': ['href', 'title', 'rel']}


def sanitize_rich(value: str) -> str:
    """
    Strip dangerous HTML but keep basic formatting tags.
    Use for: multi-line description fields that allow minimal markup.
    """
    if not value:
        return value
    return bleach.clean(value, tags=_RICH_TAGS, attributes=_RICH_ATTRS, strip=True).strip()


# ─── Stored XSS protection for AI / user-provided full HTML pages ────────────

def strip_dangerous_html(html: str) -> str:
    """
    Sanitize full HTML page content before storing in the database.
    Removes external script sources and dangerous event handlers while
    preserving inline scripts needed for legitimate page animations.

    Use for: AI-generated landing page HTML and user-submitted custom_html.
    """
    if not html:
        return html
    # Remove <script src="..."> tags (external scripts loaded from remote URLs)
    html = re.sub(
        r'<script[^>]+src\s*=\s*["\'][^"\']*["\'][^>]*>.*?</script>',
        '',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    # Block javascript: / vbscript: / data: in href, src, action, formaction
    html = re.sub(
        r'((?:href|src|action|formaction)\s*=\s*["\'])\s*(?:javascript|vbscript|data)\s*:[^"\']*(["\'])',
        r'\1#\2',
        html,
        flags=re.IGNORECASE,
    )
    # Remove on* event handlers (onclick=, onload=, onerror=, etc.)
    html = re.sub(
        r'\s+on[a-z]+\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)',
        '',
        html,
        flags=re.IGNORECASE,
    )
    return html
