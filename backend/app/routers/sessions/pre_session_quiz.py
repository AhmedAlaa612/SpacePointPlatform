from pathlib import Path
import re
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_materials_manager,
    require_session_delivery,
)
from app.models.user import User
from app.schemas.sessions.pre_session_quiz import (
    PreSessionQuizAssignmentIn,
    PreSessionQuizAssignmentOut,
    PreSessionQuizAttemptOut,
    PreSessionQuizPresetIn,
    PreSessionQuizPresetOut,
    PreSessionQuizQuestionIn,
    PreSessionQuizQuestionOut,
    PreSessionQuizReviewQuestionIn,
    PreSessionQuizSubmitIn,
    SessionPreQuizStatusOut,
)
from app.services import storage
from app.services.sessions import pre_session_quiz as svc

router = APIRouter(prefix="/sessions", tags=["sessions - pre-session quiz"])

QUIZ_IMAGE_BUCKET = "lms-quiz-images"
MAX_QUIZ_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ── Question Bank Endpoints ─────────────────────────────────────────────────

@router.get("/pre-quiz/questions", response_model=list[PreSessionQuizQuestionOut])
async def list_pre_quiz_questions(
    topic: str | None = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.list_questions(db, topic=topic, active_only=active_only)


@router.post(
    "/pre-quiz/questions",
    response_model=PreSessionQuizQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pre_quiz_question(
    body: PreSessionQuizQuestionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.create_question(db, body, current_user)


@router.put("/pre-quiz/questions/{question_id}", response_model=PreSessionQuizQuestionOut)
async def update_pre_quiz_question(
    question_id: UUID,
    body: PreSessionQuizQuestionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.update_question(db, question_id, body)


@router.delete("/pre-quiz/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pre_quiz_question(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    await svc.delete_question(db, question_id)


@router.post("/pre-quiz/images")
async def upload_pre_quiz_image(
    file: UploadFile,
    current_user: User = Depends(require_materials_manager),
) -> dict:
    """Upload a diagram/image for a pre-session quiz question or explanation."""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_QUIZ_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image exceeds the 10MB limit")

    filename = Path(file.filename or "image.png").name
    clean_name = re.sub(r"[^\w\.-]", "_", filename)
    path = f"prequiz_{uuid.uuid4().hex[:8]}_{clean_name}"
    url = await storage.upload_file(QUIZ_IMAGE_BUCKET, path, data, file.content_type or "image/png")
    return {"url": url, "path": path}


# ── Presets / Templates Endpoints ───────────────────────────────────────────

@router.get("/pre-quiz/presets", response_model=list[PreSessionQuizPresetOut])
async def list_pre_quiz_presets(
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.list_presets(db, active_only=active_only)


@router.post(
    "/pre-quiz/presets",
    response_model=PreSessionQuizPresetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pre_quiz_preset(
    body: PreSessionQuizPresetIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.create_preset(db, body, current_user)


@router.put("/pre-quiz/presets/{preset_id}", response_model=PreSessionQuizPresetOut)
async def update_pre_quiz_preset(
    preset_id: UUID,
    body: PreSessionQuizPresetIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.update_preset(db, preset_id, body)


@router.delete("/pre-quiz/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pre_quiz_preset(
    preset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    await svc.delete_preset(db, preset_id)


# ── Assignment Endpoints (Program -> Cohort -> Session) ─────────────────────

@router.get(
    "/pre-quiz/assignments/{scope}/{owner_id}",
    response_model=PreSessionQuizAssignmentOut,
)
async def get_pre_quiz_assignment(
    scope: str,
    owner_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.get_assignment_for_scope(db, scope, owner_id)


@router.put(
    "/pre-quiz/assignments/{scope}/{owner_id}",
    response_model=PreSessionQuizAssignmentOut,
)
async def set_pre_quiz_assignment(
    scope: str,
    owner_id: UUID,
    body: PreSessionQuizAssignmentIn,
    clear_override: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.set_assignment_for_scope(
        db, scope, owner_id, body.preset_id, clear_override=clear_override
    )


# ── Session Delivery & Ops Review Endpoints ─────────────────────────────────

@router.get("/{session_id}/pre-quiz", response_model=SessionPreQuizStatusOut)
async def get_session_pre_quiz(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await svc.get_session_pre_quiz_status(db, session_id, current_user)


@router.post("/{session_id}/pre-quiz/submit", response_model=PreSessionQuizAttemptOut)
async def submit_session_pre_quiz(
    session_id: UUID,
    body: PreSessionQuizSubmitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await svc.submit_session_pre_quiz(db, session_id, current_user, body)


@router.patch(
    "/pre-quiz/attempts/{attempt_id}/review",
    response_model=PreSessionQuizAttemptOut,
)
async def review_pre_quiz_attempt_question(
    attempt_id: UUID,
    body: PreSessionQuizReviewQuestionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.review_attempt_question(db, attempt_id, body, current_user)
