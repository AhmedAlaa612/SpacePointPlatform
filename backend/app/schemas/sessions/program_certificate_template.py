"""Pydantic schemas for Program Certificate Templates (2026-09).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

BackgroundType = Literal["custom", "dark", "light"]
BodyAlignment = Literal["center", "left", "right"]
TemplateKind = Literal["individual", "team"]
EmailTemplateKind = Literal["individual", "team", "combined", "profile"]


class ProgramCertificateTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    kind: TemplateKind = "individual"
    is_default: bool = False
    background_type: BackgroundType = "custom"
    background_file_path: str | None = None
    background_file_url: str | None = None

    # Name styling
    name_font_size: int = 34
    name_y: float = 298.0
    name_color: str = "#9778be"

    # Body styling
    body_text: str | None = None
    body_font_size: int = 20
    body_y: float = 260.0
    body_color: str = "#9778be"
    body_max_width: float = 600.0
    body_alignment: BodyAlignment = "center"

    # Signature styling
    show_signature: bool = False
    signature_image_path: str | None = None
    signature_image_url: str | None = None
    signature_x: float | None = None
    signature_y: float = 90.0
    signature_width: float = 140.0
    signature_height: float = 50.0


class CertificateEmailTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    kind: EmailTemplateKind = "individual"
    subject: str = Field(..., max_length=255)
    body_html: str
    is_default: bool = False


class CertificateEmailTemplateCreate(CertificateEmailTemplateBase):
    pass


class CertificateEmailTemplateUpdate(BaseModel):
    name: str | None = None
    kind: EmailTemplateKind | None = None
    subject: str | None = None
    body_html: str | None = None
    is_default: bool | None = None


class CertificateEmailTemplateOut(CertificateEmailTemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CertificateEmailTemplateTestIn(BaseModel):
    to_email: str
    recipient_name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    kind: EmailTemplateKind | None = None
    cohort_id: UUID | None = None
    certificate_template_id: str | None = None

    # Email notification settings
    email_subject: str | None = None
    email_body: str | None = None


class ProgramCertificateTemplateCreate(ProgramCertificateTemplateBase):
    pass


class ProgramCertificateTemplateUpdate(BaseModel):
    name: str | None = None
    kind: TemplateKind | None = None
    is_default: bool | None = None
    background_type: BackgroundType | None = None
    background_file_path: str | None = None
    background_file_url: str | None = None

    name_font_size: int | None = None
    name_y: float | None = None
    name_color: str | None = None

    body_text: str | None = None
    body_font_size: int | None = None
    body_y: float | None = None
    body_color: str | None = None
    body_max_width: float | None = None
    body_alignment: BodyAlignment | None = None

    show_signature: bool | None = None
    signature_image_path: str | None = None
    signature_image_url: str | None = None
    signature_x: float | None = None
    signature_y: float | None = None
    signature_width: float | None = None
    signature_height: float | None = None

    email_subject: str | None = None
    email_body: str | None = None


class ProgramCertificateTemplateOut(ProgramCertificateTemplateBase):
    id: UUID
    program_id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CertificatePreviewRequest(BaseModel):
    recipient_name: str = "Ahmed Mubarak Albalushi"
    program_name: str | None = "Space Race 2026"
    cohort_name: str | None = "Cohort Alpha"
    dates: str | None = "October 2026"
    location: str | None = "Muscat, Oman"

    background_type: BackgroundType = "custom"
    background_file_path: str | None = None

    name_font_size: int = 34
    name_y: float = 298.0
    name_color: str = "#9778be"

    body_text: str | None = None
    body_font_size: int = 20
    body_y: float = 260.0
    body_color: str = "#9778be"
    body_max_width: float = 600.0
    body_alignment: BodyAlignment = "center"

    show_signature: bool = False
    signature_image_path: str | None = None
    signature_x: float | None = None
    signature_y: float = 90.0
    signature_width: float = 140.0
    signature_height: float = 50.0


class CertificateEmailTemplateBase(BaseModel):
    name: str = Field(..., max_length=255)
    kind: EmailTemplateKind = "individual"
    subject: str = Field(..., max_length=255)
    body_html: str
    is_default: bool = False


class CertificateEmailTemplateCreate(CertificateEmailTemplateBase):
    pass


class CertificateEmailTemplateUpdate(BaseModel):
    name: str | None = None
    kind: EmailTemplateKind | None = None
    subject: str | None = None
    body_html: str | None = None
    is_default: bool | None = None


class CertificateEmailTemplateOut(CertificateEmailTemplateBase):
    id: UUID
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class CertificateEmailTemplateTestIn(BaseModel):
    to_email: str
    recipient_name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    kind: EmailTemplateKind | None = None
    cohort_id: UUID | None = None
    certificate_template_id: str | None = None
