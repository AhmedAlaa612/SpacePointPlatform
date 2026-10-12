"""Programs CRUD (V2 R2-3 — registration desk). No dedicated service module —
straightforward CRUD lives directly in the router, matching the established
convention for simple CRUD elsewhere (e.g. routers/instructors/admin.py's
invitation-code endpoints). Every route is gated by require_operations
(admin passes automatically — see core/dependencies.py's RequireRole).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.cohort import Cohort
from app.models.sessions.material import Material
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.competitions.judging import CompetitionRubric, CompetitionRubricCriterion
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.user import User
from app.schemas.sessions.programs import ProgramCloneRequest, ProgramCreate, ProgramOut, ProgramUpdate
from app.services import storage
from app.services.lms.program import PROGRAM_ITEM_PDF_BUCKET

router = APIRouter(prefix="/sessions", tags=["sessions-programs"])


@router.get("/programs", response_model=list[ProgramOut])
async def list_programs(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    rows = (await db.execute(select(Program).order_by(Program.created_at.desc()))).scalars().all()
    return rows


@router.post("/programs", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
async def create_program(
    body: ProgramCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    existing = (await db.execute(select(Program.id).where(Program.code == body.code))).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")
    if body.default_assessment_config_id is not None:
        if await db.get(AssessmentConfig, body.default_assessment_config_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")

    program = Program(id=uuid.uuid4(), **body.model_dump())
    db.add(program)
    await db.commit()
    await db.refresh(program)
    return program


@router.get("/programs/{program_id}", response_model=ProgramOut)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    return program


@router.patch("/programs/{program_id}", response_model=ProgramOut)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    changes = body.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] != program.code:
        existing = (await db.execute(select(Program.id).where(Program.code == changes["code"]))).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")
    if changes.get("default_assessment_config_id") is not None:
        if await db.get(AssessmentConfig, changes["default_assessment_config_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")

    for field, value in changes.items():
        setattr(program, field, value)
    await db.commit()
    await db.refresh(program)
    return program


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Only ever deletes an empty program.

    cohorts.program_id cascades, so an unguarded delete here would silently
    take every cohort, session, registration and attendance record with it.
    A program that has been run is history, not a mistake — deactivate it
    (PATCH active=false) instead, which keeps it out of the pickers.
    """
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    cohort_count = await db.scalar(
        select(func.count()).select_from(Cohort).where(Cohort.program_id == program_id)
    )
    if cohort_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This program has {cohort_count} cohort(s) and can't be deleted. "
                "Delete those first, or set the program to inactive to hide it."
            ),
        )

    await db.delete(program)
    await db.commit()


def _copy_lms_item_fields(item: LmsProgramItem, *, owner_type: str, owner_id: uuid.UUID) -> LmsProgramItem:
    """Deep-copy every authoring column of an LmsProgramItem onto a new owner."""
    return LmsProgramItem(
        id=uuid.uuid4(),
        owner_type=owner_type,
        owner_id=owner_id,
        position=item.position,
        item_type=item.item_type,
        title=item.title,
        description=item.description,
        optional=item.optional,
        requires_confirmation=item.requires_confirmation,
        scope=item.scope,
        course_id=item.course_id,
        mission_id=item.mission_id,
        variant_id=item.variant_id,
        external_url=item.external_url,
        submission_prompt=item.submission_prompt,
        submission_field_type=item.submission_field_type,
        submission_multi_link=item.submission_multi_link,
        submission_link_labels=item.submission_link_labels,
        pdf_path=None,
        deadline_at=item.deadline_at,
        session_date=item.session_date,
        session_starts_at=item.session_starts_at,
        session_location=item.session_location,
        session_meeting_url=item.session_meeting_url,
        mission_step_key=item.mission_step_key,
        gated=item.gated,
        guideline_kind=item.guideline_kind,
        guideline_url=item.guideline_url,
        checkpoint_label=item.checkpoint_label,
        cohort_quiz_template_id=item.cohort_quiz_template_id,
    )


async def _duplicate_item_pdf(pdf_path: str | None, copy_id: uuid.UUID) -> str | None:
    """Duplicate a `lms-attachments` storage object under a new UUID so
    deletes/edits in one checklist never affect another (mirrors
    `fork_cohort_override`)."""
    if not pdf_path:
        return None
    data = await storage.download_file(PROGRAM_ITEM_PDF_BUCKET, pdf_path)
    filename = pdf_path.rsplit("/", 1)[-1]
    return await storage.upload_to_path(
        PROGRAM_ITEM_PDF_BUCKET, f"program-items/{copy_id}/{filename}", data, "application/pdf",
    )


@router.post("/programs/{program_id}/clone", response_model=ProgramOut, status_code=status.HTTP_201_CREATED)
async def clone_program(
    program_id: uuid.UUID,
    body: ProgramCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    source = await db.get(Program, program_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    existing = (await db.execute(select(Program.id).where(Program.code == body.code.strip()))).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")

    new_program = Program(
        id=uuid.uuid4(),
        name=body.name.strip(),
        code=body.code.strip(),
        program_type=source.program_type,
        pricing_model=source.pricing_model,
        description=source.description,
        price=source.price,
        default_capacity=source.default_capacity,
        completion_rule_type=source.completion_rule_type,
        completion_rule_value=source.completion_rule_value,
        poster_template_url=source.poster_template_url,
        default_assessment_config_id=(
            source.default_assessment_config_id if "assessment" in body.carry else None
        ),
        default_certificate_template_id=(
            source.default_certificate_template_id if "certificate" in body.carry else None
        ),
        keep_course_access_after_completion=source.keep_course_access_after_completion,
    )
    db.add(new_program)
    await db.flush()

    if "roles" in body.carry:
        openings = (await db.execute(
            select(ProgramOpening).where(ProgramOpening.program_id == source.id)
        )).scalars().all()
        for opening in openings:
            db.add(ProgramOpening(
                id=uuid.uuid4(),
                program_id=new_program.id,
                role_id=opening.role_id,
                slots=opening.slots,
                amount_aed=opening.amount_aed,
                notes=opening.notes,
                responsibilities_override=opening.responsibilities_override,
                created_by=current_user.id,
            ))
        if openings:
            await db.flush()

    if "materials" in body.carry:
        materials = (await db.execute(
            select(Material).where(Material.program_id == source.id)
        )).scalars().all()
        for mat in materials:
            db.add(Material(
                id=uuid.uuid4(),
                program_id=new_program.id,
                cohort_id=None,
                session_id=None,
                title=mat.title,
                notes=mat.notes,
                bucket=mat.bucket,
                file_path=mat.file_path,
                url=mat.url,
                sort_order=mat.sort_order,
                uploaded_by=current_user.id,
            ))
        if materials:
            await db.flush()

    if "checklist" in body.carry:
        source_lms = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == source.id))
        if source_lms is not None:
            new_lms = LmsProgram(
                id=uuid.uuid4(),
                program_id=new_program.id,
                name=source_lms.name,
                description=source_lms.description,
                certificate_required=source_lms.certificate_required,
                poster_template_url=source_lms.poster_template_url,
                image_bucket=source_lms.image_bucket,
                image_path=source_lms.image_path,
            )
            db.add(new_lms)
            await db.flush()
            source_items = (await db.execute(
                select(LmsProgramItem)
                .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == source_lms.id)
                .order_by(LmsProgramItem.position)
            )).scalars().all()
            for item in source_items:
                copy = _copy_lms_item_fields(item, owner_type="program", owner_id=new_lms.id)
                if item.pdf_path:
                    copy.pdf_path = await _duplicate_item_pdf(item.pdf_path, copy.id)
                db.add(copy)
            if source_items:
                await db.flush()

    if "rubric" in body.carry and source.is_competition:
        source_rubric = await db.scalar(
            select(CompetitionRubric).where(
                CompetitionRubric.program_id == source.id,
                CompetitionRubric.cohort_id.is_(None),
            )
        )
        if source_rubric is not None:
            new_rubric = CompetitionRubric(
                id=uuid.uuid4(),
                program_id=new_program.id,
                cohort_id=None,
                name=source_rubric.name,
            )
            db.add(new_rubric)
            await db.flush()
            criteria = (await db.execute(
                select(CompetitionRubricCriterion)
                .where(CompetitionRubricCriterion.rubric_id == source_rubric.id)
                .order_by(CompetitionRubricCriterion.position)
            )).scalars().all()
            for crit in criteria:
                db.add(CompetitionRubricCriterion(
                    id=uuid.uuid4(),
                    rubric_id=new_rubric.id,
                    key=crit.key,
                    label=crit.label,
                    max_points=crit.max_points,
                    position=crit.position,
                    scored_by=crit.scored_by,
                    sub_criteria=crit.sub_criteria,
                ))
            if criteria:
                await db.flush()

    await db.commit()
    await db.refresh(new_program)
    return new_program
