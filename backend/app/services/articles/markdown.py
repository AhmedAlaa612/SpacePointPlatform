"""Markdown → sanitized HTML for website articles (Step 5).

Contributors author in Markdown; the portal preview and the public site
both render `content_html`, never raw Markdown. bleach strips everything
outside the allowlist (scripts, iframes, event handlers), so stored HTML
is safe to inject with Astro's set:html.
"""

import re
import unicodedata

import bleach
import markdown

_ALLOWED_TAGS = set(bleach.sanitizer.ALLOWED_TAGS) | {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "p",
    "pre",
    "img",
    "hr",
    "br",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "blockquote",
    "del",
    "s",
    "sub",
    "sup",
    "u",
}

_ALLOWED_ATTRIBUTES = {
    **bleach.sanitizer.ALLOWED_ATTRIBUTES,
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
}


def _normalize_gfm_markdown(text: str) -> str:
    """Ensure GFM-style lists and fenced blocks without a preceding blank line
    parse identically to client-side `marked` (e.g. when pasted from Notion/Docs)."""
    text = (text or "").replace("\r\n", "\n")
    # Convert ~~strikethrough~~ (outside inline code) to <del>...</del>
    text = re.sub(r"~~([^~\n]+?)~~", r"<del>\1</del>", text)
    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence and out and out[-1].strip() != "":
                out.append("")
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence and out:
            prev = out[-1].strip()
            is_list_item = bool(re.match(r"^([-*+]|\d+\.)\s+", stripped))
            prev_is_list = bool(re.match(r"^([-*+]|\d+\.)\s+", prev))
            if is_list_item and prev != "" and not prev_is_list:
                out.append("")
        out.append(line)
    return "\n".join(out)


def render_markdown_to_html(content_markdown: str) -> str:
    normalized = _normalize_gfm_markdown(content_markdown or "")
    html = markdown.markdown(normalized, extensions=["extra", "sane_lists"])
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )


def slugify(title: str) -> str:
    slug = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()
    return slug[:200] or "article"
