from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class PointsTransactionOut(BaseModel):
    id: UUID
    ambassador_id: UUID
    amount: int
    type: str
    reason: str
    created_at: datetime
    ambassador_name: Optional[str] = None
    ambassador_email: Optional[str] = None

    class Config:
        from_attributes = True
