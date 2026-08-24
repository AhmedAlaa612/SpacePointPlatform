"""Cohort-level staffing (operator decisions, 2026-08-24).

The session-scoped marketplace in `staffing.py` stays exactly as it is and
does all the real work — this module is the *cohort* layer on top of it:

    ops opens one CohortCall across N sessions   (staffing.open_cohort_call)
      -> instructor answers it once, ticking days (register_cohort_interest)
         which writes per-session InstructorInterest rows underneath
      -> ops picks people from one table         (select_for_cohort)
         which calls staffing.select_instructors per ticked session
         and records the deal in CohortInstructorAssignment

Nothing here duplicates `staffing.py`'s logic; every write goes through it, so
targeting, opening validation, `fully_staffed`, `staffing_status` syncing and
call auto-closing keep behaving identically whether a call was opened on one
session or across a cohort.

**The one rule that is genuinely new**: an instructor holds a single role for
a whole cohort. The operator confirmed it explicitly — Assistant in Cohort A
and Instructor in Cohort B is fine, Instructor on some days of Cohort B while
Assistant on others is not. The schema still permits per-session roles (that
is `SessionInstructor.role_id`, untouched, and legacy data really does contain
mixed-role cohorts), so this is a validation rule enforced here on the way in,
not a structural guarantee. `_assert_single_role` is the one place it lives.

Services raise `HTTPException` directly — house convention, no domain-exception
layer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.cohort_call import CohortCall, CohortCallTarget
from app.models.sessions.cohort_call_interest import CohortCallInterest
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_call import SessionCall
from app.models.user import User
from app.services.sessions import staffing
from app.services.sessions.journey import get_responsibilities_for_role
from app.services.sessions.openings import openings_for_session
from app.services.sessions.staffing import resolve_session_location_display


async def _get_call(db: AsyncSession, cohort_id: UUID, cohort_call_id: UUID) -> CohortCall:
    call = await db.get(CohortCall, cohort_call_id)
    if call is None or call.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort call not found")
    return call


async def _call_session_ids(db: AsyncSession, cohort_call_id: UUID) -> list[UUID]:
    """The sessions this call actually opened, in date order — the tick-list an
    instructor is offered. Derived from the grouped `SessionCall` rows rather
    than stored again, the same derive-don't-duplicate choice
    `_sync_cohort_call_status` already makes for the call's own status."""
    return list((await db.execute(
        select(SessionCall.session_id)
        .join(Session, Session.id == SessionCall.session_id)
        .where(SessionCall.cohort_call_id == cohort_call_id)
        .order_by(Session.meeting_date.asc(), Session.starts_at.asc())
    )).scalars().all())


async def _assert_visible(db: AsyncSession, call: CohortCall, user: User) -> None:
    """A targeted cohort call is a real restriction, not a narrower mailing
    list — same contract as `SessionCallTarget`. 404 rather than 403 so an
    untargeted instructor can't probe which cohorts exist, matching the
    don't-leak-existence convention `register_interest` and the delivery
    routes already follow."""
    targeted = await db.scalar(
        select(func.count()).select_from(CohortCallTarget)
        .where(CohortCallTarget.cohort_call_id == call.id)
    )
    if not targeted:
        return
    mine = await db.scalar(
        select(func.count()).select_from(CohortCallTarget)
        .where(CohortCallTarget.cohort_call_id == call.id, CohortCallTarget.user_id == user.id)
    )
    if not mine:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort call not found")


async def _assert_single_role(
    db: AsyncSession, *, cohort_id: UUID, user_id: UUID, role_id: UUID,
) -> None:
    """One role per instructor per cohort (operator, 2026-08-24).

    Checked against the assignment table *and* against live `SessionInstructor`
    rows: someone put on a session through the pre-existing direct-assign path
    (routers/sessions/cohorts.py) has no assignment row, and picking them for a
    second role through the cohort flow would otherwise slip past.
    """
    clash = (await db.execute(
        select(DeliveryRole.name)
        .join(CohortInstructorAssignment, CohortInstructorAssignment.role_id == DeliveryRole.id)
        .where(
            CohortInstructorAssignment.cohort_id == cohort_id,
            CohortInstructorAssignment.user_id == user_id,
            CohortInstructorAssignment.status == "active",
            CohortInstructorAssignment.role_id != role_id,
        )
        .limit(1)
    )).scalars().first()
    if clash is None:
        clash = (await db.execute(
            select(DeliveryRole.name)
            .join(SessionInstructor, SessionInstructor.role_id == DeliveryRole.id)
            .join(Session, Session.id == SessionInstructor.session_id)
            .where(
                Session.cohort_id == cohort_id,
                SessionInstructor.user_id == user_id,
                SessionInstructor.role_id != role_id,
            )
            .limit(1)
        )).scalars().first()
    if clash is not None:
        user_name = await db.scalar(select(User.full_name).where(User.id == user_id))
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"{user_name or 'That instructor'} is already {clash} in this cohort. "
                "An instructor holds one role for a whole cohort — remove the existing "
                "assignment first if the role really is changing."
            ),
        )


# ── Instructor side ─────────────────────────────────────────────────────────

async def list_available_cohort_calls(db: AsyncSession, user: User) -> list[dict]:
    """The instructor-facing feed: one card per open cohort call they can see.

    Sessions opened by a call that belongs to no cohort call are *not* returned
    here — `staffing.list_available_sessions` still serves those, and the page
    shows them as a separate "single sessions" group. Splitting it this way
    keeps the existing endpoint's shape untouched for one release rather than
    changing a live contract under the current page.
    """
    calls = (await db.execute(
        select(CohortCall, Cohort, Program)
        .join(Cohort, Cohort.id == CohortCall.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .where(CohortCall.status == "open")
        .order_by(CohortCall.created_at.desc())
    )).all()
    if not calls:
        return []

    out: list[dict] = []
    for call, cohort, program in calls:
        try:
            await _assert_visible(db, call, user)
        except HTTPException:
            continue

        session_ids = await _call_session_ids(db, call.id)
        if not session_ids:
            continue
        sessions = (await db.execute(
            select(Session).where(Session.id.in_(session_ids))
            .order_by(Session.meeting_date.asc(), Session.starts_at.asc())
        )).scalars().all()

        mine = (await db.execute(
            select(CohortCallInterest).where(
                CohortCallInterest.cohort_call_id == call.id,
                CohortCallInterest.user_id == user.id,
            )
        )).scalars().first()
        my_session_ids = []
        if mine is not None:
            my_session_ids = list((await db.execute(
                select(InstructorInterest.session_id).where(
                    InstructorInterest.session_id.in_(session_ids),
                    InstructorInterest.user_id == user.id,
                )
            )).scalars().all())

        # The offer is the same across the call's sessions in the ordinary
        # case; showing the first session's resolved openings (which already
        # inherit the cohort template and now the role default) is what the
        # instructor is actually being offered. Slots left are summed across
        # the call so "1 of 3 left" means something at cohort scale.
        per_session_openings = [await openings_for_session(db, s.id, open_only=True) for s in sessions]
        merged: dict[UUID, dict] = {}
        for openings in per_session_openings:
            for o in openings:
                agg = merged.setdefault(o["role_id"], {**o, "slots": 0, "filled": 0, "remaining": 0})
                agg["slots"] += o["slots"]
                agg["filled"] += o["filled"]
                agg["remaining"] += o["remaining"]

        location = await resolve_session_location_display(db, sessions[0], cohort)
        interested_count = await db.scalar(
            select(func.count()).select_from(CohortCallInterest)
            .where(CohortCallInterest.cohort_call_id == call.id)
        ) or 0

        out.append({
            "cohort_call_id": call.id,
            "cohort_id": cohort.id,
            "cohort_name": cohort.name,
            "program_name": program.name,
            "program_type": program.program_type,
            "description": program.description,
            "label": call.label,
            "starts_on": cohort.starts_on or sessions[0].meeting_date,
            "ends_on": cohort.ends_on or sessions[-1].meeting_date,
            "session_count": len(sessions),
            "location": location["name"],
            "location_address": location["address"],
            "location_map_url": location["maps_url"],
            "interested_count": interested_count,
            "sessions": [
                {
                    "session_id": s.id,
                    "title": s.title,
                    "meeting_date": s.meeting_date,
                    "starts_at": s.starts_at,
                    "selected": s.id in my_session_ids,
                }
                for s in sessions
            ],
            "openings": sorted(merged.values(), key=lambda o: o["role_name"]),
            "my_interest": mine is not None,
            "my_role_id": mine.role_id if mine else None,
            "my_note": mine.note if mine else None,
            "my_needs_transport": mine.needs_transport if mine else False,
            "my_needs_ops_support": mine.needs_ops_support if mine else False,
            "my_travelling_from_other_city": mine.travelling_from_other_city if mine else False,
            "my_concerns": mine.concerns if mine else None,
        })
    return out


async def register_cohort_interest(
    db: AsyncSession, *, cohort_id: UUID, cohort_call_id: UUID, user: User,
    session_ids: list[UUID], role_id: UUID | None = None, note: str | None = None,
    needs_transport: bool = False, needs_ops_support: bool = False,
    travelling_from_other_city: bool = False, concerns: str | None = None,
    responsibilities_version: str | None = None,
) -> CohortCallInterest:
    """One answer to a cohort call: a role, the days they can do, and the §2
    support answers.

    Re-registering replaces the previous answer rather than erroring — the
    instructor changing which days they can do is the normal case, not an edge
    one, and the per-session rows are reconciled to match (added for newly
    ticked days, removed for unticked ones) so the two never drift.
    """
    call = await _get_call(db, cohort_id, cohort_call_id)
    if call.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This call isn't open for interest right now")
    if not any(r in user.role_values for r in ("instructor", "facilitator")):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only instructors or facilitators can register interest"
        )
    await _assert_visible(db, call, user)

    offered = await _call_session_ids(db, cohort_call_id)
    wanted = [sid for sid in dict.fromkeys(session_ids) if sid in offered]
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Pick at least one session you can deliver")

    # The role has to be one this cohort is actually soliciting for, and it has
    # to be the same role they already hold here if they hold one.
    if role_id is not None:
        await _assert_single_role(db, cohort_id=cohort_id, user_id=user.id, role_id=role_id)

    # Responsibilities: recorded against the version that was on screen, and a
    # stale one is refused — identical contract to `journey.accept_responsibilities`,
    # just scoped to the cohort call instead of one session's interest row.
    accepted_at = None
    if responsibilities_version is not None:
        text, current, _role_name = await get_responsibilities_for_role(db, role_id)
        if text and responsibilities_version != current:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail="The responsibilities have changed — reload and read them again",
            )
        accepted_at = datetime.now(timezone.utc)

    interest = (await db.execute(
        select(CohortCallInterest).where(
            CohortCallInterest.cohort_call_id == cohort_call_id,
            CohortCallInterest.user_id == user.id,
        )
    )).scalars().first()
    if interest is None:
        interest = CohortCallInterest(
            id=uuid4(), cohort_call_id=cohort_call_id, cohort_id=cohort_id, user_id=user.id,
        )
        db.add(interest)
    interest.role_id = role_id
    interest.note = note
    interest.needs_transport = needs_transport
    interest.needs_ops_support = needs_ops_support
    interest.travelling_from_other_city = travelling_from_other_city
    interest.concerns = concerns
    interest.status = "open"
    if accepted_at is not None:
        interest.responsibilities_accepted_at = accepted_at
        interest.responsibilities_version = responsibilities_version
    await db.flush()

    # Reconcile the per-session rows through the existing service, so every
    # per-session gate (open_call state, targeting, role-is-offered) still runs
    # exactly as it does for a single-session application.
    for session_id in wanted:
        await staffing.register_interest(db, session_id, user, note=note, role_id=role_id)
    for session_id in offered:
        if session_id not in wanted:
            await staffing.withdraw_interest(db, session_id, user)

    await db.flush()
    return interest


async def withdraw_cohort_interest(
    db: AsyncSession, *, cohort_id: UUID, cohort_call_id: UUID, user: User,
) -> None:
    """Withdraws from the whole call — the cohort row and every per-session row
    it created. Idempotent: withdrawing twice is not an error."""
    await _get_call(db, cohort_id, cohort_call_id)
    interest = (await db.execute(
        select(CohortCallInterest).where(
            CohortCallInterest.cohort_call_id == cohort_call_id,
            CohortCallInterest.user_id == user.id,
        )
    )).scalars().first()
    if interest is not None:
        await db.delete(interest)
    for session_id in await _call_session_ids(db, cohort_call_id):
        await staffing.withdraw_interest(db, session_id, user)
    await db.flush()


# ── Ops side ────────────────────────────────────────────────────────────────

async def list_cohort_call_interest(db: AsyncSession, *, cohort_id: UUID, cohort_call_id: UUID) -> list[dict]:
    """The ops applicant table: **one row per instructor**, not per session.

    Each row carries the days they ticked, the role they want, the §2 support
    flags, and whether the cohort's city is one they already said they'd travel
    to — the last reusing `ApplicantProfile.deliver_city_ids`, the same signal
    `staffing.list_eligible_instructors` surfaces per session.
    """
    await _get_call(db, cohort_id, cohort_call_id)
    session_ids = await _call_session_ids(db, cohort_call_id)

    rows = (await db.execute(
        select(CohortCallInterest, User)
        .join(User, User.id == CohortCallInterest.user_id)
        .where(CohortCallInterest.cohort_call_id == cohort_call_id)
        .order_by(CohortCallInterest.created_at.asc())
    )).all()
    if not rows:
        return []

    role_names = dict((await db.execute(select(DeliveryRole.id, DeliveryRole.name))).all())

    ticked: dict[UUID, list[UUID]] = {}
    if session_ids:
        for user_id, session_id in (await db.execute(
            select(InstructorInterest.user_id, InstructorInterest.session_id)
            .where(InstructorInterest.session_id.in_(session_ids))
        )).all():
            ticked.setdefault(user_id, []).append(session_id)

    # City match, resolved once for the cohort rather than per applicant.
    cohort = await db.get(Cohort, cohort_id)
    city_id = None
    if session_ids:
        first = await db.get(Session, session_ids[0])
        if first is not None:
            city_id = await staffing._resolve_session_city_id(db, first)
    if city_id is None and cohort is not None and cohort.location_id is not None:
        from app.models.inventory.location import Location
        location = await db.get(Location, cohort.location_id)
        city_id = location.city_id if location else None

    deliver_cities: dict[UUID, list[UUID]] = {}
    if city_id is not None:
        deliver_cities = dict((await db.execute(
            select(ApplicantProfile.user_id, ApplicantProfile.deliver_city_ids)
            .where(ApplicantProfile.deliver_city_ids.isnot(None))
        )).all())

    assigned = {
        (a.user_id): a for a in (await db.execute(
            select(CohortInstructorAssignment).where(
                CohortInstructorAssignment.cohort_id == cohort_id,
                CohortInstructorAssignment.status == "active",
            )
        )).scalars().all()
    }

    return [
        {
            "user_id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "role_id": i.role_id,
            "role_name": role_names.get(i.role_id) if i.role_id else None,
            "session_ids": ticked.get(u.id, []),
            "session_count": len(ticked.get(u.id, [])),
            "note": i.note,
            "needs_transport": i.needs_transport,
            "needs_ops_support": i.needs_ops_support,
            "travelling_from_other_city": i.travelling_from_other_city,
            "concerns": i.concerns,
            "responsibilities_accepted_at": i.responsibilities_accepted_at,
            "available_in_city": city_id is not None and city_id in (deliver_cities.get(u.id) or []),
            "status": i.status,
            "already_assigned": u.id in assigned,
            "created_at": i.created_at,
        }
        for i, u in rows
    ]


async def _resolve_rate(db: AsyncSession, *, session_ids: list[UUID], role_id: UUID) -> Decimal | None:
    """The per-session rate on offer for this role, snapshotted at selection.

    Reads it through `openings_for_session`, so the whole hierarchy — session
    opening, then the cohort template, then `DeliveryRole.default_rate_aed` —
    resolves exactly as it does on the instructor's card. NULL when nothing is
    set anywhere, which stays honest: the payment line is left for ops rather
    than guessing.
    """
    for session_id in session_ids:
        for opening in await openings_for_session(db, session_id):
            if opening["role_id"] == role_id and opening["amount_aed"] is not None:
                return Decimal(str(opening["amount_aed"]))
    return None


async def select_for_cohort(
    db: AsyncSession, *, cohort_id: UUID, user_ids: list[UUID], role_id: UUID | None = None,
    session_ids: list[UUID] | None = None, cohort_call_id: UUID | None = None,
    close_call: bool = True, actor_user_id: UUID | None = None,
    rate_basis: str = "per_session", flat_amount_aed: Decimal | None = None,
) -> list[dict]:
    """Assign people to a cohort in one action.

    Per instructor: the sessions they get are the ones they ticked (or
    `session_ids` when ops overrides), and each one goes through the existing
    `staffing.select_instructors` so nothing about per-session staffing changes
    — the same table, the same `fully_staffed` check, the same call closing.
    On top of that, one `CohortInstructorAssignment` records the deal.

    `role_id` omitted falls back to the role each applicant asked for, and only
    then to the most senior role — picking somebody without overriding what
    they applied for is the common case and shouldn't require restating it.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if not user_ids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select at least one instructor")
    if rate_basis not in ("per_session", "flat"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="rate_basis is 'per_session' or 'flat'")

    cohort_session_ids = list((await db.execute(
        select(Session.id).where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date.asc(), Session.starts_at.asc())
    )).scalars().all())

    interests: dict[UUID, CohortCallInterest] = {}
    if cohort_call_id is not None:
        interests = {
            i.user_id: i for i in (await db.execute(
                select(CohortCallInterest).where(CohortCallInterest.cohort_call_id == cohort_call_id)
            )).scalars().all()
        }

    out: list[dict] = []
    for user_id in dict.fromkeys(user_ids):
        interest = interests.get(user_id)
        effective_role = role_id or (interest.role_id if interest else None)
        if effective_role is None:
            from app.services.sessions.openings import lead_role_id
            effective_role = await lead_role_id(db)
            if effective_role is None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")

        await _assert_single_role(db, cohort_id=cohort_id, user_id=user_id, role_id=effective_role)

        # Which days: an explicit override, else what they ticked, else the
        # whole cohort (an ops direct-assign with no application behind it).
        if session_ids is not None:
            wanted = [sid for sid in session_ids if sid in cohort_session_ids]
        else:
            wanted = list((await db.execute(
                select(InstructorInterest.session_id).where(
                    InstructorInterest.session_id.in_(cohort_session_ids or [None]),
                    InstructorInterest.user_id == user_id,
                )
            )).scalars().all()) if cohort_session_ids else []
            if not wanted:
                wanted = cohort_session_ids
        if not wanted:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This cohort has no sessions to assign")

        for session_id in wanted:
            await staffing.select_instructors(
                db, session_id, [user_id], role_id=effective_role,
                close_call=close_call, actor_user_id=actor_user_id,
            )

        rate = await _resolve_rate(db, session_ids=wanted, role_id=effective_role)
        assignment = (await db.execute(
            select(CohortInstructorAssignment).where(
                CohortInstructorAssignment.cohort_id == cohort_id,
                CohortInstructorAssignment.user_id == user_id,
                CohortInstructorAssignment.role_id == effective_role,
            )
        )).scalars().first()
        if assignment is None:
            assignment = CohortInstructorAssignment(
                id=uuid4(), cohort_id=cohort_id, user_id=user_id, role_id=effective_role,
                created_by=actor_user_id,
            )
            db.add(assignment)
        assignment.status = "active"
        assignment.source = "call" if cohort_call_id is not None else "direct"
        assignment.cohort_call_id = cohort_call_id
        assignment.rate_basis = rate_basis
        # Only ever set the snapshot — never overwrite one already agreed, or
        # re-picking somebody after a rate edit would silently reprice them.
        if assignment.rate_aed is None:
            assignment.rate_aed = rate
        if rate_basis == "flat":
            assignment.flat_amount_aed = flat_amount_aed

        if interest is not None:
            interest.status = "selected"

        await db.flush()
        out.append({
            "user_id": user_id,
            "role_id": effective_role,
            "session_ids": wanted,
            "rate_aed": assignment.rate_aed,
            "rate_basis": assignment.rate_basis,
            "flat_amount_aed": assignment.flat_amount_aed,
        })

    if cohort_call_id is not None:
        call = await db.get(CohortCall, cohort_call_id)
        if call is not None:
            await staffing._sync_cohort_call_status(db, call)

    await db.flush()
    return out


async def list_cohort_assignments(db: AsyncSession, cohort_id: UUID) -> list[dict]:
    """Who is staffed on this cohort, in what role, at what agreed rate, and
    across how many of its sessions."""
    rows = (await db.execute(
        select(CohortInstructorAssignment, User, DeliveryRole)
        .join(User, User.id == CohortInstructorAssignment.user_id)
        .join(DeliveryRole, DeliveryRole.id == CohortInstructorAssignment.role_id)
        .where(CohortInstructorAssignment.cohort_id == cohort_id)
        .order_by(DeliveryRole.sort_order, User.full_name)
    )).all()
    if not rows:
        return []

    counts = dict((await db.execute(
        select(SessionInstructor.user_id, func.count())
        .join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.cohort_id == cohort_id)
        .group_by(SessionInstructor.user_id)
    )).all())

    return [
        {
            "id": a.id, "cohort_id": a.cohort_id, "user_id": u.id, "full_name": u.full_name,
            "email": u.email, "role_id": r.id, "role_name": r.name,
            "rate_basis": a.rate_basis, "rate_aed": a.rate_aed,
            "flat_amount_aed": a.flat_amount_aed, "status": a.status, "source": a.source,
            "session_count": counts.get(u.id, 0), "created_at": a.created_at,
        }
        for a, u, r in rows
    ]


async def remove_cohort_assignment(
    db: AsyncSession, *, cohort_id: UUID, user_id: UUID, drop_sessions: bool = True,
) -> None:
    """Withdraws somebody from a cohort.

    Marked `withdrawn` rather than deleted so the record that they were once
    staffed survives — the same reasoning `DeliveryRole.is_active` uses. Their
    session rows go through `staffing.remove_instructor`, which is what keeps
    `staffing_status` honest; pass `drop_sessions=False` only to correct the
    assignment record itself without touching the schedule.
    """
    assignments = (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id == cohort_id,
            CohortInstructorAssignment.user_id == user_id,
        )
    )).scalars().all()
    if not assignments:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    for assignment in assignments:
        assignment.status = "withdrawn"

    if drop_sessions:
        session_ids = list((await db.execute(
            select(Session.id).where(Session.cohort_id == cohort_id)
        )).scalars().all())
        for session_id in session_ids:
            await staffing.remove_instructor(db, session_id, user_id)
    await db.flush()
