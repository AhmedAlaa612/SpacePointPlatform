"""Responsibilities acceptance (I5-5) and the sessions → payments bridge (I5-8).

Two ends of the same journey, kept together because both are about turning a
delivered session into something an instructor signs.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import PaymentLetterStatus
from app.models.instructors.payment import PaymentLetter, PaymentSession
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.payment_coverage import PaymentSessionCoverage
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.sessions.openings import resolve_duration
from app.services.sessions.staffing import resolve_session_location_display
from app.services.settings import get_portal_setting, set_portal_setting

RESPONSIBILITIES_KEY = "instructor.responsibilities"


async def get_responsibilities(db: AsyncSession) -> tuple[str, str]:
    """The general responsibilities text and its version — one chunk ops
    writes and maintains, appended after a role's own responsibilities
    regardless of which role someone is agreeing to. Whatever belongs in it —
    "arrive on time," payment terms, anything else — is ops's call; this
    isn't split into named sub-fields. Editable on its own; the combined
    version below is what an instructor actually reads.

    The version is a hash of the text rather than a counter nobody remembers
    to bump: it changes exactly when the words change, and it lets an old
    acceptance prove *which* wording was agreed to.
    """
    text = await get_portal_setting(db, RESPONSIBILITIES_KEY, "") or ""
    return text, sha256(text.encode("utf-8")).hexdigest()[:16]


async def set_responsibilities(db: AsyncSession, text: str) -> tuple[str, str]:
    await set_portal_setting(db, RESPONSIBILITIES_KEY, text or "")
    return await get_responsibilities(db)


async def get_responsibilities_for_role(
    db: AsyncSession, role_id: uuid.UUID | None, cohort_id: uuid.UUID | None = None,
) -> tuple[str, str, str | None]:
    """What an instructor actually reads and agrees to: that role's own
    responsibilities first, with the general text as a fixed note after it —
    not a generic agreement shown ahead of the part that's actually specific
    to the job. One combined block, one checkbox.

    `role_id=None` (a session with no configured openings) falls back to the
    general text alone, unchanged from before per-role responsibilities
    existed. The version is a hash of the *combination*, so editing either
    half invalidates a stale acceptance — same reasoning as the general-only
    version, just scoped to what this instructor was actually shown.

    `cohort_id` (2026-08-28), when given, checks `cohort_openings
    .responsibilities_override` for this (cohort, role) first — the cohort
    tier of the same override chain, ahead of the role's own default text.
    Folded into the version hash too: switching cohorts (or ops editing the
    override) invalidates a stale acceptance exactly like editing the role's
    own text already does.
    """
    general, general_version = await get_responsibilities(db)
    role_desc: str | None = None
    role_name: str | None = None
    override_marker = ""
    if role_id is not None:
        role = await db.get(DeliveryRole, role_id)
        if role is not None:
            role_desc = (role.description or "").strip() or None
            role_name = role.name

        if cohort_id is not None:
            opening = (await db.execute(
                select(CohortOpening).where(
                    CohortOpening.cohort_id == cohort_id, CohortOpening.role_id == role_id,
                )
            )).scalars().first()
            override = (opening.responsibilities_override or "").strip() if opening else ""
            if override:
                role_desc = override
                override_marker = f"\x1f{cohort_id}"

    if role_desc is None:
        # No role, or a role with nothing extra to say — text and version
        # are byte-identical to the general-only ones, so an acceptance
        # recorded before this role had its own text (or against a session
        # with no configured openings) still checks out.
        return general, general_version, role_name

    general_stripped = general.strip()
    text = f"{role_desc}\n\n{general_stripped}" if general_stripped else role_desc
    version = sha256(f"{role_id}{override_marker}\x1f{text}".encode("utf-8")).hexdigest()[:16]
    return text, version, role_name


async def accept_responsibilities(
    db: AsyncSession, *, interest: InstructorInterest, version: str
) -> InstructorInterest:
    """Record the read-and-agree tick against the version that was on screen.

    Scoped to the role on the interest itself (set at registration) — the
    instructor agreed to *that* role's combined text, not a generic one.
    Refusing a stale version is the point: if ops edits either half while
    somebody has the invite open, the acceptance they submit is for wording
    they never saw.
    """
    session = await db.get(Session, interest.session_id)
    cohort_id = session.cohort_id if session is not None else None
    _text, current, _role_name = await get_responsibilities_for_role(db, interest.role_id, cohort_id)
    if version != current:
        raise HTTPException(
            409, detail="The responsibilities have changed — reload and read them again"
        )

    interest.responsibilities_accepted_at = datetime.now(timezone.utc)
    interest.responsibilities_version = version
    await db.flush()
    return interest


# ── I5-8 / 2026-08-24: delivered work prefills the payment letter ───────────
#
# This section changed shape on 2026-08-24. It used to return one row per
# completed session; it now returns one row per *cohort assignment*, because
# the operator wants a letter that reads
#
#     10-14/10/2026   TDRA Camp   Lead Instructor   Abu Dhabi   4 x 500   2,000
#
# rather than five near-identical rows. The reason is operational, not
# cosmetic: the bank charges extra past ten transactions a month, so several
# cohorts are settled on one letter per instructor, and an itemised day list
# makes that unreadable.
#
# Sessions delivered outside any cohort assignment (a one-off session-only
# call, or anything staffed before assignments existed and not backfilled)
# still produce per-session rows, so nothing becomes unbillable.


async def _billed_session_ids(db: AsyncSession, instructor_user_id: uuid.UUID) -> set[uuid.UUID]:
    """Sessions already covered by one of *this instructor's* payment lines.

    Two sources, because a cohort line covers many sessions and
    `payment_sessions.session_id` can only name one: the column itself (single
    lines, manual lines, everything historical) and `payment_session_coverage`
    (cohort lines).

    **Scoped to this instructor's own letters**, exactly as before. One session
    is routinely delivered by several people and each is paid separately;
    asking globally whether a session had *ever* been billed made paying the
    lead silently delete it from the assistant's list.
    """
    direct = set((await db.execute(
        select(PaymentSession.session_id)
        .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
        .where(
            PaymentSession.session_id.isnot(None),
            PaymentLetter.instructor_user_id == instructor_user_id,
        )
    )).scalars().all())
    covered = set((await db.execute(
        select(PaymentSessionCoverage.session_id)
        .join(PaymentSession, PaymentSession.id == PaymentSessionCoverage.payment_session_id)
        .join(PaymentLetter, PaymentLetter.id == PaymentSession.payment_letter_id)
        .where(PaymentLetter.instructor_user_id == instructor_user_id)
    )).scalars().all())
    return direct | covered


async def _paid_day_session_ids(
    db: AsyncSession, instructor_user_id: uuid.UUID, session_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Which of these sessions count as *delivered* for this instructor.

    A paid day is one ops approved with the instructor present — the operator's
    rule (§18/§19, and the voice note: "operations confirms the instructor
    actually attended that day... that's locked in the system"). An approved
    absence is on the record and deliberately does not count.

    Sessions with no `InstructorSessionDay` row at all fall back to
    `completed_at`, so cohorts delivered before the daily loop existed remain
    billable rather than silently dropping to zero.
    """
    if not session_ids:
        return []
    days = {
        d.session_id: d for d in (await db.execute(
            select(InstructorSessionDay).where(
                InstructorSessionDay.session_id.in_(session_ids),
                InstructorSessionDay.user_id == instructor_user_id,
            )
        )).scalars().all()
    }
    completed = set((await db.execute(
        select(Session.id).where(Session.id.in_(session_ids), Session.completed_at.isnot(None))
    )).scalars().all())

    out = []
    for session_id in session_ids:
        day = days.get(session_id)
        if day is None:
            if session_id in completed:
                out.append(session_id)
        elif day.status == "approved" and day.att_status == "present":
            out.append(session_id)
    return out


def _format_range(dates: list) -> str:
    """The printed date cell. One day prints as one date; several print as a
    range — never an itemised attended-day list, per the operator: an absence
    shows up as a smaller session count, not as a gap in the dates."""
    if not dates:
        return ""
    lo, hi = min(dates), max(dates)
    if lo == hi:
        return lo.strftime("%d/%m/%Y")
    return f"{lo.strftime('%d/%m/%Y')} - {hi.strftime('%d/%m/%Y')}"


async def unbilled_cohorts(db: AsyncSession, instructor_user_id: uuid.UUID) -> list[dict]:
    """One draft payment line per cohort this person delivered and hasn't been
    paid for.

    `compensation_aed` is **computed here and still editable afterwards**. That
    reverses the earlier deliberate choice to leave it at 0 ("the money is a
    decision"), but keeps the decision: ops sees a filled-in draft and can
    change any cell before publishing, and `_refuse_if_signed` still blocks
    edits once signed. Typing a number the system already knows was the actual
    friction.
    """
    billed = await _billed_session_ids(db, instructor_user_id)

    assignments = (await db.execute(
        select(CohortInstructorAssignment, Cohort, Program, DeliveryRole)
        .join(Cohort, Cohort.id == CohortInstructorAssignment.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(DeliveryRole, DeliveryRole.id == CohortInstructorAssignment.role_id)
        .where(
            CohortInstructorAssignment.user_id == instructor_user_id,
            CohortInstructorAssignment.status == "active",
        )
        .order_by(Cohort.starts_on.asc().nullslast())
    )).all()

    out = []
    for assignment, cohort, program, role in assignments:
        mine = list((await db.execute(
            select(Session.id)
            .join(SessionInstructor, SessionInstructor.session_id == Session.id)
            .where(
                Session.cohort_id == cohort.id,
                SessionInstructor.user_id == instructor_user_id,
                SessionInstructor.role_id == assignment.role_id,
            )
            .order_by(Session.meeting_date.asc())
        )).scalars().all())
        delivered = [sid for sid in await _paid_day_session_ids(db, instructor_user_id, mine)
                     if sid not in billed]
        if not delivered:
            continue

        sessions = (await db.execute(
            select(Session).where(Session.id.in_(delivered)).order_by(Session.meeting_date.asc())
        )).scalars().all()
        location = await resolve_session_location_display(db, sessions[0], cohort)

        # **The printed range is the cohort's, not the delivered subset's**
        # (operator, 2026-08-24: "the data in the payment is always the range
        # of the cohort no matter which date you worked on"). An absence must
        # show up as a smaller session count and nothing else — shrinking the
        # dates would leak which specific days somebody missed onto a document
        # that is not supposed to itemise attendance at all. Falls back to the
        # cohort's own sessions when starts_on/ends_on were never filled in.
        span = [d for d in (cohort.starts_on, cohort.ends_on) if d is not None]
        if len(span) < 2:
            span = list((await db.execute(
                select(Session.meeting_date).where(Session.cohort_id == cohort.id)
            )).scalars().all())

        rate = assignment.rate_aed
        if assignment.rate_basis == "flat":
            total = float(assignment.flat_amount_aed or 0)
            rate_out = None
        else:
            rate_out = float(rate) if rate is not None else None
            total = float(rate) * len(delivered) if rate is not None else 0.0

        hours = Decimal("0")
        for session in sessions:
            hours += await resolve_duration(db, session) or Decimal("0")

        out.append({
            "cohort_id": cohort.id,
            "session_id": None,
            # What the client sends back to bill this line.
            "line_id": cohort.id,
            "session_ids": delivered,
            "session_date": _format_range(span or [s.meeting_date for s in sessions]),
            "workshop_description": cohort.name or program.name,
            "role": role.name,
            "location": location["name"],
            "session_count": len(delivered),
            "rate_aed": rate_out,
            "compensation_aed": total,
            "duration_hours": float(hours) or None,
            "rate_basis": assignment.rate_basis,
            "cohort_name": cohort.name,
        })
    return out


async def unbilled_sessions(db: AsyncSession, instructor_user_id: uuid.UUID) -> list[dict]:
    """Delivered work this person hasn't been paid for, as payment lines.

    Cohort assignments first (one line each, carrying the cohort's date range
    and `n x rate`), then any leftover delivered session that no assignment
    covers — a session-only call, or work staffed before assignments existed.
    Those keep the original one-row-per-session shape, so nothing that used to
    be billable stops being so.
    """
    lines = await unbilled_cohorts(db, instructor_user_id)
    claimed = {sid for line in lines for sid in line["session_ids"]}
    billed = await _billed_session_ids(db, instructor_user_id)

    rows = (await db.execute(
        select(Session, Cohort, Program, DeliveryRole.name)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .join(SessionInstructor, SessionInstructor.session_id == Session.id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(
            SessionInstructor.user_id == instructor_user_id,
            Session.completed_at.isnot(None),
        )
        .order_by(Session.meeting_date.desc())
    )).all()

    leftovers = [
        (session, cohort, program, role_name)
        for session, cohort, program, role_name in rows
        if session.id not in billed and session.id not in claimed
    ]
    delivered = set(await _paid_day_session_ids(
        db, instructor_user_id, [s.id for s, _c, _p, _r in leftovers]
    ))

    for session, cohort, program, role_name in leftovers:
        if session.id not in delivered:
            continue
        location = await resolve_session_location_display(db, session, cohort)
        lines.append({
            "cohort_id": None,
            "session_id": session.id,
            "line_id": session.id,
            "session_ids": [session.id],
            "session_date": session.meeting_date.strftime("%d/%m/%Y"),
            "workshop_description": session.title or program.name,
            "role": role_name,
            "location": location["name"],
            "session_count": 1,
            "rate_aed": None,
            # No assignment means no agreed rate to compute from — left for ops
            # to type, exactly as this path has always behaved.
            "compensation_aed": 0.0,
            "duration_hours": float(await resolve_duration(db, session) or 0) or None,
            "rate_basis": "per_session",
            "cohort_name": cohort.name,
        })
    return lines


async def pending_payment_instructors(db: AsyncSession) -> list[dict]:
    """Every instructor with delivered work not yet on any of their letters —
    the admin's payment-letter to-do list.

    Counts **cohorts** now rather than sessions, matching what a letter row
    actually is. Same unbilled rule as `unbilled_sessions`, just computed for
    everyone at once so admin doesn't have to know who to look up.
    """
    candidates = set((await db.execute(
        select(CohortInstructorAssignment.user_id)
        .where(CohortInstructorAssignment.status == "active")
    )).scalars().all())
    candidates |= set((await db.execute(
        select(SessionInstructor.user_id)
        .join(Session, Session.id == SessionInstructor.session_id)
        .where(Session.completed_at.isnot(None))
    )).scalars().all())
    if not candidates:
        return []

    users = {
        u.id: u for u in (await db.execute(
            select(User).where(User.id.in_(candidates))
        )).scalars().all()
    }

    out = []
    for user_id in candidates:
        lines = await unbilled_sessions(db, user_id)
        if not lines:
            continue
        user = users.get(user_id)
        dates = []
        for line in lines:
            for session_id in line["session_ids"]:
                session = await db.get(Session, session_id)
                if session is not None:
                    dates.append(session.meeting_date)
        if not dates:
            continue
        out.append({
            "instructor_user_id": user_id,
            "full_name": user.full_name if user else "",
            "email": user.email if user else "",
            "pending_cohort_count": len(lines),
            # Kept under its old name so the existing schema/UI field still
            # resolves; it now counts the days behind those lines.
            "pending_session_count": sum(line["session_count"] for line in lines),
            "earliest_date": min(dates),
            "latest_date": max(dates),
        })
    out.sort(key=lambda r: r["earliest_date"])
    return out


# ── cohort completion accrues a draft payment line ──────────────────────────

async def find_or_create_draft_letter(db: AsyncSession, instructor_user_id: uuid.UUID) -> PaymentLetter:
    """That instructor's open draft letter, or a new one.

    Appending to an existing draft is what makes monthly aggregation work: a
    second cohort completing in the same month lands on the same letter. Once
    a letter has moved past `draft` it is out of bounds — a published letter is
    being signed and a signed one is a document somebody put their name to, so
    later work starts a fresh draft instead.
    """
    letter = (await db.execute(
        select(PaymentLetter)
        .where(
            PaymentLetter.instructor_user_id == instructor_user_id,
            PaymentLetter.status == PaymentLetterStatus.draft,
        )
        .order_by(PaymentLetter.created_at.desc())
        .limit(1)
    )).scalars().first()
    if letter is not None:
        return letter

    letter = PaymentLetter(
        id=uuid.uuid4(), instructor_user_id=instructor_user_id,
        letter_date=datetime.now(timezone.utc).strftime("%d/%m/%Y"),
        status=PaymentLetterStatus.draft,
    )
    db.add(letter)
    await db.flush()
    return letter


async def accrue_cohort_pay(db: AsyncSession, cohort_id: uuid.UUID) -> list[PaymentSession]:
    """Write a draft payment line for everyone who delivered this cohort.

    No longer wired to fire when a cohort completes (2026-08-30) — that made
    a letter exist before ops ever decided one should. A completed cohort's
    sessions simply become billable (`unbilled_sessions` picks them up for
    the payments to-do list); this function stays available for bulk-billing
    a whole cohort at once, called explicitly rather than as a side effect.
    Idempotent by construction: the lines it would write are derived from
    `unbilled_sessions`, which excludes anything already covered, so running
    it twice adds nothing the second time.

    Everything it writes is a **draft ops can edit** — the amount included.
    Nothing here publishes, signs or pays.
    """
    assignments = (await db.execute(
        select(CohortInstructorAssignment).where(
            CohortInstructorAssignment.cohort_id == cohort_id,
            CohortInstructorAssignment.status == "active",
        )
    )).scalars().all()

    written: list[PaymentSession] = []
    for assignment in assignments:
        lines = [
            line for line in await unbilled_cohorts(db, assignment.user_id)
            if line["cohort_id"] == cohort_id
        ]
        if not lines:
            continue
        letter = await find_or_create_draft_letter(db, assignment.user_id)
        highest = await db.scalar(
            select(func.max(PaymentSession.sort_order))
            .where(PaymentSession.payment_letter_id == letter.id)
        ) or 0

        for offset, line in enumerate(lines, start=1):
            row = PaymentSession(
                id=uuid.uuid4(), payment_letter_id=letter.id,
                cohort_id=line["cohort_id"],
                # Left NULL on a cohort line — coverage rows carry the real
                # answer, and naming one session of five would be a lie.
                session_id=None,
                session_date=line["session_date"],
                workshop_description=line["workshop_description"],
                role=line["role"], location=line["location"],
                duration_hours=line["duration_hours"],
                compensation_aed=line["compensation_aed"],
                session_count=line["session_count"], rate_aed=line["rate_aed"],
                sort_order=highest + offset,
            )
            db.add(row)
            await db.flush()
            for session_id in line["session_ids"]:
                db.add(PaymentSessionCoverage(
                    id=uuid.uuid4(), payment_session_id=row.id, session_id=session_id,
                ))
            written.append(row)
        # A new line invalidates any PDF already rendered for this letter.
        letter.pdf_url = None
        letter.pdf_path = None

    await db.flush()
    return written
