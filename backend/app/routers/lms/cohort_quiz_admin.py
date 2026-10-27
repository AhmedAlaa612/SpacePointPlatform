"""Cohort knowledge-quiz authoring (2026-09) — facilitator-curated question
bank + fixed per-template question sets, feeding the LMS Program checklist's
`quiz` item type (see `services/lms/program.py`). Distinct from the
unrelated `services/lms/quiz.py` (random-N in-course module quizzes) and
`instructor_assessment` (instructor scenario MCQs, randomized draw) — see
`app/models/lms/cohort_quiz.py`'s own docstring for why this is a fourth,
separate quiz-shaped domain.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.lms.cohort_quiz import CohortQuizAttempt, CohortQuizQuestion, CohortQuizTemplate
from app.models.lms.program import LmsProgramItem
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.lms_cohort_quiz import (
    CohortQuizQuestionImportOut, CohortQuizQuestionIn, CohortQuizQuestionOut, CohortQuizQuestionUpdate,
    CohortQuizTemplateCreate, CohortQuizTemplateDetailOut, CohortQuizTemplateGenerateIn, CohortQuizTemplateOut,
    CohortQuizTemplateQuestionIn, CohortQuizTemplateQuestionOut, CohortQuizTemplateReorderIn,
    CohortQuizTemplateUpdate,
)
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.cohort_quiz_importer import (
    generate_cohort_quiz_question_template_xlsx, parse_cohort_quiz_question_import,
)

router = APIRouter(prefix="/lms/admin/cohort-quiz", tags=["lms-admin", "cohort-quiz"])


async def _resolve_quiz_org_scope(db: AsyncSession, current: User) -> tuple[Organization | None, str, list[uuid.UUID]]:
    if "organization" in current.role_values and not any(r in current.role_values for r in ("admin", "operations")):
        from app.services.website_events import resolve_user_organization
        org = await resolve_user_organization(db, current)
        if org is not None:
            scope = getattr(org, "quiz_scope", "own") or "own"
            raw_allowed = getattr(org, "allowed_quiz_template_ids", []) or []
            allowed_ids: list[uuid.UUID] = []
            for tid in raw_allowed:
                try:
                    allowed_ids.append(uuid.UUID(str(tid)))
                except (ValueError, TypeError):
                    pass
            return org, scope, allowed_ids
    return None, "all", []


def _question_out(q: CohortQuizQuestion) -> CohortQuizQuestionOut:
    return CohortQuizQuestionOut(
        id=q.id, topic=q.topic, subtopic=q.subtopic, difficulty=q.difficulty,
        time_limit_seconds=q.time_limit_seconds, bloom_level=q.bloom_level, question_type=q.question_type,
        is_optional=getattr(q, "is_optional", False),
        prompt=q.prompt, options=q.options, explanation=q.explanation, source_url=q.source_url,
        is_active=q.is_active,
        organization_id=getattr(q, "organization_id", None),
    )


# ── question bank ────────────────────────────────────────────────────────

@router.get("/questions", response_model=list[CohortQuizQuestionOut])
async def list_questions(
    topic: str | None = None, is_active: bool | None = None,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    org, scope, allowed_ids = await _resolve_quiz_org_scope(db, current)
    org_id = org.id if org else None
    rows = await cohort_quiz_service.list_questions(
        db, topic=topic, is_active=is_active, org_id=org_id, quiz_scope=scope, allowed_template_ids=allowed_ids,
    )
    return [_question_out(q) for q in rows]


@router.post("/questions", response_model=CohortQuizQuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    body: CohortQuizQuestionIn, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    org_id = org.id if org else None
    question = await cohort_quiz_service.create_question(
        db, body=body, created_by=current.id, organization_id=org_id,
    )
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.patch("/questions/{question_id}", response_model=CohortQuizQuestionOut)
async def update_question(
    question_id: uuid.UUID, body: CohortQuizQuestionUpdate,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    question = await db.get(CohortQuizQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and question.organization_id != org.id and question.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify questions from other organizations or platform")
    question = await cohort_quiz_service.update_question(db, question, body)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_question(
    question_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    """Retire, never delete (F1) — a question already drawn into a
    submitted attempt must stay readable in that attempt's review."""
    question = await db.get(CohortQuizQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and question.organization_id != org.id and question.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot retire questions from other organizations or platform")
    question.is_active = False
    await db.commit()


@router.get("/questions/import/template")
async def download_question_import_template(_: User = Depends(require_lms_content)):
    data = generate_cohort_quiz_question_template_xlsx()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=cohort_quiz_question_template.xlsx"},
    )


@router.post("/questions/import", response_model=CohortQuizQuestionImportOut)
async def import_questions(
    file: UploadFile, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    org_id = org.id if org else None
    data = await file.read()
    parsed, errors = parse_cohort_quiz_question_import(data)
    created, skipped = await cohort_quiz_service.import_questions_deduped(
        db, parsed=parsed, created_by=current.id, organization_id=org_id,
    )
    await db.commit()
    for q in created:
        await db.refresh(q)
    return CohortQuizQuestionImportOut(
        created=len(created), skipped_duplicates=skipped, errors=errors, questions=[_question_out(q) for q in created],
    )


# ── templates ────────────────────────────────────────────────────────────

async def _template_out(db: AsyncSession, template: CohortQuizTemplate) -> CohortQuizTemplateOut:
    count = await cohort_quiz_service.question_count_for_template(db, template.id)
    return CohortQuizTemplateOut(
        id=template.id, name=template.name, description=template.description,
        is_active=template.is_active, created_at=template.created_at, question_count=count,
        organization_id=getattr(template, "organization_id", None),
    )


async def _template_detail_out(db: AsyncSession, template: CohortQuizTemplate) -> CohortQuizTemplateDetailOut:
    rows = await cohort_quiz_service.get_template_questions(db, template.id)
    question_ids = [r.question_id for r in rows if r.question_id]
    questions_by_id = {}
    if question_ids:
        result = await db.execute(select(CohortQuizQuestion).where(CohortQuizQuestion.id.in_(question_ids)))
        questions_by_id = {q.id: q for q in result.scalars().all()}
    items = []
    for r in rows:
        q = questions_by_id.get(r.question_id)
        if q is None:
            continue
        items.append(CohortQuizTemplateQuestionOut(id=r.id, position=r.position, question=_question_out(q)))
    active_count = sum(1 for i in items if i.question.is_active)
    return CohortQuizTemplateDetailOut(
        id=template.id, name=template.name, description=template.description,
        is_active=template.is_active, created_at=template.created_at, question_count=active_count, questions=items,
        organization_id=getattr(template, "organization_id", None),
    )


@router.get("/templates", response_model=list[CohortQuizTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content)):
    org, scope, allowed_ids = await _resolve_quiz_org_scope(db, current)
    org_id = org.id if org else None
    rows = await cohort_quiz_service.list_templates(
        db, org_id=org_id, quiz_scope=scope, allowed_template_ids=allowed_ids,
    )
    counts = await cohort_quiz_service.question_counts_for_templates(db, [t.id for t in rows])
    return [
        CohortQuizTemplateOut(
            id=t.id, name=t.name, description=t.description, is_active=t.is_active,
            created_at=t.created_at, question_count=counts.get(t.id, 0),
            organization_id=getattr(t, "organization_id", None),
        )
        for t in rows
    ]


@router.post("/templates", response_model=CohortQuizTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: CohortQuizTemplateCreate, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    org_id = org.id if org else None
    template = await cohort_quiz_service.create_template(
        db, body=body, created_by=current.id, organization_id=org_id,
    )
    await db.commit()
    await db.refresh(template)
    return await _template_out(db, template)


@router.get("/templates/{template_id}", response_model=CohortQuizTemplateDetailOut)
async def get_template(
    template_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, scope, allowed_ids = await _resolve_quiz_org_scope(db, current)
    if org is not None:
        if scope == "own" and template.organization_id != org.id and template.created_by != current.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
        elif scope == "selected" and template.organization_id != org.id and template.created_by != current.id and template.id not in allowed_ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    return await _template_detail_out(db, template)


@router.patch("/templates/{template_id}", response_model=CohortQuizTemplateOut)
async def update_template(
    template_id: uuid.UUID, body: CohortQuizTemplateUpdate,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify templates from other organizations or platform")
    template = await cohort_quiz_service.update_template(db, template, body)
    await db.commit()
    await db.refresh(template)
    return await _template_out(db, template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot delete templates from other organizations or platform")
    """Hard-delete a template that was never actually used — the "retire,
    never delete" posture (PATCH is_active=false, above) is for a template
    already in play; one nobody's touched costs nothing to remove outright.

    Both `LmsProgramItem.cohort_quiz_template_id` and `CohortQuizAttempt.
    cohort_quiz_template_id` are RESTRICT, so either reference blocks this —
    checked up front (same posture as `instructor_assessment/admin.py::
    delete_config`) so the caller gets a sentence instead of a raw FK error.
    `CohortQuizTemplateQuestion` rows cascade automatically.
    """
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    checklist_uses = await db.scalar(
        select(func.count()).select_from(LmsProgramItem)
        .where(LmsProgramItem.cohort_quiz_template_id == template_id)
    )
    if checklist_uses:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This template is used by {checklist_uses} checklist item"
                f"{'' if checklist_uses == 1 else 's'}, so it can't be deleted. Point "
                f"those items at a different template first, or retire this one instead."
            ),
        )
    attempts = await db.scalar(
        select(func.count()).select_from(CohortQuizAttempt)
        .where(CohortQuizAttempt.cohort_quiz_template_id == template_id)
    )
    if attempts:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"{attempts} student attempt{'' if attempts == 1 else 's'} already reference this "
                f"template, so it can't be deleted. Retire it instead — that removes it from new picks."
            ),
        )
    await db.delete(template)
    await db.commit()


@router.post(
    "/templates/{template_id}/questions", response_model=CohortQuizTemplateDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_template_question(
    template_id: uuid.UUID, body: CohortQuizTemplateQuestionIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify templates from other organizations or platform")
    await cohort_quiz_service.add_template_question(db, template_id=template_id, question_id=body.question_id)
    await db.commit()
    return await _template_detail_out(db, template)


@router.delete("/templates/{template_id}/questions/{template_question_id}", response_model=CohortQuizTemplateDetailOut)
async def remove_template_question(
    template_id: uuid.UUID, template_question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify templates from other organizations or platform")
    await cohort_quiz_service.remove_template_question(
        db, template_id=template_id, template_question_id=template_question_id,
    )
    await db.commit()
    return await _template_detail_out(db, template)


@router.post("/templates/{template_id}/questions/reorder", response_model=CohortQuizTemplateDetailOut)
async def reorder_template_questions(
    template_id: uuid.UUID, body: CohortQuizTemplateReorderIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify templates from other organizations or platform")
    result = await cohort_quiz_service.reorder_template_questions(
        db, template_id=template_id, template_question_ids=body.template_question_ids,
    )
    if result is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="template_question_ids must match the template's current question set exactly",
        )
    await db.commit()
    return await _template_detail_out(db, template)


@router.post("/templates/{template_id}/generate", response_model=CohortQuizTemplateDetailOut)
async def generate_template_questions(
    template_id: uuid.UUID, body: CohortQuizTemplateGenerateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    """Auto-populate the template's fixed question set — replaces
    whatever's on it. "Regenerate" in the admin UI is the same call again
    for a different random pick; the facilitator can still hand-edit the
    result afterward (add/remove/reorder)."""
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    org, _, _ = await _resolve_quiz_org_scope(db, current)
    if org is not None and template.organization_id != org.id and template.created_by != current.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Cannot modify templates from other organizations or platform")
    await cohort_quiz_service.generate_template_questions(
        db, template_id=template_id, count=body.count, topics=body.topics,
    )
    await db.commit()
    return await _template_detail_out(db, template)
