"""Student search (extracted 2026-09-14 from `routers/lms/admin.py::search_students`
so the Competition Judging Assign tab can reuse the exact same search — name/email
substring, invite-code batch filter — instead of re-implementing it, and layer its
own cohort-scoped filters on top (`search_cohort_assignable_students` below, added
2026-09-15). Behavior of `search_students` itself is unchanged from the original
inline version; only the call site moved.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid
from typing import Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.invite_grant import UserInvitationCode
from app.models.lms.program import LmsProgram, LmsProgramAssignment
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.spine.identity import normalize_user_email
from app.schemas.competitions import CompetitionAssignableStudentOut
from app.schemas.lms_admin import StudentInviteBadgeOut, StudentSummaryOut


async def _summarize_users(db: AsyncSession, users: list[User]) -> list[StudentSummaryOut]:
    """Shared row-building for both `search_students` and
    `search_cohort_assignable_students` — school/grade live on the linked
    spine Contact, not on `users`, resolved in two batched queries rather
    than one pair per row."""
    if not users:
        return []

    labels = dict((await db.execute(
        select(InvitationCode.code, InvitationCode.label).where(InvitationCode.kind.in_(["student", "observer"]))
    )).all())

    user_ids = [u.id for u in users]
    user_codes_map: dict[uuid.UUID, list[StudentInviteBadgeOut]] = {}
    if user_ids:
        code_rows = (await db.execute(
            select(
                UserInvitationCode.user_id,
                UserInvitationCode.code,
                InvitationCode.label,
                InvitationCode.kind,
                UserInvitationCode.redeemed_at,
            )
            .outerjoin(
                InvitationCode,
                InvitationCode.id == UserInvitationCode.invitation_code_id,
            )
            .where(UserInvitationCode.user_id.in_(user_ids))
            .order_by(UserInvitationCode.redeemed_at.desc())
        )).all()
        for r in code_rows:
            user_codes_map.setdefault(r.user_id, []).append(
                StudentInviteBadgeOut(
                    code=r.code,
                    label=r.label,
                    kind=r.kind or "student",
                    redeemed_at=r.redeemed_at,
                )
            )

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
        badges = user_codes_map.get(u.id, [])
        if not badges and u.invitation_code_used:
            badges = [
                StudentInviteBadgeOut(
                    code=u.invitation_code_used,
                    label=labels.get(u.invitation_code_used),
                    kind="student",
                    redeemed_at=u.created_at or datetime.now(timezone.utc),
                )
            ]
        newest = badges[0] if badges else None
        out.append(StudentSummaryOut(
            id=u.id, full_name=u.full_name, nickname=u.nickname, email=u.email,
            invite_code=newest.code if newest else u.invitation_code_used,
            invite_label=newest.label if newest else (labels.get(u.invitation_code_used) if u.invitation_code_used else None),
            invite_codes=badges,
            school_name=org.name_latin if org else None,
            grade=contact.grade if contact else None,
            status=u.status,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        ))
    return out


def org_student_filter(org_id: uuid.UUID):
    org_cohort_subq = select(Cohort.id).outerjoin(Program, Cohort.program_id == Program.id).where(
        or_(Cohort.organization_id == org_id, Program.organization_id == org_id)
    )
    org_lms_prog_subq = select(LmsProgram.id).join(Program, LmsProgram.program_id == Program.id).where(
        Program.organization_id == org_id
    )
    has_org_assignment = exists(
        select(1).where(
            LmsProgramAssignment.user_id == User.id,
            or_(
                LmsProgramAssignment.cohort_id.in_(org_cohort_subq),
                LmsProgramAssignment.lms_program_id.in_(org_lms_prog_subq),
            ),
        )
    )
    has_org_registration = exists(
        select(1).where(
            Registration.cohort_id.in_(org_cohort_subq),
            Registration.status.not_in(["cancelled", "rejected"]),
            or_(
                Registration.contact_id == User.contact_id,
                exists(
                    select(1).where(
                        Contact.id == Registration.contact_id,
                        func.lower(Contact.email) == func.lower(User.email),
                    )
                ),
            ),
        )
    )
    has_org_contact = exists(
        select(1).where(
            Contact.organization_id == org_id,
            or_(
                Contact.id == User.contact_id,
                func.lower(Contact.email) == func.lower(User.email),
            ),
        )
    )
    is_org_member = User.organization_id == org_id
    return or_(is_org_member, has_org_contact, has_org_assignment, has_org_registration)


async def user_belongs_to_organization(db: AsyncSession, user_id: uuid.UUID, org_id: uuid.UUID) -> bool:
    stmt = select(1).select_from(User).where(
        User.id == user_id,
        org_student_filter(org_id),
    )
    return (await db.scalar(stmt)) is not None


async def search_students(
    db: AsyncSession, *, q: str | None = None, invite_code: str | None = None,
    login_status: Literal["all", "never", "has_logged_in"] = "all",
    mode: Literal["student", "observer", "all"] = "student",
    limit: int = 50,
    org_id: uuid.UUID | None = None,
) -> list[StudentSummaryOut]:
    """Name/email substring search over student accounts, capped at `limit` rows.

    `invite_code` filters to one batch. The literal string `none` selects
    students with no code at all — the ones who signed up before the gate
    existed; without it they'd be unreachable through the filter, since "no
    code" isn't a code you can type.

    `login_status` (2026-09-16) filters on `User.last_login_at` — "never"
    finds an account (however it was created) that's never actually been
    opened, same signal search_cohort_assignable_students's own
    login_status filters on.

    `mode` (operations roster toggle): "student" = student role without
    observer, "observer" = has observer role, "all" = either."""
    if mode == "observer":
        role_filter = User.roles.any("observer")
    elif mode == "student":
        role_filter = and_(User.roles.any("student"), ~User.roles.any("observer"))
    else:
        role_filter = or_(User.roles.any("student"), User.roles.any("observer"))
    stmt = select(User).where(role_filter)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if invite_code:
        if invite_code.strip().lower() == "none":
            stmt = stmt.where(
                User.invitation_code_used.is_(None),
                ~exists(select(1).where(UserInvitationCode.user_id == User.id)),
            )
        else:
            code = invite_code.strip().upper()
            stmt = stmt.where(
                or_(
                    exists(
                        select(1).where(
                            UserInvitationCode.user_id == User.id,
                            UserInvitationCode.code == code,
                        )
                    ),
                    User.invitation_code_used == code,
                )
            )
    if login_status == "never":
        stmt = stmt.where(User.last_login_at.is_(None))
    elif login_status == "has_logged_in":
        stmt = stmt.where(User.last_login_at.is_not(None))
    if org_id is not None:
        stmt = stmt.where(org_student_filter(org_id))
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
        want_card = q.strip().isdigit()
        # None-safe: legacy/bulk-import rows can carry NULL names or
        # non-email values; a bare .lower() would 500 the whole search.
        users = [u for u in users if like in (u.full_name or "").lower() or like in (u.email or "").lower()
                 or (want_card and u.card_number == int(q.strip()))]
    if invite_code:
        uids = [u.id for u in users]
        if invite_code.strip().lower() == "none":
            users_with_codes = set((await db.execute(
                select(UserInvitationCode.user_id).where(UserInvitationCode.user_id.in_(uids))
            )).scalars().all()) if uids else set()
            users = [u for u in users if u.invitation_code_used is None and u.id not in users_with_codes]
        else:
            code = invite_code.strip().upper()
            matching_uids = set((await db.execute(
                select(UserInvitationCode.user_id).where(
                    UserInvitationCode.user_id.in_(uids),
                    UserInvitationCode.code == code,
                )
            )).scalars().all()) if uids else set()
            users = [u for u in users if u.invitation_code_used == code or u.id in matching_uids]

    users.sort(key=lambda u: u.full_name)
    return users


async def search_cohort_assignable_students(
    db: AsyncSession, *, cohort_id: uuid.UUID, q: str | None = None, invite_code: str | None = None,
    registered_only: bool = False,
    team_status: Literal["all", "has_team", "no_team"] = "all",
    lms_status: Literal["all", "has_access", "no_access"] = "all",
    login_status: Literal["all", "never", "has_logged_in"] = "all",
    mode: Literal["all", "student", "observer", "staff"] = "student",
    role: str | None = None,
    page: int = 1,
    page_size: int = 25,
    sort: Literal["full_name", "card_number", "created_at", "email"] = "full_name",
    direction: Literal["asc", "desc"] = "asc",
) -> dict:
    """Backs the Assign tab's search + filters (`registered_only` added
    2026-09-15 alongside `team_status`/`lms_status`, replacing the old
    boolean `unassigned_only`). `registered_only=False` searches the whole
    platform's accounts so ops can still find an unregistered invite-code
    signup to assign; `registered_only=True` instead starts from this
    cohort's own Registration rows (`_registered_cohort_users` above).
    `login_status` (2026-09-16) filters on `User.last_login_at`.

    Rebuild (2026-10): `mode` is `student` (student role, no observer) |
    `observer` (has observer role) | `staff` (literally not a student) |
    `all` (back-compat). `role` narrows the staff toggle to one role.
    Server-side pagination (`page`/`page_size`) + sorting (`sort`/
    `direction`) — the tab lists whole-platform accounts now, an uncapped
    list is no longer viable. Returns `{"items", "total", "page",
    "page_size"}`; `registered` (Registration exists) is the "In program"
    signal — registration and LMS assignment are created interchangeably
    by every assign path, so `lms_status` is accepted but no longer drives
    the tab."""
    from app.services.documents.card_id import format_card_id

    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 25)))
    role_norm = (role or "").strip().lower() or None

    def _mode_ok(u) -> bool:
        roles = set(u.role_values)
        if mode == "observer":
            return "observer" in roles
        if mode == "staff":
            if "student" in roles:
                return False
            return (not role_norm) or (role_norm in roles)
        if mode == "all":
            return True
        # student: student role without observer (observer-role holders
        # live under Observers once assigned, even if also students).
        return "student" in roles and "observer" not in roles

    if registered_only:
        # Cohort-bounded candidate set (at most a roster, never the
        # platform): apply every filter BEFORE paginating so `total` is
        # honest. team/lms membership is resolved for the whole set
        # first, then sort + slice.
        users = await _registered_cohort_users(db, cohort_id=cohort_id, q=q, invite_code=invite_code)
        users = [u for u in users if _mode_ok(u)]
        if role_norm and mode != "staff":
            users = [u for u in users if role_norm in u.role_values]
        if login_status == "never":
            users = [u for u in users if u.last_login_at is None]
        elif login_status == "has_logged_in":
            users = [u for u in users if u.last_login_at is not None]
        registered_ids = {u.id for u in users}
        if users and team_status != "all":
            _ids = [u.id for u in users]
            _teamed = set((await db.execute(
                select(TeamMember.user_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.cohort_id == cohort_id, TeamMember.user_id.in_(_ids))
            )).scalars().all())
            users = [u for u in users if (u.id in _teamed) == (team_status == "has_team")]
        if users and lms_status != "all":
            _ids = [u.id for u in users]
            _lms = set((await db.execute(
                select(LmsProgramAssignment.user_id).where(
                    LmsProgramAssignment.cohort_id == cohort_id, LmsProgramAssignment.user_id.in_(_ids))
            )).scalars().all())
            users = [u for u in users if (u.id in _lms) == (lms_status == "has_access")]
        reverse = direction == "desc"
        if sort == "card_number":
            users.sort(key=lambda u: (u.card_number is None, u.card_number or 0, u.full_name or ""), reverse=reverse)
        elif sort == "created_at":
            users.sort(key=lambda u: (u.created_at is None, str(u.created_at), u.full_name or ""), reverse=reverse)
        elif sort == "email":
            users.sort(key=lambda u: (u.email or "").lower(), reverse=reverse)
        else:
            users.sort(key=lambda u: (u.full_name or "").lower(), reverse=reverse)
        total = len(users)
        users = users[(page - 1) * page_size: page * page_size]
    else:
        if mode == "observer":
            role_filter = User.roles.any("observer")
        elif mode == "staff":
            role_filter = ~User.roles.any("student")
        elif mode == "all":
            role_filter = None
        else:
            role_filter = and_(User.roles.any("student"), ~User.roles.any("observer"))
        stmt = select(User)
        if role_filter is not None:
            stmt = stmt.where(role_filter)
        if role_norm and mode == "staff":
            stmt = stmt.where(User.roles.any(role_norm))
        elif role_norm:
            stmt = stmt.where(User.roles.any(role_norm))
        if q:
            like = f"%{q.strip()}%"
            conds = [User.full_name.ilike(like), User.email.ilike(like)]
            if q.strip().isdigit():
                # Card ID column is searchable too — "42" matches card 42.
                conds.append(User.card_number == int(q.strip()))
            stmt = stmt.where(or_(*conds))
        if invite_code:
            if invite_code.strip().lower() == "none":
                stmt = stmt.where(
                    User.invitation_code_used.is_(None),
                    ~exists(select(1).where(UserInvitationCode.user_id == User.id)),
                )
            else:
                code = invite_code.strip().upper()
                stmt = stmt.where(
                    or_(
                        exists(
                            select(1).where(
                                UserInvitationCode.user_id == User.id,
                                UserInvitationCode.code == code,
                            )
                        ),
                        User.invitation_code_used == code,
                    )
                )
        if login_status == "never":
            stmt = stmt.where(User.last_login_at.is_(None))
        elif login_status == "has_logged_in":
            stmt = stmt.where(User.last_login_at.is_not(None))
        if team_status != "all" or lms_status != "all":
            # Cohort-bounded id sets (small): push team/lms narrowing into
            # the platform query itself so `total` stays honest instead of
            # dropping rows after the page is sliced.
            if team_status != "all":
                _teamed_ids = list(set((await db.execute(
                    select(TeamMember.user_id)
                    .join(Team, Team.id == TeamMember.team_id)
                    .where(Team.cohort_id == cohort_id)
                )).scalars().all()))
                if team_status == "has_team":
                    stmt = stmt.where(User.id.in_(_teamed_ids)) if _teamed_ids else stmt.where(False)
                elif _teamed_ids:
                    stmt = stmt.where(User.id.not_in(_teamed_ids))
            if lms_status != "all":
                _lms_ids = list(set((await db.execute(
                    select(LmsProgramAssignment.user_id).where(
                        LmsProgramAssignment.cohort_id == cohort_id)
                )).scalars().all()))
                if lms_status == "has_access":
                    stmt = stmt.where(User.id.in_(_lms_ids)) if _lms_ids else stmt.where(False)
                elif _lms_ids:
                    stmt = stmt.where(User.id.not_in(_lms_ids))
        # Total before ordering/pagination — the tab needs the full match
        # count for its pagination controls.
        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int(await db.scalar(total_stmt) or 0)
        if total:
            order_col = {
                "card_number": User.card_number,
                "created_at": User.created_at,
                "email": User.email,
            }.get(sort, User.full_name)
            order_col = order_col.desc() if direction == "desc" else order_col.asc()
            stmt = stmt.order_by(order_col, User.full_name.asc()).offset((page - 1) * page_size).limit(page_size)
            users = list((await db.execute(stmt)).scalars().all())
        else:
            users = []

        contact_ids = [u.contact_id for u in users if u.contact_id]
        registered_contact_ids = set((await db.execute(
            select(Registration.contact_id).where(
                Registration.cohort_id == cohort_id, Registration.status != "cancelled",
                Registration.contact_id.in_(contact_ids),
            )
        )).scalars().all()) if contact_ids else set()
        registered_ids = {u.id for u in users if u.contact_id in registered_contact_ids}

    if not users:
        return {"items": [], "total": total, "page": page, "page_size": page_size}

    summaries = await _summarize_users(db, users)
    user_ids = [u.id for u in users]

    team_rows = (await db.execute(
        select(TeamMember.user_id, Team.roster_team_id, Team.name, Team.id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.cohort_id == cohort_id, TeamMember.user_id.in_(user_ids))
    )).all()
    team_by_user = {row.user_id: (row.roster_team_id, row.name, row.id) for row in team_rows}

    lms_user_ids = set((await db.execute(
        select(LmsProgramAssignment.user_id).where(
            LmsProgramAssignment.cohort_id == cohort_id, LmsProgramAssignment.user_id.in_(user_ids),
        )
    )).scalars().all())

    items: list[CompetitionAssignableStudentOut] = []
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
        if registered_only:
            pass  # login_status already applied above for this branch
        else:
            if login_status == "never" and u.last_login_at is not None:
                continue
            if login_status == "has_logged_in" and u.last_login_at is None:
                continue
        team_id, team_name, team_uuid = team_by_user.get(u.id, (None, None, None))
        card_number = getattr(u, "card_number", None)
        try:
            card_id = format_card_id(card_number, u.role_values) if card_number is not None else None
        except Exception:
            card_id = None
        items.append(CompetitionAssignableStudentOut(
            **summary.model_dump(), team_id=team_id, team_name=team_name, team_uuid=team_uuid,
            registered=u.id in registered_ids, lms_access=has_lms,
            is_observer="observer" in u.role_values,
            card_number=card_number, card_id=card_id, roles=list(u.role_values),
        ))
    if registered_only:
        # team_status/lms_status/login_status narrow after enrichment, so
        # the total reflects the filtered set, not the raw roster.
        total = None  # recompute below from the pre-page full pass
        # Re-run the filter pass without pagination to count honestly would
        # cost a second roster scan; instead count from this page's logic
        # is wrong — so do the cheap thing: paginate AFTER filtering. The
        # registered_only branch is cohort-bounded (small), so rebuild the
        # full filtered list first.
        # NOTE: `users` above was already paginated; re-derive from the
        # cohort set would need the unpaginated list. To keep this simple
        # and correct, refetch the cohort users when a post-enrichment
        # filter is active is overkill — team/has filters are the common
        # case and the roster is small, so accept a two-pass approach:
        total = len(items)  # placeholder, corrected by caller contract below
        # Correct two-pass: rebuild unpaginated when filters narrowed.
        # (Kept explicit so the next reader doesn't "optimize" it away.)
        pass
    # Recompute the honest total for the registered_only branch with a
    # second cheap pass (cohort-bounded, small): re-list without slicing.
    if registered_only:
        all_users = await _registered_cohort_users(db, cohort_id=cohort_id, q=q, invite_code=invite_code)
        all_users = [u for u in all_users if _mode_ok(u)]
        if role_norm and mode != "staff":
            all_users = [u for u in all_users if role_norm in u.role_values]
        if login_status == "never":
            all_users = [u for u in all_users if u.last_login_at is None]
        elif login_status == "has_logged_in":
            all_users = [u for u in all_users if u.last_login_at is not None]
        if all_users:
            all_ids = [u.id for u in all_users]
            all_team_ids = set((await db.execute(
                select(TeamMember.user_id)
                .join(Team, Team.id == TeamMember.team_id)
                .where(Team.cohort_id == cohort_id, TeamMember.user_id.in_(all_ids))
            )).scalars().all())
            all_lms_ids = set((await db.execute(
                select(LmsProgramAssignment.user_id).where(
                    LmsProgramAssignment.cohort_id == cohort_id, LmsProgramAssignment.user_id.in_(all_ids))
            )).scalars().all())
            n = 0
            for u in all_users:
                has_team = u.id in all_team_ids
                has_lms = u.id in all_lms_ids
                if team_status == "has_team" and not has_team:
                    continue
                if team_status == "no_team" and has_team:
                    continue
                if lms_status == "has_access" and not has_lms:
                    continue
                if lms_status == "no_access" and has_lms:
                    continue
                n += 1
            total = n
        else:
            total = 0
    return {"items": items, "total": total, "page": page, "page_size": page_size}
