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
    contract_signed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class InstructorProfileUpdate(BaseModel):
    linkedin_url: Optional[str] = None


class SignContractRequest(BaseModel):
    signature: str  # data:image/png;base64,...


class IdCardOut(BaseModel):
    card_id: Optional[str] = None
    front_b64: Optional[str] = None   # base64-encoded PNG of the rendered card
    back_b64: Optional[str] = None    # base64-encoded PNG of the rendered card back
    generated_at: Optional[datetime] = None
    has_photo: bool = False
    has_linkedin: bool = False
    photo_url: Optional[str] = None
    linkedin_url: Optional[str] = None


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
