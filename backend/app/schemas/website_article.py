from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ArticlePublicOut(BaseModel):
    """Public list + slug view — exactly the shape spacepoint.ae/insights consumes."""

    id: UUID
    slug: str
    title: str
    summary: Optional[str] = None
    content_html: str
    category: str
    author_display_name: str
    author_role: Optional[str] = None
    author_initials: Optional[str] = None
    cover_image_url: Optional[str] = None
    featured_order: int = 0
    published_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ArticleContributorOut(ArticlePublicOut):
    status: str
    content_markdown: str
    reviewer_feedback: Optional[str] = None
    updated_at: datetime


class ArticleCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: Optional[str] = None
    content_markdown: str = Field(min_length=1)
    category: str = Field(default="EDUCATION", max_length=64)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    author_display_name: Optional[str] = Field(default=None, max_length=255)
    author_role: Optional[str] = Field(default=None, max_length=128)
    author_initials: Optional[str] = Field(default=None, max_length=8)


class ArticleUpdateIn(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    summary: Optional[str] = None
    content_markdown: Optional[str] = Field(default=None, min_length=1)
    category: Optional[str] = Field(default=None, max_length=64)
    cover_image_url: Optional[str] = Field(default=None, max_length=512)
    featured_order: Optional[int] = None
    author_display_name: Optional[str] = Field(default=None, max_length=255)
    author_role: Optional[str] = Field(default=None, max_length=128)
    author_initials: Optional[str] = Field(default=None, max_length=8)


class ArticleReviewIn(BaseModel):
    action: Literal["approve", "request_changes", "unpublish"]
    feedback: Optional[str] = None
