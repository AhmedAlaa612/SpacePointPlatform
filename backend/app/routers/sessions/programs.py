"""Programs CRUD (V2 R2-3 — registration desk). No dedicated service module —
straightforward CRUD lives directly in the router, matching the established
convention for simple CRUD elsewhere (e.g. routers/instructors/admin.py's
invitation-code endpoints). Every route is gated by require_operations
(admin passes automatically — see core/dependencies.py's RequireRole).
"""

from datetime import date, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations
from app.db.session import get_db
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.material import Material
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.sessions.session import Session
from app.models.competitions.judging import CompetitionRubric, CompetitionRubricCriterion
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.user import User
from app.schemas.sessions.programs import ProgramCloneRequest, ProgramCreate, ProgramOut, ProgramUpdate
from app.services import storage
from app.services.lms.program import PROGRAM_ITEM_PDF_BUCKET

class TemplateDayOut(BaseModel):
    id: uuid.UUID
    cohort_id: uuid.UUID
    day_number: int
    title: str | None = None
    duration_hours: float | None = None
    meeting_date: str | None = None

    class Config:
        from_attributes = True

class ProgramTemplateOut(BaseModel):
    program_id: uuid.UUID
    template_cohort_id: uuid.UUID
    days_count: int
    sessions: list[TemplateDayOut]

class TemplateDayCreate(BaseModel):
    title: str | None = None
    duration_hours: float | None = None

class TemplateDayUpdate(BaseModel):
    title: str | None = None
    duration_hours: float | None = None

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

        # ── Delivery checklist (program-level pre-program/pre-workshop items) ──
        source_delivery_items = (await db.execute(
            select(DeliveryChecklistItem).where(DeliveryChecklistItem.program_id == source.id)
            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
        )).scalars().all()
        for ci in source_delivery_items:
            db.add(DeliveryChecklistItem(
                id=uuid.uuid4(),
                program_id=new_program.id,
                cohort_id=None,
                session_id=None,
                role_id=ci.role_id,
                title=ci.title,
                description=ci.description,
                requires_proof=ci.requires_proof,
                is_required=ci.is_required,
                sort_order=ci.sort_order,
                created_by=current_user.id,
            ))
        if source_delivery_items:
            await db.flush()

        # ── Clone program's template cohort, days and checklists ──
        source_template_cohort = await db.scalar(
            select(Cohort).where(
                Cohort.program_id == source.id,
                Cohort.name.ilike("%template%"),
            ).order_by(Cohort.created_at.asc())
        )
        if source_template_cohort:
            new_template_cohort = Cohort(
                id=uuid.uuid4(),
                program_id=new_program.id,
                name=f"[Template] {new_program.name}",
                status="draft",
                visibility="private",
                duration_hours=source_template_cohort.duration_hours,
            )
            db.add(new_template_cohort)
            await db.flush()

            source_template_sessions = (await db.execute(
                select(Session).where(Session.cohort_id == source_template_cohort.id)
                .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
            )).scalars().all()

            for s in source_template_sessions:
                new_session = Session(
                    id=uuid.uuid4(),
                    cohort_id=new_template_cohort.id,
                    meeting_date=s.meeting_date,
                    starts_at=s.starts_at,
                    title=s.title,
                    duration_hours=s.duration_hours,
                )
                db.add(new_session)
                await db.flush()

                items = (await db.execute(
                    select(DeliveryChecklistItem).where(DeliveryChecklistItem.session_id == s.id)
                    .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                )).scalars().all()
                for item in items:
                    db.add(DeliveryChecklistItem(
                        id=uuid.uuid4(),
                        session_id=new_session.id,
                        role_id=item.role_id,
                        title=item.title,
                        description=item.description,
                        requires_proof=item.requires_proof,
                        is_required=item.is_required,
                        sort_order=item.sort_order,
                        created_by=current_user.id,
                    ))
            if source_template_sessions:
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


async def _get_or_create_template_cohort(db: AsyncSession, program: Program) -> Cohort:
    """Finds or auto-creates the draft template cohort where a program defines its default days & checklists."""
    template_cohort = await db.scalar(
        select(Cohort).where(
            Cohort.program_id == program.id,
            Cohort.name.ilike("%template%"),
        ).order_by(Cohort.created_at.asc())
    )
    if template_cohort is None:
        template_cohort = Cohort(
            id=uuid.uuid4(),
            name=f"[Template] {program.name}",
            program_id=program.id,
            status="draft",
            visibility="private",
            duration_hours=program.duration_hours or 4.0,
        )
        db.add(template_cohort)
        await db.flush()
    return template_cohort


@router.get("/programs/{program_id}/template", response_model=ProgramTemplateOut)
async def get_program_template(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Returns the program's template cohort, default days, and session IDs."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    template_cohort = await _get_or_create_template_cohort(db, program)
    sessions = (await db.execute(
        select(Session).where(Session.cohort_id == template_cohort.id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )).scalars().all()

    return ProgramTemplateOut(
        program_id=program.id,
        template_cohort_id=template_cohort.id,
        days_count=len(sessions),
        sessions=[
            TemplateDayOut(
                id=s.id,
                cohort_id=s.cohort_id,
                day_number=idx + 1,
                title=s.title or f"Day {idx + 1}",
                duration_hours=float(s.duration_hours) if s.duration_hours is not None else None,
                meeting_date=str(s.meeting_date) if s.meeting_date else None,
            )
            for idx, s in enumerate(sessions)
        ],
    )


@router.post("/programs/{program_id}/template-days", response_model=TemplateDayOut, status_code=status.HTTP_201_CREATED)
async def add_program_template_day(
    program_id: uuid.UUID,
    body: TemplateDayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Adds a new default day to the program template."""
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    template_cohort = await _get_or_create_template_cohort(db, program)
    existing_sessions = (await db.execute(
        select(Session).where(Session.cohort_id == template_cohort.id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )).scalars().all()

    next_idx = len(existing_sessions) + 1
    new_day = Session(
        id=uuid.uuid4(),
        cohort_id=template_cohort.id,
        meeting_date=date.today() + timedelta(days=next_idx),
        title=body.title or f"Day {next_idx}",
        duration_hours=body.duration_hours or program.duration_hours or 4.0,
    )
    db.add(new_day)
    await db.commit()
    await db.refresh(new_day)

    return TemplateDayOut(
        id=new_day.id,
        cohort_id=new_day.cohort_id,
        day_number=next_idx,
        title=new_day.title,
        duration_hours=float(new_day.duration_hours) if new_day.duration_hours is not None else None,
        meeting_date=str(new_day.meeting_date),
    )


@router.patch("/programs/{program_id}/template-days/{session_id}", response_model=TemplateDayOut)
async def update_program_template_day(
    program_id: uuid.UUID,
    session_id: uuid.UUID,
    body: TemplateDayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Updates a program template day's title or duration."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template day not found")

    if body.title is not None:
        session.title = body.title.strip()
    if body.duration_hours is not None:
        session.duration_hours = body.duration_hours

    await db.commit()
    await db.refresh(session)

    all_sessions = (await db.execute(
        select(Session).where(Session.cohort_id == session.cohort_id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )).scalars().all()
    day_idx = next((i + 1 for i, s in enumerate(all_sessions) if s.id == session.id), 1)

    return TemplateDayOut(
        id=session.id,
        cohort_id=session.cohort_id,
        day_number=day_idx,
        title=session.title,
        duration_hours=float(session.duration_hours) if session.duration_hours is not None else None,
        meeting_date=str(session.meeting_date),
    )


@router.delete("/programs/{program_id}/template-days/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program_template_day(
    program_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Deletes a template day from the program template."""
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template day not found")

    await db.execute(
        sa_delete(DeliveryChecklistItem).where(DeliveryChecklistItem.session_id == session_id)
    )
    await db.delete(session)
    await db.commit()

