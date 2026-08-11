"""Unified prerequisite status + authoring (7B-2) — shared shape between
course and mission detail responses, since 7B-2 lets either kind gate on
either kind; also the admin CRUD surface for `Prerequisite` edges, the
first one either mission-mission or course-involving edges have ever had.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class PrerequisiteItemOut(BaseModel):
    item_type: str  # 'course'|'mission'
    item_id: UUID
    title: str
    satisfied: bool


ItemTypeLiteral = Literal["course", "mission"]


class PrerequisiteEdgeIn(BaseModel):
    item_type: ItemTypeLiteral
    item_id: UUID
    requires_type: ItemTypeLiteral
    requires_id: UUID


class PrerequisiteEdgeOut(BaseModel):
    item_type: str
    item_id: UUID
    requires_type: str
    requires_id: UUID
    requires_title: str
