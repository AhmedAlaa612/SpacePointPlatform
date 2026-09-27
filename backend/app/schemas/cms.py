from datetime import datetime
import re
import unicodedata
from uuid import UUID

try:
    import bleach
    from markdown_it import MarkdownIt
    md_parser = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    HAS_BLEACH = True
except ImportError:
    bleach = None
    md_parser = None
    HAS_BLEACH = False

from pydantic import BaseModel, EmailStr

# Initialize Markdown parser with standard CommonMark and table/strikethrough plugins
ALLOWED_TAGS = [
    "a", "abbr", "acronym", "b", "blockquote", "code", "em", "i", "li", "ol",
    "p", "strong", "ul", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "span",
    "img", "figure", "figcaption", "hr", "br", "table", "thead", "tbody", "tr", "th", "td"
]
ALLOWED_ATTRIBUTES = {
    "*": ["class", "id"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "th": ["scope", "align", "colspan", "rowspan"],
    "td": ["align", "colspan", "rowspan"],
}


def compile_markdown_to_safe_html(markdown_text: str) -> str:
    """Renders raw markdown to HTML and cleans it with Bleach against XSS attacks."""
    if not markdown_text:
        return ""
    if HAS_BLEACH and md_parser:
        raw_html = md_parser.render(markdown_text)
        clean_html = bleach.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        )
        return clean_html
    import html
    return f"<p>{html.escape(markdown_text)}</p>"


def slugify(text: str) -> str:
    """Generates an SEO-safe URL slug from a title string."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[-\s]+", "-", text)[:150]


# ── Articles ─────────────────────────────────────────────────────────────────

class ArticleBase(BaseModel):
    title: str
    summary: str | None = None
    category: str = "TECHNOLOGY"
    cover_image_url: str | None = None
    content_markdown: str


class ArticleCreate(ArticleBase):
    slug: str | None = None
    author_display_name: str | None = None
    author_role: str | None = None
    author_initials: str | None = None
    submit_for_review: bool = False


class ArticleUpdate(BaseModel):
    title: str | None = None
    summary: str | None = None
    category: str | None = None
    content_markdown: str | None = None
    cover_image_url: str | None = None
    submit_for_review: bool | None = None


class ArticleReviewAction(BaseModel):
    action: str  # approve | request_changes | archive | unpublish
    reviewer_feedback: str | None = None
    featured_order: int | None = None


class ArticlePublicOut(BaseModel):
    id: UUID
    slug: str
    title: str
    summary: str | None = None
    content_html: str
    category: str
    author_display_name: str
    author_role: str | None = None
    author_initials: str | None = None
    cover_image_url: str | None = None
    featured_order: int | None = None
    published_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class ArticleAdminOut(BaseModel):
    id: UUID
    slug: str
    title: str
    summary: str | None = None
    content_markdown: str
    content_html: str
    category: str
    author_id: UUID | None = None
    author_display_name: str
    author_role: str | None = None
    author_initials: str | None = None
    cover_image_url: str | None = None
    status: str
    reviewer_feedback: str | None = None
    reviewed_by_id: UUID | None = None
    reviewed_at: datetime | None = None
    featured_order: int | None = None
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Sponsors ─────────────────────────────────────────────────────────────────

class SponsorBase(BaseModel):
    name: str
    logo_url: str
    website_url: str | None = None
    tier: str = "partner"  # client | partner | supporter | academic
    display_order: int = 0
    is_active: bool = True


class SponsorCreate(SponsorBase):
    pass


class SponsorUpdate(BaseModel):
    name: str | None = None
    logo_url: str | None = None
    website_url: str | None = None
    tier: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class SponsorOut(SponsorBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Media Clippings ──────────────────────────────────────────────────────────

class MediaClippingBase(BaseModel):
    publisher_name: str
    article_title: str
    article_url: str
    published_date: datetime
    logo_url: str | None = None
    is_arabic: bool = False
    snippet: str | None = None
    display_order: int = 0
    is_active: bool = True


class MediaClippingCreate(MediaClippingBase):
    pass


class MediaClippingUpdate(BaseModel):
    publisher_name: str | None = None
    article_title: str | None = None
    article_url: str | None = None
    published_date: datetime | None = None
    logo_url: str | None = None
    is_arabic: bool | None = None
    snippet: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


class MediaClippingOut(MediaClippingBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Student Missions ─────────────────────────────────────────────────────────

class StudentMissionBase(BaseModel):
    student_name: str
    project_title: str
    category: str
    description: str
    docx_url: str | None = None
    photo_url: str | None = None
    metrics_json: dict = {}
    display_order: int = 0
    is_active: bool = True


class StudentMissionCreate(StudentMissionBase):
    pass


class StudentMissionUpdate(BaseModel):
    student_name: str | None = None
    project_title: str | None = None
    category: str | None = None
    description: str | None = None
    docx_url: str | None = None
    photo_url: str | None = None
    metrics_json: dict | None = None
    display_order: int | None = None
    is_active: bool | None = None


class StudentMissionOut(StudentMissionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ── Website Leads ────────────────────────────────────────────────────────────

class WebsiteLeadCreate(BaseModel):
    lead_type: str  # workshop_booking | newsletter | inquiry
    contact_name: str | None = None
    email: EmailStr
    phone: str | None = None
    organization_name: str | None = None
    program_interest: str | None = None
    details: dict = {}


class WebsiteLeadStatusUpdate(BaseModel):
    status: str  # new | contacted | converted | archived


class WebsiteLeadOut(BaseModel):
    id: UUID
    lead_type: str
    contact_name: str | None = None
    email: str
    phone: str | None = None
    organization_name: str | None = None
    program_interest: str | None = None
    details: dict
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
