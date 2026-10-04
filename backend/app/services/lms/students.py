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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.program import LmsProgramAssignment
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.spine.identity import normalize_user_email
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
            last_login_at=u.last_login_at,
        ))
    return out


async def search_students(
    db: AsyncSession, *, q: str | None = None, invite_code: str | None = None,
    login_status: Literal["all", "never", "has_logged_in"] = "all", limit: int = 50,
) -> list[StudentSummaryOut]:
    """Name/email substring search over student accounts, capped at `limit` rows.

    `invite_code` filters to one batch. The literal string `none` selects
    students with no code at all — the ones who signed up before the gate
    existed; without it they'd be unreachable through the filter, since "no
    code" isn't a code you can type.

    `login_status` (2026-09-16) filters on `User.last_login_at` — "never"
    finds an account (however it was created) that's never actually been
    opened, same signal search_cohort_assignable_students's own
    login_status filters on."""
    stmt = select(User).where(User.roles.any("student"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if invite_code:
        if invite_code.strip().lower() == "none":
            stmt = stmt.where(User.invitation_code_used.is_(None))
        else:
            stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
    if login_status == "never":
        stmt = stmt.where(User.last_login_at.is_(None))
    elif login_status == "has_logged_in":
        stmt = stmt.where(User.last_login_at.is_not(None))
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
    # Normalized on both sides + LOWER() on the column, so a legacy
    # mixed-case contact or user row still resolves to the same account
    # instead of reporting "no access".
    missing_emails = {
        normalize_user_email(contacts[cid].email)
        for cid in missing_ids if contacts.get(cid) and contacts[cid].email
    }
    missing_emails.discard("")
    if missing_emails:
        by_email = {
            normalize_user_email(u.email): u for u in
            (await db.execute(select(User).where(func.lower(User.email).in_(missing_emails)))).scalars().all()
        }
        for cid in missing_ids:
            contact = contacts.get(cid)
            if contact and contact.email and normalize_user_email(contact.email) in by_email:
                resolved[cid] = by_email[normalize_user_email(contact.email)]

    users = list({u.id: u for u in resolved.values()}.values())

    if q:
        like = q.strip().lower()
        # None-safe: legacy/bulk-import rows can carry NULL names or
        # non-email values; a bare .lower() would 500 the whole search.
        users = [u for u in users if like in (u.full_name or "").lower() or like in (u.email or "").lower()]
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
    login_status: Literal["all", "never", "has_logged_in"] = "all",
    mode: Literal["all", "student", "observer"] = "student",
) -> list[CompetitionAssignableStudentOut]:
    """Backs the Assign tab's search + filters (`registered_only` added
    2026-09-15 alongside `team_status`/`lms_status`, replacing the old
    boolean `unassigned_only`). `registered_only=False` searches the whole
    platform's student accounts (uncapped, see the note inline below — this
    used to mirror `search_students`'s 50-row cap and that caused real
    confusion, since "all matches" and "this one batch" behaved
    inconsistently) so ops can still find an unregistered invite-code
    signup to assign; `registered_only=True` instead starts from this
    cohort's own Registration rows (`_registered_cohort_users` above),
    same idea, since "everyone actually registered in my competition" is
    the whole point of that view. `login_status` (2026-09-16) filters on
    `User.last_login_at` — "never" means the account (however it was
    created) has never actually been opened, not just that it exists."""
    if registered_only:
        users = await _registered_cohort_users(db, cohort_id=cohort_id, q=q, invite_code=invite_code)
        registered_ids = {u.id for u in users}
    else:
        role_filter = (
            User.roles.any("observer") if mode == "observer"
            else or_(User.roles.any("student"), User.roles.any("observer")) if mode == "all"
            else User.roles.any("student")
        )
        stmt = select(User).where(role_filter)
        if q:
            like = f"%{q.strip()}%"
            stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
        if invite_code:
            if invite_code.strip().lower() == "none":
                stmt = stmt.where(User.invitation_code_used.is_(None))
            else:
                stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
        # No cap at all here (2026-09-15, dropped the last remaining 50-row
        # one) — same reasoning as _registered_cohort_users being fully
        # uncapped: this is one cohort's Assign tab, not an open platform-wide
        # directory, and the actual boundedness comes from the filters above
        # (q/invite_code/team_status/lms_status), not from an arbitrary row
        # count. A cap here silently returns an alphabetically-first slice —
        # "All batches" showing fewer relevant people than one specific batch
        # (found live) was one symptom of that; capping only the *unfiltered*
        # case still left "no filter at all" returning a near-random slice of
        # the whole platform's students instead of an honest "here's
        # everyone, now filter" — worse than just querying it all. Diverges
        # from search_students/`/lms/admin/students` on purpose: that one is
        # a genuine platform-wide people-finder with no cohort to bound it by.
        stmt = stmt.order_by(User.full_name)
        users = (await db.execute(stmt)).scalars().all()

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
        if login_status == "never" and u.last_login_at is not None:
            continue
        if login_status == "has_logged_in" and u.last_login_at is None:
            continue
        team_id, team_name = team_by_user.get(u.id, (None, None))
        out.append(CompetitionAssignableStudentOut(
            **summary.model_dump(), team_id=team_id, team_name=team_name,
            registered=u.id in registered_ids, lms_access=has_lms,
        ))
    return out
