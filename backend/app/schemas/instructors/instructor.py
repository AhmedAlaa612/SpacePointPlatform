from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class InstructorProfileOut(BaseModel):
    user_id: UUID
    linkedin_url: Optional[str] = None
    photo_url: Optional[str] = None
    contract_url: Optional[str] = None
    signed_contract_url: Optional[str] = None

    class Config:
        from_attributes = True


class InstructorProfileUpdate(BaseModel):
    linkedin_url: Optional[str] = None


class IdCardOut(BaseModel):
    card_id: Optional[str] = None
    front_url: Optional[str] = None
    back_url: Optional[str] = None
    pdf_url: Optional[str] = None
    generated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BankDetailsOut(BaseModel):
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None

    class Config:
        from_attributes = True


class BankDetailsUpdate(BaseModel):
    account_holder_name: Optional[str] = None
    bank_name: Optional[str] = None
    iban: Optional[str] = None
    swift_bic: Optional[str] = None


class InstructorDocumentOut(BaseModel):
    id: UUID
    document_type: str
    file_url: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
