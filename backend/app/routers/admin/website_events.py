from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import require_website_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.cohort_quiz import (
    CohortQuizQuestion,
    CohortQuizTemplate,
    CohortQuizTemplateQuestion,
)
from app.models.lms.course import Course, CourseModule
from app.models.lms.enrollment import Enrollment
from app.models.lms.invite_grant import InvitationCodeGrant
from app.models.lms.learning_path import LearningPath
from app.models.lms.program import (
    CohortLmsEditor,
    LmsProgram,
    LmsProgramAssignment,
    LmsProgramCohortOverride,
    LmsProgramItem,
    LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.competitions.judging import CompetitionJudge
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team, TeamMember
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent
from app.schemas.website_event import (
    MegaEventCreate,
    MegaEventOut,
    MegaEventUpdate,
    OrgTeamMemberCreateIn,
    OrgTeamMemberOut,
    OrgTeamMemberUpdateIn,
    OrganizationAccountCreateIn,
    OrganizationDetailOut,
    OrganizationSummaryOut,
    WebsiteEventCreate,
    WebsiteEventOut,
    WebsiteEventUpdate,
)
from app.services.documents.card_id import format_card_id
from app.services.documents.id_card import ensure_card_number
from app.services.email import (
    send_org_team_added_email,
    send_org_team_invite_email,
    send_password_set_link_email,
)
from app.services.org_access import (
    clear_user_org_roles,
    effective_org_roles,
    global_roles_for_org_roles,
    normalize_org_roles,
    set_user_org_roles,
)
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES
from app.services.spine.identity import (
    normalize_user_email,
    resolve_or_create_contact,
    user_email_matches,
)
from app.services.website_events import (
    build_organization_team_member,
    ensure_default_events_seeded,
    serialize_mega_events,
    serialize_website_events,
    unique_mega_event_slug,
    unique_website_event_slug,
)

router = APIRouter(prefix="/website", tags=["admin-website-events"])


class PublishToggleIn(BaseModel):
    is_published: bool


# ── Mega Events CRUD ─────────────────────────────────────────────────────────
@router.get("/mega-events", response_model=list[MegaEventOut])
async def admin_list_mega_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    await ensure_default_events_seeded(db)
    rows = (
        await db.execute(
            select(MegaEvent).order_by(MegaEvent.display_order.asc(), MegaEvent.created_at.desc())
        )
    ).scalars().all()
    return await serialize_mega_events(db, rows, published_only_counts=False)


@router.post("/mega-events", response_model=MegaEventOut, status_code=status.HTTP_201_CREATED)
async def admin_create_mega_event(
    body: MegaEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    slug = await unique_mega_event_slug(db, body.slug or body.title)
    data = body.model_dump(exclude={"slug"})
    data["country"] = (data.get("country") or "uae").strip().lower()
    row = MegaEvent(**data, slug=slug)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_mega_events(db, [row]))[0]


@router.put("/mega-events/{mega_id}", response_model=MegaEventOut)
async def admin_update_mega_event(
    mega_id: UUID,
    body: MegaEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(MegaEvent, mega_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mega event not found")
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_mega_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_mega_events(db, [row]))[0]


@router.delete("/mega-events/{mega_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_mega_event(
    mega_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(MegaEvent, mega_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Mega event not found")
    await db.delete(row)
    await db.commit()
    return None


# ── Website Events CRUD & Publishing ─────────────────────────────────────────
@router.get("/events", response_model=list[WebsiteEventOut])
async def admin_list_website_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    await ensure_default_events_seeded(db)
    rows = (
        await db.execute(
            select(WebsiteEvent).order_by(
                WebsiteEvent.display_order.asc(),
                WebsiteEvent.updated_at.desc(),
            )
        )
    ).scalars().all()
    return await serialize_website_events(db, rows)


@router.post("/events", response_model=WebsiteEventOut, status_code=status.HTTP_201_CREATED)
async def admin_create_website_event(
    body: WebsiteEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    slug = await unique_website_event_slug(db, body.slug or body.title)
    data = body.model_dump(exclude={"slug"})
    data["country"] = (data.get("country") or "uae").strip().lower()
    if data.get("organization_id") and not data.get("host_org_name"):
        org = await db.get(Organization, data["organization_id"])
        if org:
            data["host_org_name"] = org.name_latin
    row = WebsiteEvent(**data, slug=slug, created_by_user_id=current_user.id)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.put("/events/{event_id}", response_model=WebsiteEventOut)
async def admin_update_website_event(
    event_id: UUID,
    body: WebsiteEventUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    updates = body.model_dump(exclude_unset=True)
    if "slug" in updates and updates["slug"]:
        updates["slug"] = await unique_website_event_slug(db, updates["slug"], exclude_id=row.id)
    if "country" in updates and updates["country"]:
        updates["country"] = updates["country"].strip().lower()
    if "organization_id" in updates and updates["organization_id"] and not updates.get("host_org_name"):
        org = await db.get(Organization, updates["organization_id"])
        if org and not row.host_org_name:
            updates["host_org_name"] = org.name_latin
    for k, v in updates.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.post("/events/{event_id}/publish", response_model=WebsiteEventOut)
async def admin_toggle_publish_event(
    event_id: UUID,
    body: PublishToggleIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    row.is_published = body.is_published
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return (await serialize_website_events(db, [row]))[0]


@router.delete("/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_website_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    row = await db.get(WebsiteEvent, event_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.delete(row)
    await db.commit()
    return None


# ── Organization Accounts & Event Assignment ─────────────────────────────────
def _safe_uuids(raw: list[Any] | None) -> list[UUID]:
    out: list[UUID] = []
    for item in raw or []:
        try:
            out.append(item if isinstance(item, UUID) else UUID(str(item)))
        except (ValueError, TypeError):
            continue
    return out


def _user_card_id(user: User | None) -> str | None:
    if user is None or user.card_number is None:
        return None
    return format_card_id(user.card_number, user.role_values)


def _password_set_url(user: User, days: int = 7) -> str:
    from datetime import timedelta

    from app.core.config import settings
    from app.core.security import create_password_set_token

    token = create_password_set_token(user.id, expires_delta=timedelta(days=days))
    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    return f"{base}/set-password?token={token}"


async def _build_reset_link_response(org: Organization, user: User) -> dict:
    reset_url = _password_set_url(user)
    email_sent = await send_password_set_link_email(
        user.email, user.full_name, org.name_latin, reset_url
    )
    return {
        "organization_id": str(org.id),
        "user_id": str(user.id),
        "email": user.email,
        "reset_url": reset_url,
        "email_sent": email_sent,
    }


async def _serialize_org_summaries(db: AsyncSession, orgs: list[Organization]) -> list[dict]:
    if not orgs:
        return []

    org_ids = [o.id for o in orgs]
    org_id_set = set(org_ids)

    owner_ids = {o.owner_user_id for o in orgs if o.owner_user_id}
    user_conds: list[Any] = [User.organization_id.in_(org_ids)]
    if owner_ids:
        user_conds.append(User.id.in_(owner_ids))
    user_rows = (
        await db.execute(select(User).where(or_(*user_conds)))
    ).scalars().all()
    users_by_id: dict[UUID, User] = {u.id: u for u in user_rows}
    org_team_user_ids: dict[UUID, set[UUID]] = {oid: set() for oid in org_ids}
    for u in user_rows:
        if u.organization_id in org_id_set:
            org_team_user_ids[u.organization_id].add(u.id)
    for o in orgs:
        if o.owner_user_id:
            org_team_user_ids[o.id].add(o.owner_user_id)

    # Programs and cohorts owned by these organizations
    owned_programs = (
        await db.execute(select(Program).where(Program.organization_id.in_(org_ids)))
    ).scalars().all()
    programs_by_org: dict[UUID, set[UUID]] = {oid: set() for oid in org_ids}
    for p in owned_programs:
        if p.organization_id in org_id_set:
            programs_by_org[p.organization_id].add(p.id)

    cohort_rows = (
        await db.execute(
            select(Cohort, Program)
            .join(Program, Program.id == Cohort.program_id)
            .where(
                Cohort.status != "draft",
                ~Cohort.name.ilike("[Template]%"),
                func.lower(func.trim(Cohort.name)) != "template",
                or_(Cohort.organization_id.in_(org_ids), Program.organization_id.in_(org_ids)),
            )
        )
    ).all()
    cohorts_by_org: dict[UUID, list[Cohort]] = {oid: [] for oid in org_ids}
    cohort_to_org: dict[UUID, UUID] = {}
    cohort_by_id: dict[UUID, Cohort] = {}
    for c, p in cohort_rows:
        eff_org = c.organization_id or p.organization_id
        if eff_org in org_id_set:
            cohorts_by_org[eff_org].append(c)
            cohort_to_org[c.id] = eff_org
            cohort_by_id[c.id] = c
            programs_by_org[eff_org].add(p.id)

    all_cohort_ids = list(cohort_by_id.keys())

    # Website events counts (total & published)
    event_rows = (
        await db.execute(
            select(WebsiteEvent.organization_id, WebsiteEvent.is_published)
            .where(WebsiteEvent.organization_id.in_(org_ids))
        )
    ).all()
    events_total: dict[UUID, int] = {}
    events_published: dict[UUID, int] = {}
    for oid, is_pub in event_rows:
        if oid in org_id_set:
            events_total[oid] = events_total.get(oid, 0) + 1
            if is_pub:
                events_published[oid] = events_published.get(oid, 0) + 1

    # Active student registrations per cohort
    reg_counts: dict[UUID, int] = {}
    obs_counts: dict[UUID, int] = {}
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

    # Courses authored by org + total published platform courses
    course_rows = (
        await db.execute(
            select(Course.organization_id, Course.is_published, Course.submitted_for_review_at)
            .where(Course.organization_id.in_(org_ids))
        )
    ).all()
    authored_counts: dict[UUID, int] = {}
    pending_review_counts: dict[UUID, int] = {}
    for oid, is_pub, submitted_at in course_rows:
        if oid in org_id_set:
            authored_counts[oid] = authored_counts.get(oid, 0) + 1
            if not is_pub and submitted_at is not None:
                pending_review_counts[oid] = pending_review_counts.get(oid, 0) + 1

    platform_course_count = await db.scalar(
        select(func.count(Course.id)).where(Course.organization_id.is_(None), Course.is_published == True)  # noqa: E712
    ) or 0

    # Quiz templates & questions authored by org
    qt_counts = dict(
        (
            await db.execute(
                select(CohortQuizTemplate.organization_id, func.count(CohortQuizTemplate.id))
                .where(CohortQuizTemplate.organization_id.in_(org_ids))
                .group_by(CohortQuizTemplate.organization_id)
            )
        ).all()
    )
    qq_counts = dict(
        (
            await db.execute(
                select(CohortQuizQuestion.organization_id, func.count(CohortQuizQuestion.id))
                .where(CohortQuizQuestion.organization_id.in_(org_ids))
                .group_by(CohortQuizQuestion.organization_id)
            )
        ).all()
    )

    # Invite code batches linked by creator or granted cohort
    all_team_uids = {uid for s in org_team_user_ids.values() for uid in s}
    creator_to_orgs: dict[UUID, set[UUID]] = {}
    for oid, uids in org_team_user_ids.items():
        for uid in uids:
            creator_to_orgs.setdefault(uid, set()).add(oid)

    codes_by_id: dict[UUID, InvitationCode] = {}
    code_orgs: dict[UUID, set[UUID]] = {}
    if all_team_uids:
        inv_rows = (
            await db.execute(
                select(InvitationCode).where(
                    InvitationCode.kind.in_(["student", "observer"]),
                    InvitationCode.created_by.in_(all_team_uids),
                )
            )
        ).scalars().all()
        for inv in inv_rows:
            codes_by_id[inv.id] = inv
            for oid in creator_to_orgs.get(inv.created_by, ()):
                code_orgs.setdefault(inv.id, set()).add(oid)

    if all_cohort_ids:
        grant_rows = (
            await db.execute(
                select(InvitationCodeGrant.cohort_id, InvitationCode)
                .join(InvitationCode, InvitationCode.id == InvitationCodeGrant.invitation_code_id)
                .where(InvitationCodeGrant.cohort_id.in_(all_cohort_ids))
            )
        ).all()
        for cid, inv in grant_rows:
            codes_by_id[inv.id] = inv
            oid = cohort_to_org.get(cid)
            if oid:
                code_orgs.setdefault(inv.id, set()).add(oid)

    now_utc = datetime.now(timezone.utc)
    invite_active_counts: dict[UUID, int] = {}
    invite_used_totals: dict[UUID, int] = {}
    invite_max_totals: dict[UUID, int] = {}
    for cid_code, oids in code_orgs.items():
        inv = codes_by_id[cid_code]
        is_live = bool(inv.is_active and (inv.expires_at is None or inv.expires_at > now_utc))
        for oid in oids:
            if is_live:
                invite_active_counts[oid] = invite_active_counts.get(oid, 0) + 1
            invite_used_totals[oid] = invite_used_totals.get(oid, 0) + (inv.used_count or 0)
            invite_max_totals[oid] = invite_max_totals.get(oid, 0) + (inv.max_uses or 0)

    out: list[dict] = []
    for o in orgs:
        owner = users_by_id.get(o.owner_user_id) if o.owner_user_id else None
        org_cohorts = cohorts_by_org.get(o.id, [])
        running_cohorts = sum(1 for c in org_cohorts if c.status == "running")

        enrolled_total = 0
        highest_stud = 0
        highest_stud_name = None
        highest_obs = 0
        highest_obs_name = None
        for c in org_cohorts:
            sc = reg_counts.get(c.id, 0)
            oc = obs_counts.get(c.id, 0)
            enrolled_total += sc
            if sc > highest_stud or (sc == highest_stud and highest_stud_name is None and sc > 0):
                highest_stud = sc
                highest_stud_name = c.name
            if oc > highest_obs or (oc == highest_obs and highest_obs_name is None and oc > 0):
                highest_obs = oc
                highest_obs_name = c.name

        allowed_courses = [str(c) for c in (o.allowed_course_ids or [])]
        allowed_quizzes = [str(q) for q in (o.allowed_quiz_template_ids or [])]
        allowed_readiness = [str(r) for r in (getattr(o, "allowed_readiness_preset_ids", None) or [])]
        shared_cnt = platform_course_count if o.course_scope_all else len(_safe_uuids(allowed_courses))

        out.append(
            {
                "id": o.id,
                "name_latin": o.name_latin,
                "name_arabic": o.name_arabic,
                "org_type": o.org_type,
                "country": o.country,
                "city": o.city,
                "created_at": o.created_at,
                "owner_user_id": o.owner_user_id,
                "owner_email": owner.email if owner else None,
                "owner_name": owner.full_name if owner else None,
                "owner_phone": owner.phone if owner else None,
                "owner_status": owner.status if owner else None,
                "owner_card_id": _user_card_id(owner),
                "logo_url": owner.photo_url if owner else None,
                "events_count": events_total.get(o.id, 0),
                "published_events_count": events_published.get(o.id, 0),
                "members_count": max(len(org_team_user_ids.get(o.id, set())), 1 if o.owner_user_id else 0),
                "programs_count": len(programs_by_org.get(o.id, set())),
                "cohorts_count": len(org_cohorts),
                "running_cohorts_count": running_cohorts,
                "enrolled_students_count": enrolled_total,
                "highest_cohort_students": highest_stud,
                "highest_cohort_name": highest_stud_name,
                "highest_cohort_observers": highest_obs,
                "highest_observers_cohort_name": highest_obs_name,
                "authored_courses_count": authored_counts.get(o.id, 0),
                "pending_review_courses_count": pending_review_counts.get(o.id, 0),
                "shared_courses_count": shared_cnt,
                "invite_batches_active_count": invite_active_counts.get(o.id, 0),
                "invite_used_count": invite_used_totals.get(o.id, 0),
                "invite_max_count": invite_max_totals.get(o.id, 0),
                "quiz_templates_authored_count": qt_counts.get(o.id, 0),
                "quiz_questions_authored_count": qq_counts.get(o.id, 0),
                "is_approved": o.is_approved,
                "can_publish_events": o.can_publish_events,
                "can_author_courses": o.can_author_courses,
                "can_publish_courses": o.can_publish_courses,
                "course_scope_all": o.course_scope_all,
                "allowed_course_ids": allowed_courses,
                "quiz_scope": o.quiz_scope or "own",
                "allowed_quiz_template_ids": allowed_quizzes,
                "readiness_scope": getattr(o, "readiness_scope", None) or "own",
                "allowed_readiness_preset_ids": allowed_readiness,
                "max_events": o.max_events,
                "max_programs": o.max_programs,
                "max_cohorts": o.max_cohorts,
                "max_students_per_cohort": o.max_students_per_cohort,
                "max_observers_per_cohort": o.max_observers_per_cohort,
            }
        )
    return out


@router.get("/organizations", response_model=list[OrganizationSummaryOut])
async def admin_list_event_organizations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    orgs = (
        await db.execute(
            select(Organization)
            .where(Organization.owner_user_id.is_not(None))
            .order_by(Organization.name_latin.asc())
        )
    ).scalars().all()
    return await _serialize_org_summaries(db, orgs)


@router.get("/organizations/{org_id}/detail", response_model=OrganizationDetailOut)
async def admin_get_organization_detail(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    summary = (await _serialize_org_summaries(db, [org]))[0]

    # Programs & Cohorts
    cohort_rows = (
        await db.execute(
            select(Cohort, Program)
            .join(Program, Program.id == Cohort.program_id)
            .where(
                Cohort.status != "draft",
                ~Cohort.name.ilike("[Template]%"),
                func.lower(func.trim(Cohort.name)) != "template",
                or_(Cohort.organization_id == org.id, Program.organization_id == org.id),
            )
            .order_by(Cohort.created_at.desc())
        )
    ).all()
    owned_cohort_pairs = [
        (c, p) for c, p in cohort_rows if (c.organization_id or p.organization_id) == org.id
    ]
    cohort_ids = [c.id for c, _ in owned_cohort_pairs]

    owned_prog_ids = {p.id for _, p in owned_cohort_pairs}
    prog_conds: list[Any] = [Program.organization_id == org.id]
    if owned_prog_ids:
        prog_conds.append(Program.id.in_(owned_prog_ids))
    owned_programs = (
        await db.execute(
            select(Program)
            .where(or_(*prog_conds))
            .order_by(Program.created_at.desc())
        )
    ).scalars().all()
    program_ids = [p.id for p in owned_programs]

    # Program LMS checklists + cohort overrides
    lms_progs_by_prog_id: dict[UUID, LmsProgram] = {}
    items_by_owner: dict[tuple[str, UUID], list[LmsProgramItem]] = {}
    if program_ids:
        lp_rows = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id.in_(program_ids)))
        ).scalars().all()
        lms_progs_by_prog_id = {lp.program_id: lp for lp in lp_rows if lp.program_id}
        lp_ids = [lp.id for lp in lp_rows]
        if lp_ids:
            p_items = (
                await db.execute(
                    select(LmsProgramItem)
                    .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id.in_(lp_ids))
                    .order_by(LmsProgramItem.position.asc())
                )
            ).scalars().all()
            for it in p_items:
                items_by_owner.setdefault(("program", it.owner_id), []).append(it)

    overrides_by_cohort: dict[UUID, LmsProgramCohortOverride] = {}
    if cohort_ids:
        ov_rows = (
            await db.execute(
                select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id.in_(cohort_ids))
            )
        ).scalars().all()
        overrides_by_cohort = {ov.cohort_id: ov for ov in ov_rows}
        ov_ids = [ov.id for ov in ov_rows]
        if ov_ids:
            ov_items = (
                await db.execute(
                    select(LmsProgramItem)
                    .where(
                        LmsProgramItem.owner_type == "cohort_override",
                        LmsProgramItem.owner_id.in_(ov_ids),
                    )
                    .order_by(LmsProgramItem.position.asc())
                )
            ).scalars().all()
            for it in ov_items:
                items_by_owner.setdefault(("cohort_override", it.owner_id), []).append(it)

    cohort_count_by_prog: dict[UUID, int] = {}
    for c, _ in owned_cohort_pairs:
        cohort_count_by_prog[c.program_id] = cohort_count_by_prog.get(c.program_id, 0) + 1

    programs_out = []
    for p in owned_programs:
        lp = lms_progs_by_prog_id.get(p.id)
        p_items = items_by_owner.get(("program", lp.id), []) if lp else []
        programs_out.append(
            {
                "id": p.id,
                "name": p.name,
                "program_type": p.program_type,
                "active": p.active,
                "lms_program_id": lp.id if lp else None,
                "checklist_name": lp.name if lp else None,
                "certificate_required": lp.certificate_required if lp else True,
                "cohorts_count": cohort_count_by_prog.get(p.id, 0),
                "checklist_items": [
                    {
                        "id": it.id,
                        "position": it.position,
                        "title": it.title,
                        "item_type": it.item_type,
                        "optional": it.optional,
                        "scope": it.scope,
                    }
                    for it in p_items
                ],
            }
        )

    # Sessions, registrations, observers & assignment completion per cohort
    reg_counts: dict[UUID, int] = {}
    obs_counts: dict[UUID, int] = {}
    sess_counts: dict[UUID, int] = {}
    cohort_avg_completion: dict[UUID, int] = {}
    user_cohort_completion: dict[tuple[UUID, UUID], int] = {}

    if cohort_ids:
        reg_counts = dict(
            (
                await db.execute(
                    select(Registration.cohort_id, func.count(Registration.id))
                    .where(
                        Registration.cohort_id.in_(cohort_ids),
                        Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                    )
                    .group_by(Registration.cohort_id)
                )
            ).all()
        )
        obs_counts = dict(
            (
                await db.execute(
                    select(LmsProgramAssignment.cohort_id, func.count(LmsProgramAssignment.id))
                    .where(
                        LmsProgramAssignment.cohort_id.in_(cohort_ids),
                        LmsProgramAssignment.mode == "observer",
                    )
                    .group_by(LmsProgramAssignment.cohort_id)
                )
            ).all()
        )
        sess_counts = dict(
            (
                await db.execute(
                    select(Session.cohort_id, func.count(Session.id))
                    .where(Session.cohort_id.in_(cohort_ids))
                    .group_by(Session.cohort_id)
                )
            ).all()
        )

        # Checklist completion calculation per assignment & cohort
        assign_rows = (
            await db.execute(
                select(LmsProgramAssignment).where(
                    LmsProgramAssignment.cohort_id.in_(cohort_ids),
                    LmsProgramAssignment.mode == "participant",
                )
            )
        ).scalars().all()
        assign_ids = [a.id for a in assign_rows]

        done_ind: set[tuple[UUID, UUID]] = set()
        if assign_ids:
            ind_rows = (
                await db.execute(
                    select(LmsProgramItemProgress.assignment_id, LmsProgramItemProgress.item_id).where(
                        LmsProgramItemProgress.assignment_id.in_(assign_ids),
                        LmsProgramItemProgress.status == "done",
                    )
                )
            ).all()
            done_ind = {(aid, iid) for aid, iid in ind_rows}

        team_rows = (
            await db.execute(
                select(Team.id, Team.cohort_id, TeamMember.user_id)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(Team.cohort_id.in_(cohort_ids), Team.is_observer == False)  # noqa: E712
            )
        ).all()
        user_cohort_team: dict[tuple[UUID, UUID], UUID] = {}
        team_ids: set[UUID] = set()
        for tid, cid, uid in team_rows:
            if cid:
                user_cohort_team[(uid, cid)] = tid
                team_ids.add(tid)

        done_team: set[tuple[UUID, UUID]] = set()
        if team_ids:
            tp_rows = (
                await db.execute(
                    select(LmsProgramTeamItemProgress.team_id, LmsProgramTeamItemProgress.item_id).where(
                        LmsProgramTeamItemProgress.team_id.in_(team_ids),
                        LmsProgramTeamItemProgress.status == "done",
                    )
                )
            ).all()
            done_team = {(tid, iid) for tid, iid in tp_rows}

        resolved_items_by_cohort: dict[UUID, list[LmsProgramItem]] = {}
        for c, _ in owned_cohort_pairs:
            ov = overrides_by_cohort.get(c.id)
            if ov is not None and ("cohort_override", ov.id) in items_by_owner:
                items = items_by_owner[("cohort_override", ov.id)]
            else:
                lp = lms_progs_by_prog_id.get(c.program_id)
                items = items_by_owner.get(("program", lp.id), []) if lp else []
            req = [it for it in items if not it.optional]
            resolved_items_by_cohort[c.id] = req if req else items

        pcts_by_cohort: dict[UUID, list[int]] = {}
        for a in assign_rows:
            if not a.cohort_id:
                continue
            target_items = resolved_items_by_cohort.get(a.cohort_id, [])
            if not target_items:
                p_val = 0
            else:
                tid = user_cohort_team.get((a.user_id, a.cohort_id))
                done_cnt = 0
                for it in target_items:
                    if it.scope == "team":
                        if tid and (tid, it.id) in done_team:
                            done_cnt += 1
                    elif (a.id, it.id) in done_ind:
                        done_cnt += 1
                p_val = round((done_cnt / len(target_items)) * 100)
            user_cohort_completion[(a.user_id, a.cohort_id)] = p_val
            pcts_by_cohort.setdefault(a.cohort_id, []).append(p_val)

        for cid, pct_list in pcts_by_cohort.items():
            cohort_avg_completion[cid] = round(sum(pct_list) / len(pct_list)) if pct_list else 0

    cohorts_out = [
        {
            "id": c.id,
            "program_id": p.id,
            "program_name": p.name,
            "name": c.name,
            "status": c.status,
            "starts_on": c.starts_on.isoformat() if c.starts_on else None,
            "ends_on": c.ends_on.isoformat() if c.ends_on else None,
            "enrolled_count": reg_counts.get(c.id, 0),
            "capacity": c.capacity,
            "observers_count": obs_counts.get(c.id, 0),
            "sessions_count": sess_counts.get(c.id, 0),
            "completion_pct": cohort_avg_completion.get(c.id, 0),
        }
        for c, p in owned_cohort_pairs
    ]

    # Team members & observers (built early so we know org creator IDs for invite codes too)
    team_conds: list[Any] = [User.organization_id == org.id]
    if org.owner_user_id:
        team_conds.append(User.id == org.owner_user_id)
    team_users = (await db.execute(select(User).where(or_(*team_conds)))).scalars().all()
    team_user_map: dict[UUID, User] = {u.id: u for u in team_users}

    cohort_name_by_id = {c.id: c.name for c, _ in owned_cohort_pairs}
    obs_cohorts_by_user: dict[UUID, list[str]] = {}
    if cohort_ids:
        obs_assigns = (
            await db.execute(
                select(LmsProgramAssignment.user_id, LmsProgramAssignment.cohort_id)
                .where(LmsProgramAssignment.cohort_id.in_(cohort_ids), LmsProgramAssignment.mode == "observer")
            )
        ).all()
        obs_uids = {uid for uid, _ in obs_assigns if uid not in team_user_map}
        if obs_uids:
            extra_obs_users = (await db.execute(select(User).where(User.id.in_(obs_uids)))).scalars().all()
            for u in extra_obs_users:
                team_user_map[u.id] = u
        for uid, cid in obs_assigns:
            cname = cohort_name_by_id.get(cid)
            if cname and cname not in obs_cohorts_by_user.setdefault(uid, []):
                obs_cohorts_by_user[uid].append(cname)

    role_labels = {
        "owner": "Owner",
        "coordinator": "Coordinator",
        "instructor": "Instructor",
        "judge": "Judge",
        "observer": "Observer",
    }
    team_out = []
    for uid, u in team_user_map.items():
        is_primary_owner = org.owner_user_id == uid
        has_org_membership = (
            is_primary_owner
            or u.org_role is not None
            or bool(getattr(u, "org_roles", None))
            or "organization" in u.role_values
        )
        # Affiliation is not membership: skip students/trainees whose profile
        # merely points at this organization. Observers assigned to at least
        # one cohort are still included (they're in team_user_map above).
        if not has_org_membership:
            if not obs_cohorts_by_user.get(uid):
                continue
            roles_list = ["observer"]
        else:
            roles_list = effective_org_roles(u, is_owner=is_primary_owner) or ["observer"]
        primary_role = roles_list[0]
        team_out.append(
            {
                "user_id": u.id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "role": ", ".join(role_labels.get(r, "Coordinator") for r in roles_list),
                "is_owner": is_primary_owner,
                "org_role": primary_role,
                "org_roles": roles_list,
                "card_id": _user_card_id(u),
                "status": u.status,
                # `must_change_password` is set on invite and cleared by
                # /auth/set-password, so it's a reliable "invited, not joined yet".
                "invite_pending": bool(u.must_change_password),
                "observer_cohorts": obs_cohorts_by_user.get(u.id, []),
            }
        )
    role_rank = {"owner": 0, "coordinator": 1, "instructor": 2, "judge": 3, "observer": 4}
    team_out.sort(key=lambda m: (role_rank.get(m["org_role"], 9), m["full_name"].lower()))

    # Invite code batches
    org_creator_ids = [u.id for u in team_users]
    inv_conds = []
    if org_creator_ids:
        inv_conds.append(InvitationCode.created_by.in_(org_creator_ids))
    if cohort_ids:
        granted_code_ids_subq = select(InvitationCodeGrant.invitation_code_id).where(
            InvitationCodeGrant.cohort_id.in_(cohort_ids)
        )
        inv_conds.append(InvitationCode.id.in_(granted_code_ids_subq))

    invite_batches_out = []
    if inv_conds:
        inv_rows = (
            await db.execute(
                select(InvitationCode)
                .where(InvitationCode.kind.in_(["student", "observer"]), or_(*inv_conds))
                .order_by(InvitationCode.created_at.desc())
            )
        ).scalars().all()
        inv_ids = [r.id for r in inv_rows]
        grants_by_code: dict[UUID, list[str]] = {}
        if inv_ids:
            g_rows = (
                await db.execute(
                    select(
                        InvitationCodeGrant.invitation_code_id,
                        InvitationCodeGrant.product_type,
                        Cohort.name,
                        Course.title,
                        LearningPath.title,
                    )
                    .outerjoin(Cohort, Cohort.id == InvitationCodeGrant.cohort_id)
                    .outerjoin(Course, Course.id == InvitationCodeGrant.course_id)
                    .outerjoin(LearningPath, LearningPath.id == InvitationCodeGrant.learning_path_id)
                    .where(InvitationCodeGrant.invitation_code_id.in_(inv_ids))
                )
            ).all()
            for code_id, ptype, cname, ctitle, lptitle in g_rows:
                if cname:
                    grants_by_code.setdefault(code_id, []).append(f"Cohort: {cname}")
                elif ctitle:
                    grants_by_code.setdefault(code_id, []).append(f"Course: {ctitle}")
                elif lptitle:
                    grants_by_code.setdefault(code_id, []).append(f"Path: {lptitle}")
                else:
                    grants_by_code.setdefault(code_id, []).append(ptype)

        now_utc = datetime.now(timezone.utc)
        for inv in inv_rows:
            targets = grants_by_code.get(inv.id, [])
            is_live = bool(inv.is_active and (inv.expires_at is None or inv.expires_at > now_utc))
            invite_batches_out.append(
                {
                    "id": inv.id,
                    "code": inv.code,
                    "label": inv.label,
                    "kind": inv.kind,
                    "granted_target": ", ".join(targets) if targets else None,
                    "used_count": inv.used_count or 0,
                    "max_uses": inv.max_uses or 0,
                    "expires_at": inv.expires_at,
                    "is_active": is_live,
                }
            )

    # Students enrolled across org cohorts
    students_out = []
    if cohort_ids:
        stud_rows = (
            await db.execute(
                select(Registration, Contact, User)
                .join(Contact, Contact.id == Registration.contact_id)
                .outerjoin(User, User.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(cohort_ids),
                    Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                )
                .order_by(Registration.created_at.desc())
            )
        ).all()
        for reg, contact, user in stud_rows:
            comp = user_cohort_completion.get((user.id, reg.cohort_id), 0) if user else 0
            students_out.append(
                {
                    "registration_id": reg.id,
                    "contact_id": contact.id,
                    "user_id": user.id if user else None,
                    "full_name": contact.full_name,
                    "email": contact.email or (user.email if user else ""),
                    "phone": contact.primary_phone_e164 or (user.phone if user else None),
                    "cohort_id": reg.cohort_id,
                    "cohort_name": cohort_name_by_id.get(reg.cohort_id, ""),
                    "status": reg.status,
                    "enrolled_at": reg.created_at,
                    "completion_pct": comp,
                }
            )

    # Authored & Shared LMS courses
    authored_rows = (
        await db.execute(
            select(Course).where(Course.organization_id == org.id).order_by(Course.created_at.desc())
        )
    ).scalars().all()
    authored_ids = [c.id for c in authored_rows]

    allowed_platform_ids = _safe_uuids(org.allowed_course_ids)
    if org.course_scope_all:
        shared_rows = (
            await db.execute(
                select(Course)
                .where(Course.organization_id.is_(None), Course.is_published == True)  # noqa: E712
                .order_by(Course.title.asc())
            )
        ).scalars().all()
    elif allowed_platform_ids:
        shared_rows = (
            await db.execute(
                select(Course)
                .where(Course.id.in_(allowed_platform_ids))
                .order_by(Course.title.asc())
            )
        ).scalars().all()
    else:
        shared_rows = []

    all_course_ids = list({*authored_ids, *[c.id for c in shared_rows]})
    mod_counts: dict[UUID, int] = {}
    enr_counts: dict[UUID, int] = {}
    if all_course_ids:
        mod_counts = dict(
            (
                await db.execute(
                    select(CourseModule.course_id, func.count(CourseModule.id))
                    .where(CourseModule.course_id.in_(all_course_ids))
                    .group_by(CourseModule.course_id)
                )
            ).all()
        )
    if authored_ids:
        enr_counts = dict(
            (
                await db.execute(
                    select(Enrollment.course_id, func.count(Enrollment.id))
                    .where(Enrollment.course_id.in_(authored_ids), Enrollment.status == "active")
                    .group_by(Enrollment.course_id)
                )
            ).all()
        )

    authored_courses_out = [
        {
            "id": c.id,
            "title": c.title,
            "track": c.track,
            "is_published": c.is_published,
            "submitted_for_review_at": c.submitted_for_review_at,
            "modules_count": mod_counts.get(c.id, 0),
            "enrolled_count": enr_counts.get(c.id, 0),
            "created_at": c.created_at,
        }
        for c in authored_rows
    ]
    shared_courses_out = [
        {
            "id": c.id,
            "title": c.title,
            "track": c.track,
            "level": c.level,
            "modules_count": mod_counts.get(c.id, 0),
            "is_published": c.is_published,
        }
        for c in shared_rows
    ]

    # Org Quiz Templates
    qt_rows = (
        await db.execute(
            select(CohortQuizTemplate)
            .where(CohortQuizTemplate.organization_id == org.id)
            .order_by(CohortQuizTemplate.created_at.desc())
        )
    ).scalars().all()
    qt_ids = [qt.id for qt in qt_rows]
    qt_q_counts: dict[UUID, int] = {}
    linked_cohorts_by_qt: dict[UUID, list[str]] = {}
    if qt_ids:
        qt_q_counts = dict(
            (
                await db.execute(
                    select(CohortQuizTemplateQuestion.template_id, func.count(CohortQuizTemplateQuestion.id))
                    .where(CohortQuizTemplateQuestion.template_id.in_(qt_ids))
                    .group_by(CohortQuizTemplateQuestion.template_id)
                )
            ).all()
        )
        # Resolve checklist items pointing at these quiz templates back to org cohorts
        ov_id_to_cohort_name = {ov.id: cohort_name_by_id.get(cid, "") for cid, ov in overrides_by_cohort.items()}
        lp_id_to_cohort_names: dict[UUID, list[str]] = {}
        for c, _ in owned_cohort_pairs:
            lp = lms_progs_by_prog_id.get(c.program_id)
            if lp:
                lp_id_to_cohort_names.setdefault(lp.id, []).append(c.name)

        q_item_rows = (
            await db.execute(
                select(
                    LmsProgramItem.cohort_quiz_template_id,
                    LmsProgramItem.owner_type,
                    LmsProgramItem.owner_id,
                ).where(LmsProgramItem.cohort_quiz_template_id.in_(qt_ids))
            )
        ).all()
        for qtid, otype, oid in q_item_rows:
            if not qtid:
                continue
            target_list = linked_cohorts_by_qt.setdefault(qtid, [])
            if otype == "cohort_override":
                cname = ov_id_to_cohort_name.get(oid)
                if cname and cname not in target_list:
                    target_list.append(cname)
            elif otype == "program":
                for cname in lp_id_to_cohort_names.get(oid, []):
                    if cname not in target_list:
                        target_list.append(cname)

    quiz_templates_out = [
        {
            "id": qt.id,
            "name": qt.name,
            "questions_count": qt_q_counts.get(qt.id, 0),
            "is_active": qt.is_active,
            "linked_cohorts": linked_cohorts_by_qt.get(qt.id, []),
            "created_at": qt.created_at,
        }
        for qt in qt_rows
    ]

    # Event landing pages
    ev_rows = (
        await db.execute(
            select(WebsiteEvent)
            .where(WebsiteEvent.organization_id == org.id)
            .order_by(WebsiteEvent.updated_at.desc())
        )
    ).scalars().all()
    ev_cohort_ids = {ev.cohort_id for ev in ev_rows if ev.cohort_id and ev.cohort_id not in reg_counts}
    extra_ev_reg_counts: dict[UUID, int] = {}
    extra_ev_cohort_names: dict[UUID, str] = {}
    if ev_cohort_ids:
        extra_ev_reg_counts = dict(
            (
                await db.execute(
                    select(Registration.cohort_id, func.count(Registration.id))
                    .where(
                        Registration.cohort_id.in_(ev_cohort_ids),
                        Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                    )
                    .group_by(Registration.cohort_id)
                )
            ).all()
        )
        ec_rows = (await db.execute(select(Cohort.id, Cohort.name).where(Cohort.id.in_(ev_cohort_ids)))).all()
        extra_ev_cohort_names = dict(ec_rows)

    landing_pages_out = [
        {
            "id": ev.id,
            "title": ev.title,
            "slug": ev.slug,
            "country": ev.country,
            "is_published": ev.is_published,
            "cohort_id": ev.cohort_id,
            "cohort_name": (
                cohort_name_by_id.get(ev.cohort_id) or extra_ev_cohort_names.get(ev.cohort_id)
                if ev.cohort_id
                else None
            ),
            "registrations_count": (
                reg_counts.get(ev.cohort_id, extra_ev_reg_counts.get(ev.cohort_id, 0))
                if ev.cohort_id
                else 0
            ),
            "updated_at": ev.updated_at,
        }
        for ev in ev_rows
    ]

    return {
        "organization": summary,
        "programs": programs_out,
        "cohorts": cohorts_out,
        "invite_batches": invite_batches_out,
        "students": students_out,
        "authored_courses": authored_courses_out,
        "shared_courses": shared_courses_out,
        "quiz_templates": quiz_templates_out,
        "landing_pages": landing_pages_out,
        "team": team_out,
    }


@router.post("/organizations/account", response_model=OrganizationSummaryOut, status_code=status.HTTP_201_CREATED)
async def admin_create_organization_account(
    body: OrganizationAccountCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Admin creates an Organization and a portal login account (`organization`
    role) so the organization can log in, create events, and edit assigned events."""
    email = normalize_user_email(body.email)
    existing_user = (
        await db.execute(select(User).where(user_email_matches(email)))
    ).scalars().first()

    if existing_user is not None:
        if "organization" not in existing_user.role_values:
            existing_user.roles = list(existing_user.roles or []) + [UserRole.organization]
        user = existing_user
        contact_id = existing_user.contact_id
    else:
        contact, _ = await resolve_or_create_contact(
            db,
            full_name=body.full_name.strip(),
            phone=(body.phone or "").strip() or None,
            email=email,
            contact_roles=["sponsor_rep"],
            role_event_source="admin_org_account",
            country=(body.country or "uae").strip().lower(),
            city=(body.city or "").strip() or None,
        )
        contact_id = contact.id
        user = User(
            full_name=body.full_name.strip(),
            email=email,
            password_hash=get_password_hash(body.password),
            roles=[UserRole.organization],
            status="active",
            must_change_password=False,
            contact_id=contact.id,
            phone=(body.phone or "").strip() or None,
            country=(body.country or "uae").strip().lower(),
            city_other=(body.city or "").strip() or None,
        )
        db.add(user)
        await db.flush()
        await ensure_card_number(db, user)

    org = Organization(
        name_latin=body.org_name_latin.strip(),
        name_arabic=(body.org_name_arabic or "").strip() or None,
        org_type=(body.org_type or "university").strip().lower(),
        country=(body.country or "uae").strip().lower(),
        city=(body.city or "").strip() or None,
        primary_contact_id=contact_id,
        owner_user_id=user.id,
        is_approved=body.is_approved,
        can_publish_events=body.can_publish_events,
        can_author_courses=body.can_author_courses,
        can_publish_courses=body.can_publish_courses,
        course_scope_all=body.course_scope_all,
        allowed_course_ids=body.allowed_course_ids,
        quiz_scope=(body.quiz_scope or "all").strip().lower(),
        allowed_quiz_template_ids=body.allowed_quiz_template_ids,
        readiness_scope=(body.readiness_scope or "own").strip().lower(),
        allowed_readiness_preset_ids=body.allowed_readiness_preset_ids,
        max_events=body.max_events,
        max_programs=body.max_programs,
        max_cohorts=body.max_cohorts,
        max_students_per_cohort=body.max_students_per_cohort,
        max_observers_per_cohort=body.max_observers_per_cohort,
    )
    db.add(org)
    await db.flush()
    user.organization_id = org.id
    if not (getattr(user, "org_roles", None) or []):
        set_user_org_roles(user, ["owner"])
    await db.commit()
    await db.refresh(org)

    return (await _serialize_org_summaries(db, [org]))[0]


@router.put("/organizations/{org_id}", response_model=OrganizationSummaryOut)
async def admin_update_organization_account(
    org_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    from app.schemas.website_event import OrganizationAccountUpdateIn
    from app.services.spine.identity import replace_user_email

    payload = OrganizationAccountUpdateIn.model_validate(body)
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    if payload.org_name_latin is not None and payload.org_name_latin.strip():
        org.name_latin = payload.org_name_latin.strip()
    if payload.org_name_arabic is not None:
        org.name_arabic = payload.org_name_arabic.strip() or None
    if payload.org_type is not None and payload.org_type.strip():
        org.org_type = payload.org_type.strip().lower()
    if payload.country is not None:
        org.country = payload.country.strip().lower() or None
    if payload.city is not None:
        org.city = payload.city.strip() or None

    if payload.is_approved is not None:
        org.is_approved = payload.is_approved
        from app.models.application import Application
        app_rows = (await db.execute(
            select(Application).where(Application.role == "organization")
        )).scalars().all()
        for a in app_rows:
            if (a.answers or {}).get("organization_id") == str(org.id):
                if payload.is_approved and a.status == "pending":
                    a.status = "approved"
                    a.reviewed_at = datetime.now(timezone.utc)
                    a.reviewed_by = current_user.id
                elif not payload.is_approved and a.status == "approved":
                    a.status = "rejected"
                    a.reviewed_at = datetime.now(timezone.utc)
                    a.reviewed_by = current_user.id
    if payload.can_publish_events is not None:
        org.can_publish_events = payload.can_publish_events
    if payload.can_author_courses is not None:
        org.can_author_courses = payload.can_author_courses
    if payload.can_publish_courses is not None:
        org.can_publish_courses = payload.can_publish_courses
    if payload.course_scope_all is not None:
        org.course_scope_all = payload.course_scope_all
    if payload.allowed_course_ids is not None:
        org.allowed_course_ids = payload.allowed_course_ids
    if payload.quiz_scope is not None and payload.quiz_scope.strip():
        org.quiz_scope = payload.quiz_scope.strip().lower()
    if payload.allowed_quiz_template_ids is not None:
        org.allowed_quiz_template_ids = payload.allowed_quiz_template_ids
    if payload.readiness_scope is not None and payload.readiness_scope.strip():
        org.readiness_scope = payload.readiness_scope.strip().lower()
    if payload.allowed_readiness_preset_ids is not None:
        org.allowed_readiness_preset_ids = payload.allowed_readiness_preset_ids
    if "max_events" in body:
        org.max_events = payload.max_events
    if "max_programs" in body:
        org.max_programs = payload.max_programs
    if "max_cohorts" in body:
        org.max_cohorts = payload.max_cohorts
    if "max_students_per_cohort" in body:
        org.max_students_per_cohort = payload.max_students_per_cohort
    if "max_observers_per_cohort" in body:
        org.max_observers_per_cohort = payload.max_observers_per_cohort

    owner = await db.get(User, org.owner_user_id) if org.owner_user_id else None
    if owner is not None:
        if payload.full_name is not None and payload.full_name.strip():
            owner.full_name = payload.full_name.strip()
        if payload.phone is not None:
            owner.phone = payload.phone.strip() or None
        if payload.email is not None and payload.email.strip():
            new_email = normalize_user_email(payload.email)
            clash = (
                await db.execute(
                    select(User).where(user_email_matches(new_email), User.id != owner.id)
                )
            ).scalars().first()
            if clash is not None:
                raise HTTPException(status_code=409, detail="Email already registered")
            await replace_user_email(db, owner, new_email)
            owner.email = new_email
        if payload.password is not None and payload.password.strip():
            owner.password_hash = get_password_hash(payload.password.strip())
            owner.must_change_password = False
    elif payload.email and payload.password:
        # Link/create a login user for an organization that previously had none
        email = normalize_user_email(payload.email)
        existing_user = (
            await db.execute(select(User).where(user_email_matches(email)))
        ).scalars().first()
        if existing_user is not None:
            if "organization" not in existing_user.role_values:
                existing_user.roles = list(existing_user.roles or []) + [UserRole.organization]
            owner = existing_user
        else:
            contact, _ = await resolve_or_create_contact(
                db,
                full_name=(payload.full_name or org.name_latin).strip(),
                phone=(payload.phone or "").strip() or None,
                email=email,
                contact_roles=["sponsor_rep"],
                role_event_source="admin_org_account",
                country=org.country or "uae",
                city=org.city,
            )
            owner = User(
                full_name=(payload.full_name or org.name_latin).strip(),
                email=email,
                password_hash=get_password_hash(payload.password.strip()),
                roles=[UserRole.organization],
                status="active",
                must_change_password=False,
                contact_id=contact.id,
                phone=(payload.phone or "").strip() or None,
                country=org.country or "uae",
                city_other=org.city,
            )
            db.add(owner)
            await db.flush()
            await ensure_card_number(db, owner)
        org.owner_user_id = owner.id
        owner.organization_id = org.id
    elif owner is not None and owner.organization_id is None:
        owner.organization_id = org.id

    await db.commit()
    await db.refresh(org)

    return (await _serialize_org_summaries(db, [org]))[0]


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_organization_account(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    from sqlalchemy import text
    from app.services import user as user_service

    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    owner_id = org.owner_user_id
    await db.execute(
        text("UPDATE website_events SET organization_id = NULL WHERE organization_id = :oid"),
        {"oid": org_id},
    )
    await db.execute(
        text("UPDATE contacts SET organization_id = NULL WHERE organization_id = :oid"),
        {"oid": org_id},
    )
    cohort_cnt = (
        await db.execute(
            text("SELECT COUNT(*) FROM cohorts WHERE organization_id = :oid"),
            {"oid": org_id},
        )
    ).scalar_one()
    if cohort_cnt == 0:
        await db.delete(org)
    else:
        org.owner_user_id = None
    await db.commit()

    # If the linked user only holds the `organization` role, delete that user account too
    if owner_id is not None:
        owner = await db.get(User, owner_id)
        if owner is not None and owner.role_values == ["organization"]:
            try:
                await user_service.delete_user(db, owner_id)
            except Exception:
                pass
    return None


@router.post("/organizations/{org_id}/reset-link")
async def admin_organization_reset_link(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Generates a 72-hour password reset/set link for the organization's owner user account."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not org.owner_user_id:
        raise HTTPException(status_code=400, detail="This organization has no login account linked yet.")
    owner = await db.get(User, org.owner_user_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Linked user account not found.")

    return await _build_reset_link_response(org, owner)


@router.post("/organizations/{org_id}/members/{user_id}/reset-link")
async def admin_organization_member_reset_link(
    org_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Generates a 72-hour password reset/set link for any team member or observer linked to this org."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    is_member = org.owner_user_id == user.id or user.organization_id == org.id
    if not is_member:
        obs_match = (
            await db.execute(
                select(LmsProgramAssignment.id)
                .join(Cohort, Cohort.id == LmsProgramAssignment.cohort_id)
                .join(Program, Program.id == Cohort.program_id)
                .where(
                    LmsProgramAssignment.user_id == user.id,
                    LmsProgramAssignment.mode == "observer",
                    or_(Cohort.organization_id == org.id, Program.organization_id == org.id),
                )
            )
        ).first()
        is_member = obs_match is not None

    if not is_member:
        raise HTTPException(status_code=404, detail="User is not associated with this organization")

    return await _build_reset_link_response(org, user)


@router.post(
    "/organizations/{org_id}/members",
    response_model=OrgTeamMemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def admin_add_organization_member(
    org_id: UUID,
    body: OrgTeamMemberCreateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Admin/ops invite a coordinator onto an organization's team.

    Same account shape as the org's own self-service add (shared service
    helper) and the same 7-day emailed set-password invite, so staff never
    have to sign in as the partner just to onboard a second person.
    """
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    user, created = await build_organization_team_member(
        db,
        org=org,
        full_name=body.full_name,
        email=str(body.email),
        password=body.password,
        phone=body.phone,
        role_event_source="admin_org_team_member",
        org_role=body.org_role,
        org_roles=body.org_roles,
    )

    base = (settings.FRONTEND_URL or "http://localhost:5173").rstrip("/")
    if created:
        email_sent = await send_org_team_invite_email(
            user.email, user.full_name, org.name_latin, _password_set_url(user)
        )
    else:
        email_sent = await send_org_team_added_email(
            user.email, user.full_name, org.name_latin, f"{base}/login"
        )
    roles_list = effective_org_roles(user) or ["coordinator"]
    return OrgTeamMemberOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        is_owner=False,
        org_role=roles_list[0],
        org_roles=roles_list,
        invite_email_sent=email_sent,
        existing_account=not created,
    )


@router.patch("/organizations/{org_id}/members/{user_id}", response_model=OrgTeamMemberOut)
async def admin_update_organization_member(
    org_id: UUID,
    user_id: UUID,
    body: OrgTeamMemberUpdateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Admin/ops set a member's sandbox roles from the Ops organization Team tab."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if body.org_roles is None and body.org_role is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide org_roles or org_role",
        )

    is_owner = user_id == org.owner_user_id
    user = await db.get(User, user_id)
    is_member = user is not None and (is_owner or user.organization_id == org.id)
    if user is not None and not is_member:
        obs_match = (
            await db.execute(
                select(LmsProgramAssignment.id)
                .join(Cohort, Cohort.id == LmsProgramAssignment.cohort_id)
                .join(Program, Program.id == Cohort.program_id)
                .where(
                    LmsProgramAssignment.user_id == user.id,
                    LmsProgramAssignment.mode == "observer",
                    or_(Cohort.organization_id == org.id, Program.organization_id == org.id),
                )
            )
        ).first()
        is_member = obs_match is not None
    if not is_member:
        raise HTTPException(status_code=404, detail="User is not associated with this organization")

    roles_list = normalize_org_roles(body.org_roles, fallback_role=body.org_role, is_owner=is_owner)
    user.organization_id = org.id
    set_user_org_roles(user, roles_list)
    merged = list(user.roles or [])
    existing_values = {r.value if hasattr(r, "value") else str(r) for r in merged}
    for needed in global_roles_for_org_roles(roles_list):
        if needed.value not in existing_values:
            merged.append(needed)
    user.roles = merged
    await db.commit()
    await db.refresh(user)

    return OrgTeamMemberOut(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        status=user.status,
        created_at=user.created_at,
        is_owner=is_owner,
        org_role=roles_list[0],
        org_roles=roles_list,
        invite_pending=bool(user.must_change_password),
    )


@router.delete("/organizations/{org_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_remove_organization_member(
    org_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Detach a member without deleting the account (same rule as the org's own
    Team page — an account can be a student elsewhere)."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    if user_id == org.owner_user_id:
        raise HTTPException(status_code=400, detail="Cannot remove the organization primary owner")

    user = await db.get(User, user_id)
    is_member = user is not None and user.organization_id == org.id
    if user is not None and not is_member:
        obs_match = (
            await db.execute(
                select(LmsProgramAssignment.id)
                .join(Cohort, Cohort.id == LmsProgramAssignment.cohort_id)
                .join(Program, Program.id == Cohort.program_id)
                .where(
                    LmsProgramAssignment.user_id == user.id,
                    LmsProgramAssignment.mode == "observer",
                    or_(Cohort.organization_id == org.id, Program.organization_id == org.id),
                )
            )
        ).first()
        is_member = obs_match is not None
    if not is_member:
        raise HTTPException(status_code=404, detail="User is not associated with this organization")

    org_cohort_ids = (
        select(Cohort.id)
        .outerjoin(Program, Program.id == Cohort.program_id)
        .where(or_(Cohort.organization_id == org.id, Program.organization_id == org.id))
    )
    org_session_ids = select(Session.id).where(Session.cohort_id.in_(org_cohort_ids))

    await db.execute(
        delete(SessionInstructor).where(
            SessionInstructor.user_id == user.id,
            SessionInstructor.session_id.in_(org_session_ids),
        )
    )
    await db.execute(
        delete(CompetitionJudge).where(
            CompetitionJudge.user_id == user.id,
            CompetitionJudge.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.execute(
        delete(CohortLmsEditor).where(
            CohortLmsEditor.user_id == user.id,
            CohortLmsEditor.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.execute(
        delete(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user.id,
            LmsProgramAssignment.cohort_id.in_(org_cohort_ids),
        )
    )
    await db.flush()

    remaining_roles = [
        r for r in (user.roles or [])
        if (r.value if hasattr(r, "value") else str(r)) != "organization"
    ]
    if any((r.value if hasattr(r, "value") else str(r)) == "observer" for r in remaining_roles):
        still_observing = await db.scalar(
            select(LmsProgramAssignment.id)
            .where(
                LmsProgramAssignment.user_id == user.id,
                LmsProgramAssignment.mode == "observer",
            )
            .limit(1)
        )
        if still_observing is None:
            remaining_roles = [
                r for r in remaining_roles
                if (r.value if hasattr(r, "value") else str(r)) != "observer"
            ]
    if not remaining_roles:
        remaining_roles = [UserRole.student]

    user.roles = remaining_roles
    if user.organization_id == org.id:
        user.organization_id = None
    clear_user_org_roles(user)
    if user.contact_id:
        contact = await db.get(Contact, user.contact_id)
        if contact is not None and contact.organization_id == org.id:
            contact.organization_id = None
    await db.commit()
    return None


@router.post("/organizations/{org_id}/courses/{course_id}/publish")
async def admin_toggle_organization_course_publish(
    org_id: UUID,
    course_id: UUID,
    body: PublishToggleIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_website_admin),
):
    """Publishes or unpublishes a course authored by the organization."""
    org = await db.get(Organization, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    course = await db.get(Course, course_id)
    if course is None or course.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Course not found for this organization")

    course.is_published = body.is_published
    await db.commit()
    await db.refresh(course)
    return {
        "id": str(course.id),
        "is_published": course.is_published,
    }
