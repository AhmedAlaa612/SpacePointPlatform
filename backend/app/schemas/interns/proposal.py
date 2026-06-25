from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class ProposalCreate(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None


class ProposalReview(BaseModel):
    status: str          # accepted | rejected
    review_note: Optional[str] = None


class ProposalOut(BaseModel):
    id: UUID
    epic_id: UUID
    proposed_by: UUID
    proposer_name: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    reviewed_by: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def populate_proposer_name(cls, data: Any) -> Any:
        if not hasattr(data, "_sa_instance_state"):
            return data
        loaded = data._sa_instance_state.dict
        proposer = loaded.get("proposer")
        obj = {k: v for k, v in data.__dict__.items() if not k.startswith("_")}
        obj["proposer_name"] = proposer.full_name if proposer is not None else None
        return obj

    class Config:
        from_attributes = True
