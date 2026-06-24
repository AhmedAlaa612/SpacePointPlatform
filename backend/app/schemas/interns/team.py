from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from app.schemas.user import UserOut

class TeamBase(BaseModel):
    name: str
    leader_id: UUID

class TeamCreate(TeamBase):
    pass

class TeamUpdate(BaseModel):
    name: Optional[str] = None
    leader_id: Optional[UUID] = None

class TeamOut(TeamBase):
    id: UUID
    members: List[UserOut] = []

    class Config:
        from_attributes = True
