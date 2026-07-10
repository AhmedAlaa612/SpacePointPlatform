from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.instructors.payment import CertificateOut


class RecommendationLetterCreate(BaseModel):
    user_id: UUID
    recommendation_text: str
    signatory_name: Optional[str] = None
    signatory_title: Optional[str] = None


class DocumentOut(BaseModel):
    id: UUID
    label: str
    file_url: str
    generated_at: datetime

    class Config:
        from_attributes = True


class MyDocumentsOut(BaseModel):
    certificates: list[CertificateOut] = []
    documents: list[DocumentOut] = []


class AvailableTemplateOut(BaseModel):
    id: UUID
    key: str
    name: str
    roles: list[str] = []


class DocumentTemplateOut(BaseModel):
    id: UUID
    key: str
    name: str
    roles: list[str] = []
    body_text: Optional[str] = None
    template_file_url: Optional[str] = None
    type: str = "letter"
    is_system: bool = False
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentTemplateUpdate(BaseModel):
    name: Optional[str] = None
    roles: Optional[list[str]] = None
    body_text: Optional[str] = None
    template_file_url: Optional[str] = None


class DocumentTemplateCreate(BaseModel):
    key: str
    name: str
    roles: list[str]
    body_text: Optional[str] = None
    type: str = "letter"   # 'letter' | 'certificate'


class StorageFileOut(BaseModel):
    name: str
    size: Optional[int] = None
    mimetype: Optional[str] = None
    last_modified: Optional[str] = None
    signed_url: Optional[str] = None
    owner_name: Optional[str] = None
    document_type_label: Optional[str] = None


class DossierItem(BaseModel):
    category: str          # e.g. "Documents", "Certificates", "Personal Vault"...
    label: str
    date: Optional[datetime] = None
    url: Optional[str] = None
    meta: Optional[str] = None  # short status/context string shown alongside the label
    id: Optional[UUID] = None  # row id — only set for categories the dossier UI can delete


class UserDossierOut(BaseModel):
    items: list[DossierItem] = []
