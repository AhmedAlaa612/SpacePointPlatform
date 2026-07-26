from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel


class ImportRowOut(BaseModel):
    row_number: int
    disposition: Literal["create", "link", "already_registered", "review", "error"]
    data: dict
    reason: Optional[str] = None
    contact_id: Optional[str] = None


class ImportBatchOut(BaseModel):
    id: UUID
    source: Literal["b2b_sheet", "backfill"]
    cohort_id: UUID
    filename: str
    status: Literal["dry_run", "committed", "failed"]
    summary: dict
    rows: list[ImportRowOut]
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportBatchListItem(BaseModel):
    id: UUID
    source: Literal["b2b_sheet", "backfill"]
    cohort_id: UUID
    filename: str
    status: Literal["dry_run", "committed", "failed"]
    summary: dict
    created_at: datetime

    model_config = {"from_attributes": True}
