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

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import Course
from app.models.lms.enrollment import Enrollment
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.models.missions.team import MissionTeam
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
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
    straight from `MissionAttempt.user_id`, scoped to this cohort's own
    `cohort_id` (2026-08-17) — before that column existed this queried
    every attempt by anyone currently on the roster, which was wrong for a
    student who'd since changed cohorts; a `NULL` cohort_id (self-service,
    or a pre-migration row) still counts, since it was never attributed to
    a *different* cohort either. Team attempts come via the frozen
    `MissionAttemptMember` roster for teams assigned to this cohort (the
    live `MissionTeamMember` roster can drift after the fact — the
    per-attempt freeze is what actually earned the grade, same reasoning
    the team-scoring code already uses)."""
    if not user_ids:
        return {}

    attempts_by_user: dict[uuid.UUID, list[MissionAttempt]] = {}

    solo_attempts = (await db.execute(
        select(MissionAttempt).where(
            MissionAttempt.user_id.in_(user_ids),
            or_(MissionAttempt.cohort_id == cohort_id, MissionAttempt.cohort_id.is_(None)),
        )
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

    # Who these students are, not just their ids. Madar's equivalent table
    # carried school, grade and the invitation code beside every row, and
    # that context is most of what makes the table usable at a camp: "the
    # ALDAR2 cohort stalls at the link budget" is a finding, "seven of
    # nineteen names stalled" is not.
    contact_ids = [u.contact_id for u in users_by_id.values() if u.contact_id]
    contacts_by_id = {
        c.id: c for c in (
            (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            if contact_ids else []
        )
    }
    org_ids = {c.organization_id for c in contacts_by_id.values() if c.organization_id}
    orgs_by_id = {
        o.id: o for o in (
            (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
            if org_ids else []
        )
    }

    # Per-step completion for every attempt on this mission, so the row can
    # show where each student actually is rather than only that they haven't
    # finished. Empty for mission kinds with no step model.
    steps_by_attempt = await design_steps_for_attempts(db, [a.id for a in attempts])

    rows = []
    for uid, group in by_user.items():
        user = users_by_id.get(uid)
        if user is None:
            continue
        attempt = best_attempt(group)
        contact = contacts_by_id.get(user.contact_id) if user.contact_id else None
        org = orgs_by_id.get(contact.organization_id) if contact and contact.organization_id else None
        # The furthest-along attempt's steps, which is not always the
        # best-scoring one — for a student still working, "how far did they
        # ever get" is the question the table is being asked.
        step_sets = [steps_by_attempt[a.id] for a in group if a.id in steps_by_attempt]
        steps = max(
            step_sets,
            key=lambda st: sum(1 for key, _ in DESIGN_STEP_LABELS if st.get(key)),
            default=None,
        )
        rows.append({
            "user_id": uid, "full_name": user.full_name,
            "status": attempt.status,
            "score": float(attempt.score) if attempt.score is not None else None,
            "attempt_no": attempt.attempt_no,
            "school_name": org.name_latin if org else None,
            "grade": contact.grade if contact else None,
            "invitation_code_used": user.invitation_code_used,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "steps": steps,
        })
    rows.sort(key=lambda r: r["full_name"])

    return {
        "mission_id": mission_id,
        "mission_title": mission.title,
        "step_labels": [{"key": key, "label": label} for key, label in DESIGN_STEP_LABELS],
        "has_steps": any(r["steps"] for r in rows),
        "rows": rows,
    }


async def courses_overview(db: AsyncSession) -> list[dict]:
    """Every course with how many students are enrolled and how many have
    finished it — the landing list for the progress page's Courses tab, so
    picking a course to look at doesn't require already knowing its name."""
    courses = (await db.execute(select(Course).order_by(Course.title))).scalars().all()
    if not courses:
        return []

    enrolled_by_course: dict[uuid.UUID, list[uuid.UUID]] = {}
    for user_id, course_id in (await db.execute(
        select(Enrollment.user_id, Enrollment.course_id).where(
            Enrollment.course_id.in_([c.id for c in courses]), *enrollment_is_active(),
        )
    )).all():
        enrolled_by_course.setdefault(course_id, []).append(user_id)

    rows = []
    for course in courses:
        user_ids = enrolled_by_course.get(course.id, [])
        completion = (
            await batch_course_completion(db, user_ids=user_ids, course_id=course.id) if user_ids else {}
        )
        completed = sum(1 for c in completion.values() if c["pct"] >= 100)
        rows.append({
            "course_id": course.id,
            "title": course.title,
            "enrolled_count": len(user_ids),
            "completed_count": completed,
            "completion_pct": round(completed / len(user_ids) * 100) if user_ids else 0,
        })
    return rows


async def missions_overview(db: AsyncSession) -> list[dict]:
    """Every mission with how many students have attempted it and how many
    passed — the landing list for the progress page's Missions tab. Attempted
    counts a student once regardless of retries, same as `mission_progress_all`."""
    missions = (await db.execute(select(Mission).order_by(Mission.title))).scalars().all()
    if not missions:
        return []
    mission_ids = [m.id for m in missions]

    attempts = (
        await db.execute(select(MissionAttempt).where(MissionAttempt.mission_id.in_(mission_ids)))
    ).scalars().all()

    team_attempt_ids = [a.id for a in attempts if a.mission_team_id is not None]
    members_by_attempt: dict[uuid.UUID, list[uuid.UUID]] = {}
    if team_attempt_ids:
        for attempt_id, user_id in (await db.execute(
            select(MissionAttemptMember.attempt_id, MissionAttemptMember.user_id)
            .where(MissionAttemptMember.attempt_id.in_(team_attempt_ids))
        )).all():
            members_by_attempt.setdefault(attempt_id, []).append(user_id)

    # mission_id -> user_id -> every attempt they have on it (solo or via a
    # team roster), so passed/attempted counts a student once per mission.
    per_mission: dict[uuid.UUID, dict[uuid.UUID, list[MissionAttempt]]] = {}
    for a in attempts:
        user_ids = [a.user_id] if a.user_id is not None else members_by_attempt.get(a.id, [])
        bucket = per_mission.setdefault(a.mission_id, {})
        for uid in user_ids:
            bucket.setdefault(uid, []).append(a)

    rows = []
    for mission in missions:
        by_student = per_mission.get(mission.id, {})
        attempted = len(by_student)
        passed = sum(1 for group in by_student.values() if best_attempt(group).status == "passed")
        rows.append({
            "mission_id": mission.id,
            "title": mission.title,
            "kind": mission.kind,
            "attempted_count": attempted,
            "passed_count": passed,
            "completion_pct": round(passed / attempted * 100) if attempted else 0,
        })
    return rows


# The design mission's nine steps, in the order a student walks them —
# matching `CompletionMap`'s own list in DesignMissionPage.tsx exactly (2026-08-14:
# they'd drifted — this used to be 8 keys with no "downlink" at all, so a
# design that the workbench itself called 9/9 closed could show 7/8 here).
# Named here rather than in each caller so the profile, the cohort grid and
# the per-mission table can never disagree about what the phases are or what
# they're called.
DESIGN_STEP_LABELS: list[tuple[str, str]] = [
    ("components", "Components"),
    ("conops", "CONOPS"),
    ("data_budget", "Data"),
    ("power_budget", "Power"),
    ("energy_budget", "Energy"),
    ("link_budget", "Link"),
    ("downlink", "Downlink"),
    ("mass_budget", "Mass"),
    ("cost_budget", "Cost"),
]

# The real math prerequisite graph for cohort-scoped step *selection*
# (2026-08-17) — deliberately narrower than `DesignMissionPage.tsx`'s
# `DESIGN_TABS.needs` UI hints, which explain *order* without being a real
# dependency check (D2). Verified directly against `calculators.py`:
# `calc_power_budget`/`calc_data_budget`'s `is_valid` never reads CONOPS at
# all (power ignores `modes` for validity entirely; data's validity is a
# storage-capacity check that a defaulted/empty CONOPS trivially satisfies)
# — confirmed by the real-world TDRA Summer Camp cohort, which selects
# Power + Mass with no CONOPS. `downlink` is excluded here since it isn't a
# directly-selectable step; see `DOWNLINK_STEP_DEPS` below instead.
DESIGN_STEP_PREREQS: dict[str, tuple[str, ...]] = {
    "components": (),
    "conops": (),
    "data_budget": ("components",),
    "power_budget": ("components",),
    "energy_budget": ("power_budget",),
    "mass_budget": ("components",),
    "cost_budget": ("components",),
    "link_budget": (),
}

SELECTABLE_STEP_KEYS: frozenset[str] = frozenset(DESIGN_STEP_PREREQS)

# The one place CONOPS is a genuine hard dependency: downlink's ground-
# station contact minutes come from real (non-default) mode durations, so
# it only counts toward a cohort's completion check when all three of its
# real inputs are in the selected subset.
DOWNLINK_STEP_DEPS: frozenset[str] = frozenset({"data_budget", "link_budget", "conops"})


async def _design_steps_by_attempt(
    db: AsyncSession, mission_status: dict,
) -> dict[uuid.UUID, dict]:
    """Per-design-attempt step completion, for the grid's mission cells."""
    attempt_ids = [a.id for per_user in mission_status.values() for a in per_user.values()]
    return await design_steps_for_attempts(db, attempt_ids)


async def design_steps_for_attempts(
    db: AsyncSession, attempt_ids: list[uuid.UUID],
) -> dict[uuid.UUID, dict]:
    """Per-step completion, keyed by attempt id, for the profile card, the
    cohort grid and the per-mission table.

    Runs the actual `compute_dashboard()` per attempt — the same calculators
    the design workbench itself uses — rather than a "does a row exist"
    presence check. The two used to disagree in both directions: a step with
    a saved-but-out-of-range value (e.g. a power budget with negative margin)
    counted as done under the old heuristic despite the workbench calling it
    open, and conversely nothing here distinguished "entered" from "passes",
    so every admin view under-reported a design's real progress relative to
    what the student actually sees on their own screen (2026-08-14).
    """
    from app.models.missions.design import Design
    from app.models.missions.mission import MissionVariant
    from app.services.missions.design.service import compute_dashboard

    if not attempt_ids:
        return {}

    designs = (await db.execute(
        select(Design).where(Design.attempt_id.in_(attempt_ids))
    )).scalars().all()
    if not designs:
        return {}

    attempts_by_id = {
        a.id: a for a in (await db.execute(
            select(MissionAttempt).where(MissionAttempt.id.in_([d.attempt_id for d in designs]))
        )).scalars().all()
    }
    variant_ids = {a.variant_id for a in attempts_by_id.values()}
    configs_by_variant = {
        v.id: (v.config or {}) for v in (
            (await db.execute(
                select(MissionVariant).where(MissionVariant.id.in_(variant_ids))
            )).scalars().all() if variant_ids else []
        )
    }

    out: dict[uuid.UUID, dict] = {}
    for design in designs:
        attempt = attempts_by_id.get(design.attempt_id)
        if attempt is None:
            continue
        variant_config = configs_by_variant.get(attempt.variant_id, {})
        dashboard = await compute_dashboard(db, design=design, variant_config=variant_config, attempt=attempt)
        out[design.attempt_id] = {key: bool(step["is_valid"]) for key, step in dashboard["steps"].items()}
    return out


async def student_design_runs(db: AsyncSession, *, user_id: uuid.UUID) -> dict:
    """Every CubeSat design run this student has — plural, since 2026-08-15 a
    student can run the design mission multiple times concurrently, each a
    separately-named `Design`. For the student-detail page: unlike
    `mission_progress_all` (one row per student, furthest attempt only, for
    scanning a whole cohort), this is one row per *run*, for looking at one
    student closely.
    """
    from app.models.missions.design import Design
    from app.models.missions.mission import MissionVariant

    attempts = (await db.execute(
        select(MissionAttempt)
        .join(Mission, Mission.id == MissionAttempt.mission_id)
        .where(Mission.kind == "design", MissionAttempt.user_id == user_id)
        .order_by(MissionAttempt.started_at.desc())
    )).scalars().all()

    if not attempts:
        return {"step_labels": [{"key": key, "label": label} for key, label in DESIGN_STEP_LABELS], "runs": []}

    variant_by_id = {
        v.id: v for v in (await db.execute(
            select(MissionVariant).where(MissionVariant.id.in_({a.variant_id for a in attempts}))
        )).scalars().all()
    }
    design_by_attempt = {
        d.attempt_id: d for d in (await db.execute(
            select(Design).where(Design.attempt_id.in_([a.id for a in attempts]))
        )).scalars().all()
    }
    steps_by_attempt = await design_steps_for_attempts(db, [a.id for a in attempts])

    runs = []
    for a in attempts:
        design = design_by_attempt.get(a.id)
        variant = variant_by_id.get(a.variant_id)
        runs.append({
            "attempt_id": a.id,
            "design_name": design.design_name if design else "My CubeSat",
            "design_objective": design.design_objective if design else None,
            "variant_label": variant.label if variant else "",
            "status": a.status,
            "attempt_no": a.attempt_no,
            "started_at": a.started_at.isoformat() if a.started_at else None,
            "steps": steps_by_attempt.get(a.id),
        })

    return {
        "step_labels": [{"key": key, "label": label} for key, label in DESIGN_STEP_LABELS],
        "runs": runs,
    }
