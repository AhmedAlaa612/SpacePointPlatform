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
from app.services.lms.enrollment import enrollment_is_active
from app.services.lms.progress import batch_course_completion
from app.services.missions.best_attempt import best_attempt
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES


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
        by_mission: dict[uuid.UUID, list[MissionAttempt]] = {}
        for attempt in attempts:
            by_mission.setdefault(attempt.mission_id, []).append(attempt)
        result[uid] = {mission_id: best_attempt(group) for mission_id, group in by_mission.items()}
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
    # Design v2 (7D-9) — Madar's admin showed every student against the
    # seven design steps at a glance, which is more useful than one
    # pass/fail chip: "stuck on the link budget" is actionable, "in
    # progress" is not. Loaded in one query for the whole grid.
    design_steps = await _design_steps_by_attempt(db, mission_status)
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
                "steps": design_steps.get(attempt.id),
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


# ── all-students progress views (2026-08-12) ────────────────────────────────
#
# The grid above is deliberately cohort-scoped (§ docstring above). The
# operator's actual day-to-day ask turned out to be simpler and different:
# not one combined matrix, but two narrow single-item views — "everyone
# enrolled in this course" and "everyone who's attempted this mission" — each
# optionally narrowed to a cohort, rather than picking a cohort first.


async def course_progress_all(
    db: AsyncSession, *, course_id: uuid.UUID, cohort_id: uuid.UUID | None = None,
) -> dict | None:
    """Every actively-enrolled student in one course, with their completion
    %. `cohort_id` narrows to students with an active registration in that
    cohort (same roster resolution as `_cohort_roster` above) — optional,
    since the operator wants an all-students default with cohort as a
    filter, not a mandatory funnel."""
    course = await db.get(Course, course_id)
    if course is None:
        return None

    stmt = select(Enrollment.user_id).where(Enrollment.course_id == course_id, *enrollment_is_active())
    if cohort_id is not None:
        contact_ids = (await db.execute(
            select(Registration.contact_id).where(
                Registration.cohort_id == cohort_id,
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
        )).scalars().all()
        cohort_user_ids = (await db.execute(
            select(User.id).where(User.contact_id.in_(contact_ids))
        )).scalars().all()
        stmt = stmt.where(Enrollment.user_id.in_(cohort_user_ids))

    user_ids = list((await db.execute(stmt)).scalars().all())
    users = (
        (await db.execute(select(User).where(User.id.in_(user_ids)).order_by(User.full_name))).scalars().all()
        if user_ids else []
    )
    completion = await batch_course_completion(db, user_ids=[u.id for u in users], course_id=course_id)

    return {
        "course_id": course_id,
        "course_title": course.title,
        "rows": [
            {"user_id": u.id, "full_name": u.full_name, "pct": completion.get(u.id, {"pct": 0})["pct"]}
            for u in users
        ],
    }


async def mission_progress_all(db: AsyncSession, *, mission_id: uuid.UUID) -> dict | None:
    """Every student (solo or via a team roster) who has attempted one
    mission, with their best attempt's status/score — the "click a mission,
    see everyone on it" view. Mirrors `_mission_status_by_user`'s solo +
    frozen-team-roster resolution above, but for one mission across every
    cohort rather than one cohort across every mission."""
    mission = await db.get(Mission, mission_id)
    if mission is None:
        return None

    attempts = (
        await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id == mission_id))
    ).scalars().all()

    by_user: dict[uuid.UUID, list[MissionAttempt]] = {}
    for a in attempts:
        if a.user_id is not None:
            by_user.setdefault(a.user_id, []).append(a)

    team_attempt_ids = [a.id for a in attempts if a.mission_team_id is not None]
    if team_attempt_ids:
        attempts_by_id = {a.id: a for a in attempts}
        members = (await db.execute(
            select(MissionAttemptMember).where(MissionAttemptMember.attempt_id.in_(team_attempt_ids))
        )).scalars().all()
        for m in members:
            by_user.setdefault(m.user_id, []).append(attempts_by_id[m.attempt_id])

    user_ids = list(by_user)
    users_by_id = {
        u.id: u for u in (
            (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all() if user_ids else []
        )
    }

    rows = []
    for uid, group in by_user.items():
        user = users_by_id.get(uid)
        if user is None:
            continue
        attempt = best_attempt(group)
        rows.append({
            "user_id": uid, "full_name": user.full_name,
            "status": attempt.status,
            "score": float(attempt.score) if attempt.score is not None else None,
            "attempt_no": attempt.attempt_no,
        })
    rows.sort(key=lambda r: r["full_name"])

    return {"mission_id": mission_id, "mission_title": mission.title, "rows": rows}


async def _design_steps_by_attempt(
    db: AsyncSession, mission_status: dict,
) -> dict[uuid.UUID, dict]:
    """Per-design-attempt step completion, for the grid's mission cells.

    Deliberately cheap and approximate: it reports which steps a student has
    *entered data for*, not whether each one passes. Running the full
    dashboard for every student x every design attempt would mean a
    six-calculator rollup per cell, and the grid is a scanning tool — "no
    link budget yet" is the actionable fact, and the exact margin is one
    click away on the design itself.
    """
    from app.models.missions.design import (
        Design, DesignComponent, DesignCostBudgetEntry, DesignDataBudgetEntry,
        DesignLinkBudgetEntry, DesignMassBudgetEntry, DesignPowerBudgetEntry,
    )

    attempt_ids = [a.id for per_user in mission_status.values() for a in per_user.values()]
    if not attempt_ids:
        return {}

    designs = (await db.execute(
        select(Design).where(Design.attempt_id.in_(attempt_ids))
    )).scalars().all()
    if not designs:
        return {}

    design_ids = [d.id for d in designs]
    components = (await db.execute(
        select(DesignComponent.id, DesignComponent.design_id)
        .where(DesignComponent.design_id.in_(design_ids))
    )).all()
    design_of_component = {cid: did for cid, did in components}
    component_ids = list(design_of_component)

    async def designs_with_rows(model) -> set:
        if not component_ids:
            return set()
        rows = (await db.execute(
            select(model.design_component_id).where(model.design_component_id.in_(component_ids))
        )).scalars().all()
        return {design_of_component[cid] for cid in rows if cid in design_of_component}

    has_data = await designs_with_rows(DesignDataBudgetEntry)
    has_power = await designs_with_rows(DesignPowerBudgetEntry)
    has_mass = await designs_with_rows(DesignMassBudgetEntry)
    has_cost = await designs_with_rows(DesignCostBudgetEntry)
    has_link = {
        d for d in (await db.execute(
            select(DesignLinkBudgetEntry.design_id)
            .where(DesignLinkBudgetEntry.design_id.in_(design_ids), DesignLinkBudgetEntry.is_saved.is_(True))
        )).scalars().all()
    }
    with_components = {design_of_component[cid] for cid in component_ids}

    out: dict[uuid.UUID, dict] = {}
    for d in designs:
        out[d.attempt_id] = {
            "components": d.id in with_components,
            "conops": bool(d.orbit_duration_min),
            "data_budget": d.id in has_data,
            "power_budget": d.id in has_power,
            "energy_budget": bool(d.battery_capacity_wh),
            "link_budget": d.id in has_link,
            "mass_budget": d.id in has_mass,
            "cost_budget": d.id in has_cost,
        }
    return out
