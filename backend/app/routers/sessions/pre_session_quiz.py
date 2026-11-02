from pathlib import Path
import re
import uuid
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_db,
    require_materials_manager,
    require_session_delivery,
)
from app.models.user import User
from app.schemas.sessions.pre_session_quiz import (
    CohortPreQuizStatusOut,
    PhaseTrialOut,
    PhaseTrialSubmitIn,
    PreSessionQuizAssignmentIn,
    PreSessionQuizAssignmentOut,
    PreSessionQuizAttemptOut,
    PreSessionQuizDatasheetIn,
    PreSessionQuizDatasheetOut,
    PreSessionQuizDatasheetUpdateIn,
    PreSessionQuizImportOut,
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
MAX_QUIZ_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB (to support multi-page datasheet PDFs)


class PhaseSubmitResponse(BaseModel):
    trial: PhaseTrialOut
    attempt: PreSessionQuizAttemptOut


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


@router.get("/pre-quiz/questions/import/template")
async def download_pre_quiz_import_template(
    current_user: User = Depends(require_materials_manager),
):
    """Download official SpacePoint question bank import template."""
    from app.services.sessions.pre_session_quiz_importer import generate_question_template_xlsx
    content = generate_question_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=spacepoint_question_bank_template.xlsx"},
    )


@router.post("/pre-quiz/questions/import", response_model=PreSessionQuizImportOut)
async def import_pre_quiz_questions(
    file: UploadFile,
    topic: str | None = Query(None),
    preset_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    """Bulk import questions from Excel (.xlsx) or CSV (.csv)."""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload file")

    filename = file.filename or "questions.xlsx"
    created_count, errors, created_questions = await svc.import_questions_from_file(
        db, data, filename, current_user, topic_override=topic, preset_id=preset_id
    )
    return PreSessionQuizImportOut(
        created=created_count,
        errors=errors,
        questions=[PreSessionQuizQuestionOut.model_validate(q) for q in created_questions],
    )


@router.post("/pre-quiz/questions/deduplicate")
async def deduplicate_pre_quiz_questions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
) -> dict:
    """Finds duplicate questions, cleans float IDs (1.0 -> 1), and keeps single canonical instances."""
    return await svc.deduplicate_bank_questions(db)


@router.post("/pre-quiz/images")
async def upload_pre_quiz_image(
    file: UploadFile,
    current_user: User = Depends(require_materials_manager),
) -> dict:
    """Upload a diagram/image or datasheet PDF for a pre-session quiz question or catalog."""
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_QUIZ_IMAGE_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20MB limit")

    filename = Path(file.filename or "file.pdf").name
    clean_name = re.sub(r"[^\w\.-]", "_", filename)
    path = f"prequiz_{uuid.uuid4().hex[:8]}_{clean_name}"
    content_type = file.content_type or ("application/pdf" if filename.lower().endswith(".pdf") else "image/png")
    url = await storage.upload_file(QUIZ_IMAGE_BUCKET, path, data, content_type)
    return {"url": url, "path": path}


# ── Datasheet Library Endpoints ─────────────────────────────────────────────

@router.get("/pre-quiz/datasheets", response_model=list[PreSessionQuizDatasheetOut])
async def list_pre_quiz_datasheets(
    subsystem: str | None = Query(None),
    doc_type: str | None = Query(None),
    search: str | None = Query(None),
    active_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    """List all technical datasheets in the centralized library."""
    return await svc.list_datasheets(
        db, subsystem=subsystem, doc_type=doc_type, search=search, active_only=active_only
    )


@router.post(
    "/pre-quiz/datasheets",
    response_model=PreSessionQuizDatasheetOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_pre_quiz_datasheet(
    body: PreSessionQuizDatasheetIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    """Add a new technical datasheet or reference document to the library."""
    return await svc.create_datasheet(db, body, current_user)


@router.put("/pre-quiz/datasheets/{datasheet_id}", response_model=PreSessionQuizDatasheetOut)
async def update_pre_quiz_datasheet(
    datasheet_id: UUID,
    body: PreSessionQuizDatasheetUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    """Update a datasheet in the library."""
    return await svc.update_datasheet(db, datasheet_id, body)


@router.delete("/pre-quiz/datasheets/{datasheet_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pre_quiz_datasheet(
    datasheet_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    """Deactivate/remove a datasheet from the library."""
    await svc.delete_datasheet(db, datasheet_id)


@router.post("/pre-quiz/datasheets/upload")
async def upload_pre_quiz_datasheet_pdf(
    file: UploadFile,
    current_user: User = Depends(require_materials_manager),
) -> dict:
    """Upload a module datasheet PDF into storage."""
    return await upload_pre_quiz_image(file, current_user)


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


# ── Cohort Readiness Pipeline Delivery Endpoints ────────────────────────────

@router.get("/cohorts/{cohort_id}/pre-quiz", response_model=CohortPreQuizStatusOut)
async def get_cohort_pre_quiz(
    cohort_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await svc.get_cohort_pre_quiz_status(db, cohort_id, current_user)


@router.post(
    "/cohorts/{cohort_id}/pre-quiz/phases/{phase_id}/start",
    response_model=PreSessionQuizAttemptOut,
)
async def start_cohort_phase(
    cohort_id: UUID,
    phase_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await svc.start_cohort_phase(db, cohort_id, phase_id, current_user)


@router.post(
    "/cohorts/{cohort_id}/pre-quiz/phases/{phase_id}/submit",
    response_model=PhaseSubmitResponse,
)
async def submit_cohort_phase(
    cohort_id: UUID,
    phase_id: str,
    body: PhaseTrialSubmitIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    return await svc.submit_cohort_phase(db, cohort_id, phase_id, current_user, body)


# ── Legacy Session Pre-Quiz & Ops Review Endpoints ──────────────────────────

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


@router.post(
    "/pre-quiz/attempts/{attempt_id}/unlock-cooldown",
    response_model=PreSessionQuizAttemptOut,
)
async def unlock_quiz_attempt_cooldown(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_materials_manager),
):
    return await svc.unlock_cooldown(db, attempt_id, current_user)
