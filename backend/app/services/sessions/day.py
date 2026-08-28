"""The instructor's day: check-in, the daily checklist, submission and ops
review (operations process doc §4-§12, scoped in 2026-08-24).

The shape, end to end:

    morning   instructor checks in, or declares an absence with a reason
    during    they work the resolved checklist, uploading proof where required
    evening   they submit the day
    after     ops approves it, or returns it with a comment to be redone

**That approval is the gate.** `status='approved'` and `att_status='present'`
is what makes a day a *paid* day (§18/§19) — nothing else in the system gets
to decide what counts as delivered, which is why `approve_day` is also where
cohort auto-completion is triggered from.

Checklist resolution is override-not-merge across program -> cohort -> session,
identical in rule and reasoning to `services/sessions/materials.py`. Proof
files go through the existing `services/sessions/reports.py`, never a second
upload path.

Authorisation follows `delivery.py`: `_get_deliverable_session` already means
"the assigned instructor, or ops/admin", and returns 404 rather than 403 for
someone unassigned so the endpoints don't leak which sessions exist.

Services raise `HTTPException` directly — house convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.checklist import (
    DeliveryChecklistItem,
    InstructorChecklistProgress,
    InstructorSessionDay,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.user import User
from app.services.sessions.delivery import _get_deliverable_session, complete_cohort
from app.services.sessions.reports import resolve_report_url

ATT_STATUSES = {"present", "absent"}
DAY_STATUSES = {"draft", "submitted", "changes_required", "approved"}


# ── checklist templates (ops) ───────────────────────────────────────────────

async def _items_at_level(
    db: AsyncSession, *,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
) -> list[DeliveryChecklistItem]:
    """Every item set at exactly one level — general *and* every role's,
    unfiltered. The raw fetch both `list_checklist_items` (which then filters
    to one role bucket) and `resolve_checklist` (which splits by role itself,
    level by level) build on."""
    column = (
        DeliveryChecklistItem.program_id if program_id
        else DeliveryChecklistItem.cohort_id if cohort_id
        else DeliveryChecklistItem.session_id if session_id
        else None
    )
    value = program_id or cohort_id or session_id
    if column is None:
        return []
    return list((await db.execute(
        select(DeliveryChecklistItem).where(column == value)
        .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
    )).scalars().all())


async def list_checklist_items(
    db: AsyncSession, *,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    role_id: UUID | None = None,
) -> list[DeliveryChecklistItem]:
    """One (level, role) bucket — no inheritance, no role fallback applied.

    This is the management view: ops editing a program's *general* checklist
    has to see exactly the program's own general rows, not whatever a cohort
    happens to inherit and not another role's list. `role_id=None` (the
    default) means the general bucket; pass a role to edit that role's own
    list. Same split as `materials.list_materials` vs. its resolver, with role
    as a second, independent axis on top.
    """
    items = await _items_at_level(db, program_id=program_id, cohort_id=cohort_id, session_id=session_id)
    return [i for i in items if i.role_id == role_id]


async def set_checklist_items(
    db: AsyncSession, *, lines: list[dict], actor_user_id: UUID,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    role_id: UUID | None = None,
) -> list[DeliveryChecklistItem]:
    """Replace one (level, role) bucket wholesale.

    Whole-bucket rather than per-line editing, the same choice `set_openings`
    and `PUT /templates/{id}/items` already make: the client never has to
    diff, and a half-applied edit can't leave a checklist half-rewritten
    mid-workshop. Scoped to `role_id` so editing a role's own list never
    touches the general bucket or another role's — each is independent.

    Rows are replaced wholesale, so progress rows against removed items go with
    them (CASCADE). That is correct — an item ops deleted is not an item
    anybody still owes proof for — but it does mean editing a checklist while a
    workshop is running discards ticks for the items removed.
    """
    owners = [program_id, cohort_id, session_id]
    if sum(1 for o in owners if o is not None) != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A checklist belongs to exactly one of a program, a cohort or a session",
        )

    existing = await list_checklist_items(
        db, program_id=program_id, cohort_id=cohort_id, session_id=session_id, role_id=role_id,
    )
    for item in existing:
        await db.delete(item)
    await db.flush()

    out = []
    for i, line in enumerate(lines):
        title = (line.get("title") or "").strip()
        if not title:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A checklist item needs a title")
        item = DeliveryChecklistItem(
            id=uuid4(), program_id=program_id, cohort_id=cohort_id, session_id=session_id, role_id=role_id,
            title=title, description=line.get("description"),
            requires_proof=bool(line.get("requires_proof")),
            is_required=bool(line.get("is_required", True)),
            sort_order=int(line.get("sort_order") or (i + 1)),
            created_by=actor_user_id,
        )
        db.add(item)
        out.append(item)
    await db.flush()
    return out


async def _instructor_role(db: AsyncSession, session_id: UUID, user_id: UUID) -> UUID | None:
    """Which role this instructor holds on this session — what `resolve_checklist`
    needs to pick their bucket over the general one. `None` for someone with no
    `SessionInstructor` row (shouldn't happen for a deliverable session, but
    resolving to the general checklist rather than raising is the safer default)."""
    return await db.scalar(
        select(SessionInstructor.role_id).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
        )
    )


async def resolve_checklist(
    db: AsyncSession, session: Session, role_id: UUID | None = None,
) -> list[DeliveryChecklistItem]:
    """What this instructor actually works through on this session.

    Two overrides stacked, both **override, not merge**:

    * **Level** — the nearest of session -> cohort -> program with *anything*
      set at all wins outright; a level with nothing set is skipped entirely,
      not treated as "zero items."
    * **Role**, within whichever level wins — that role's own items if any
      exist there, else that level's general (role_id IS NULL) items. A role
      checklist replaces the general one for that role; it is never added on
      top of it.

    Merging either axis would make it impossible to *remove* an item for one
    cohort or one role, which is exactly what overridable has to mean (see
    `materials.py` for the level half of this reasoning).
    """
    for kwargs in (
        {"session_id": session.id},
        {"cohort_id": session.cohort_id},
    ):
        items = await _items_at_level(db, **kwargs)
        if not items:
            continue
        role_items = [i for i in items if i.role_id == role_id] if role_id is not None else []
        if role_items:
            return role_items
        general = [i for i in items if i.role_id is None]
        if general:
            return general
    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is None:
        return []
    items = await _items_at_level(db, program_id=cohort.program_id)
    role_items = [i for i in items if i.role_id == role_id] if role_id is not None else []
    if role_items:
        return role_items
    return [i for i in items if i.role_id is None]


# ── the instructor's day ────────────────────────────────────────────────────

async def _get_or_create_day(db: AsyncSession, session_id: UUID, user_id: UUID) -> InstructorSessionDay:
    day = (await db.execute(
        select(InstructorSessionDay).where(
            InstructorSessionDay.session_id == session_id,
            InstructorSessionDay.user_id == user_id,
        )
    )).scalars().first()
    if day is None:
        day = InstructorSessionDay(id=uuid4(), session_id=session_id, user_id=user_id, status="draft")
        db.add(day)
        await db.flush()
    return day


def _refuse_if_locked(day: InstructorSessionDay) -> None:
    """An approved day is what ops signed off and what the payment line counts.
    Reopening it is an ops decision (`return_day`), not something an instructor
    can do by editing underneath the approval."""
    if day.status == "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This day is approved — ask ops to reopen it if something needs changing",
        )


async def check_in(
    db: AsyncSession, session_id: UUID, user: User, *,
    att_status: str, reason: str | None = None,
) -> InstructorSessionDay:
    """"I'm here" / "I can't attend today" (§4).

    Recorded day by day and never inferred from the cohort assignment — the
    whole point is that an instructor assigned to five days may legitimately
    miss one, and the letter should say four.
    """
    if att_status not in ATT_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Attendance is 'present' or 'absent'")
    await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    day.att_status = att_status
    day.absence_reason = reason if att_status == "absent" else None
    # Idempotent on the timestamp, same reasoning as `start_session`: tapping
    # twice on a flaky connection must not move the recorded arrival time.
    if att_status == "present" and day.checked_in_at is None:
        day.checked_in_at = datetime.now(timezone.utc)
    if att_status == "absent":
        day.checked_in_at = None
    await db.flush()
    return day


async def set_checklist_progress(
    db: AsyncSession, session_id: UUID, user: User, *,
    checklist_item_id: UUID, is_done: bool | None = None,
    proof_report_id: UUID | None = None, note: str | None = None,
) -> InstructorChecklistProgress:
    """Tick an item, attach proof to it, or both."""
    session = await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    role_id = await _instructor_role(db, session_id, user.id)
    valid_ids = {i.id for i in await resolve_checklist(db, session, role_id)}
    if checklist_item_id not in valid_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That item isn't on this session's checklist")

    if proof_report_id is not None:
        report = await db.get(SessionReport, proof_report_id)
        if report is None or report.session_id != session_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proof upload not found for this session")

    row = (await db.execute(
        select(InstructorChecklistProgress).where(
            InstructorChecklistProgress.day_id == day.id,
            InstructorChecklistProgress.checklist_item_id == checklist_item_id,
        )
    )).scalars().first()
    if row is None:
        row = InstructorChecklistProgress(
            id=uuid4(), day_id=day.id, checklist_item_id=checklist_item_id,
        )
        db.add(row)
    if is_done is not None:
        row.is_done = is_done
    if proof_report_id is not None:
        row.proof_report_id = proof_report_id
    if note is not None:
        row.note = note
    await db.flush()
    return row


async def _missing_requirements(
    db: AsyncSession, session: Session, day: InstructorSessionDay,
) -> list[str]:
    """What still stands between this day and being submittable.

    Returned as a list rather than raising on the first problem: an instructor
    at 3pm should see everything outstanding at once, not discover it one
    round-trip at a time.
    """
    if day.att_status is None:
        return ["Check in (or declare an absence) before submitting the day"]
    if day.att_status == "absent":
        # An absence has nothing to submit — ops acknowledges it directly.
        return []

    role_id = await _instructor_role(db, session.id, day.user_id)
    items = await resolve_checklist(db, session, role_id)
    progress = {
        p.checklist_item_id: p for p in (await db.execute(
            select(InstructorChecklistProgress).where(InstructorChecklistProgress.day_id == day.id)
        )).scalars().all()
    }
    missing = []
    for item in items:
        row = progress.get(item.id)
        if item.is_required and (row is None or not row.is_done):
            missing.append(f"'{item.title}' isn't ticked")
        elif item.requires_proof and (row is None or row.proof_report_id is None):
            missing.append(f"'{item.title}' needs a photo")
    return missing


async def submit_day(db: AsyncSession, session_id: UUID, user: User, *, notes: str | None = None):
    """Send the day for ops review (§11)."""
    session = await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    if notes is not None:
        day.instructor_notes = notes

    missing = await _missing_requirements(db, session, day)
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This day isn't ready to submit: " + "; ".join(missing),
        )

    day.status = "submitted"
    day.submitted_at = datetime.now(timezone.utc)
    # Clear the previous round's comment — leaving it would make a resubmitted
    # day still look like it had been rejected.
    day.review_comment = None
    await db.flush()
    return day


# ── ops review ──────────────────────────────────────────────────────────────

async def _get_day(db: AsyncSession, day_id: UUID) -> InstructorSessionDay:
    day = await db.get(InstructorSessionDay, day_id)
    if day is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Day not found")
    return day


async def approve_day(db: AsyncSession, day_id: UUID, actor_user_id: UUID) -> InstructorSessionDay:
    """Ops signs off a day (§12) — and this is what makes it a paid day.

    Only a submitted day can be approved, with one deliberate exception: an
    absence, which the instructor has nothing to submit for and ops simply
    acknowledges.
    """
    day = await _get_day(db, day_id)
    if day.status == "approved":
        return day  # idempotent — approving twice is not an error
    if day.status != "submitted" and day.att_status != "absent":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Only a submitted day can be approved",
        )
    day.status = "approved"
    day.reviewed_at = datetime.now(timezone.utc)
    day.reviewed_by = actor_user_id
    await db.flush()
    return day


async def return_day(
    db: AsyncSession, day_id: UUID, actor_user_id: UUID, *, comment: str,
) -> InstructorSessionDay:
    """Send it back with something to fix (§12).

    A comment is mandatory: "changes required" with no reason is the exact
    thing this replaces from WhatsApp.
    """
    comment = (comment or "").strip()
    if not comment:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Say what needs changing when returning a day"
        )
    day = await _get_day(db, day_id)
    day.status = "changes_required"
    day.review_comment = comment
    day.reviewed_at = datetime.now(timezone.utc)
    day.reviewed_by = actor_user_id
    await db.flush()
    return day


async def list_day_reviews(
    db: AsyncSession, *, status_filter: str | None = "submitted", cohort_id: UUID | None = None,
) -> list[dict]:
    """The ops queue. Defaults to what needs attention now (`submitted`);
    pass `status_filter=None` for everything, or a cohort to scope it."""
    stmt = (
        select(InstructorSessionDay, User, Session, Cohort, Program)
        .join(User, User.id == InstructorSessionDay.user_id)
        .join(Session, Session.id == InstructorSessionDay.session_id)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .order_by(Session.meeting_date.asc(), User.full_name.asc())
    )
    if status_filter:
        stmt = stmt.where(InstructorSessionDay.status == status_filter)
    if cohort_id is not None:
        stmt = stmt.where(Session.cohort_id == cohort_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    day_ids = [d.id for d, _u, _s, _c, _p in rows]
    done_counts = dict((await db.execute(
        select(InstructorChecklistProgress.day_id, func.count())
        .where(
            InstructorChecklistProgress.day_id.in_(day_ids),
            InstructorChecklistProgress.is_done.is_(True),
        )
        .group_by(InstructorChecklistProgress.day_id)
    )).all())

    out = []
    for day, user, session, cohort, program in rows:
        role_id = await _instructor_role(db, session.id, user.id)
        total = len(await resolve_checklist(db, session, role_id))
        out.append({
            "day_id": day.id,
            "session_id": session.id,
            "cohort_id": cohort.id,
            "cohort_name": cohort.name,
            "program_name": program.name,
            "session_title": session.title,
            "meeting_date": session.meeting_date,
            "user_id": user.id,
            "full_name": user.full_name,
            "att_status": day.att_status,
            "absence_reason": day.absence_reason,
            "checked_in_at": day.checked_in_at,
            "status": day.status,
            "submitted_at": day.submitted_at,
            "review_comment": day.review_comment,
            "instructor_notes": day.instructor_notes,
            "checklist_done": done_counts.get(day.id, 0),
            "checklist_total": total,
        })
    return out


async def get_day_detail(db: AsyncSession, session_id: UUID, user: User, *, for_user_id: UUID | None = None) -> dict:
    """One instructor's day, with the resolved checklist and their progress —
    what both the instructor's own portal and the ops review card render."""
    session = await _get_deliverable_session(db, session_id, user)
    target_id = for_user_id or user.id
    day = await _get_or_create_day(db, session_id, target_id)

    role_id = await _instructor_role(db, session_id, target_id)
    items = await resolve_checklist(db, session, role_id)
    progress = {
        p.checklist_item_id: p for p in (await db.execute(
            select(InstructorChecklistProgress).where(InstructorChecklistProgress.day_id == day.id)
        )).scalars().all()
    }

    checklist = []
    for item in items:
        row = progress.get(item.id)
        proof_url = None
        if row is not None and row.proof_report_id is not None:
            report = await db.get(SessionReport, row.proof_report_id)
            if report is not None:
                proof_url = await resolve_report_url(report)
        checklist.append({
            "item_id": item.id,
            "title": item.title,
            "description": item.description,
            "requires_proof": item.requires_proof,
            "is_required": item.is_required,
            "sort_order": item.sort_order,
            "is_done": bool(row and row.is_done),
            "note": row.note if row else None,
            "proof_report_id": row.proof_report_id if row else None,
            "proof_url": proof_url,
        })

    return {
        "day_id": day.id,
        "session_id": session_id,
        "user_id": target_id,
        "att_status": day.att_status,
        "absence_reason": day.absence_reason,
        "checked_in_at": day.checked_in_at,
        "status": day.status,
        "submitted_at": day.submitted_at,
        "reviewed_at": day.reviewed_at,
        "review_comment": day.review_comment,
        "instructor_notes": day.instructor_notes,
        "checklist": checklist,
        "can_submit": not await _missing_requirements(db, session, day),
        "missing": await _missing_requirements(db, session, day),
    }


# ── cohort auto-completion ──────────────────────────────────────────────────

async def cohort_is_fully_reviewed(db: AsyncSession, cohort_id: UUID) -> bool:
    """Every session delivered and every instructor-day signed off.

    Three conditions, all necessary:
      * the cohort has sessions at all;
      * every one of them has `completed_at` set;
      * somebody was actually staffed, and every day row is `approved`.

    The staffing check is not redundant. Without it a cohort nobody was ever
    assigned to has zero day rows, "all approved" is vacuously true, and the
    cohort would complete itself the moment its last session was marked done.
    """
    session_ids = list((await db.execute(
        select(Session.id).where(Session.cohort_id == cohort_id)
    )).scalars().all())
    if not session_ids:
        return False

    unfinished = await db.scalar(
        select(func.count()).select_from(Session)
        .where(Session.cohort_id == cohort_id, Session.completed_at.is_(None))
    )
    if unfinished:
        return False

    staffed = await db.scalar(
        select(func.count()).select_from(SessionInstructor)
        .where(SessionInstructor.session_id.in_(session_ids))
    )
    if not staffed:
        return False

    days = (await db.execute(
        select(InstructorSessionDay.status)
        .where(InstructorSessionDay.session_id.in_(session_ids))
    )).scalars().all()
    # One row per assigned instructor per session, all approved. Fewer rows
    # than assignments means somebody never submitted their day.
    if len(days) < staffed:
        return False
    return all(s == "approved" for s in days)


async def maybe_complete_cohort(db: AsyncSession, cohort_id: UUID, actor_user_id: UUID) -> bool:
    """Flip a cohort to completed once its last day is approved.

    Reuses `complete_cohort()` unchanged — student statuses, the LMS
    certificate gate and student certificates all behave exactly as they do
    when ops presses the button today. The only new thing is who presses it.
    Returns whether it fired, so the caller can report it.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or cohort.status == "completed":
        return False
    if not await cohort_is_fully_reviewed(db, cohort_id):
        return False
    await complete_cohort(db, cohort_id, actor_user_id)
    # The same event pays the instructors: a draft line per cohort assignment,
    # amount pre-computed, on their open draft letter (or a new one). Imported
    # here rather than at module scope — `journey` imports `openings`, which
    # imports back into this domain, and a top-level import closes the cycle.
    from app.services.sessions.journey import accrue_cohort_pay
    await accrue_cohort_pay(db, cohort_id)
    return True
