from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EmailTemplateOut(BaseModel):
    id: UUID
    key: str
    name: str
    category: str
    description: str
    subject: str
    body_html: str
    placeholders: list[str] = []
    attachment_labels: list[str] = []
    is_paused: bool = False
    is_internal: bool = False
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class EmailTemplateUpdate(BaseModel):
    subject: Optional[str] = None
    body_html: Optional[str] = None


class EmailTemplatePauseUpdate(BaseModel):
    is_paused: bool


class EmailTemplatePreviewRequest(BaseModel):
    subject: str
    body_html: str
    values: Optional[dict[str, str]] = None  # admin-edited overrides on top of the sample defaults


class EmailTemplatePreviewOut(BaseModel):
    subject: str
    body_html: str


class EmailTemplateSendTestOut(BaseModel):
    sent: bool
    to: str
