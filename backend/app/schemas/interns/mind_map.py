from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class MindMapLayoutUpdate(BaseModel):
    layout: Dict[str, Any]   # { "nodeId": { "x": 0, "y": 0 } }


class MindMapLayoutOut(BaseModel):
    id: UUID
    epic_id: UUID
    layout: Dict[str, Any]
    updated_at: datetime

    class Config:
        from_attributes = True


class TaskMindMapNoteUpdate(BaseModel):
    note: str


class TaskMindMapNoteOut(BaseModel):
    task_id: UUID
    note: Optional[str] = None
    updated_at: datetime

    class Config:
        from_attributes = True
