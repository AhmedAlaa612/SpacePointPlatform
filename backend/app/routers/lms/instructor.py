"""Cohort-scoped instructor LMS Program checklist view (2026-08-21) —
`/lms/instructor/*`. Mirrors `routers/missions/instructor.py`'s cohort_access
pattern for the new checklist entity: instructors track their own cohort's
students without becoming ops/facilitator generally. `require_instructor_missions`
is reused as-is — same role population (instructor/facilitator/operations,
admin bypasses) an LMS-side instructor view needs, no reason to duplicate it.

Program-merge additions (2026-08-22, operator ask — Programs/Cohort Missions
merge): the program-wide roster, per-assignment item detail, and student-
profile mirrors below all reuse the exact same ops-only service functions
`routers/lms/admin.py` already calls — `_require_student_access` is the one
new piece of logic, applying `instructor_cohort_ids()` the same way
`require_cohort_access` already does for a cohort_id, just against a
student's own active registrations instead.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_instructor_missions
from app.db.session import get_db
from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.user import User
from app.routers.lms.admin import enrollment_admin_out, program_out
from app.schemas.lms_admin import (
    EnrollmentAdminOut, LmsProgramCohortEffectiveOut, LmsProgramItemIn, LmsProgramItemOut, LmsProgramOut,
    StudentProfileOut, StudentProgramOut,
)
from app.schemas.lms_cohort_quiz import CohortQuizResultOut, CohortQuizTopicBreakdownOut
from app.schemas.lms_instructor import (
    CourseProgressOut, LmsAssignmentItemDetailOut, LmsProgramRosterRowOut, ModuleProgressOut, QuizProgressOut,
)
from app.schemas.lms_progress_grid import StudentDesignRunsOut
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.admin_progress import student_design_runs
from app.services.lms.instructor_progress import student_course_progress
from app.services.lms.my_programs import my_programs
from app.services.lms.program import (
    assignment_item_detail, check_item_conflicts, cohort_program_roster, confirm_program_item,
    effective_cohort_program_items, fork_cohort_override, guard_locked_submission_scope, item_out, items_out,
    next_position, program_roster, sync_cohort_assignments, validate_item_payload, validate_item_refs,
)
from app.services.missions.cohort_access import instructor_cohort_ids, require_cohort_access
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

router = APIRouter(prefix="/lms/instructor", tags=["lms-instructor"], dependencies=[Depends(require_instructor_missions)])


@router.get("/programs", response_model=list[LmsProgramOut])
async def my_reachable_programs(
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Program picker source for the merged Programs page (2026-08-22) —
    every checklist for staff, else only the ones attached to a Sessions
    Program that at least one of the instructor's own cohorts uses."""
    allowed = await instructor_cohort_ids(db, user=current)
    query = select(LmsProgram)
    if allowed is not None:
        if not allowed:
            return []
        program_ids = (await db.execute(
            select(Cohort.program_id).where(Cohort.id.in_(allowed))
        )).scalars().all()
        query = query.where(LmsProgram.program_id.in_(program_ids))
    programs = (await db.execute(query.order_by(LmsProgram.name))).scalars().all()
    return [await program_out(db, p) for p in programs]


@router.get("/cohorts/{cohort_id}/program-progress", response_model=list[LmsProgramRosterRowOut])
async def cohort_program_progress(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    return await cohort_program_roster(db, cohort_id=cohort_id)


@router.get("/programs/{lms_program_id}/progress", response_model=list[LmsProgramRosterRowOut])
async def program_progress(
    lms_program_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Program-wide roster (2026-08-22) — every cohort using this program at
    once, restricted to the instructor's own cohorts when they aren't staff
    (`instructor_cohort_ids()` returns `None`, unrestricted, for staff)."""
    restrict = await instructor_cohort_ids(db, user=current)
    return await program_roster(db, lms_program_id=lms_program_id, restrict_to_cohort_ids=restrict)


@router.get(
    "/cohorts/{cohort_id}/program-progress/{assignment_id}/items", response_model=list[LmsAssignmentItemDetailOut],
)
async def assignment_items(
    cohort_id: uuid.UUID, assignment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Every item on one student's assignment — not just the ones awaiting
    confirmation the roster already shows — for the "detailed submissions"
    drill-in (operator ask, 2026-08-22)."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    items = await assignment_item_detail(db, assignment_id=assignment_id)
    if items is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return items


async def _cohort_quiz_assignment_item(
    db: AsyncSession, *, cohort_id: uuid.UUID, assignment_id: uuid.UUID, item_id: uuid.UUID,
) -> tuple[LmsProgramAssignment, LmsProgramItem]:
    """Resolves (assignment, item) for the two quiz routes below, the same
    way `student.py`'s own `_own_progress_row` resolves its pair — checking
    `assignment.cohort_id == cohort_id` (the caller only ever has
    `require_cohort_access`-verified access to *that* cohort, not to
    whichever cohort `assignment_id` actually belongs to) and that a real
    `LmsProgramItemProgress` row ties `item_id` to this exact assignment's
    own checklist, rather than trusting a same-shaped id pair from an
    unrelated program/cohort the caller has no business reading."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    item = await db.get(LmsProgramItem, item_id)
    if assignment is None or item is None or item.item_type != "quiz" or assignment.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz item not found")
    linked = await db.scalar(
        select(LmsProgramItemProgress.id).where(
            LmsProgramItemProgress.assignment_id == assignment_id, LmsProgramItemProgress.item_id == item_id,
        )
    )
    if linked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz item not found")
    return assignment, item


@router.get(
    "/cohorts/{cohort_id}/program-progress/{assignment_id}/items/{item_id}/quiz/review",
    response_model=CohortQuizResultOut,
)
async def instructor_quiz_review(
    cohort_id: uuid.UUID, assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Ops/instructor drill-in on one student's quiz answers — per-question
    correct/incorrect, response time, and explanation, plus what they left
    unanswered (`selected_index: null`). Mirrors the student's own
    `GET /lms/programs/{assignment_id}/items/{item_id}/quiz/result`, just
    reached by (assignment, item) instead of the caller's own user id."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    assignment, _ = await _cohort_quiz_assignment_item(
        db, cohort_id=cohort_id, assignment_id=assignment_id, item_id=item_id,
    )
    attempt = await cohort_quiz_service.get_own_attempt(db, program_item_id=item_id, user_id=assignment.user_id)
    if attempt is None or attempt.status != "submitted":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This student hasn't submitted the quiz yet")
    review = await cohort_quiz_service.get_attempt_review(db, attempt)
    return cohort_quiz_service.result_out(attempt, review)


@router.post(
    "/cohorts/{cohort_id}/program-progress/{assignment_id}/items/{item_id}/quiz/reset",
    response_model=list[LmsAssignmentItemDetailOut],
)
async def instructor_reset_quiz(
    cohort_id: uuid.UUID, assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Ops/instructor "let them retake" — deletes the student's attempt
    (in-progress or submitted) so their next visit starts a brand-new one:
    fresh question order, fresh per-question timers. The checklist item
    reverts to not-done, same as any other auto-tracked item un-completing."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    assignment, _ = await _cohort_quiz_assignment_item(
        db, cohort_id=cohort_id, assignment_id=assignment_id, item_id=item_id,
    )
    await cohort_quiz_service.reset_attempt(db, program_item_id=item_id, user_id=assignment.user_id)
    await db.commit()
    items = await assignment_item_detail(db, assignment_id=assignment_id)
    if items is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return items


@router.post(
    "/cohorts/{cohort_id}/program-progress/{assignment_id}/items/{item_id}/confirm",
    response_model=LmsProgramRosterRowOut,
)
async def confirm_checklist_item(
    cohort_id: uuid.UUID, assignment_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Ops/instructor sign-off for a `requires_confirmation` item — the
    review-queue-shaped action for whatever the system can't auto-track
    (a meeting attendance, a manual check-off)."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    progress = await confirm_program_item(
        db, assignment_id=assignment_id, item_id=item_id, confirmed_by_user_id=current.id,
    )
    if progress is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checklist item not found")
    await db.commit()
    roster = await cohort_program_roster(db, cohort_id=cohort_id)
    row = next((r for r in roster if r["assignment_id"] == assignment_id), None)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    return row


# ── cohort override checklist (2026-08-23) — fixes a real 403: instructors
# had no way to even read their own cohort's checklist, despite the
# Program-scope template already being visible to them. Read is open to
# every item type, same as the ops-side endpoint this mirrors — an
# instructor needs to see the whole effective checklist to make sense of
# the Missions/Checklist tabs. Write is narrower: a plain instructor may
# only add/edit/delete `mission_run` items (the "edit only their cohort's
# missions... any extra edits need ops" boundary from the operator's
# original ask) — enforced here via `instructor_cohort_ids()`'s staff/
# non-staff signal, not left to the frontend hiding the controls.

@router.get("/cohorts/{cohort_id}/program-override", response_model=LmsProgramCohortEffectiveOut)
async def cohort_program_override(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    resolved = await effective_cohort_program_items(db, cohort_id)
    if resolved is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort's program has no LMS checklist yet")
    program, items, is_inherited = resolved
    return LmsProgramCohortEffectiveOut(
        cohort_id=cohort_id, lms_program_id=program.id, is_inherited=is_inherited, items=await items_out(db, items),
    )


async def _enforce_instructor_item_scope(db: AsyncSession, *, current: User, item_type: str) -> None:
    """A plain instructor may only touch `mission_run` items on their
    cohort's override — every other checklist item type stays ops-only."""
    restricted = await instructor_cohort_ids(db, user=current)
    if restricted is not None and item_type != "mission_run":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Instructors can only add, edit, or delete mission runs here — other checklist items need ops.",
        )


@router.post(
    "/cohorts/{cohort_id}/program-override/items", response_model=LmsProgramItemOut, status_code=status.HTTP_201_CREATED,
)
async def add_cohort_override_item(
    cohort_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    await _enforce_instructor_item_scope(db, current=current, item_type=body.item_type)
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This cohort's program has no LMS checklist to override yet — create one first",
        )
    override, _id_map = forked
    validate_item_payload(body)
    await validate_item_refs(db, body)
    await check_item_conflicts(db, owner_type="cohort_override", owner_id=override.id, body=body)
    position = body.position or await next_position(db, owner_type="cohort_override", owner_id=override.id)
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="cohort_override", owner_id=override.id, position=position,
        **body.model_dump(exclude={"position"}),
    )
    db.add(item)
    await db.flush()
    await sync_cohort_assignments(db, cohort_id=cohort_id)
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.patch("/cohorts/{cohort_id}/program-override/items/{item_id}", response_model=LmsProgramItemOut)
async def update_cohort_override_item(
    cohort_id: uuid.UUID, item_id: uuid.UUID, body: LmsProgramItemIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """`item_id` may be a not-yet-forked program item's id (the "inherited"
    list the GET above serves) — `fork_cohort_override`'s id map translates
    it to the override's own freshly-copied item on exactly the call that
    triggers the fork, same as the ops-side endpoint."""
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    await _enforce_instructor_item_scope(db, current=current, item_type=body.item_type)
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort has no checklist to override")
    override, id_map = forked
    resolved_item_id = id_map.get(item_id, item_id)
    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == resolved_item_id,
            LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    await _enforce_instructor_item_scope(db, current=current, item_type=item.item_type)
    guard_locked_submission_scope(item, body)
    validate_item_payload(body)
    await validate_item_refs(db, body, require_active_quiz=False)
    await check_item_conflicts(db, owner_type="cohort_override", owner_id=override.id, body=body, exclude_item_id=item.id)
    for field, value in body.model_dump(exclude={"position"}).items():
        setattr(item, field, value)
    if body.position is not None:
        item.position = body.position
    await db.commit()
    await db.refresh(item)
    return await item_out(db, item)


@router.delete("/cohorts/{cohort_id}/program-override/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_override_item(
    cohort_id: uuid.UUID, item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await require_cohort_access(db, cohort_id=cohort_id, user=current)
    forked = await fork_cohort_override(db, cohort_id=cohort_id)
    if forked is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort has no checklist to override")
    override, id_map = forked
    resolved_item_id = id_map.get(item_id, item_id)
    item = (await db.execute(
        select(LmsProgramItem).where(
            LmsProgramItem.id == resolved_item_id,
            LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id,
        )
    )).scalars().first()
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    await _enforce_instructor_item_scope(db, current=current, item_type=item.item_type)
    await db.delete(item)
    await db.commit()


# ── student profile (2026-08-22, Programs/Cohort Missions merge) ────────────
# Instructor mirrors of `routers/lms/admin.py`'s ops-only student endpoints —
# same underlying service calls, gated by cohort membership instead of
# `require_lms_content`.

async def _require_student_access(db: AsyncSession, *, user_id: uuid.UUID, current: User) -> None:
    """404s unless the caller is staff or this student has an active
    registration in one of the instructor's own cohorts — the same
    "don't leak existence" posture `require_cohort_access` already uses,
    just checked against a student instead of a cohort_id directly."""
    allowed = await instructor_cohort_ids(db, user=current)
    if allowed is None:
        return
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    student = await db.get(User, user_id)
    if student is None or student.contact_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    in_scope = await db.scalar(
        select(Registration.id).where(
            Registration.contact_id == student.contact_id, Registration.cohort_id.in_(allowed),
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        ).limit(1)
    )
    if in_scope is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")


@router.get("/students/{user_id}", response_model=StudentProfileOut)
async def student_profile(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _require_student_access(db, user_id=user_id, current=current)
    user = await db.get(User, user_id)
    if user is None or "student" not in user.role_values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    programs = await my_programs(db, user=user)
    return StudentProfileOut(
        id=user.id, full_name=user.full_name, nickname=user.nickname, avatar=user.avatar,
        email=user.email, programs=[StudentProgramOut(**p) for p in programs],
    )


@router.get("/students/{user_id}/enrollments", response_model=list[EnrollmentAdminOut])
async def student_enrollments(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _require_student_access(db, user_id=user_id, current=current)
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    rows = (await db.execute(
        select(Enrollment).where(Enrollment.user_id == user_id).order_by(Enrollment.created_at.desc())
    )).scalars().all()
    out = []
    for e in rows:
        row = await enrollment_admin_out(db, e)
        course = await db.get(Course, e.course_id)
        row.course_title = course.title if course else None
        out.append(row)
    return out


@router.get("/students/{user_id}/design-runs", response_model=StudentDesignRunsOut)
async def student_design_runs_route(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _require_student_access(db, user_id=user_id, current=current)
    user = await db.get(User, user_id)
    if user is None or "student" not in user.role_values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    return await student_design_runs(db, user_id=user_id)


@router.get("/students/{user_id}/quiz-breakdown", response_model=CohortQuizTopicBreakdownOut)
async def student_quiz_breakdown_route(
    user_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Cohort-scoped mirror of the ops-only `admin.py` endpoint of the same
    name — same 404-unless-in-one-of-the-instructor's-cohorts posture as
    every other student endpoint in this file."""
    await _require_student_access(db, user_id=user_id, current=current)
    user = await db.get(User, user_id)
    if user is None or "student" not in user.role_values:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    breakdown = await cohort_quiz_service.get_student_topic_breakdown(db, user_id)
    return CohortQuizTopicBreakdownOut(topic_breakdown=breakdown)


@router.get("/students/{user_id}/courses/{course_id}/progress", response_model=CourseProgressOut)
async def student_course_progress_route(
    user_id: uuid.UUID, course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Per-course module/quiz breakdown (operator ask, 2026-08-22: "review...
    course progress") — `student_course_progress` already existed but was
    only reachable via the session-roster route; this is the direct,
    per-student version the new student-detail page needs."""
    await _require_student_access(db, user_id=user_id, current=current)
    course = await db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    progress = await student_course_progress(db, user_id=user_id, course_id=course_id)
    return CourseProgressOut(
        course_id=course_id, course_title=course.title, completed=progress["completed"],
        modules=[ModuleProgressOut(**m) for m in progress["modules"]],
        quizzes=[QuizProgressOut(**q) for q in progress["quizzes"]],
    )
