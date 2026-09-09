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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_lms_content
from app.db.session import get_db
from app.models.lms.cohort_quiz import CohortQuizQuestion, CohortQuizTemplate
from app.models.user import User
from app.schemas.lms_cohort_quiz import (
    CohortQuizQuestionImportOut, CohortQuizQuestionIn, CohortQuizQuestionOut, CohortQuizQuestionUpdate,
    CohortQuizTemplateCreate, CohortQuizTemplateDetailOut, CohortQuizTemplateOut, CohortQuizTemplateQuestionIn,
    CohortQuizTemplateQuestionOut, CohortQuizTemplateReorderIn, CohortQuizTemplateUpdate,
)
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.cohort_quiz_importer import (
    generate_cohort_quiz_question_template_xlsx, parse_cohort_quiz_question_import,
)

router = APIRouter(prefix="/lms/admin/cohort-quiz", tags=["lms-admin", "cohort-quiz"])


def _question_out(q: CohortQuizQuestion) -> CohortQuizQuestionOut:
    return CohortQuizQuestionOut(
        id=q.id, topic=q.topic, subtopic=q.subtopic, difficulty=q.difficulty,
        time_limit_seconds=q.time_limit_seconds, bloom_level=q.bloom_level, question_type=q.question_type,
        prompt=q.prompt, options=q.options, explanation=q.explanation, source_url=q.source_url,
        is_active=q.is_active,
    )


# ── question bank ────────────────────────────────────────────────────────

@router.get("/questions", response_model=list[CohortQuizQuestionOut])
async def list_questions(
    topic: str | None = None, is_active: bool | None = None,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    rows = await cohort_quiz_service.list_questions(db, topic=topic, is_active=is_active)
    return [_question_out(q) for q in rows]


@router.post("/questions", response_model=CohortQuizQuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(
    body: CohortQuizQuestionIn, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    question = await cohort_quiz_service.create_question(db, body=body, created_by=current.id)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.patch("/questions/{question_id}", response_model=CohortQuizQuestionOut)
async def update_question(
    question_id: uuid.UUID, body: CohortQuizQuestionUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    question = await db.get(CohortQuizQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    question = await cohort_quiz_service.update_question(db, question, body)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def retire_question(
    question_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    """Retire, never delete (F1) — a question already drawn into a
    submitted attempt must stay readable in that attempt's review."""
    question = await db.get(CohortQuizQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
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
    data = await file.read()
    parsed, errors = parse_cohort_quiz_question_import(data)
    created, skipped = await cohort_quiz_service.import_questions_deduped(db, parsed=parsed, created_by=current.id)
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
            continue  # the question row itself is gone (SET NULL) — nothing left to show for this slot
        # Retired (is_active=False) questions stay listed here, not dropped
        # — a facilitator editing the template needs to see one is retired
        # (CohortQuizQuestionOut.is_active carries the flag) so they know to
        # remove it, rather than the count silently shrinking with no
        # visible reason.
        items.append(CohortQuizTemplateQuestionOut(id=r.id, position=r.position, question=_question_out(q)))
    # Active-only, matching question_count everywhere else (the checklist
    # badge, the template list) and what start_attempt will actually draw —
    # deliberately NOT len(items), which would count retired rows too.
    # Derived from `items` (already fetched above) rather than a third query.
    active_count = sum(1 for i in items if i.question.is_active)
    return CohortQuizTemplateDetailOut(
        id=template.id, name=template.name, description=template.description,
        is_active=template.is_active, created_at=template.created_at, question_count=active_count, questions=items,
    )


@router.get("/templates", response_model=list[CohortQuizTemplateOut])
async def list_templates(db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content)):
    rows = await cohort_quiz_service.list_templates(db)
    counts = await cohort_quiz_service.question_counts_for_templates(db, [t.id for t in rows])
    return [
        CohortQuizTemplateOut(
            id=t.id, name=t.name, description=t.description, is_active=t.is_active,
            created_at=t.created_at, question_count=counts.get(t.id, 0),
        )
        for t in rows
    ]


@router.post("/templates", response_model=CohortQuizTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: CohortQuizTemplateCreate, db: AsyncSession = Depends(get_db), current: User = Depends(require_lms_content),
):
    template = await cohort_quiz_service.create_template(db, body=body, created_by=current.id)
    await db.commit()
    await db.refresh(template)
    return await _template_out(db, template)


@router.get("/templates/{template_id}", response_model=CohortQuizTemplateDetailOut)
async def get_template(
    template_id: uuid.UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    return await _template_detail_out(db, template)


@router.patch("/templates/{template_id}", response_model=CohortQuizTemplateOut)
async def update_template(
    template_id: uuid.UUID, body: CohortQuizTemplateUpdate,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    template = await cohort_quiz_service.update_template(db, template, body)
    await db.commit()
    await db.refresh(template)
    return await _template_out(db, template)


@router.post(
    "/templates/{template_id}/questions", response_model=CohortQuizTemplateDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_template_question(
    template_id: uuid.UUID, body: CohortQuizTemplateQuestionIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    await cohort_quiz_service.add_template_question(db, template_id=template_id, question_id=body.question_id)
    await db.commit()
    return await _template_detail_out(db, template)


@router.delete("/templates/{template_id}/questions/{template_question_id}", response_model=CohortQuizTemplateDetailOut)
async def remove_template_question(
    template_id: uuid.UUID, template_question_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
    await cohort_quiz_service.remove_template_question(
        db, template_id=template_id, template_question_id=template_question_id,
    )
    await db.commit()
    return await _template_detail_out(db, template)


@router.post("/templates/{template_id}/questions/reorder", response_model=CohortQuizTemplateDetailOut)
async def reorder_template_questions(
    template_id: uuid.UUID, body: CohortQuizTemplateReorderIn,
    db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content),
):
    template = await db.get(CohortQuizTemplate, template_id)
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
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
