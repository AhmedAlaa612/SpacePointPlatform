from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from uuid import UUID


class NotificationOut(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    body: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
