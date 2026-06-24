from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from app.schemas.interns.team import TeamOut

class ProjectBase(BaseModel):
    title: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class ProjectOut(ProjectBase):
    id: UUID
    status: str = "active"
    created_by: UUID
    teams: List[TeamOut] = []

    class Config:
        from_attributes = True
