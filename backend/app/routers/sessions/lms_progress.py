"""Instructor LMS progress route (LM1-10) — `GET /sessions/{session_id}/lms-progress`.

Same guard as the roster/delivery routes (`require_session_delivery`: the
assigned instructor/facilitator, or ops/admin); the actual per-session
assignment check happens in `delivery.get_roster` -> `_get_deliverable_session`,
not here, matching this router's own established discipline.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_session_delivery
from app.db.session import get_db
from app.models.user import User
from app.schemas.lms_instructor import SessionLmsProgressOut
from app.services.lms.instructor_progress import session_lms_progress

router = APIRouter(prefix="/sessions", tags=["sessions-lms-progress"])


@router.get("/{session_id}/lms-progress", response_model=SessionLmsProgressOut)
async def get_session_lms_progress(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await session_lms_progress(db, session_id=session_id, user=current_user)
