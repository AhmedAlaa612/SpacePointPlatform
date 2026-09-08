"""Instructor assessment facilitator-authoring routes (2026-09) —
`/instructor-assessment/admin/*`, gated by `require_materials_manager` (same
population as teaching-materials/LMS-content authoring — operations +
facilitator; admin passes automatically). Simple CRUD lives directly in the
router, matching the established `routers/games/admin.py` convention.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_materials_manager
from app.db.session import get_db
from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion
from app.models.user import User
from app.schemas.instructor_assessment import (
    AssessmentConfigCreate,
    AssessmentConfigDetailOut,
    AssessmentConfigOut,
    AssessmentConfigUpdate,
    AssessmentQuestionImportOut,
    AssessmentQuestionIn,
    AssessmentQuestionOut,
    AssessmentQuestionUpdate,
)
from app.services.instructor_assessment.importer import (
    generate_assessment_question_template_xlsx,
    parse_assessment_question_import,
)

router = APIRouter(
    prefix="/instructor-assessment/admin", tags=["instructor-assessment-admin"],
    dependencies=[Depends(require_materials_manager)],
)


def _question_out(q: AssessmentQuestion) -> AssessmentQuestionOut:
    return AssessmentQuestionOut(
        id=q.id, category=q.category, prompt=q.prompt, options=q.options,
        critical=q.critical, rationale=q.rationale, is_active=q.is_active,
    )


async def _config_or_404(db: AsyncSession, config_id: uuid.UUID) -> AssessmentConfig:
    config = await db.get(AssessmentConfig, config_id)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")
    return config


async def _config_out(db: AsyncSession, config: AssessmentConfig) -> AssessmentConfigOut:
    rows = (await db.execute(
        select(AssessmentQuestion.category, AssessmentQuestion.critical)
        .where(AssessmentQuestion.config_id == config.id, AssessmentQuestion.is_active.is_(True))
    )).all()
    category_counts: dict[str, int] = {}
    critical_count = 0
    for category, critical in rows:
        category_counts[category] = category_counts.get(category, 0) + 1
        if critical:
            critical_count += 1
    return AssessmentConfigOut(
        id=config.id, name=config.name, description=config.description, is_active=config.is_active,
        created_at=config.created_at, question_count=len(rows),
        category_counts=category_counts, critical_count=critical_count,
    )


# ── configs ──────────────────────────────────────────────────────────────

@router.get("/configs", response_model=list[AssessmentConfigOut])
async def list_configs(db: AsyncSession = Depends(get_db)):
    configs = (await db.execute(select(AssessmentConfig).order_by(AssessmentConfig.created_at.desc()))).scalars().all()
    return [await _config_out(db, c) for c in configs]


@router.post("/configs", response_model=AssessmentConfigOut, status_code=status.HTTP_201_CREATED)
async def create_config(
    body: AssessmentConfigCreate, db: AsyncSession = Depends(get_db),
    current: User = Depends(require_materials_manager),
):
    config = AssessmentConfig(id=uuid.uuid4(), created_by=current.id, **body.model_dump())
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return await _config_out(db, config)


@router.get("/configs/{config_id}", response_model=AssessmentConfigDetailOut)
async def get_config(config_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    config = await _config_or_404(db, config_id)
    questions = (await db.execute(
        select(AssessmentQuestion).where(AssessmentQuestion.config_id == config_id).order_by(AssessmentQuestion.created_at)
    )).scalars().all()
    out = await _config_out(db, config)
    return AssessmentConfigDetailOut(**out.model_dump(), questions=[_question_out(q) for q in questions])


@router.patch("/configs/{config_id}", response_model=AssessmentConfigOut)
async def update_config(config_id: uuid.UUID, body: AssessmentConfigUpdate, db: AsyncSession = Depends(get_db)):
    config = await _config_or_404(db, config_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    await db.commit()
    await db.refresh(config)
    return await _config_out(db, config)


# ── questions ────────────────────────────────────────────────────────────

@router.post("/configs/{config_id}/questions", response_model=AssessmentQuestionOut, status_code=status.HTTP_201_CREATED)
async def create_question(config_id: uuid.UUID, body: AssessmentQuestionIn, db: AsyncSession = Depends(get_db)):
    await _config_or_404(db, config_id)
    question = AssessmentQuestion(
        id=uuid.uuid4(), config_id=config_id, category=body.category, prompt=body.prompt,
        options=[o.model_dump() for o in body.options], critical=body.critical, rationale=body.rationale,
    )
    db.add(question)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.patch("/questions/{question_id}", response_model=AssessmentQuestionOut)
async def update_question(question_id: uuid.UUID, body: AssessmentQuestionUpdate, db: AsyncSession = Depends(get_db)):
    question = await db.get(AssessmentQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(question, field, value)
    await db.commit()
    await db.refresh(question)
    return _question_out(question)


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_question(question_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    question = await db.get(AssessmentQuestion, question_id)
    if question is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    await db.delete(question)
    await db.commit()


# ── bulk import from Excel ──────────────────────────────────────────────────

@router.get("/questions/import/template")
async def download_question_import_template():
    content = generate_assessment_question_template_xlsx()
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=instructor_assessment_questions_template.xlsx"},
    )


@router.post("/configs/{config_id}/questions/import", response_model=AssessmentQuestionImportOut)
async def import_questions(config_id: uuid.UUID, file: UploadFile, db: AsyncSession = Depends(get_db)):
    """Bad rows are skipped and reported, not fatal — same posture as the
    games question importer and the payments bulk importer."""
    await _config_or_404(db, config_id)
    data = await file.read()
    parsed, errors = parse_assessment_question_import(data)

    created: list[AssessmentQuestion] = []
    for body in parsed:
        question = AssessmentQuestion(
            id=uuid.uuid4(), config_id=config_id, category=body.category, prompt=body.prompt,
            options=[o.model_dump() for o in body.options], critical=body.critical, rationale=body.rationale,
        )
        db.add(question)
        created.append(question)
    await db.commit()
    for question in created:
        await db.refresh(question)

    return AssessmentQuestionImportOut(created=len(created), errors=errors, questions=[_question_out(q) for q in created])
