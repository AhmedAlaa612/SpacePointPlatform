from __future__ import annotations

import re
import uuid
import datetime as dt
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_organization_account
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import WebsiteEvent
from app.services.lms.ops_integration import sync_registration_lms
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES, register
from app.services.spine.identity import normalize_user_email, resolve_or_create_contact
from app.services.website_events import resolve_user_organization

router = APIRouter(prefix="/organization", tags=["organization-programs"])


def _is_admin_or_ops(user: User) -> bool:
    return any(r in user.role_values for r in ("admin", "operations"))


def _ensure_org_approved(org: Organization, current_user: User):
    if not _is_admin_or_ops(current_user) and not org.is_approved:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your partner organization account is currently under review by SpacePoint Operations. Program creation and enrollment are locked until approved.",
        )


async def _get_org_or_400(db: AsyncSession, current_user: User) -> Organization:
    org = await resolve_user_organization(db, current_user)
    if org is None:
        if _is_admin_or_ops(current_user):
            org = (await db.execute(select(Organization).order_by(Organization.created_at.asc()))).scalars().first()
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization context found for this account",
            )
    return org


# ── Schemas ──────────────────────────────────────────────────────────────────
class OrganizationProgramCreate(BaseModel):
    name: str
    code: str | None = None
    program_type: str = "competition"  # competition|workshop|course|info_session
    description: str | None = None
    default_capacity: int | None = None
    pricing_model: str = "free"
    price: float | None = None
    completion_rule_type: str = "percentage"
    completion_rule_value: float = 70.0
    keep_course_access_after_completion: bool = True


class OrganizationProgramUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    program_type: str | None = None
    description: str | None = None
    default_capacity: int | None = None
    pricing_model: str | None = None
    price: float | None = None
    completion_rule_type: str | None = None
    completion_rule_value: float | None = None
    keep_course_access_after_completion: bool | None = None


class OrganizationCohortSummary(BaseModel):
    id: uuid.UUID
    name: str
    code: str = ""
    starts_on: date | None = None
    ends_on: date | None = None
    start_date: str = ""
    end_date: str = ""
    location: str | None = None
    status: str = "planned"
    capacity: int | None = None
    visibility: str = "public"
    is_public: bool = True
    registered_count: int = 0
    active_students_count: int = 0
    observers_count: int = 0
    active_observers_count: int = 0
    spots_left: int | None = None
    program_id: uuid.UUID | None = None
    program_name: str | None = None
    checklist_title_override: str | None = None
    linked_event_id: uuid.UUID | None = None
    linked_event_slug: str | None = None


class OrganizationProgramOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    program_type: str
    description: str | None = None
    default_capacity: int | None = None
    pricing_model: str = "free"
    price: float | None = None
    completion_rule_type: str = "percentage"
    completion_rule_value: float = 70.0
    keep_course_access_after_completion: bool = True
    lms_program_id: uuid.UUID | None = None
    created_at: datetime | None = None
    cohorts_count: int = 0
    cohorts: list[OrganizationCohortSummary] = []


class OrganizationCohortCreate(BaseModel):
    program_id: uuid.UUID
    name: str
    starts_on: date | None = None
    ends_on: date | None = None
    capacity: int | None = None
    visibility: str = "public"  # public|private
    poster_template_url: str | None = None
    checklist_title_override: str | None = None


class OrganizationCohortUpdate(BaseModel):
    name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    capacity: int | None = None
    visibility: str | None = None
    poster_template_url: str | None = None
    checklist_title_override: str | None = None
    status: str | None = None


class OrganizationCohortOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    program_name: str
    program_type: str
    name: str
    code: str = ""
    starts_on: date | None = None
    ends_on: date | None = None
    start_date: str = ""
    end_date: str = ""
    location: str | None = None
    status: str
    capacity: int | None = None
    org_capacity_limit: int | None = None
    org_observer_limit: int | None = None
    visibility: str = "public"
    is_public: bool = True
    poster_template_url: str | None = None
    checklist_title_override: str | None = None
    registered_count: int = 0
    active_students_count: int = 0
    observers_count: int = 0
    active_observers_count: int = 0
    spots_left: int | None = None
    landing_event_id: uuid.UUID | None = None
    landing_event_slug: str | None = None
    sessions: list[dict[str, Any]] = []
    linked_events: list[dict[str, Any]] = []
    registrations_count: int = 0


class StudentRegisterIn(BaseModel):
    full_name: str = ""
    student_name: str | None = None
    email: str
    phone: str | None = None
    grade: str | None = None
    city: str | None = None
    school_name: str | None = None
    date_of_birth: str | None = None
    gender: str | None = None

    @property
    def resolved_name(self) -> str:
        return (self.student_name or self.full_name or "").strip()


class BulkStudentImportIn(BaseModel):
    students: list[StudentRegisterIn]


class AddObserverIn(BaseModel):
    user_id: uuid.UUID


class CohortObserverOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    full_name: str
    email: str
    phone: str | None = None
    assigned_at: datetime | None = None


class SessionCreateIn(BaseModel):
    title: str
    session_type: str = "workshop"
    date: dt.date | None = None
    meeting_date: dt.date | None = None
    start_time: str | None = None
    starts_at: str | None = None
    end_time: str | None = None
    duration_hours: float | None = 2.0
    location: str | None = None


class SessionUpdateIn(BaseModel):
    title: str | None = None
    session_type: str | None = None
    date: dt.date | None = None
    meeting_date: dt.date | None = None
    start_time: str | None = None
    starts_at: str | None = None
    end_time: str | None = None
    duration_hours: float | None = None
    location: str | None = None


# ── Programs Endpoints ───────────────────────────────────────────────────────
@router.get("/programs-overview")
async def get_organization_programs_overview(
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)

    programs = (
        await db.execute(
            select(Program)
            .where(Program.organization_id == org.id)
            .order_by(Program.created_at.desc())
        )
    ).scalars().all()

    program_ids = [p.id for p in programs]
    cohorts_by_program: dict[uuid.UUID, list[Cohort]] = {pid: [] for pid in program_ids}

    if program_ids:
        c_rows = (
            await db.execute(
                select(Cohort)
                .where(Cohort.program_id.in_(program_ids))
                .order_by(Cohort.created_at.desc())
            )
        ).scalars().all()
        for c in c_rows:
            cohorts_by_program.setdefault(c.program_id, []).append(c)

    all_cohort_ids = [c.id for plist in cohorts_by_program.values() for c in plist]

    reg_counts: dict[uuid.UUID, int] = {}
    obs_counts: dict[uuid.UUID, int] = {}
    if all_cohort_ids:
        r_rows = (
            await db.execute(
                select(Registration.cohort_id, func.count(Registration.id))
                .where(
                    Registration.cohort_id.in_(all_cohort_ids),
                    Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                )
                .group_by(Registration.cohort_id)
            )
        ).all()
        reg_counts = dict(r_rows)

        o_rows = (
            await db.execute(
                select(LmsProgramAssignment.cohort_id, func.count(LmsProgramAssignment.id))
                .where(
                    LmsProgramAssignment.cohort_id.in_(all_cohort_ids),
                    LmsProgramAssignment.mode == "observer",
                )
                .group_by(LmsProgramAssignment.cohort_id)
            )
        ).all()
        obs_counts = dict(o_rows)

    events_by_cohort: dict[uuid.UUID, WebsiteEvent] = {}
    if all_cohort_ids:
        we_rows = (
            await db.execute(
                select(WebsiteEvent).where(WebsiteEvent.cohort_id.in_(all_cohort_ids))
            )
        ).scalars().all()
        for we in we_rows:
            if we.cohort_id:
                events_by_cohort[we.cohort_id] = we

    events_count = await db.scalar(
        select(func.count(WebsiteEvent.id)).where(WebsiteEvent.organization_id == org.id)
    ) or 0

    lms_prog_map: dict[uuid.UUID, uuid.UUID] = {}
    if program_ids:
        lp_rows = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id.in_(program_ids)))
        ).scalars().all()
        lms_prog_map = {lp.program_id: lp.id for lp in lp_rows if lp.program_id}

    programs_out: list[OrganizationProgramOut] = []
    total_cohorts = 0
    for p in programs:
        c_list = cohorts_by_program.get(p.id, [])
        total_cohorts += len(c_list)
        c_summaries = []
        for c in c_list:
            rc = reg_counts.get(c.id, 0)
            oc = obs_counts.get(c.id, 0)
            spots = max(c.capacity - rc, 0) if c.capacity is not None else None
            linked_ev = events_by_cohort.get(c.id)
            c_summaries.append(
                OrganizationCohortSummary(
                    id=c.id,
                    name=c.name,
                    code=c.name,
                    starts_on=c.starts_on,
                    ends_on=c.ends_on,
                    start_date=c.starts_on.isoformat() if c.starts_on else "",
                    end_date=c.ends_on.isoformat() if c.ends_on else "",
                    location=c.location,
                    status=c.status,
                    capacity=c.capacity,
                    visibility=c.visibility,
                    is_public=c.visibility == "public",
                    registered_count=rc,
                    active_students_count=rc,
                    observers_count=oc,
                    active_observers_count=oc,
                    spots_left=spots,
                    program_id=p.id,
                    program_name=p.name,
                    checklist_title_override=c.checklist_title_override,
                    linked_event_id=linked_ev.id if linked_ev else None,
                    linked_event_slug=linked_ev.slug if linked_ev else None,
                )
            )
        programs_out.append(
            OrganizationProgramOut(
                id=p.id,
                code=p.code,
                name=p.name,
                program_type=p.program_type,
                description=p.description,
                default_capacity=p.default_capacity,
                pricing_model=p.pricing_model or "free",
                price=float(p.price) if p.price is not None else None,
                completion_rule_type=p.completion_rule_type or "percentage",
                completion_rule_value=float(p.completion_rule_value) if p.completion_rule_value is not None else 70.0,
                keep_course_access_after_completion=bool(p.keep_course_access_after_completion),
                lms_program_id=lms_prog_map.get(p.id),
                created_at=p.created_at,
                cohorts_count=len(c_list),
                cohorts=c_summaries,
            )
        )

    return {
        "organization": {
            "id": str(org.id),
            "name_latin": org.name_latin or "",
            "name_arabic": org.name_arabic,
            "org_type": org.org_type or "company",
            "country": org.country,
            "city": org.city,
            "is_approved": bool(org.is_approved),
            "can_publish_events": bool(org.can_publish_events),
            "can_author_courses": bool(org.can_author_courses),
            "can_publish_courses": bool(org.can_publish_courses),
            "course_scope_all": bool(org.course_scope_all),
            "allowed_course_ids": org.allowed_course_ids or [],
            "max_events": org.max_events,
            "max_programs": org.max_programs,
            "max_cohorts": org.max_cohorts,
            "max_students_per_cohort": org.max_students_per_cohort,
            "max_observers_per_cohort": org.max_observers_per_cohort,
        },
        "programs": programs_out,
        "quotas": {
            "programs_count": len(programs),
            "max_programs": org.max_programs,
            "cohorts_count": total_cohorts,
            "max_cohorts": org.max_cohorts,
            "events_count": events_count,
            "max_events": org.max_events,
            "max_students_per_cohort": org.max_students_per_cohort,
            "max_observers_per_cohort": org.max_observers_per_cohort,
        },
    }


@router.post("/programs", response_model=OrganizationProgramOut, status_code=status.HTTP_201_CREATED)
async def create_organization_program(
    body: OrganizationProgramCreate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    _ensure_org_approved(org, current_user)

    if org.max_programs is not None and not _is_admin_or_ops(current_user):
        curr_count = await db.scalar(
            select(func.count(Program.id)).where(Program.organization_id == org.id)
        ) or 0
        if curr_count >= org.max_programs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_programs} program(s). Contact the SpacePoint team to increase your limit.",
            )

    if body.code and body.code.strip():
        code = body.code.strip().upper()
        # Verify uniqueness
        existing = await db.scalar(select(func.count(Program.id)).where(Program.code == code))
        if existing:
            code = f"{code[:24]}-{uuid.uuid4().hex[:4].upper()}"
    else:
        code_base = re.sub(r"[^A-Za-z0-9]+", "", org.name_latin or "ORG")[:6].upper()
        code = f"{code_base}-{uuid.uuid4().hex[:6].upper()}"

    program = Program(
        code=code,
        name=body.name.strip(),
        program_type=body.program_type.strip().lower(),
        description=body.description.strip() if body.description else None,
        default_capacity=body.default_capacity,
        pricing_model=body.pricing_model if body.pricing_model in ("paid", "free") else "free",
        price=body.price if body.pricing_model == "paid" else None,
        completion_rule_type=body.completion_rule_type if body.completion_rule_type in ("percentage", "session_count") else "percentage",
        completion_rule_value=body.completion_rule_value or 70.0,
        keep_course_access_after_completion=body.keep_course_access_after_completion,
        organization_id=org.id,
    )
    db.add(program)
    await db.flush()

    # Automatically create companion LmsProgram checklist template
    lms_prog = LmsProgram(
        program_id=program.id,
        name=program.name,
        certificate_required=True,
    )
    db.add(lms_prog)

    await db.commit()
    await db.refresh(program)
    await db.refresh(lms_prog)

    return OrganizationProgramOut(
        id=program.id,
        code=program.code,
        name=program.name,
        program_type=program.program_type,
        description=program.description,
        default_capacity=program.default_capacity,
        pricing_model=program.pricing_model,
        price=float(program.price) if program.price is not None else None,
        completion_rule_type=program.completion_rule_type,
        completion_rule_value=float(program.completion_rule_value) if program.completion_rule_value is not None else 70.0,
        keep_course_access_after_completion=program.keep_course_access_after_completion,
        lms_program_id=lms_prog.id,
        created_at=program.created_at,
        cohorts_count=0,
        cohorts=[],
    )


@router.patch("/programs/{program_id}", response_model=OrganizationProgramOut)
async def update_organization_program(
    program_id: uuid.UUID,
    body: OrganizationProgramUpdate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    program = await db.get(Program, program_id)
    if program is None or (program.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Program not found")

    if body.name is not None and body.name.strip():
        program.name = body.name.strip()
        lms_prog = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))
        ).scalars().first()
        if lms_prog:
            lms_prog.name = program.name
    if body.description is not None:
        program.description = body.description.strip() or None
    if body.program_type is not None and body.program_type.strip():
        program.program_type = body.program_type.strip().lower()
    if body.default_capacity is not None:
        program.default_capacity = body.default_capacity
    if body.pricing_model is not None:
        program.pricing_model = body.pricing_model
    if body.price is not None:
        program.price = body.price
    if body.completion_rule_type is not None:
        program.completion_rule_type = body.completion_rule_type
    if body.completion_rule_value is not None:
        program.completion_rule_value = body.completion_rule_value
    if body.keep_course_access_after_completion is not None:
        program.keep_course_access_after_completion = body.keep_course_access_after_completion

    await db.commit()
    await db.refresh(program)

    lms_prog = (
        await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))
    ).scalars().first()

    return OrganizationProgramOut(
        id=program.id,
        code=program.code,
        name=program.name,
        program_type=program.program_type,
        description=program.description,
        default_capacity=program.default_capacity,
        pricing_model=program.pricing_model,
        price=float(program.price) if program.price is not None else None,
        completion_rule_type=program.completion_rule_type,
        completion_rule_value=float(program.completion_rule_value) if program.completion_rule_value is not None else 70.0,
        keep_course_access_after_completion=program.keep_course_access_after_completion,
        lms_program_id=lms_prog.id if lms_prog else None,
        created_at=program.created_at,
        cohorts_count=0,
        cohorts=[],
    )


@router.delete("/programs/{program_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization_program(
    program_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    program = await db.get(Program, program_id)
    if program is None or (program.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Program not found")

    has_cohorts = await db.scalar(
        select(func.count(Cohort.id)).where(Cohort.program_id == program.id)
    ) or 0
    if has_cohorts > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a program that has cohorts. Delete or reassign cohorts first.",
        )

    await db.delete(program)
    await db.commit()
    return None


# ── Cohorts Endpoints ────────────────────────────────────────────────────────
@router.post("/cohorts", response_model=OrganizationCohortOut, status_code=status.HTTP_201_CREATED)
async def create_organization_cohort(
    body: OrganizationCohortCreate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    _ensure_org_approved(org, current_user)

    program = await db.get(Program, body.program_id)
    if program is None or (program.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Program not found")

    if org.max_cohorts is not None and not _is_admin_or_ops(current_user):
        curr_cohorts = await db.scalar(
            select(func.count(Cohort.id)).where(Cohort.organization_id == org.id)
        ) or 0
        if curr_cohorts >= org.max_cohorts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_cohorts} cohort(s). Contact the SpacePoint team to increase your limit.",
            )

    capacity = body.capacity
    if org.max_students_per_cohort is not None and not _is_admin_or_ops(current_user):
        if capacity is None:
            capacity = org.max_students_per_cohort
        elif capacity > org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort. Contact the SpacePoint team to increase your limit.",
            )

    cohort = Cohort(
        program_id=program.id,
        name=body.name.strip(),
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        capacity=capacity,
        visibility=body.visibility if body.visibility in ("public", "private") else "public",
        status="registration_open",
        organization_id=org.id,
        poster_template_url=body.poster_template_url,
        checklist_title_override=body.checklist_title_override,
    )
    db.add(cohort)
    await db.flush()

    # Ensure LmsProgram exists
    lms_prog = (
        await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))
    ).scalars().first()
    if lms_prog is None:
        lms_prog = LmsProgram(program_id=program.id, name=program.name)
        db.add(lms_prog)
        await db.flush()

    # Provision cohort override
    override = LmsProgramCohortOverride(cohort_id=cohort.id, lms_program_id=lms_prog.id)
    db.add(override)

    await db.commit()
    await db.refresh(cohort)

    return await get_organization_cohort_detail(cohort.id, current_user, db)


@router.get("/cohorts/{cohort_id}", response_model=OrganizationCohortOut)
async def get_organization_cohort_detail(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    program = await db.get(Program, cohort.program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Parent program not found")

    reg_count = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.cohort_id == cohort.id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    ) or 0

    obs_count = await db.scalar(
        select(func.count(LmsProgramAssignment.id)).where(
            LmsProgramAssignment.cohort_id == cohort.id,
            LmsProgramAssignment.mode == "observer",
        )
    ) or 0

    spots = max(cohort.capacity - reg_count, 0) if cohort.capacity is not None else None

    # Linked landing page event
    landing_event = (
        await db.execute(
            select(WebsiteEvent).where(WebsiteEvent.cohort_id == cohort.id).limit(1)
        )
    ).scalars().first()

    session_rows = (
        await db.execute(
            select(Session)
            .where(Session.cohort_id == cohort.id)
            .order_by(Session.meeting_date.asc().nullslast(), Session.created_at.asc())
        )
    ).scalars().all()

    sessions_list = [
        {
            "id": str(s.id),
            "title": s.title or "Session",
            "session_type": "workshop",
            "date": s.meeting_date.isoformat() if s.meeting_date else "",
            "start_time": str(s.starts_at) if s.starts_at else "",
            "end_time": "",
            "location": cohort.location or "",
        }
        for s in session_rows
    ]

    linked_events_list = []
    if landing_event:
        linked_events_list.append({
            "id": str(landing_event.id),
            "slug": landing_event.slug,
            "title": landing_event.title_latin,
            "is_published": landing_event.is_published,
        })

    return OrganizationCohortOut(
        id=cohort.id,
        program_id=program.id,
        program_name=program.name,
        program_type=program.program_type,
        name=cohort.name,
        code=cohort.name,
        starts_on=cohort.starts_on,
        ends_on=cohort.ends_on,
        start_date=cohort.starts_on.isoformat() if cohort.starts_on else "",
        end_date=cohort.ends_on.isoformat() if cohort.ends_on else "",
        location=cohort.location or None,
        status=cohort.status,
        capacity=cohort.capacity,
        org_capacity_limit=org.max_students_per_cohort,
        org_observer_limit=org.max_observers_per_cohort,
        visibility=cohort.visibility,
        is_public=cohort.visibility == "public",
        poster_template_url=cohort.poster_template_url,
        checklist_title_override=cohort.checklist_title_override,
        registered_count=reg_count,
        active_students_count=reg_count,
        observers_count=obs_count,
        active_observers_count=obs_count,
        spots_left=spots,
        landing_event_id=landing_event.id if landing_event else None,
        landing_event_slug=landing_event.slug if landing_event else None,
        sessions=sessions_list,
        linked_events=linked_events_list,
        registrations_count=reg_count,
    )


@router.patch("/cohorts/{cohort_id}", response_model=OrganizationCohortOut)
@router.put("/cohorts/{cohort_id}", response_model=OrganizationCohortOut)
async def update_organization_cohort(
    cohort_id: uuid.UUID,
    body: OrganizationCohortUpdate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    if body.capacity is not None and org.max_students_per_cohort is not None and not _is_admin_or_ops(current_user):
        if body.capacity > org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort. Contact the SpacePoint team to increase your limit.",
            )

    updates = body.model_dump(exclude_unset=True)
    if "start_date" in updates:
        cohort.starts_on = updates.pop("start_date")
    if "end_date" in updates:
        cohort.ends_on = updates.pop("end_date")
    if "is_public" in updates:
        cohort.visibility = "public" if updates.pop("is_public") else "private"
    if "code" in updates:
        updates.pop("code")  # Cohort model does not have a code column
    for k, v in updates.items():
        if hasattr(cohort, k):
            setattr(cohort, k, v)

    await db.commit()
    await db.refresh(cohort)
    return await get_organization_cohort_detail(cohort_id, current_user, db)


@router.post("/cohorts/{cohort_id}/duplicate", response_model=OrganizationCohortOut, status_code=status.HTTP_201_CREATED)
async def duplicate_organization_cohort(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Duplicates a cohort and clones its full milestone checklist items so the
    organization can reuse its setup for a new batch in 1 click."""
    org = await _get_org_or_400(db, current_user)
    source = await db.get(Cohort, cohort_id)
    if source is None or (source.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Source cohort not found")

    if org.max_cohorts is not None and not _is_admin_or_ops(current_user):
        curr_cohorts = await db.scalar(
            select(func.count(Cohort.id)).where(Cohort.organization_id == org.id)
        ) or 0
        if curr_cohorts >= org.max_cohorts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_cohorts} cohort(s). Contact the SpacePoint team to increase your limit.",
            )

    new_cohort = Cohort(
        program_id=source.program_id,
        name=f"{source.name} (Copy)",
        starts_on=source.starts_on,
        ends_on=source.ends_on,
        capacity=source.capacity,
        visibility=source.visibility,
        status="registration_open",
        organization_id=org.id,
        poster_template_url=source.poster_template_url,
        checklist_title_override=source.checklist_title_override,
    )
    db.add(new_cohort)
    await db.flush()

    source_override = (
        await db.execute(
            select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == source.id)
        )
    ).scalars().first()

    lms_prog_id = source_override.lms_program_id if source_override else None
    if not lms_prog_id:
        lms_prog = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id == source.program_id))
        ).scalars().first()
        lms_prog_id = lms_prog.id if lms_prog else None

    if lms_prog_id:
        new_override = LmsProgramCohortOverride(cohort_id=new_cohort.id, lms_program_id=lms_prog_id)
        db.add(new_override)
        await db.flush()

        if source_override:
            source_items = (
                await db.execute(
                    select(LmsProgramItem).where(
                        LmsProgramItem.owner_type == "cohort_override",
                        LmsProgramItem.owner_id == source_override.id,
                    )
                )
            ).scalars().all()
            for item in source_items:
                cloned_item = LmsProgramItem(
                    owner_type="cohort_override",
                    owner_id=new_override.id,
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
                    pdf_path=item.pdf_path,
                    deadline_at=item.deadline_at,
                    max_team_size=item.max_team_size,
                    session_date=item.session_date,
                    session_starts_at=item.session_starts_at,
                    session_location=item.session_location,
                    session_meeting_url=item.session_meeting_url,
                    checkpoint_label=item.checkpoint_label,
                    gated=item.gated,
                    guideline_kind=item.guideline_kind,
                    guideline_url=item.guideline_url,
                    cohort_quiz_template_id=item.cohort_quiz_template_id,
                    arcade_game_id=item.arcade_game_id,
                    arcade_game_mode=item.arcade_game_mode,
                )
                db.add(cloned_item)

    await db.commit()
    await db.refresh(new_cohort)
    return await get_organization_cohort_detail(new_cohort.id, current_user, db)


# ── Registrations / Student Enrollment ───────────────────────────────────────
@router.get("/cohorts/{cohort_id}/registrations")
async def list_cohort_registrations(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    rows = (
        await db.execute(
            select(Registration, Contact, User)
            .join(Contact, Contact.id == Registration.contact_id)
            .outerjoin(User, User.contact_id == Contact.id)
            .where(
                Registration.cohort_id == cohort_id,
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
            .order_by(Registration.created_at.desc())
        )
    ).all()

    out = []
    for reg, contact, user in rows:
        out.append({
            "id": str(reg.id),
            "contact_id": str(contact.id),
            "user_id": str(user.id) if user else None,
            "full_name": contact.full_name,
            "email": contact.email,
            "phone": contact.phone,
            "status": reg.status,
            "created_at": reg.created_at,
            "ticket_token": reg.ticket_token,
        })
    return out


@router.post("/cohorts/{cohort_id}/registrations", status_code=status.HTTP_201_CREATED)
async def register_student_to_cohort(
    cohort_id: uuid.UUID,
    body: StudentRegisterIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    _ensure_org_approved(org, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    active_count = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.cohort_id == cohort.id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    ) or 0

    if org.max_students_per_cohort is not None and not _is_admin_or_ops(current_user):
        if active_count >= org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort. Contact the SpacePoint team to increase your limit.",
            )

    if cohort.capacity is not None and active_count >= cohort.capacity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cohort capacity reached ({cohort.capacity} spots)",
        )

    email = normalize_user_email(body.email)
    contact, _ = await resolve_or_create_contact(
        db,
        full_name=body.full_name.strip(),
        email=email,
        phone=body.phone.strip() if body.phone else None,
        grade=body.grade,
        organization_id=org.id,
        contact_roles=["student"],
        role_event_source="org_cohort_registration",
    )

    reg = await register(
        db,
        contact_id=contact.id,
        cohort_id=cohort.id,
        price_charged=0,
        registered_via="import",
    )

    await sync_registration_lms(
        db,
        registration=reg,
        cohort=cohort,
        create_account=True,
        send_welcome_email=True,
    )
    await db.commit()
    await db.refresh(reg)

    return {"message": "Student registered successfully", "registration_id": str(reg.id)}


@router.post("/cohorts/{cohort_id}/bulk-import")
@router.post("/cohorts/{cohort_id}/registrations/bulk-import")
async def bulk_import_students_to_cohort(
    cohort_id: uuid.UUID,
    body: BulkStudentImportIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    _ensure_org_approved(org, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    incoming_count = len(body.students)
    if incoming_count == 0:
        return {"registered": 0, "imported": 0, "failed": 0, "errors": []}

    active_count = await db.scalar(
        select(func.count(Registration.id)).where(
            Registration.cohort_id == cohort.id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    ) or 0

    if org.max_students_per_cohort is not None and not _is_admin_or_ops(current_user):
        if (active_count + incoming_count) > org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Importing {incoming_count} student(s) would exceed your organization limit of {org.max_students_per_cohort} per cohort. (Currently {active_count} enrolled).",
            )

    registered_count = 0
    errors: list[dict[str, Any]] = []

    for idx, item in enumerate(body.students):
        try:
            name = item.resolved_name
            if not name:
                errors.append({"row": idx + 1, "reason": "Missing student name"})
                continue
            email = normalize_user_email(item.email)
            contact, _ = await resolve_or_create_contact(
                db,
                full_name=name,
                email=email,
                phone=item.phone.strip() if item.phone else None,
                grade=item.grade,
                organization_id=org.id,
                contact_roles=["student"],
                role_event_source="org_bulk_import",
            )
            reg = await register(
                db,
                contact_id=contact.id,
                cohort_id=cohort.id,
                price_charged=0,
                registered_via="import",
            )
            await sync_registration_lms(
                db,
                registration=reg,
                cohort=cohort,
                create_account=True,
                send_welcome_email=True,
            )
            registered_count += 1
        except Exception as exc:
            errors.append({"row": idx + 1, "reason": f"{item.email}: {exc}"})

    await db.commit()
    return {
        "registered": registered_count,
        "imported": registered_count,
        "failed": len(errors),
        "errors": errors,
    }


@router.delete("/cohorts/{cohort_id}/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_cohort_registration(
    cohort_id: uuid.UUID,
    registration_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    reg = await db.get(Registration, registration_id)
    if reg is None or reg.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Registration not found")

    reg.status = "cancelled"
    await db.commit()
    return None


# ── Observers Endpoints ─────────────────────────────────────────────────────
@router.get("/cohorts/{cohort_id}/observers", response_model=list[CohortObserverOut])
async def list_cohort_observers(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    rows = (
        await db.execute(
            select(LmsProgramAssignment, User)
            .join(User, User.id == LmsProgramAssignment.user_id)
            .where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.mode == "observer",
            )
            .order_by(LmsProgramAssignment.assigned_at.desc())
        )
    ).all()

    return [
        CohortObserverOut(
            id=assign.id,
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            phone=user.phone,
            assigned_at=assign.assigned_at,
        )
        for assign, user in rows
    ]


@router.post("/cohorts/{cohort_id}/observers", response_model=CohortObserverOut, status_code=status.HTTP_201_CREATED)
async def add_cohort_observer(
    cohort_id: uuid.UUID,
    body: AddObserverIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    target_user = await db.get(User, body.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    is_team_member = False
    if target_user.organization_id == org.id or target_user.id == org.owner_user_id:
        is_team_member = True
    elif target_user.contact_id:
        contact = await db.get(Contact, target_user.contact_id)
        if contact and contact.organization_id == org.id:
            is_team_member = True

    if not is_team_member and not _is_admin_or_ops(current_user):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only members of your organization team can be assigned as observers.",
        )

    active_count = await db.scalar(
        select(func.count(LmsProgramAssignment.id)).where(
            LmsProgramAssignment.cohort_id == cohort.id,
            LmsProgramAssignment.mode == "observer",
        )
    ) or 0

    if org.max_observers_per_cohort is not None and not _is_admin_or_ops(current_user):
        if active_count >= org.max_observers_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_observers_per_cohort} observer(s) per cohort. Contact the SpacePoint team to increase your limit.",
            )

    from app.services.lms.program import assign_lms_program
    assignment = await assign_lms_program(db, user_id=target_user.id, cohort_id=cohort.id, mode="observer")
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not assign observer to cohort checklist. Ensure cohort program has checklist items.",
        )
    assignment.mode = "observer"

    if "observer" not in target_user.role_values and "student" not in target_user.role_values:
        roles = list(target_user.roles or [])
        roles.append(UserRole.OBSERVER)
        target_user.roles = roles

    await db.commit()
    await db.refresh(assignment)

    return CohortObserverOut(
        id=assignment.id,
        user_id=target_user.id,
        full_name=target_user.full_name,
        email=target_user.email,
        phone=target_user.phone,
        assigned_at=assignment.assigned_at,
    )


@router.delete("/cohorts/{cohort_id}/observers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_cohort_observer(
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    assignment = (
        await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.user_id == user_id,
                LmsProgramAssignment.mode == "observer",
            )
        )
    ).scalars().first()

    if assignment is None:
        raise HTTPException(status_code=404, detail="Observer assignment not found")

    await db.delete(assignment)
    await db.commit()
    return None


# ── Sessions Endpoints ───────────────────────────────────────────────────────
@router.get("/cohorts/{cohort_id}/sessions")
async def list_cohort_sessions(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    rows = (
        await db.execute(
            select(Session)
            .where(Session.cohort_id == cohort_id)
            .order_by(Session.meeting_date.asc().nullslast(), Session.created_at.asc())
        )
    ).scalars().all()

    return [
        {
            "id": str(s.id),
            "title": s.title,
            "meeting_date": str(s.meeting_date) if s.meeting_date else None,
            "starts_at": s.starts_at,
            "duration_hours": float(s.duration_hours) if s.duration_hours else None,
        }
        for s in rows
    ]


@router.post("/cohorts/{cohort_id}/sessions", status_code=status.HTTP_201_CREATED)
async def create_cohort_session(
    cohort_id: uuid.UUID,
    body: SessionCreateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    meeting_date = body.meeting_date or body.date or date.today()
    starts_at = body.starts_at or body.start_time

    s = Session(
        cohort_id=cohort.id,
        title=body.title.strip(),
        meeting_date=meeting_date,
        starts_at=starts_at,
        duration_hours=body.duration_hours,
        staffing_status="staffed",
    )
    db.add(s)
    await db.commit()
    await db.refresh(s)

    return {
        "id": str(s.id),
        "title": s.title,
        "meeting_date": str(s.meeting_date) if s.meeting_date else None,
        "starts_at": str(s.starts_at) if s.starts_at else None,
        "duration_hours": float(s.duration_hours) if s.duration_hours else None,
    }


@router.patch("/cohorts/{cohort_id}/sessions/{session_id}")
@router.put("/cohorts/{cohort_id}/sessions/{session_id}")
async def update_cohort_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    body: SessionUpdateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    s = await db.get(Session, session_id)
    if s is None or s.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.model_dump(exclude_unset=True)
    if "date" in updates:
        s.meeting_date = updates.pop("date")
    if "start_time" in updates:
        s.starts_at = updates.pop("start_time")
    for k, v in updates.items():
        if hasattr(s, k):
            setattr(s, k, v)

    await db.commit()
    await db.refresh(s)
    return {
        "id": str(s.id),
        "title": s.title,
        "meeting_date": str(s.meeting_date) if s.meeting_date else None,
        "starts_at": s.starts_at,
        "duration_hours": float(s.duration_hours) if s.duration_hours else None,
    }


@router.delete("/cohorts/{cohort_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or (cohort.organization_id != org.id and not _is_admin_or_ops(current_user)):
        raise HTTPException(status_code=404, detail="Cohort not found")

    s = await db.get(Session, session_id)
    if s is None or s.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(s)
    await db.commit()
    return None
