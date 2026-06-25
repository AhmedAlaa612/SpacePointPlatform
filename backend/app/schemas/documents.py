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


class RecommendationLetterOut(BaseModel):
    id: UUID
    user_id: UUID
    signatory_name: str
    signatory_title: str
    file_url: str
    generated_at: datetime

    class Config:
        from_attributes = True


class InternLetterOut(BaseModel):
    id: UUID
    user_id: UUID
    type: str
    file_url: str
    generated_at: datetime

    class Config:
        from_attributes = True


class MyDocumentsOut(BaseModel):
    certificates: list[CertificateOut] = []
    recommendation_letters: list[RecommendationLetterOut] = []
    intern_letters: list[InternLetterOut] = []
