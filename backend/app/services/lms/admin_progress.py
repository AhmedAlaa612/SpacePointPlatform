"""Admin progress grid (7B-1, Missions Phase 2B) — every student in one
cohort x every course in its curriculum x every mission any of them has
attempted, completion at a glance. Scoped to one cohort at a time, matching
every other progress-view precedent in this codebase (`session_lms_progress`
is per-session, `my_programs` is per-cohort-registration) — there is no
platform-wide matrix here.

Course columns come from `resolve_cohort_curriculum` (the cohort's actual
curriculum, override-aware) and completion is computed with
`batch_course_completion` — one batched call per course, not one call per
student per course (the N+1 shape already fixed once for
`session_lms_progress`, B11).

Mission columns are NOT the full mission catalog — missions have no cohort
curriculum table of their own — they're derived from whichever missions the
roster has actually attempted, solo or as a member of a team assigned to
this cohort. A student can have multiple attempts at one mission (retries);
the cell shows the passed attempt if one exists, else the most recent.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.models.missions.team import MissionTeam
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.user import User
from app.services.lms.curriculum import resolve_cohort_curriculum
from app.services.lms.progress import batch_course_completion
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

_STATUS_RANK = {"abandoned": 0, "failed": 1, "in_progress": 2, "submitted": 3, "passed": 4}


async def _cohort_roster(db: AsyncSession, cohort_id: uuid.UUID) -> list[User]:
    contact_ids = (await db.execute(
        select(Registration.contact_id).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()
    if not contact_ids:
        return []
    return list((await db.execute(
        select(User).where(User.contact_id.in_(contact_ids)).order_by(User.full_name)
    )).scalars().all())


async def _mission_status_by_user(
    db: AsyncSession, *, cohort_id: uuid.UUID, user_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict[uuid.UUID, MissionAttempt]]:
    """user_id -> mission_id -> the one attempt to show. Solo attempts come
    straight from `MissionAttempt.user_id`; team attempts come via the
    frozen `MissionAttemptMember` roster for teams assigned to this cohort
    (the live `MissionTeamMember` roster can drift after the fact — the
    per-attempt freeze is what actually earned the grade, same reasoning
    the team-scoring code already uses)."""
    if not user_ids:
        return {}

    attempts_by_user: dict[uuid.UUID, list[MissionAttempt]] = {}

    solo_attempts = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.user_id.in_(user_ids))
    )).scalars().all()
    for a in solo_attempts:
        attempts_by_user.setdefault(a.user_id, []).append(a)

    team_ids = (await db.execute(
        select(MissionTeam.id).where(MissionTeam.cohort_id == cohort_id)
    )).scalars().all()
    if team_ids:
        team_attempts = (await db.execute(
            select(MissionAttempt).where(MissionAttempt.mission_team_id.in_(team_ids))
        )).scalars().all()
        if team_attempts:
            attempts_by_id = {a.id: a for a in team_attempts}
            members = (await db.execute(
                select(MissionAttemptMember).where(
                    MissionAttemptMember.attempt_id.in_(list(attempts_by_id)),
                    MissionAttemptMember.user_id.in_(user_ids),
                )
            )).scalars().all()
            for m in members:
                attempts_by_user.setdefault(m.user_id, []).append(attempts_by_id[m.attempt_id])

    result: dict[uuid.UUID, dict[uuid.UUID, MissionAttempt]] = {}
    for uid, attempts in attempts_by_user.items():
        best_by_mission: dict[uuid.UUID, MissionAttempt] = {}
        for attempt in attempts:
            current = best_by_mission.get(attempt.mission_id)
            if current is None or (_STATUS_RANK[attempt.status], attempt.attempt_no) > (
                _STATUS_RANK[current.status], current.attempt_no
            ):
                best_by_mission[attempt.mission_id] = attempt
        result[uid] = best_by_mission
    return result


async def cohort_progress_grid(db: AsyncSession, *, cohort_id: uuid.UUID) -> dict | None:
    """Returns None if the cohort doesn't exist — the router turns that into
    a 404, mirroring every other admin cohort lookup in this codebase."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None

    roster = await _cohort_roster(db, cohort_id)
    user_ids = [u.id for u in roster]

    course_ids = await resolve_cohort_curriculum(db, cohort_id)
    courses = (
        (await db.execute(select(Course).where(Course.id.in_(course_ids)))).scalars().all()
        if course_ids else []
    )
    courses_by_id = {c.id: c for c in courses}

    completion_by_course: dict[uuid.UUID, dict[uuid.UUID, dict]] = {}
    for course_id in course_ids:
        if course_id in courses_by_id:
            completion_by_course[course_id] = await batch_course_completion(
                db, user_ids=user_ids, course_id=course_id,
            )

    enrolled_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    if user_ids and courses_by_id:
        enrolled_pairs = set((await db.execute(
            select(Enrollment.user_id, Enrollment.course_id).where(
                Enrollment.user_id.in_(user_ids), Enrollment.course_id.in_(list(courses_by_id)),
            )
        )).all())

    mission_status = await _mission_status_by_user(db, cohort_id=cohort_id, user_ids=user_ids)
    mission_ids = sorted(
        {mid for per_user in mission_status.values() for mid in per_user}, key=str,
    )
    missions = (
        (await db.execute(select(Mission).where(Mission.id.in_(mission_ids)))).scalars().all()
        if mission_ids else []
    )
    missions_by_id = {m.id: m for m in missions}

    rows = []
    for user in roster:
        course_cells = {}
        for course_id in course_ids:
            if course_id not in courses_by_id:
                continue
            completion = completion_by_course.get(course_id, {}).get(user.id, {"pct": 0})
            course_cells[str(course_id)] = {
                "enrolled": (user.id, course_id) in enrolled_pairs,
                "pct": completion["pct"],
            }
        mission_cells = {}
        for mission_id, attempt in mission_status.get(user.id, {}).items():
            if mission_id not in missions_by_id:
                continue
            mission_cells[str(mission_id)] = {
                "status": attempt.status,
                "score": float(attempt.score) if attempt.score is not None else None,
                "attempt_no": attempt.attempt_no,
            }
        rows.append({
            "user_id": user.id, "full_name": user.full_name,
            "courses": course_cells, "missions": mission_cells,
        })

    return {
        "cohort_id": cohort_id,
        "courses": [
            {"course_id": cid, "title": courses_by_id[cid].title} for cid in course_ids if cid in courses_by_id
        ],
        "missions": [
            {"mission_id": mid, "title": missions_by_id[mid].title} for mid in mission_ids if mid in missions_by_id
        ],
        "rows": rows,
    }
