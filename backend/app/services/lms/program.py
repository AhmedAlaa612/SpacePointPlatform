"""LMS Program resolution, assignment, and progress (2026-08-21) — the
checklist-driven redesign. `resolve_cohort_program` is the one place that
reads both `lms_program_cohort_overrides` and `lms_programs` and applies
the override, same role `resolve_cohort_curriculum` used to play; nothing
else should query `lms_program_items` directly to figure out what a
specific cohort's students see.

Items are resolved and materialized ONCE, at assignment time
(`assign_lms_program`) — a later edit to a program's or cohort's checklist
does not retroactively change an existing assignment, mirroring
`enroll_in_cohort_curriculum`'s original "no reconciliation on read"
behavior. A `reconcile`-style fan-out (the `enroll_in_cohort_curriculum`
precedent has one) is a deliberate v1 gap, not an oversight — there is no
production data yet to migrate and no cohort has re-registered students
against a changed checklist; add one the same way P4-2 did if that need
shows up.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.lms.course import Course
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.user import User
from app.services.lms.enrollment import enroll
from app.services.lms.progress import course_completion
from app.services.missions import assign_mission_run

AUTO_TRACKED_TYPES = {"course", "mission_run"}


async def resolve_cohort_program(
    db: AsyncSession, cohort_id: uuid.UUID,
) -> tuple[LmsProgram, list[LmsProgramItem]] | None:
    """The winning `(LmsProgram, items)` pair for this cohort — a cohort
    override with any item rows wins outright over its program's own
    checklist, never merged (the `CohortCurriculum` idiom). Returns None
    when the cohort has no checklist at all (no override, and its program
    has none either) — not every cohort needs one."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None

    override = await db.scalar(
        select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == cohort_id)
    )
    if override is not None:
        items = (await db.execute(
            select(LmsProgramItem)
            .where(LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id)
            .order_by(LmsProgramItem.position)
        )).scalars().all()
        if items:
            program = await db.get(LmsProgram, override.lms_program_id)
            return (program, list(items)) if program else None

    program = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == cohort.program_id))
    if program is None:
        return None
    items = (await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == program.id)
        .order_by(LmsProgramItem.position)
    )).scalars().all()
    return program, list(items)


async def resolve_cohort_program_course_ids(db: AsyncSession, cohort_id: uuid.UUID) -> list[uuid.UUID]:
    """Drop-in replacement for the old `resolve_cohort_curriculum` — just
    the `course`-type items' course ids, in position order. Callers that
    only ever cared about "what courses does this cohort teach"
    (progress grids, the public catalog, session progress) keep working
    unchanged; they don't need to become checklist-aware."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return []
    _, items = resolved
    return [item.course_id for item in items if item.item_type == "course" and item.course_id]


async def resolve_course_titles_by_cohort(
    db: AsyncSession, cohort_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[str]]:
    """Batched drop-in for the public catalog's old `ProgramCurriculum`
    join (`routers/sessions/public.py`) — course titles per cohort, in
    position order, override-aware. One resolver call per cohort (the
    catalog's cohort count is small and this is a cheap read-only
    endpoint already, unlike a hot path), then a single batched title
    lookup for the union of course ids."""
    course_ids_by_cohort = {cohort_id: await resolve_cohort_program_course_ids(db, cohort_id) for cohort_id in cohort_ids}
    all_course_ids = {cid for ids in course_ids_by_cohort.values() for cid in ids}
    if not all_course_ids:
        return {cohort_id: [] for cohort_id in cohort_ids}
    titles = dict((await db.execute(
        select(Course.id, Course.title).where(Course.id.in_(all_course_ids))
    )).all())
    return {
        cohort_id: [titles[cid] for cid in ids if cid in titles]
        for cohort_id, ids in course_ids_by_cohort.items()
    }


async def assign_lms_program(
    db: AsyncSession, *, user_id: uuid.UUID, cohort_id: uuid.UUID, registration_id: uuid.UUID | None = None,
) -> LmsProgramAssignment | None:
    """The per-registration path — called once, at registration time, by
    `sync_registration_lms`, exactly where `enroll_in_cohort_curriculum`
    used to be called. Idempotent on `(user_id, cohort_id)`. Enrolls every
    `course` item immediately and assigns every `mission_run` item's
    attempt immediately (same "enroll everything up front" behavior the
    old curriculum table had) — sequential position only governs the
    checklist's own display/certificate gate, never actual access."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return None
    program, items = resolved
    if not items:
        return None

    existing = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user_id, LmsProgramAssignment.cohort_id == cohort_id,
        )
    )
    if existing is not None:
        return existing

    cohort = await db.get(Cohort, cohort_id)
    assignment = LmsProgramAssignment(
        id=uuid.uuid4(), user_id=user_id, lms_program_id=program.id,
        cohort_id=cohort_id, registration_id=registration_id,
    )
    db.add(assignment)
    await db.flush()

    for item in items:
        progress = LmsProgramItemProgress(id=uuid.uuid4(), assignment_id=assignment.id, item_id=item.id)
        if item.item_type == "course" and item.course_id:
            await enroll(
                db, user_id=user_id, course_id=item.course_id, source="registration",
                program_id=cohort.program_id if cohort else None, registration_id=registration_id,
            )
        elif item.item_type == "mission_run" and item.mission_id:
            attempt = await assign_mission_run(
                db, mission_id=item.mission_id, user_id=user_id, cohort_id=cohort_id, variant_id=item.variant_id,
            )
            progress.mission_attempt_id = attempt.id
        db.add(progress)

    await db.flush()
    return assignment


async def _course_item_done(db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    completion = await course_completion(db, user_id=user_id, course_id=course_id)
    modules = completion["modules"]
    return bool(modules) and all(m["completed"] for m in modules)


async def _mission_run_item_done(db: AsyncSession, *, mission_attempt_id: uuid.UUID | None) -> bool:
    if mission_attempt_id is None:
        return False
    attempt = await db.get(MissionAttempt, mission_attempt_id)
    return attempt is not None and attempt.status == "passed"


async def refresh_item_progress(
    db: AsyncSession, *, progress: LmsProgramItemProgress, item: LmsProgramItem, user_id: uuid.UUID,
) -> str:
    """For `course`/`mission_run` items, recompute `status` from the real
    Enrollment/MissionAttempt state and persist it if it changed — never
    trust a stored 'done' alone, the same instinct
    `compute_dashboard`'s `all_valid` follows for Design missions. Manual/
    external/submission/article items are untouched here; their status is
    written directly by the self-check/confirm actions. Returns the
    resulting status."""
    if item.item_type not in AUTO_TRACKED_TYPES:
        return progress.status

    if item.item_type == "course":
        done = await _course_item_done(db, user_id=user_id, course_id=item.course_id) if item.course_id else False
    else:
        done = await _mission_run_item_done(db, mission_attempt_id=progress.mission_attempt_id)

    if done and progress.status != "done":
        progress.status = "done"
        progress.completed_at = datetime.now(timezone.utc)
    elif not done and progress.status == "done":
        # A course/attempt can un-complete (e.g. a mission gets reset) —
        # reflect that rather than leaving a stale "done".
        progress.status = "pending"
        progress.completed_at = None
    return progress.status


async def certificate_gate_satisfied(db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
    """Whether this student's checklist (if any) is done enough to let the
    cohort's `student_completion` certificate issue. True when: the
    cohort has no checklist at all, its checklist doesn't require one
    (`certificate_required=False`), or every non-optional item is done.
    False when a checklist requires it and the student has no LMS
    account/assignment at all — an unassigned student's checklist is, by
    definition, not done. Only `complete_cohort`'s automatic path should
    call this; `issue_certificate_override` is the deliberate ops
    bypass and must not."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return True
    program, items = resolved
    if not program.certificate_required:
        return True
    required_items = [item for item in items if not item.optional]
    if not required_items:
        return True
    if user_id is None:
        return False

    assignment = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user_id, LmsProgramAssignment.cohort_id == cohort_id,
        )
    )
    if assignment is None:
        return False

    progress_rows = {
        p.item_id: p for p in (await db.execute(
            select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
        )).scalars().all()
    }
    for item in required_items:
        progress = progress_rows.get(item.id)
        if progress is None:
            return False
        status = await refresh_item_progress(db, progress=progress, item=item, user_id=user_id)
        if status != "done":
            return False
    return True


async def _certificate_earned(db: AsyncSession, registration_id: uuid.UUID | None) -> bool:
    if registration_id is None:
        return False
    return await db.scalar(select(Certificate.id).where(Certificate.registration_id == registration_id)) is not None


async def _assignment_items_and_progress(
    db: AsyncSession, assignment_id: uuid.UUID,
) -> list[tuple[LmsProgramItem, LmsProgramItemProgress]]:
    """The assignment's own materialized item set, resolved via its
    progress rows rather than re-resolving `resolve_cohort_program` —
    a later checklist edit must not retroactively change an existing
    assignment (see module docstring)."""
    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment_id)
    )).scalars().all()
    if not progress_rows:
        return []
    item_ids = [p.item_id for p in progress_rows]
    items_by_id = {
        i.id: i for i in (await db.execute(select(LmsProgramItem).where(LmsProgramItem.id.in_(item_ids)))).scalars().all()
    }
    pairs = [(items_by_id[p.item_id], p) for p in progress_rows if p.item_id in items_by_id]
    pairs.sort(key=lambda pair: pair[0].position)
    return pairs


async def get_student_checklist(db: AsyncSession, *, assignment_id: uuid.UUID, user_id: uuid.UUID) -> dict | None:
    """None means either the assignment doesn't exist or belongs to a
    different student — the router turns both into a plain 404, never
    leaking which."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None or assignment.user_id != user_id:
        return None
    program = await db.get(LmsProgram, assignment.lms_program_id)
    if program is None:
        return None
    cohort = await db.get(Cohort, assignment.cohort_id) if assignment.cohort_id else None

    pairs = await _assignment_items_and_progress(db, assignment_id)
    mission_ids = {item.mission_id for item, _ in pairs if item.mission_id}
    mission_kinds = dict((await db.execute(
        select(Mission.id, Mission.kind).where(Mission.id.in_(mission_ids))
    )).all()) if mission_ids else {}

    items_out = []
    for item, progress in pairs:
        status = await refresh_item_progress(db, progress=progress, item=item, user_id=user_id)
        items_out.append({
            "id": item.id, "position": item.position, "item_type": item.item_type,
            "title": item.title, "description": item.description,
            "optional": item.optional, "requires_confirmation": item.requires_confirmation,
            "status": status, "course_id": item.course_id,
            "mission_attempt_id": progress.mission_attempt_id,
            "mission_id": item.mission_id, "mission_kind": mission_kinds.get(item.mission_id),
            "external_url": item.external_url, "submission_prompt": item.submission_prompt,
            "submitted_url": progress.submitted_url,
        })

    return {
        "assignment_id": assignment.id, "lms_program_id": program.id, "name": program.name,
        "description": program.description, "cohort_id": assignment.cohort_id,
        "cohort_name": cohort.name if cohort else None,
        "certificate_required": program.certificate_required,
        "certificate_earned": await _certificate_earned(db, assignment.registration_id),
        "items": items_out,
    }


async def _assignment_summary(db: AsyncSession, assignment: LmsProgramAssignment) -> dict | None:
    program = await db.get(LmsProgram, assignment.lms_program_id)
    if program is None:
        return None
    cohort = await db.get(Cohort, assignment.cohort_id) if assignment.cohort_id else None

    done = 0
    required_total = 0
    next_item_title: str | None = None
    for item, progress in await _assignment_items_and_progress(db, assignment.id):
        if item.optional:
            continue
        required_total += 1
        status = await refresh_item_progress(db, progress=progress, item=item, user_id=assignment.user_id)
        if status == "done":
            done += 1
        elif next_item_title is None:
            next_item_title = item.title

    return {
        "assignment_id": assignment.id, "lms_program_id": program.id, "name": program.name,
        "cohort_id": assignment.cohort_id, "cohort_name": cohort.name if cohort else None,
        "items_total": required_total, "items_done": done,
        "pct": round(100 * done / required_total) if required_total else 100,
        "next_item_title": next_item_title,
        "certificate_required": program.certificate_required,
        "certificate_earned": await _certificate_earned(db, assignment.registration_id),
    }


async def list_student_assignments(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    assignments = (await db.execute(
        select(LmsProgramAssignment)
        .where(LmsProgramAssignment.user_id == user_id)
        .order_by(LmsProgramAssignment.assigned_at.desc())
    )).scalars().all()
    out = []
    for assignment in assignments:
        summary = await _assignment_summary(db, assignment)
        if summary is not None:
            out.append(summary)
    return out


async def cohort_program_roster(db: AsyncSession, *, cohort_id: uuid.UUID) -> list[dict]:
    """Instructor/ops view — every student assigned this cohort's LMS
    Program checklist, each with the same progress summary shape as the
    student's own `/lms/programs` list."""
    assignments = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.cohort_id == cohort_id)
    )).scalars().all()
    out = []
    for assignment in assignments:
        summary = await _assignment_summary(db, assignment)
        if summary is None:
            continue
        user = await db.get(User, assignment.user_id)
        pending = [
            {"item_id": item.id, "title": item.title}
            for item, progress in await _assignment_items_and_progress(db, assignment.id)
            if progress.status == "awaiting_confirmation"
        ]
        out.append({
            **summary, "user_id": assignment.user_id, "student_name": user.full_name if user else "?",
            "pending_confirmations": pending,
        })
    return out


async def confirm_program_item(
    db: AsyncSession, *, assignment_id: uuid.UUID, item_id: uuid.UUID, confirmed_by_user_id: uuid.UUID,
) -> LmsProgramItemProgress | None:
    """Ops/instructor sign-off for a `requires_confirmation` item —
    the other half of the self-check flow (services/lms/program.py's
    `refresh_item_progress` never touches these, they're only ever
    written here or by the student's own self-check)."""
    progress = await db.scalar(
        select(LmsProgramItemProgress).where(
            LmsProgramItemProgress.assignment_id == assignment_id, LmsProgramItemProgress.item_id == item_id,
        )
    )
    if progress is None:
        return None
    progress.status = "done"
    progress.completed_at = datetime.now(timezone.utc)
    progress.confirmed_by_user_id = confirmed_by_user_id
    await db.flush()
    return progress
