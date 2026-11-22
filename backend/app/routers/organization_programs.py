from __future__ import annotations

import re
import uuid
import datetime as dt
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import and_, delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_organization_account
from app.db.session import get_db
from app.models.competitions.judging import CompetitionJudge
from app.models.enums import UserRole
from app.models.inventory.location import Location
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import (
    PreSessionQuizAssignment,
    PreSessionQuizAttempt,
    PreSessionQuizPreset,
)
from app.models.sessions.program import Program
from app.models.sessions.program_variation import ProgramVariation
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import TeamMember
from app.models.user import User
from app.models.website_event import WebsiteEvent
from app.services.lms.ops_integration import deactivate_registration_enrollments, sync_registration_lms
from app.services.lms.program import team_for_cohort_member
from app.services.org_access import (
    can_manage_cohort_delivery,
    can_org_use_shared_program,
    can_read_cohort,
    cohort_organization_id,
    effective_org_role,
    effective_org_roles,
    global_roles_for_org_role,
    has_org_role,
    is_ops_or_admin,
    is_partner_managed,
    is_program_allowed_for_org,
    is_spacepoint_managed,
    require_cohort_delivery_manager_or_ops,
    require_org_manager,
    resolve_target_org_for_actor,
)
from app.services.sessions import variations as var_svc
from app.services.sessions.cohort_seeding import seed_cohort_from_program
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


async def _get_org_or_400(
    db: AsyncSession,
    current_user: User,
    organization_id: uuid.UUID | None = None,
) -> Organization:
    if organization_id is None and _is_admin_or_ops(current_user):
        org = await resolve_user_organization(db, current_user)
        if org is None:
            org = (await db.execute(select(Organization).order_by(Organization.created_at.asc()))).scalars().first()
        if org is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization context found for this account",
            )
        return org
    return await resolve_target_org_for_actor(db, current_user, organization_id)


async def _resolve_cohort_and_org(
    db: AsyncSession,
    cohort_id: uuid.UUID,
    current_user: User,
    *,
    not_found_detail: str = "Cohort not found",
    read_only: bool = False,
) -> tuple[Cohort, Organization]:
    """Resolve both a cohort and its owning Organization from the cohort itself.

    When Ops/Admin co-manages an org cohort, `org` is always the cohort's own
    organization (never the caller's arbitrary first org). For org users, verifies
    the cohort belongs to their organization.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    program = await db.get(Program, cohort.program_id)
    cohort_org_id = cohort.organization_id or (program.organization_id if program else None)

    if _is_admin_or_ops(current_user):
        if cohort_org_id is not None:
            org = await db.get(Organization, cohort_org_id)
            if org is None:
                raise HTTPException(status_code=404, detail="Organization not found")
            return cohort, org
        return cohort, await _get_org_or_400(db, current_user)

    org = await _get_org_or_400(db, current_user)
    if cohort_org_id != org.id:
        raise HTTPException(status_code=404, detail=not_found_detail)
    if read_only and not await can_read_cohort(db, cohort, current_user):
        raise HTTPException(status_code=403, detail="Operation not permitted")
    return cohort, org


def _preset_question_count(p: dict[str, Any]) -> int:
    q_ids = p.get("question_ids") or []
    if q_ids:
        return len(q_ids)
    return sum(
        len(ph.get("questions") or ph.get("question_ids") or [])
        for ph in (p.get("phases") or [])
    )


# ── Schemas ──────────────────────────────────────────────────────────────────
class OrganizationProgramCreate(BaseModel):
    name: str
    code: str | None = None
    program_type: str = "competition"  # competition|workshop|course|info_session
    description: str | None = None
    default_capacity: int | None = None
    duration_hours: float | None = None
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
    duration_hours: float | None = None
    pricing_model: str | None = None
    price: float | None = None
    completion_rule_type: str | None = None
    completion_rule_value: float | None = None
    keep_course_access_after_completion: bool | None = None
    active: bool | None = None


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
    duration_hours: float | None = None
    visibility: str = "public"
    is_public: bool = True
    registered_count: int = 0
    active_students_count: int = 0
    observers_count: int = 0
    active_observers_count: int = 0
    spots_left: int | None = None
    sessions_count: int = 0
    unstaffed_count: int = 0
    program_id: uuid.UUID | None = None
    program_name: str | None = None
    variation_id: uuid.UUID | None = None
    variation_name: str | None = None
    management_mode: str = "spacepoint"
    location_id: uuid.UUID | None = None
    location_name: str | None = None
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
    duration_hours: float | None = None
    pricing_model: str = "free"
    price: float | None = None
    completion_rule_type: str = "percentage"
    completion_rule_value: float = 70.0
    keep_course_access_after_completion: bool = True
    is_org_owned: bool = True
    is_shared_program: bool = False
    can_create_cohort: bool = True
    active: bool = True
    lms_program_id: uuid.UUID | None = None
    default_certificate_template_id: uuid.UUID | None = None
    created_at: datetime | None = None
    cohorts_count: int = 0
    cohorts: list[OrganizationCohortSummary] = []


class OrganizationCohortCreate(BaseModel):
    program_id: uuid.UUID
    name: str
    starts_on: date | None = None
    ends_on: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity: int | None = None
    duration_hours: float | None = None
    location_id: uuid.UUID | None = None
    location: str | None = None
    visibility: str = "private"  # public|private
    is_public: bool | None = None
    status: str | None = None
    variation_id: uuid.UUID | None = None
    poster_template_url: str | None = None
    checklist_title_override: str | None = None


class OrganizationCohortUpdate(BaseModel):
    name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    capacity: int | None = None
    duration_hours: float | None = None
    location_id: uuid.UUID | None = None
    location: str | None = None
    visibility: str | None = None
    is_public: bool | None = None
    variation_id: uuid.UUID | None = None
    poster_template_url: str | None = None
    checklist_title_override: str | None = None
    status: str | None = None


class OrganizationCohortOut(BaseModel):
    id: uuid.UUID
    program_id: uuid.UUID
    program_name: str
    program_type: str
    management_mode: str = "spacepoint"
    can_manage_delivery: bool = True
    name: str
    code: str = ""
    starts_on: date | None = None
    ends_on: date | None = None
    start_date: str = ""
    end_date: str = ""
    location: str | None = None
    location_id: uuid.UUID | None = None
    location_name: str | None = None
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


def _coerce_time(value) -> dt.time | None:
    """Parse an ``HH:MM`` string from the UI into a real ``datetime.time``.

    ``sessions.starts_at`` is a Postgres ``TIME`` column. The org session form
    sends a string, and asyncpg refuses to bind str to TIME (it expects
    ``.hour``), so convert before it reaches the model. Accepts ``HH:MM``,
    ``HH:MM:SS``, ``h:MM AM/PM`` and already-parsed time/datetime values.
    """
    if value is None or value == "":
        return None
    if isinstance(value, dt.time):
        return value
    if isinstance(value, dt.datetime):
        return value.timetz().replace(tzinfo=None)

    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            return dt.datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise HTTPException(status_code=422, detail=f"Invalid time value: {value!r}")


class AssignOrgInstructorIn(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID | None = None
    # None = every session in the cohort (the "assign them to a cohort" action);
    # otherwise only these sessions.
    session_ids: list[uuid.UUID] | None = None


class UpdateOrgInstructorRoleIn(BaseModel):
    role_id: uuid.UUID


class AssignOrgJudgeIn(BaseModel):
    user_id: uuid.UUID


class OrgReadinessAssignIn(BaseModel):
    preset_id: uuid.UUID | None = None


# ── Programs Endpoints ───────────────────────────────────────────────────────
@router.get("/programs-overview")
async def get_organization_programs_overview(
    organization_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user, organization_id=organization_id)
    if not _is_admin_or_ops(current_user):
        roles = effective_org_roles(current_user, is_owner=(org.owner_user_id == current_user.id))
        if not any(r in ("owner", "coordinator", "observer") for r in roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Operation not permitted")

    # Include both org-owned programs AND any SpacePoint program that has a
    # cohort assigned to this org (e.g. Ops created a cohort for the org).
    direct_org_cohorts = (
        await db.execute(
            select(Cohort)
            .where(
                Cohort.organization_id == org.id,
                Cohort.is_template_legacy.is_(False),
                Cohort.status != "draft",
                ~Cohort.name.ilike("[Template]%"),
                func.lower(func.trim(Cohort.name)) != "template",
            )
            .order_by(Cohort.created_at.desc())
        )
    ).scalars().all()
    extra_program_ids = {c.program_id for c in direct_org_cohorts}

    scope = (getattr(org, "program_scope", None) or "own").strip().lower()
    shared_cond = None
    if scope == "all":
        shared_cond = and_(Program.organization_id.is_(None), Program.active.is_(True))
    elif scope == "selected":
        allowed_ids: list[uuid.UUID] = []
        for raw_pid in (getattr(org, "allowed_program_ids", None) or []):
            try:
                allowed_ids.append(uuid.UUID(str(raw_pid)))
            except ValueError:
                continue
        if allowed_ids:
            shared_cond = and_(
                Program.organization_id.is_(None),
                Program.active.is_(True),
                Program.id.in_(allowed_ids),
            )

    prog_conds = [Program.organization_id == org.id]
    if extra_program_ids:
        prog_conds.append(Program.id.in_(extra_program_ids))
    if shared_cond is not None:
        prog_conds.append(shared_cond)

    programs = (
        await db.execute(
            select(Program)
            .where(or_(*prog_conds))
            .order_by(Program.created_at.desc())
        )
    ).scalars().all()

    program_ids = [p.id for p in programs]
    owned_program_ids = {p.id for p in programs if p.organization_id == org.id}
    cohorts_by_program: dict[uuid.UUID, list[Cohort]] = {pid: [] for pid in program_ids}

    if program_ids:
        c_rows = (
            await db.execute(
                select(Cohort)
                .where(
                    or_(
                        Cohort.organization_id == org.id,
                        Cohort.program_id.in_(owned_program_ids) if owned_program_ids else False,
                    ),
                    Cohort.is_template_legacy.is_(False),
                    Cohort.status != "draft",
                    ~Cohort.name.ilike("[Template]%"),
                    func.lower(func.trim(Cohort.name)) != "template",
                )
                .order_by(Cohort.created_at.desc())
            )
        ).scalars().all()
        for c in c_rows:
            cohorts_by_program.setdefault(c.program_id, []).append(c)

    all_cohort_ids = [c.id for plist in cohorts_by_program.values() for c in plist]

    reg_counts: dict[uuid.UUID, int] = {}
    obs_counts: dict[uuid.UUID, int] = {}
    session_counts: dict[uuid.UUID, int] = {}
    unstaffed_counts: dict[uuid.UUID, int] = {}
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

        s_rows = (
            await db.execute(
                select(Session.cohort_id, func.count(Session.id))
                .where(Session.cohort_id.in_(all_cohort_ids))
                .group_by(Session.cohort_id)
            )
        ).all()
        session_counts = dict(s_rows)

        u_rows = (
            await db.execute(
                select(Session.cohort_id, func.count(Session.id))
                .where(
                    Session.cohort_id.in_(all_cohort_ids),
                    Session.staffing_status == "unstaffed",
                )
                .group_by(Session.cohort_id)
            )
        ).all()
        unstaffed_counts = dict(u_rows)

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

    location_names: dict[uuid.UUID, str] = {}
    loc_ids = {c.location_id for plist in cohorts_by_program.values() for c in plist if c.location_id is not None}
    if loc_ids:
        location_names = {
            loc.id: loc.name
            for loc in (await db.execute(select(Location).where(Location.id.in_(loc_ids)))).scalars().all()
        }

    variation_names: dict[uuid.UUID, str] = {}
    var_ids = {c.variation_id for plist in cohorts_by_program.values() for c in plist if c.variation_id is not None}
    if var_ids:
        variation_names = {
            v.id: v.name
            for v in (await db.execute(select(ProgramVariation).where(ProgramVariation.id.in_(var_ids)))).scalars().all()
        }

    programs_out: list[OrganizationProgramOut] = []
    total_partner_cohorts = 0
    for p in programs:
        c_list = cohorts_by_program.get(p.id, [])
        total_partner_cohorts += sum(1 for c in c_list if is_partner_managed(c))
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
                    location_id=c.location_id,
                    location_name=location_names.get(c.location_id) if c.location_id else None,
                    management_mode=getattr(c, "management_mode", "spacepoint") or "spacepoint",
                    status=c.status,
                    capacity=c.capacity,
                    duration_hours=c.duration_hours,
                    visibility=c.visibility,
                    is_public=c.visibility == "public",
                    registered_count=rc,
                    active_students_count=rc,
                    observers_count=oc,
                    active_observers_count=oc,
                    spots_left=spots,
                    sessions_count=session_counts.get(c.id, 0),
                    unstaffed_count=(unstaffed_counts.get(c.id, 0) if is_partner_managed(c) else 0),
                    program_id=p.id,
                    program_name=p.name,
                    variation_id=c.variation_id,
                    variation_name=variation_names.get(c.variation_id) if c.variation_id else None,
                    checklist_title_override=c.checklist_title_override,
                    linked_event_id=linked_ev.id if linked_ev else None,
                    linked_event_slug=linked_ev.slug if linked_ev else None,
                )
            )
        is_org_owned = (p.organization_id == org.id)
        is_shared = (p.organization_id is None) and can_org_use_shared_program(org, p)
        programs_out.append(
            OrganizationProgramOut(
                id=p.id,
                code=p.code,
                name=p.name,
                program_type=p.program_type,
                description=p.description,
                default_capacity=p.default_capacity,
                duration_hours=float(p.duration_hours) if p.duration_hours is not None else None,
                pricing_model=p.pricing_model or "free",
                price=float(p.price) if p.price is not None else None,
                completion_rule_type=p.completion_rule_type or "percentage",
                completion_rule_value=float(p.completion_rule_value) if p.completion_rule_value is not None else 70.0,
                keep_course_access_after_completion=bool(p.keep_course_access_after_completion),
                is_org_owned=is_org_owned,
                is_shared_program=is_shared,
                can_create_cohort=(is_org_owned or is_shared),
                active=bool(p.active),
                lms_program_id=lms_prog_map.get(p.id),
                default_certificate_template_id=p.default_certificate_template_id,
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
            "program_scope": scope,
            "allowed_program_ids": [str(pid) for pid in (org.allowed_program_ids or [])],
            "program_page_access": (getattr(org, "program_page_access", None) or "disabled").strip().lower(),
            "max_events": org.max_events,
            "max_programs": org.max_programs,
            "max_cohorts": org.max_cohorts,
            "max_students_per_cohort": org.max_students_per_cohort,
            "max_observers_per_cohort": org.max_observers_per_cohort,
        },
        "programs": programs_out,
        "quotas": {
            "programs_count": sum(1 for p in programs if p.organization_id == org.id),
            "max_programs": org.max_programs,
            "cohorts_count": total_partner_cohorts,
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
    organization_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user, organization_id=organization_id)
    require_org_manager(current_user)
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
        duration_hours=body.duration_hours,
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
        duration_hours=float(program.duration_hours) if program.duration_hours is not None else None,
        pricing_model=program.pricing_model,
        price=float(program.price) if program.price is not None else None,
        completion_rule_type=program.completion_rule_type,
        completion_rule_value=float(program.completion_rule_value) if program.completion_rule_value is not None else 70.0,
        keep_course_access_after_completion=program.keep_course_access_after_completion,
        is_org_owned=True,
        active=bool(program.active),
        lms_program_id=lms_prog.id,
        created_at=program.created_at,
        cohorts_count=0,
        cohorts=[],
    )


@router.patch("/programs/{program_id}", response_model=OrganizationProgramOut)
@router.put("/programs/{program_id}", response_model=OrganizationProgramOut)
async def update_organization_program(
    program_id: uuid.UUID,
    body: OrganizationProgramUpdate,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user)
    require_org_manager(current_user)
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
    if body.code is not None and body.code.strip():
        candidate_code = body.code.strip().upper()
        if candidate_code != program.code:
            existing = await db.scalar(
                select(func.count(Program.id)).where(Program.code == candidate_code, Program.id != program.id)
            )
            if existing:
                raise HTTPException(status_code=409, detail="Program code already exists")
            program.code = candidate_code
    if body.description is not None:
        program.description = body.description.strip() or None
    if body.program_type is not None and body.program_type.strip():
        program.program_type = body.program_type.strip().lower()
    if body.default_capacity is not None:
        program.default_capacity = body.default_capacity
    if body.duration_hours is not None:
        program.duration_hours = body.duration_hours
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
    if body.active is not None:
        program.active = body.active

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
        duration_hours=float(program.duration_hours) if program.duration_hours is not None else None,
        pricing_model=program.pricing_model,
        price=float(program.price) if program.price is not None else None,
        completion_rule_type=program.completion_rule_type,
        completion_rule_value=float(program.completion_rule_value) if program.completion_rule_value is not None else 70.0,
        keep_course_access_after_completion=program.keep_course_access_after_completion,
        is_org_owned=(program.organization_id == org.id),
        active=bool(program.active),
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
    require_org_manager(current_user)
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
    organization_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    org = await _get_org_or_400(db, current_user, organization_id=organization_id)
    require_org_manager(current_user)
    _ensure_org_approved(org, current_user)

    program = await db.get(Program, body.program_id)
    if program is None or (not _is_admin_or_ops(current_user) and not is_program_allowed_for_org(org, program)):
        raise HTTPException(status_code=404, detail="Program not found")

    if org.max_cohorts is not None and not _is_admin_or_ops(current_user):
        curr_cohorts = await db.scalar(
            select(func.count(Cohort.id)).where(
                Cohort.organization_id == org.id,
                Cohort.management_mode == "partner",
            )
        ) or 0
        if curr_cohorts >= org.max_cohorts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_cohorts} cohort(s). Contact the SpacePoint team to increase your limit.",
            )

    if body.location_id is not None:
        loc = await db.get(Location, body.location_id)
        if loc is None:
            raise HTTPException(status_code=404, detail="Location not found")
        if not _is_admin_or_ops(current_user) and loc.organization_id != org.id:
            raise HTTPException(status_code=403, detail="Location does not belong to your organization")

    selected_var: ProgramVariation | None = None
    if body.variation_id is not None:
        selected_var = await var_svc.resolve_variation_for_program(db, program.id, body.variation_id)
    else:
        selected_var = await var_svc.resolve_variation_for_program(db, program.id, active_only=True)
    eff_scalars = var_svc.resolve_effective_scalars(program, selected_var)

    capacity = body.capacity if body.capacity is not None else eff_scalars.get("capacity")
    if org.max_students_per_cohort is not None and not _is_admin_or_ops(current_user):
        if body.capacity is None:
            capacity = (
                min(capacity, org.max_students_per_cohort)
                if capacity is not None
                else org.max_students_per_cohort
            )
        elif capacity is not None and capacity > org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort. Contact the SpacePoint team to increase your limit.",
            )

    starts_on = body.starts_on or body.start_date
    ends_on = body.ends_on or body.end_date
    if body.is_public is not None:
        visibility = "public" if body.is_public else "private"
    else:
        visibility = body.visibility if body.visibility in ("public", "private") else "private"
    cohort_status = body.status if body.status in ("planned", "registration_open", "running") else "registration_open"

    duration_hours = body.duration_hours if body.duration_hours is not None else eff_scalars.get("duration_hours")
    poster_url = body.poster_template_url if body.poster_template_url is not None else eff_scalars.get("poster_template_url")

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        variation_id=selected_var.id if selected_var else None,
        name=body.name.strip(),
        starts_on=starts_on,
        ends_on=ends_on,
        capacity=capacity,
        duration_hours=duration_hours,
        location_id=body.location_id,
        location=body.location,
        visibility=visibility,
        status=cohort_status,
        organization_id=org.id,
        management_mode="partner",
        inherit_default_checklists=True,
        poster_template_url=poster_url,
        checklist_title_override=body.checklist_title_override,
        keep_course_access_after_completion=bool(
            eff_scalars.get("keep_course_access_after_completion", program.keep_course_access_after_completion)
        ),
    )
    db.add(cohort)
    await db.flush()

    await seed_cohort_from_program(
        db,
        cohort=cohort,
        program=program,
        selected_var=selected_var,
        apply_defaults=True,
        eff_scalars=eff_scalars,
        import_default_checklists=True,
        actor_user_id=current_user.id,
        ensure_lms_override=True,
    )

    await db.commit()
    await db.refresh(cohort)

    return await get_organization_cohort_detail(cohort.id, current_user, db)


@router.get("/cohorts/{cohort_id}", response_model=OrganizationCohortOut)
async def get_organization_cohort_detail(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

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

    location_name = None
    if cohort.location_id:
        loc_obj = await db.get(Location, cohort.location_id)
        location_name = loc_obj.name if loc_obj else None

    return OrganizationCohortOut(
        id=cohort.id,
        program_id=program.id,
        program_name=program.name,
        program_type=program.program_type,
        management_mode=getattr(cohort, "management_mode", "spacepoint") or "spacepoint",
        can_manage_delivery=await can_manage_cohort_delivery(db, cohort, current_user),
        name=cohort.name,
        code=cohort.name,
        starts_on=cohort.starts_on,
        ends_on=cohort.ends_on,
        start_date=cohort.starts_on.isoformat() if cohort.starts_on else "",
        end_date=cohort.ends_on.isoformat() if cohort.ends_on else "",
        location=cohort.location or location_name,
        location_id=cohort.location_id,
        location_name=location_name,
        status=cohort.status,
        capacity=cohort.capacity,
        org_capacity_limit=org.max_students_per_cohort if is_partner_managed(cohort) else None,
        org_observer_limit=org.max_observers_per_cohort if is_partner_managed(cohort) else None,
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
    require_org_manager(current_user)
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)

    if (
        is_partner_managed(cohort)
        and body.capacity is not None
        and org.max_students_per_cohort is not None
        and not _is_admin_or_ops(current_user)
    ):
        if body.capacity > org.max_students_per_cohort:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort. Contact the SpacePoint team to increase your limit.",
            )

    updates = body.model_dump(exclude_unset=True)
    if "status" in updates:
        new_status = updates["status"]
        if not await can_manage_cohort_delivery(db, cohort, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Status for SpacePoint-managed cohorts is managed by SpacePoint Ops.",
            )
        if new_status == "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Use the cohort completion workflow to mark a cohort completed.",
            )
        if new_status not in ("planned", "registration_open", "running", "cancelled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid cohort status.",
            )
    if (
        "duration_hours" in updates
        and updates["duration_hours"] != cohort.duration_hours
        and not await can_manage_cohort_delivery(db, cohort, current_user)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Duration hours for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
        )
    if "variation_id" in updates and updates["variation_id"] is not None:
        await var_svc.resolve_variation_for_program(db, cohort.program_id, updates["variation_id"])
    if (
        updates.get("location_id") is not None
        and updates["location_id"] != cohort.location_id
    ):
        loc = await db.get(Location, updates["location_id"])
        if loc is None:
            raise HTTPException(status_code=404, detail="Location not found")
        if not _is_admin_or_ops(current_user) and loc.organization_id != org.id:
            raise HTTPException(status_code=403, detail="Location does not belong to your organization")
    if "start_date" in updates:
        cohort.starts_on = updates.pop("start_date")
    if "end_date" in updates:
        cohort.ends_on = updates.pop("end_date")
    if "is_public" in updates:
        is_pub = updates.pop("is_public")
        if is_pub is not None:
            cohort.visibility = "public" if is_pub else "private"
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
    require_org_manager(current_user)
    source, org = await _resolve_cohort_and_org(
        db, cohort_id, current_user, not_found_detail="Source cohort not found"
    )

    if org.max_cohorts is not None and not _is_admin_or_ops(current_user):
        curr_cohorts = await db.scalar(
            select(func.count(Cohort.id)).where(
                Cohort.organization_id == org.id,
                Cohort.management_mode == "partner",
            )
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
        duration_hours=source.duration_hours,
        location_id=source.location_id,
        location=source.location,
        visibility=source.visibility,
        status="registration_open",
        organization_id=org.id,
        management_mode="partner",
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
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

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
    require_org_manager(current_user)
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)
    _ensure_org_approved(org, current_user)

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
    require_org_manager(current_user)
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)
    _ensure_org_approved(org, current_user)

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
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)

    reg = await db.get(Registration, registration_id)
    if reg is None or reg.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Registration not found")

    reg.status = "cancelled"
    await db.flush()
    await deactivate_registration_enrollments(db, reg.id)

    linked_users = (await db.execute(
        select(User).where(User.contact_id == reg.contact_id)
    )).scalars().all()
    for linked_user in linked_users:
        assignment = (await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.user_id == linked_user.id,
                LmsProgramAssignment.cohort_id == cohort.id,
            )
        )).scalars().first()
        if assignment is not None:
            team = await team_for_cohort_member(db, cohort_id=cohort.id, user_id=linked_user.id)
            if team is not None:
                member = await db.get(TeamMember, (team.id, linked_user.id))
                if member is not None:
                    await db.delete(member)
                    await db.flush()
            await db.delete(assignment)

    await db.commit()
    return None


# ── Observers Endpoints ─────────────────────────────────────────────────────
@router.get("/cohorts/{cohort_id}/observers", response_model=list[CohortObserverOut])
async def list_cohort_observers(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

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
    require_org_manager(current_user)
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)

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

    if (
        is_partner_managed(cohort)
        and org.max_observers_per_cohort is not None
        and not _is_admin_or_ops(current_user)
    ):
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
        roles.append(UserRole.observer)
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
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)

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
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

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
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)
    can_delivery = await can_manage_cohort_delivery(db, cohort, current_user)
    if not can_delivery and "duration_hours" in body.model_fields_set and body.duration_hours is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Duration hours for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
        )

    meeting_date = body.meeting_date or body.date or date.today()
    starts_at = _coerce_time(body.starts_at or body.start_time)

    s = Session(
        cohort_id=cohort.id,
        title=body.title.strip(),
        meeting_date=meeting_date,
        starts_at=starts_at,
        duration_hours=body.duration_hours if can_delivery else None,
        staffing_status="staffed" if can_delivery else "unstaffed",
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
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)

    s = await db.get(Session, session_id)
    if s is None or s.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Session not found")

    updates = body.model_dump(exclude_unset=True)
    if (
        "duration_hours" in updates
        and updates["duration_hours"] != s.duration_hours
        and not await can_manage_cohort_delivery(db, cohort, current_user)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Duration hours for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
        )
    if "date" in updates:
        s.meeting_date = updates.pop("date")
    if "meeting_date" in updates:
        s.meeting_date = updates.pop("meeting_date")
    if "start_time" in updates:
        s.starts_at = _coerce_time(updates.pop("start_time"))
    if "starts_at" in updates:
        s.starts_at = _coerce_time(updates.pop("starts_at"))
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
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)

    s = await db.get(Session, session_id)
    if s is None or s.cohort_id != cohort.id:
        raise HTTPException(status_code=404, detail="Session not found")

    await db.delete(s)
    await db.commit()
    return None


# ── Sandbox staffing: org instructors & judges ───────────────────────────────
async def _default_delivery_role_id(db: AsyncSession) -> uuid.UUID:
    role = (
        await db.execute(
            select(DeliveryRole)
            .where(DeliveryRole.is_active.is_(True))
            .order_by(DeliveryRole.sort_order.asc())
            .limit(1)
        )
    ).scalars().first()
    if role is None:
        raise HTTPException(
            status_code=400,
            detail="No delivery roles are configured yet — ask SpacePoint Operations to add one",
        )
    return role.id


async def _org_instructor_or_400(db: AsyncSession, org: Organization, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    is_owner = user is not None and user.id == org.owner_user_id
    if (
        user is None
        or (user.organization_id != org.id and not is_owner)
        or not has_org_role(user, "instructor", is_owner=is_owner)
    ):
        raise HTTPException(
            status_code=400,
            detail="Pick a team member whose organization roles include Instructor",
        )
    return user


async def _org_judge_or_400(db: AsyncSession, org: Organization, user_id: uuid.UUID) -> User:
    user = await db.get(User, user_id)
    is_owner = user is not None and user.id == org.owner_user_id
    if (
        user is None
        or (user.organization_id != org.id and not is_owner)
        or not has_org_role(user, "judge", is_owner=is_owner)
    ):
        raise HTTPException(
            status_code=400,
            detail="Pick a team member whose organization roles include Judge",
        )
    return user


@router.get("/cohorts/{cohort_id}/staff")
async def get_cohort_staff(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """The org's staffing board: instructors assigned to this cohort, judges,
    per-session staffing & attendance, and readiness attempts."""
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

    sessions = (
        await db.execute(
            select(Session)
            .where(Session.cohort_id == cohort.id)
            .order_by(Session.meeting_date.asc().nullslast(), Session.created_at.asc())
        )
    ).scalars().all()
    session_ids = [s.id for s in sessions]

    role_names = {
        r.id: r.name for r in (await db.execute(select(DeliveryRole))).scalars().all()
    }

    assignments: list[tuple[SessionInstructor, User]] = []
    if session_ids:
        assignments = list(
            (
                await db.execute(
                    select(SessionInstructor, User)
                    .join(User, User.id == SessionInstructor.user_id)
                    .where(SessionInstructor.session_id.in_(session_ids))
                )
            ).all()
        )

    attendance: dict[uuid.UUID, dict[str, int]] = {}
    if session_ids:
        att_rows = (
            await db.execute(
                select(
                    AttendanceRecord.session_id,
                    AttendanceRecord.att_status,
                    func.count(AttendanceRecord.id),
                )
                .where(AttendanceRecord.session_id.in_(session_ids))
                .group_by(AttendanceRecord.session_id, AttendanceRecord.att_status)
            )
        ).all()
        for sid, status_value, count in att_rows:
            attendance.setdefault(sid, {})[status_value] = int(count)

    instructor_map: dict[uuid.UUID, User] = {}
    for _si, assigned_user in assignments:
        instructor_map.setdefault(assigned_user.id, assigned_user)

    attempt_by_user: dict[uuid.UUID, PreSessionQuizAttempt] = {}
    if instructor_map:
        attempts = (
            await db.execute(
                select(PreSessionQuizAttempt).where(
                    PreSessionQuizAttempt.cohort_id == cohort.id,
                    PreSessionQuizAttempt.user_id.in_(instructor_map.keys()),
                )
            )
        ).scalars().all()
        attempt_by_user = {a.user_id: a for a in attempts}

    session_by_id = {s.id: s for s in sessions}
    by_instructor: dict[uuid.UUID, list[SessionInstructor]] = {}
    for si, _u in assignments:
        by_instructor.setdefault(si.user_id, []).append(si)

    instructors_out = []
    for uid, person in instructor_map.items():
        rows = by_instructor.get(uid, [])
        assigned_sessions = [session_by_id[r.session_id] for r in rows if r.session_id in session_by_id]
        present = sum(attendance.get(sid, {}).get("present", 0) for sid in (s.id for s in assigned_sessions))
        absent = sum(attendance.get(sid, {}).get("absent", 0) for sid in (s.id for s in assigned_sessions))
        attempt = attempt_by_user.get(uid)
        primary_role_id = rows[0].role_id if rows else None
        instructors_out.append(
            {
                "user_id": str(uid),
                "full_name": person.full_name,
                "email": person.email,
                "phone": person.phone,
                "status": person.status,
                "session_ids": [str(s.id) for s in assigned_sessions],
                "sessions_count": len(assigned_sessions),
                "completed_sessions": sum(1 for s in assigned_sessions if s.completed_at is not None),
                "attendance_present": present,
                "attendance_absent": absent,
                "role_id": str(primary_role_id) if primary_role_id else None,
                "role_name": role_names.get(primary_role_id) if primary_role_id else None,
                "roles": [role_names.get(r.role_id, "") for r in rows],
                "readiness": (
                    {
                        "status": attempt.status,
                        "final_score": attempt.final_score,
                        "total_questions": attempt.total_questions,
                        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
                        "passed": attempt.status == "completed",
                    }
                    if attempt is not None
                    else None
                ),
            }
        )
    instructors_out.sort(key=lambda r: (-r["sessions_count"], r["full_name"].lower()))

    judge_rows = (
        await db.execute(
            select(CompetitionJudge, User)
            .join(User, User.id == CompetitionJudge.user_id)
            .where(CompetitionJudge.cohort_id == cohort.id)
        )
    ).all()

    return {
        "cohort_id": str(cohort.id),
        "management_mode": getattr(cohort, "management_mode", "spacepoint") or "spacepoint",
        "can_manage_delivery": await can_manage_cohort_delivery(db, cohort, current_user),
        "sessions": [
            {
                "id": str(s.id),
                "title": s.title,
                "meeting_date": s.meeting_date.isoformat() if s.meeting_date else None,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "staffing_status": s.staffing_status,
                "attendance_present": attendance.get(s.id, {}).get("present", 0),
                "attendance_absent": attendance.get(s.id, {}).get("absent", 0),
                "attendance_total": sum(attendance.get(s.id, {}).values()),
                "instructors": [
                    {
                        "user_id": str(u.id),
                        "full_name": u.full_name,
                        "role_id": str(si.role_id) if si.role_id else None,
                        "role_name": role_names.get(si.role_id) if si.role_id else None,
                    }
                    for si, u in assignments
                    if si.session_id == s.id
                ],
            }
            for s in sessions
        ],
        "instructors": instructors_out,
        "judges": [
            {
                "user_id": str(u.id),
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "status": u.status,
                "onboarding_sent_at": j.onboarding_sent_at.isoformat() if j.onboarding_sent_at else None,
            }
            for j, u in judge_rows
        ],
    }


@router.post("/cohorts/{cohort_id}/instructors", status_code=status.HTTP_201_CREATED)
async def assign_instructor_to_cohort(
    cohort_id: uuid.UUID,
    body: AssignOrgInstructorIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Assign an org instructor to the whole cohort (one `SessionInstructor` per
    session — the same shape Ops staffing writes)."""
    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    if is_partner_managed(cohort):
        org_id = await cohort_organization_id(db, cohort)
        if org_id is not None:
            org = await db.get(Organization, org_id)
            if org is not None:
                await _org_instructor_or_400(db, org, body.user_id)

    sessions = (
        await db.execute(select(Session).where(Session.cohort_id == cohort.id))
    ).scalars().all()
    if body.session_ids is not None:
        wanted = set(body.session_ids)
        sessions = [s for s in sessions if s.id in wanted]
    if not sessions:
        raise HTTPException(status_code=400, detail="This cohort has no sessions to assign yet")

    if body.role_id is not None and await db.get(DeliveryRole, body.role_id) is None:
        raise HTTPException(status_code=404, detail="Delivery role not found")
    role_id = body.role_id or await _default_delivery_role_id(db)
    created = 0
    for s in sessions:
        existing = (
            await db.execute(
                select(SessionInstructor).where(
                    SessionInstructor.session_id == s.id,
                    SessionInstructor.user_id == body.user_id,
                )
            )
        ).scalars().first()
        if existing is not None:
            if body.role_id is not None:
                existing.role_id = body.role_id
            continue
        db.add(
            SessionInstructor(
                session_id=s.id,
                user_id=body.user_id,
                role_id=role_id,
            )
        )
        s.staffing_status = "staffed"
        created += 1
    await db.commit()
    return {"assigned": created}


@router.patch("/cohorts/{cohort_id}/instructors/{user_id}")
async def update_cohort_instructor_role(
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateOrgInstructorRoleIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Update the DeliveryRole for an assigned instructor across all sessions of this cohort."""
    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    role = await db.get(DeliveryRole, body.role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="Delivery role not found")

    session_ids = (await db.execute(select(Session.id).where(Session.cohort_id == cohort.id))).scalars().all()
    if not session_ids:
        raise HTTPException(status_code=404, detail="No sessions found in this cohort")
    rows = (
        await db.execute(
            select(SessionInstructor).where(
                SessionInstructor.session_id.in_(session_ids),
                SessionInstructor.user_id == user_id,
            )
        )
    ).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Instructor is not assigned to this cohort")
    for r in rows:
        r.role_id = role.id
    await db.commit()
    return {"user_id": str(user_id), "role_id": str(role.id), "role_name": role.name}


@router.delete("/cohorts/{cohort_id}/instructors/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_instructor_from_cohort(
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)

    if session_id is not None:
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort.id:
            raise HTTPException(status_code=404, detail="Session not found")
        await db.execute(
            sa_delete(SessionInstructor).where(
                SessionInstructor.user_id == user_id,
                SessionInstructor.session_id == session.id,
            )
        )
    else:
        session_ids = select(Session.id).where(Session.cohort_id == cohort.id)
        await db.execute(
            sa_delete(SessionInstructor).where(
                SessionInstructor.user_id == user_id,
                SessionInstructor.session_id.in_(session_ids),
            )
        )
    await db.commit()
    return None


@router.post("/cohorts/{cohort_id}/judges", status_code=status.HTTP_201_CREATED)
async def assign_judge_to_cohort(
    cohort_id: uuid.UUID,
    body: AssignOrgJudgeIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Give an org judge the cohort's competition — one `CompetitionJudge` row,
    the exact same assignment Ops writes."""
    require_org_manager(current_user)
    cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)
    await _org_judge_or_400(db, org, body.user_id)

    existing = (
        await db.execute(
            select(CompetitionJudge).where(
                CompetitionJudge.cohort_id == cohort.id,
                CompetitionJudge.user_id == body.user_id,
            )
        )
    ).scalars().first()
    if existing is None:
        db.add(CompetitionJudge(cohort_id=cohort.id, user_id=body.user_id))
        await db.commit()
    return {"assigned": True}


@router.delete("/cohorts/{cohort_id}/judges/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_judge_from_cohort(
    cohort_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    require_org_manager(current_user)
    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user)

    existing = (
        await db.execute(
            select(CompetitionJudge).where(
                CompetitionJudge.cohort_id == cohort.id,
                CompetitionJudge.user_id == user_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        await db.delete(existing)
        await db.commit()
    return None


def _org_allows_readiness_preset(org: Organization, preset: dict[str, Any]) -> bool:
    preset_org_id = preset.get("organization_id")
    if preset_org_id is not None:
        return str(preset_org_id) == str(org.id)
    scope = (getattr(org, "readiness_scope", None) or "own").strip().lower()
    if scope == "all":
        return True
    if scope == "selected":
        allowed = {str(x) for x in (getattr(org, "allowed_readiness_preset_ids", None) or [])}
        return str(preset.get("id")) in allowed
    return False


class OrgReadinessQuestionIn(BaseModel):
    prompt: str
    question_type: str = "mcq"  # mcq | written
    options: list[dict[str, Any]] = Field(default_factory=list)
    explanation: str | None = None
    critical: bool = False


class OrgReadinessPresetCreateIn(BaseModel):
    name: str
    description: str | None = None
    passing_score_percent: int = Field(default=80, ge=0, le=100)
    cohort_id: uuid.UUID | None = None
    questions: list[OrgReadinessQuestionIn] = Field(default_factory=list)


@router.get("/readiness-presets")
async def list_org_readiness_presets(
    cohort_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Presets the org can assign as instructor readiness for a cohort."""
    from app.services.sessions import pre_session_quiz as quiz_svc

    if cohort_id is not None:
        _cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)
    else:
        org = await _get_org_or_400(db, current_user)

    presets = await quiz_svc.list_presets(db)
    visible = [p for p in presets if _org_allows_readiness_preset(org, p)]
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "description": p.get("description"),
            "preset_type": p.get("preset_type"),
            "passing_score_percent": p.get("passing_score_percent", 80),
            "question_count": _preset_question_count(p),
            "phases_count": len(p.get("phases") or []),
            "is_own": str(p.get("organization_id")) == str(org.id) if p.get("organization_id") else False,
        }
        for p in visible
    ]


@router.get("/readiness-presets/{preset_id}")
async def get_org_readiness_preset_detail(
    preset_id: uuid.UUID,
    cohort_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Return full hydrated readiness preset details (questions, phases, media) for preview."""
    from app.services.sessions import pre_session_quiz as quiz_svc

    if cohort_id is not None:
        _cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)
    else:
        org = await _get_org_or_400(db, current_user)

    presets = await quiz_svc.list_presets(db, active_only=False)
    preset = next((p for p in presets if str(p.get("id")) == str(preset_id)), None)
    if preset is None or not _org_allows_readiness_preset(org, preset):
        raise HTTPException(status_code=404, detail="Readiness preset not found")
    return preset


@router.post("/readiness-presets", status_code=status.HTTP_201_CREATED)
async def create_org_readiness_preset(
    body: OrgReadinessPresetCreateIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Create a readiness assessment owned by this organization."""
    from app.models.sessions.pre_session_quiz import PreSessionQuizQuestion

    require_org_manager(current_user)
    if body.cohort_id is not None:
        _cohort, org = await _resolve_cohort_and_org(db, body.cohort_id, current_user)
    else:
        org = await _get_org_or_400(db, current_user)

    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Assessment name is required")
    if not body.questions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Add at least one question")

    q_ids: list[str] = []
    for idx, q in enumerate(body.questions):
        prompt = q.prompt.strip()
        if not prompt:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Question {idx + 1} prompt is required")
        q_type = "written" if q.question_type == "written" else "mcq"
        opts = []
        if q_type == "mcq":
            opts = [
                {"text": str(o.get("text", "")).strip(), "is_correct": bool(o.get("is_correct"))}
                for o in (q.options or [])
                if str(o.get("text", "")).strip()
            ]
            if len(opts) < 2 or not any(o["is_correct"] for o in opts):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"Question {idx + 1} needs at least 2 options and 1 correct answer",
                )
        q_row = PreSessionQuizQuestion(
            id=uuid.uuid4(),
            topic="Organization Readiness",
            question_type=q_type,
            title=prompt[:120],
            prompt=prompt,
            options=opts,
            critical=q.critical,
            points=1,
            explanation=q.explanation.strip() if q.explanation else None,
            is_active=True,
            organization_id=org.id,
            created_by=current_user.id,
        )
        db.add(q_row)
        q_ids.append(str(q_row.id))

    preset = PreSessionQuizPreset(
        id=uuid.uuid4(),
        name=name,
        description=body.description.strip() if body.description else None,
        preset_type="readiness_pipeline",
        draw_size=len(q_ids),
        critical_floor=0,
        passing_score_percent=body.passing_score_percent,
        question_ids=q_ids,
        reference_attachments=[],
        phases=[
            {
                "id": f"phase-{uuid.uuid4().hex[:6]}",
                "phase_type": "quiz",
                "title": name,
                "subtitle": body.description.strip() if body.description else "",
                "instructions": [],
                "pass_percentage": body.passing_score_percent,
                "cooldown_seconds": 0,
                "show_correct_on_fail": False,
                "show_explanation_on_fail": True,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": q_ids,
                "matching_config": None,
            }
        ],
        is_active=True,
        organization_id=org.id,
        created_by=current_user.id,
    )
    db.add(preset)
    await db.commit()
    await db.refresh(preset)

    return {
        "id": str(preset.id),
        "name": preset.name,
        "description": preset.description,
        "preset_type": preset.preset_type,
        "passing_score_percent": preset.passing_score_percent,
        "question_count": len(q_ids),
        "phases_count": 1,
        "is_own": True,
    }


@router.delete("/readiness-presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org_readiness_preset(
    preset_id: uuid.UUID,
    cohort_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    require_org_manager(current_user)
    if cohort_id is not None:
        _cohort, org = await _resolve_cohort_and_org(db, cohort_id, current_user)
    else:
        org = await _get_org_or_400(db, current_user)

    preset = await db.get(PreSessionQuizPreset, preset_id)
    if preset is None or preset.organization_id != org.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Readiness assessment not found")
    preset.is_active = False
    await db.commit()
    return None


@router.get("/cohorts/{cohort_id}/readiness")
async def get_org_cohort_readiness(
    cohort_id: uuid.UUID,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """The readiness preset assigned to this cohort plus every org instructor's
    attempt — the org-side view Ops already has."""
    from app.services.sessions import pre_session_quiz as quiz_svc

    cohort, _org = await _resolve_cohort_and_org(db, cohort_id, current_user, read_only=True)

    assignment = await quiz_svc.get_assignment_for_scope(db, "cohorts", cohort.id)
    preset = None
    if assignment.get("preset_id"):
        hydrated = await quiz_svc.get_preset_hydrated(db, assignment["preset_id"])
        if hydrated:
            preset = {
                "id": hydrated.get("id"),
                "name": hydrated.get("name"),
                "description": hydrated.get("description"),
                "question_count": _preset_question_count(hydrated),
            }

    attempts = (
        await db.execute(
            select(PreSessionQuizAttempt, User)
            .join(User, User.id == PreSessionQuizAttempt.user_id)
            .where(PreSessionQuizAttempt.cohort_id == cohort.id)
            .order_by(PreSessionQuizAttempt.started_at.desc())
        )
    ).all()

    return {
        "preset": preset,
        "instructors": [
            {
                "user_id": str(u.id),
                "full_name": u.full_name,
                "email": u.email,
                "status": a.status,
                "final_score": a.final_score,
                "total_questions": a.total_questions,
                "pending_review_count": a.pending_review_count,
                "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
                "passed": a.status == "completed",
            }
            for a, u in attempts
        ],
    }


@router.put("/cohorts/{cohort_id}/readiness")
async def set_org_cohort_readiness(
    cohort_id: uuid.UUID,
    body: OrgReadinessAssignIn,
    current_user: User = Depends(require_organization_account),
    db: AsyncSession = Depends(get_db),
):
    """Assign (or clear) the Instructor Readiness quiz for a cohort. The
    existing session-start gate already refuses an instructor who hasn't
    passed a cohort-level preset."""
    from app.services.sessions import pre_session_quiz as quiz_svc

    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    org_id = await cohort_organization_id(db, cohort)
    org = await db.get(Organization, org_id) if org_id else None
    if body.preset_id is not None and not _is_admin_or_ops(current_user):
        hydrated = await quiz_svc.get_preset_hydrated(db, body.preset_id)
        if hydrated is None or org is None or not _org_allows_readiness_preset(org, hydrated):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="This organization does not have access to the selected readiness assessment.",
            )
    return await quiz_svc.set_assignment_for_scope(
        db,
        "cohorts",
        cohort.id,
        body.preset_id,
        clear_override=body.preset_id is None,
    )

