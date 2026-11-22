"""Programs CRUD (V2 R2-3 — registration desk). No dedicated service module —
straightforward CRUD lives directly in the router, matching the established
convention for simple CRUD elsewhere (e.g. routers/instructors/admin.py's
invitation-code endpoints). Every route is gated by require_operations
(admin passes automatically — see core/dependencies.py's RequireRole).
"""

from datetime import date, timedelta
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_operations, require_session_delivery
from app.db.session import get_db
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.material import Material
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.sessions.program_variation import ProgramVariation, ProgramVariationDay
from app.models.sessions.session import Session
from app.models.competitions.judging import CompetitionRubric, CompetitionRubricCriterion
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.sessions.programs import (
    ProgramCloneRequest,
    ProgramCreate,
    ProgramOut,
    ProgramUpdate,
    ProgramVariationCreate,
    ProgramVariationDayCreate,
    ProgramVariationDayOut,
    ProgramVariationDaysReorderIn,
    ProgramVariationDayUpdate,
    ProgramVariationOut,
    ProgramVariationUpdate,
)
from app.services import storage
from app.services.lms.program import PROGRAM_ITEM_PDF_BUCKET
from app.services.org_access import (
    can_read_cohort,
    is_ops_or_admin,
    require_program_manager_or_ops,
    require_program_read_or_ops,
)
from app.services.sessions import variations as var_svc

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
    template_cohort_id: uuid.UUID | None = None
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
    organization_id: uuid.UUID | None = Query(None),
    include_org_programs: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    stmt = select(Program)
    if organization_id is not None:
        stmt = stmt.where(Program.organization_id == organization_id)
    elif not include_org_programs:
        stmt = stmt.where(Program.organization_id.is_(None))
    rows = (await db.execute(stmt.order_by(Program.created_at.desc()))).scalars().all()
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
    if body.organization_id is not None:
        if await db.get(Organization, body.organization_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found")
    if body.default_assessment_config_id is not None:
        if await db.get(AssessmentConfig, body.default_assessment_config_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")

    program = Program(id=uuid.uuid4(), **body.model_dump())
    db.add(program)
    await db.flush()
    if body.organization_id is not None:
        db.add(LmsProgram(
            id=uuid.uuid4(),
            program_id=program.id,
            name=program.name,
            certificate_required=True,
        ))
    await db.commit()
    await db.refresh(program)
    return _program_out_for_user(program, current_user)


def _program_out_for_user(program: Program, current_user: User) -> ProgramOut:
    """Serialize a program while stripping ops-only fields for non-ops callers."""
    out = ProgramOut.model_validate(program)
    if not is_ops_or_admin(current_user):
        out.default_assessment_config_id = None
    return out


@router.get("/programs/{program_id}", response_model=ProgramOut)
async def get_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program = await require_program_read_or_ops(db, program_id, current_user)
    return _program_out_for_user(program, current_user)


def _template_cohort_match():
    return or_(
        Cohort.status == "draft",
        Cohort.name.ilike("[Template]%"),
        func.lower(Cohort.name) == "template",
    )


async def _find_template_cohort(db: AsyncSession, program_id: uuid.UUID) -> Cohort | None:
    return await db.scalar(
        select(Cohort)
        .where(Cohort.program_id == program_id, _template_cohort_match())
        .order_by(Cohort.created_at.asc())
    )


@router.patch("/programs/{program_id}", response_model=ProgramOut)
async def update_program(
    program_id: uuid.UUID,
    body: ProgramUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    program = await require_program_manager_or_ops(db, program_id, current_user)

    changes = body.model_dump(exclude_unset=True)
    if not is_ops_or_admin(current_user):
        changes.pop("default_assessment_config_id", None)
    if "code" in changes and changes["code"] != program.code:
        existing = (await db.execute(select(Program.id).where(Program.code == changes["code"]))).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="A program with this code already exists")
    if changes.get("default_assessment_config_id") is not None:
        if await db.get(AssessmentConfig, changes["default_assessment_config_id"]) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment config not found")

    for field, value in changes.items():
        setattr(program, field, value)
    if "name" in changes:
        lms_prog = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == program.id))
        if lms_prog is not None:
            lms_prog.name = program.name
        template_cohort = await _find_template_cohort(db, program.id)
        if template_cohort is not None:
            template_cohort.name = f"[Template] {program.name}"
            template_cohort.status = "draft"
            template_cohort.visibility = "private"
    await db.commit()
    await db.refresh(program)
    return _program_out_for_user(program, current_user)


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program(
    program_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Only ever deletes an empty program.

    cohorts.program_id cascades, so an unguarded delete here would silently
    take every cohort, session, registration and attendance record with it.
    A program that has been run is history, not a mistake — deactivate it
    (PATCH active=false) instead, which keeps it out of the pickers.
    """
    program = await require_program_manager_or_ops(db, program_id, current_user)

    cohort_count = await db.scalar(
        select(func.count()).select_from(Cohort).where(
            Cohort.program_id == program_id,
            Cohort.is_template_legacy.is_(False),
            Cohort.status != "draft",
            ~Cohort.name.ilike("[Template]%"),
            func.lower(Cohort.name) != "template",
        )
    )
    if cohort_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This program has {cohort_count} cohort(s) and can't be deleted. "
                "Delete those first, or set the program to inactive to hide it."
            ),
        )

    existing_vars = (await db.execute(
        select(ProgramVariation).where(ProgramVariation.program_id == program_id)
    )).scalars().all()
    for v in existing_vars:
        await var_svc.delete_variation(db, program_id=program_id, variation_id=v.id)

    template_cohort_ids = list((
        await db.execute(
            select(Cohort.id).where(Cohort.program_id == program_id, _template_cohort_match())
        )
    ).scalars().all())
    if template_cohort_ids:
        template_session_ids = list((
            await db.execute(select(Session.id).where(Session.cohort_id.in_(template_cohort_ids)))
        ).scalars().all())
        if template_session_ids:
            await db.execute(
                sa_delete(DeliveryChecklistItem).where(DeliveryChecklistItem.session_id.in_(template_session_ids))
            )
            await db.execute(
                sa_delete(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id.in_(template_session_ids))
            )
            await db.execute(sa_delete(Session).where(Session.id.in_(template_session_ids)))
        await db.execute(
            sa_delete(DeliveryChecklistItem).where(DeliveryChecklistItem.cohort_id.in_(template_cohort_ids))
        )
        await db.execute(
            sa_delete(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id.in_(template_cohort_ids))
        )
        await db.execute(sa_delete(Cohort).where(Cohort.id.in_(template_cohort_ids)))

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
        submission_table_config=item.submission_table_config,
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
        duration_hours=source.duration_hours,
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
                is_published=mat.is_published,
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

    if "roles" in body.carry or "checklist" in body.carry:
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
                target_audience=ci.target_audience,
                material_id=ci.material_id,
                link_url=ci.link_url,
                attachments=list(ci.attachments or []),
                sub_items=list(ci.sub_items or []),
                created_by=current_user.id,
            ))
        if source_delivery_items:
            await db.flush()

        # ── Program-level Pre-Session Quiz Assignment ──
        source_prog_quiz = await db.scalar(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.program_id == source.id)
        )
        if source_prog_quiz is not None and source_prog_quiz.preset_id is not None:
            db.add(PreSessionQuizAssignment(
                id=uuid.uuid4(),
                program_id=new_program.id,
                preset_id=source_prog_quiz.preset_id,
            ))
            await db.flush()

        # ── Clone Program Variations (replaces legacy [Template] cohort creation) ──
        source_variations = (await db.execute(
            select(ProgramVariation)
            .where(ProgramVariation.program_id == source.id)
            .order_by(ProgramVariation.is_default.desc(), ProgramVariation.sort_order.asc())
        )).scalars().all()
        if source_variations:
            carry_buckets = {"days", "pre_quiz", "roles", "scalars", "materials", "assessment", "certificate"}
            if "checklist" in body.carry:
                carry_buckets |= {"lms", "component_config", "hints"}
            if "rubric" in body.carry and source.is_competition:
                carry_buckets.add("rubric")
            for sv in source_variations:
                cloned_var = ProgramVariation(
                    id=uuid.uuid4(),
                    program_id=new_program.id,
                    name=sv.name,
                    description=sv.description,
                    is_default=sv.is_default,
                    is_active=sv.is_active,
                    sort_order=sv.sort_order,
                )
                db.add(cloned_var)
                await db.flush()
                await var_svc.copy_variation_contents(
                    db, source=sv, target=cloned_var, carry=carry_buckets, actor_user_id=current_user.id,
                )

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


# ── Program Variations CRUD (first-class defaults, replaces legacy template cohorts) ──

@router.get("/programs/{program_id}/variations", response_model=list[ProgramVariationOut])
async def list_program_variations(
    program_id: uuid.UUID,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_read_or_ops(db, program_id, current_user)
    return await var_svc.list_variations(db, program_id, active_only=active_only)


@router.post("/programs/{program_id}/variations", response_model=ProgramVariationOut, status_code=status.HTTP_201_CREATED)
async def create_program_variation(
    program_id: uuid.UUID,
    body: ProgramVariationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    payload = body.model_dump()
    include_rates = is_ops_or_admin(current_user)
    if not include_rates:
        payload["default_assessment_config_id"] = None
        payload["carry"] = [c for c in payload.get("carry", []) if c != "assessment"]
        if payload.get("mode") == "from_cohort" and payload.get("source_cohort_id") is not None:
            src_cohort = await db.get(Cohort, payload["source_cohort_id"])
            if src_cohort is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source cohort not found")
            if not await can_read_cohort(db, src_cohort, current_user):
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")
    out = await var_svc.create_variation(
        db,
        program_id=program_id,
        payload=payload,
        actor_user_id=current_user.id,
        include_rates=include_rates,
    )
    await db.commit()
    return out


@router.patch("/programs/{program_id}/variations/{variation_id}", response_model=ProgramVariationOut)
async def update_program_variation(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    body: ProgramVariationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    payload = body.model_dump(exclude_unset=True)
    if not is_ops_or_admin(current_user):
        payload.pop("default_assessment_config_id", None)
    out = await var_svc.update_variation(
        db, program_id=program_id, variation_id=variation_id, payload=payload,
    )
    await db.commit()
    return out


@router.delete("/programs/{program_id}/variations/{variation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program_variation(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    await var_svc.delete_variation(db, program_id=program_id, variation_id=variation_id)
    await db.commit()


@router.post(
    "/programs/{program_id}/variations/{variation_id}/days",
    response_model=ProgramVariationDayOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_program_variation_day(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    body: ProgramVariationDayCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    day = await var_svc.add_variation_day(
        db,
        program_id=program_id,
        variation_id=variation_id,
        title=body.title,
        duration_hours=body.duration_hours,
        starts_at=body.starts_at,
        day_number=body.day_number,
    )
    await db.commit()
    await db.refresh(day)
    return day


@router.patch(
    "/programs/{program_id}/variations/{variation_id}/days/{day_id}",
    response_model=ProgramVariationDayOut,
)
async def update_program_variation_day(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    day_id: uuid.UUID,
    body: ProgramVariationDayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    day = await var_svc.update_variation_day(
        db,
        program_id=program_id,
        variation_id=variation_id,
        day_id=day_id,
        payload=body.model_dump(exclude_unset=True),
    )
    await db.commit()
    await db.refresh(day)
    return day


@router.delete(
    "/programs/{program_id}/variations/{variation_id}/days/{day_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_program_variation_day(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    day_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    await var_svc.delete_variation_day(db, program_id=program_id, variation_id=variation_id, day_id=day_id)
    await db.commit()


@router.post(
    "/programs/{program_id}/variations/{variation_id}/days/reorder",
    response_model=list[ProgramVariationDayOut],
)
async def reorder_program_variation_days(
    program_id: uuid.UUID,
    variation_id: uuid.UUID,
    body: ProgramVariationDaysReorderIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_program_manager_or_ops(db, program_id, current_user)
    days = await var_svc.reorder_variation_days(
        db, program_id=program_id, variation_id=variation_id, day_ids=body.day_ids,
    )
    await db.commit()
    return days


# ── Legacy /template & /template-days routes backed by default ProgramVariation ──

@router.get("/programs/{program_id}/template", response_model=ProgramTemplateOut)
async def get_program_template(
    program_id: uuid.UUID,
    variation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Returns the program variation's template days cleanly without creating a draft Cohort."""
    program = await require_program_read_or_ops(db, program_id, current_user)

    var = await var_svc.resolve_variation_for_program(db, program.id, variation_id)
    if var is None:
        return ProgramTemplateOut(
            program_id=program.id,
            template_cohort_id=None,
            days_count=0,
            sessions=[],
        )

    days = await var_svc.variation_days(db, var.id)
    return ProgramTemplateOut(
        program_id=program.id,
        template_cohort_id=var.id,
        days_count=len(days),
        sessions=[
            TemplateDayOut(
                id=d.id,
                cohort_id=d.variation_id,
                day_number=d.day_number,
                title=d.title or f"Day {d.day_number}",
                duration_hours=float(d.duration_hours) if d.duration_hours is not None else None,
                meeting_date=None,
            )
            for d in days
        ],
    )


@router.post("/programs/{program_id}/template-days", response_model=TemplateDayOut, status_code=status.HTTP_201_CREATED)
async def add_program_template_day(
    program_id: uuid.UUID,
    body: TemplateDayCreate,
    variation_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Adds a day to the specified (or default) ProgramVariation."""
    program = await require_program_manager_or_ops(db, program_id, current_user)

    if variation_id is not None:
        var = await var_svc.resolve_variation_for_program(db, program.id, variation_id)
    else:
        var = await var_svc.get_or_create_default_variation(db, program.id)

    day = await var_svc.add_variation_day(
        db,
        program_id=program.id,
        variation_id=var.id,
        title=body.title,
        duration_hours=body.duration_hours if body.duration_hours is not None else (var.duration_hours or program.duration_hours),
    )
    await db.commit()
    await db.refresh(day)
    return TemplateDayOut(
        id=day.id,
        cohort_id=day.variation_id,
        day_number=day.day_number,
        title=day.title,
        duration_hours=float(day.duration_hours) if day.duration_hours is not None else None,
        meeting_date=None,
    )


@router.patch("/programs/{program_id}/template-days/{day_id}", response_model=TemplateDayOut)
async def update_program_template_day(
    program_id: uuid.UUID,
    day_id: uuid.UUID,
    body: TemplateDayUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Updates a ProgramVariationDay's title or duration."""
    await require_program_manager_or_ops(db, program_id, current_user)
    day = await db.get(ProgramVariationDay, day_id)
    if day is not None:
        day = await var_svc.update_variation_day(
            db,
            program_id=program_id,
            variation_id=day.variation_id,
            day_id=day_id,
            payload=body.model_dump(exclude_unset=True),
        )
        await db.commit()
        await db.refresh(day)
        return TemplateDayOut(
            id=day.id,
            cohort_id=day.variation_id,
            day_number=day.day_number,
            title=day.title,
            duration_hours=float(day.duration_hours) if day.duration_hours is not None else None,
            meeting_date=None,
        )

    session = await db.get(Session, day_id)
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


@router.delete("/programs/{program_id}/template-days/{day_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_program_template_day(
    program_id: uuid.UUID,
    day_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Deletes a ProgramVariationDay (or legacy template session)."""
    await require_program_manager_or_ops(db, program_id, current_user)
    day = await db.get(ProgramVariationDay, day_id)
    if day is not None:
        await var_svc.delete_variation_day(db, program_id=program_id, variation_id=day.variation_id, day_id=day_id)
        await db.commit()
        return

    session = await db.get(Session, day_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Template day not found")
    await db.execute(sa_delete(DeliveryChecklistItem).where(DeliveryChecklistItem.session_id == day_id))
    await db.delete(session)
    await db.commit()

