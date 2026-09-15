"""Student search (extracted 2026-09-14 from `routers/lms/admin.py::search_students`
so the Competition Judging Assign tab can reuse the exact same search — name/email
substring, invite-code batch filter — instead of re-implementing it, and layer its
own cohort-scoped filters on top (`search_cohort_assignable_students` below, added
2026-09-15). Behavior of `search_students` itself is unchanged from the original
inline version; only the call site moved.
"""

from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team, TeamMember
from app.models.user import User
from app.schemas.competitions import CompetitionAssignableStudentOut
from app.schemas.lms_admin import StudentSummaryOut


async def _summarize_users(db: AsyncSession, users: list[User]) -> list[StudentSummaryOut]:
    """Shared row-building for both `search_students` and
    `search_cohort_assignable_students` — school/grade live on the linked
    spine Contact, not on `users`, resolved in two batched queries rather
    than one pair per row."""
    labels = dict((await db.execute(
        select(InvitationCode.code, InvitationCode.label).where(InvitationCode.kind == "student")
    )).all())

    contact_ids = [u.contact_id for u in users if u.contact_id]
    contacts = {
        c.id: c for c in (
            (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            if contact_ids else []
        )
    }
    org_ids = {c.organization_id for c in contacts.values() if c.organization_id}
    orgs = {
        o.id: o for o in (
            (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
            if org_ids else []
        )
    }

    out = []
    for u in users:
        contact = contacts.get(u.contact_id) if u.contact_id else None
        org = orgs.get(contact.organization_id) if contact and contact.organization_id else None
        out.append(StudentSummaryOut(
            id=u.id, full_name=u.full_name, nickname=u.nickname, email=u.email,
            invite_code=u.invitation_code_used,
            invite_label=labels.get(u.invitation_code_used) if u.invitation_code_used else None,
            school_name=org.name_latin if org else None,
            grade=contact.grade if contact else None,
            status=u.status,
            created_at=u.created_at,
        ))
    return out


async def search_students(
    db: AsyncSession, *, q: str | None = None, invite_code: str | None = None, limit: int = 50,
) -> list[StudentSummaryOut]:
    """Name/email substring search over student accounts, capped at `limit` rows.

    `invite_code` filters to one batch. The literal string `none` selects
    students with no code at all — the ones who signed up before the gate
    existed; without it they'd be unreachable through the filter, since "no
    code" isn't a code you can type."""
    stmt = select(User).where(User.roles.any("student"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if invite_code:
        if invite_code.strip().lower() == "none":
            stmt = stmt.where(User.invitation_code_used.is_(None))
        else:
            stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
    rows = (await db.execute(stmt.order_by(User.full_name).limit(limit))).scalars().all()
    return await _summarize_users(db, rows)


async def _registered_cohort_users(
    db: AsyncSession, *, cohort_id: uuid.UUID, q: str | None, invite_code: str | None,
) -> list[User]:
    """Every non-cancelled Registration in `cohort_id`, resolved to its
    student account — same contact_id-first, email-fallback resolution
    `get_or_create_student_account` (services/lms/ops_integration.py) and
    `scripts/backfill_registration_access.py` both use, so "registered"
    here means the same thing it does everywhere else in the app, not a
    simpler approximation. `q`/`invite_code` are applied in Python after
    resolving, since they're User-field filters and the candidate set here
    is already cohort-bounded (at most a cohort's roster, not the whole
    student body) rather than needing a DB-level filter to stay small."""
    contact_ids = list(set((await db.execute(
        select(Registration.contact_id).where(
            Registration.cohort_id == cohort_id, Registration.status != "cancelled",
        )
    )).scalars().all()))
    if not contact_ids:
        return []

    contacts = {
        c.id: c for c in
        (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
    }

    linked = (await db.execute(select(User).where(User.contact_id.in_(contact_ids)))).scalars().all()
    resolved: dict[uuid.UUID, User] = {u.contact_id: u for u in linked}

    missing_ids = [cid for cid in contact_ids if cid not in resolved]
    missing_emails = {
        contacts[cid].email for cid in missing_ids if contacts.get(cid) and contacts[cid].email
    }
    if missing_emails:
        by_email = {
            u.email: u for u in
            (await db.execute(select(User).where(User.email.in_(missing_emails)))).scalars().all()
        }
        for cid in missing_ids:
            contact = contacts.get(cid)
            if contact and contact.email and contact.email in by_email:
                resolved[cid] = by_email[contact.email]

    users = list({u.id: u for u in resolved.values()}.values())

    if q:
        like = q.strip().lower()
        users = [u for u in users if like in u.full_name.lower() or like in u.email.lower()]
    if invite_code:
        if invite_code.strip().lower() == "none":
            users = [u for u in users if u.invitation_code_used is None]
        else:
            code = invite_code.strip().upper()
            users = [u for u in users if u.invitation_code_used == code]

    users.sort(key=lambda u: u.full_name)
    return users


async def search_cohort_assignable_students(
    db: AsyncSession, *, cohort_id: uuid.UUID, q: str | None = None, invite_code: str | None = None,
    registered_only: bool = False,
    team_status: Literal["all", "has_team", "no_team"] = "all",
    lms_status: Literal["all", "has_access", "no_access"] = "all",
) -> list[CompetitionAssignableStudentOut]:
    """Backs the Assign tab's search + filters (`registered_only` added
    2026-09-15 alongside `team_status`/`lms_status`, replacing the old
    boolean `unassigned_only`). `registered_only=False` keeps the original
    platform-wide student search (capped at 50, same as `/lms/admin/
    students`) so ops can still find an unregistered invite-code signup to
    assign; `registered_only=True` instead starts from this cohort's own
    Registration rows (`_registered_cohort_users` above), uncapped, since
    "everyone actually registered in my competition" is the whole point of
    that view and a cohort's roster is bounded by nature, unlike an
    open-ended name search."""
    if registered_only:
        users = await _registered_cohort_users(db, cohort_id=cohort_id, q=q, invite_code=invite_code)
        registered_ids = {u.id for u in users}
    else:
        stmt = select(User).where(User.roles.any("student"))
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
        if invite_code:
            if invite_code.strip().lower() == "none":
                stmt = stmt.where(User.invitation_code_used.is_(None))
            else:
                stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
        users = (await db.execute(stmt.order_by(User.full_name).limit(50))).scalars().all()

        contact_ids = [u.contact_id for u in users if u.contact_id]
        registered_contact_ids = set((await db.execute(
            select(Registration.contact_id).where(
                Registration.cohort_id == cohort_id, Registration.status != "cancelled",
                Registration.contact_id.in_(contact_ids),
            )
        )).scalars().all()) if contact_ids else set()
        registered_ids = {u.id for u in users if u.contact_id in registered_contact_ids}

    if not users:
        return []

    summaries = await _summarize_users(db, users)
    user_ids = [u.id for u in users]

    team_rows = (await db.execute(
        select(TeamMember.user_id, Team.roster_team_id, Team.name)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.cohort_id == cohort_id, TeamMember.user_id.in_(user_ids))
    )).all()
    team_by_user = {row.user_id: (row.roster_team_id, row.name) for row in team_rows}

    lms_user_ids = set((await db.execute(
        select(LmsProgramAssignment.user_id).where(
            LmsProgramAssignment.cohort_id == cohort_id, LmsProgramAssignment.user_id.in_(user_ids),
        )
    )).scalars().all())

    out = []
    for u, summary in zip(users, summaries):
        has_team = u.id in team_by_user
        has_lms = u.id in lms_user_ids
        if team_status == "has_team" and not has_team:
            continue
        if team_status == "no_team" and has_team:
            continue
        if lms_status == "has_access" and not has_lms:
            continue
        if lms_status == "no_access" and has_lms:
            continue
        team_id, team_name = team_by_user.get(u.id, (None, None))
        out.append(CompetitionAssignableStudentOut(
            **summary.model_dump(), team_id=team_id, team_name=team_name,
            registered=u.id in registered_ids, lms_access=has_lms,
        ))
    return out
