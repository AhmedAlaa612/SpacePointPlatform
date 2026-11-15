"""Cohort-level team analytics (2026-09-16) — the read-only "how is this
competition actually going" view behind the Judging page's Analysis tab.

Deliberately team-first. Per-*student* checklist progress already has a
home (`cohort_program_roster` -> `ProgressPanel`, one expandable row per
student); what nothing surfaced before this was the other axis: how many
teams there are, how far each one has got, and which specific deliverable
the cohort as a whole is stuck on. Same cohort scope every other progress
view in this codebase uses (`cohort_progress_grid` is per-cohort,
`my_programs` is per-cohort-registration) — there is no platform-wide
competition dashboard here.

Everything is computed set-based, in a fixed number of queries regardless
of roster size: the N+1 shape `batch_course_completion` already exists to
avoid (B11, then the 7B-1 progress grid) is exactly what a "every team x
every checklist item" screen walks into if each team is resolved on its
own. One pass per table, joined in Python.

**Where a "done" comes from**, per item type — this is the one subtle part:

- `scope="team"` items (`submission`/`external_link`/`manual`/`team_setup`/`checkpoint`)
  — `lms_program_team_item_progress.status` is the literal truth. Nothing
  auto-tracks these; a self-check, a submission, a checkpoint lock, or an
  ops confirmation is what writes them. (`mission_run` team items live in
  the same table but are charted separately — see below.)
- `scope="individual"` items — the stored `lms_program_item_progress.status`,
  EXCEPT the two auto-tracked types that can be batch-reconciled honestly:
  `course` (via `batch_course_completion`, same rule `_course_item_done`
  applies — every mandatory module item done) and `quiz` (a submitted
  `CohortQuizAttempt`, score irrelevant, same rule `_cohort_quiz_item_done`
  applies). Stored status for those two can lag until someone opens the
  checklist; reconciling here means the chart never understates them.
- `mission_run` items (either scope) are **excluded from the item-rate
  chart entirely** and reported separately in `missions` instead. Their
  real completion is per-design-step, resolved through a Design dashboard
  that costs a query cascade per attempt (`refresh_item_progress` ->
  `_design_dashboard_for_attempt`) — a bar labelled "Build the CubeSat"
  sitting at a stale stored status would be worse than no bar. The
  mission block reports the shared `MissionAttempt.status` instead, which
  IS truth and IS batchable.

`awaiting_confirmation` counts as **not done** everywhere here, matching
what the checklist itself shows the student: the item isn't finished until
ops confirms it. It's reported as its own bucket so ops can see the
difference between "nobody submitted" and "everyone submitted and I
haven't confirmed".
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.arcade_game import ArcadeGameAttempt
from app.models.lms.cohort_quiz import CohortQuizAttempt
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.missions.design import Design
from app.models.missions.mission import Mission, MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.lms.program import effective_cohort_program_items
from app.services.lms.progress import batch_course_completion
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

# How far back the activity sparkline looks. 30 days covers a competition
# stage end to end (Ru'ya's qualifier ran ~4 weeks) without turning into a
# year-long axis nobody reads.
ACTIVITY_WINDOW_DAYS = 30

# A team with no team-progress row touched in this long, and not already
# finished, is what the Analysis tab flags as stalled. Two weeks, not one:
# a competition checklist is deliberately paced over weeks, so a quiet
# seven days is normal and a quiet fourteen is not.
STALLED_AFTER_DAYS = 14


def _pct(done: int, total: int) -> int:
    return round(100 * done / total) if total else 0


async def _team_rosters(
    db: AsyncSession, *, team_ids: list[uuid.UUID],
) -> tuple[dict[uuid.UUID, list[uuid.UUID]], dict[uuid.UUID, User]]:
    """team_id -> member user_ids, plus every one of those users by id —
    two queries for the whole cohort, not one pair per team."""
    if not team_ids:
        return {}, {}
    rows = (await db.execute(
        select(TeamMember.team_id, TeamMember.user_id).where(TeamMember.team_id.in_(team_ids))
    )).all()
    members_by_team: dict[uuid.UUID, list[uuid.UUID]] = {tid: [] for tid in team_ids}
    for team_id, user_id in rows:
        members_by_team[team_id].append(user_id)

    user_ids = {uid for _, uid in rows}
    users = (
        (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        if user_ids else []
    )
    return members_by_team, {u.id: u for u in users}


async def _cohort_roster_user_ids(
    db: AsyncSession, *, cohort_id: uuid.UUID, mode: str = "participant",
) -> set[uuid.UUID]:
    """Every student with an active Registration in this cohort, as user
    ids — resolved via contact_id first, then email fallback, and
    partitioned by assignment mode (participant vs observer)."""
    if mode == "observer":
        return set((await db.execute(
            select(LmsProgramAssignment.user_id).where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.mode == "observer",
            )
        )).scalars().all())

    contact_rows = (await db.execute(
        select(Contact.id, Contact.email)
        .join(Registration, Registration.contact_id == Contact.id)
        .where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).all()
    if not contact_rows:
        return set()

    contact_ids = [cid for cid, _ in contact_rows]
    user_rows = (await db.execute(
        select(User.id, User.contact_id).where(User.contact_id.in_(contact_ids))
    )).all()
    matched_cids = {cid for _, cid in user_rows if cid is not None}
    uid_set = {uid for uid, _ in user_rows}

    fallback_emails = [
        email.strip().lower()
        for cid, email in contact_rows
        if cid not in matched_cids and email and email.strip()
    ]
    if fallback_emails:
        email_uids = (await db.execute(
            select(User.id).where(func.lower(User.email).in_(fallback_emails))
        )).scalars().all()
        uid_set.update(email_uids)

    if mode == "participant" and uid_set:
        observer_uids = set((await db.execute(
            select(LmsProgramAssignment.user_id).where(
                LmsProgramAssignment.cohort_id == cohort_id,
                LmsProgramAssignment.mode == "observer",
            )
        )).scalars().all())
        uid_set -= observer_uids

    return uid_set


async def _individual_done_user_ids(
    db: AsyncSession, *, items: list[LmsProgramItem], cohort_id: uuid.UUID, mode: str = "participant",
) -> tuple[dict[uuid.UUID, set[uuid.UUID]], dict[uuid.UUID, set[uuid.UUID]], set[uuid.UUID]]:
    """For every individual-scoped, non-mission_run item: which users have
    it done, and which are awaiting confirmation. Returns
    `(done_by_item, awaiting_by_item, assigned_user_ids)`.

    `assigned_user_ids` is the honest denominator — students who actually
    hold this cohort's checklist assignment, not everyone registered. A
    student registered but never assigned the LMS program has no progress
    row for any item, and counting them against every bar would read as
    the cohort failing rather than as an assignment gap (which the KPI
    row reports separately).
    """
    assign_query = select(LmsProgramAssignment.id, LmsProgramAssignment.user_id).where(
        LmsProgramAssignment.cohort_id == cohort_id
    )
    if mode == "participant":
        assign_query = assign_query.where(LmsProgramAssignment.mode != "observer")
    elif mode == "observer":
        assign_query = assign_query.where(LmsProgramAssignment.mode == "observer")
    assignments = (await db.execute(assign_query)).all()
    user_by_assignment = {aid: uid for aid, uid in assignments}
    assigned_user_ids = set(user_by_assignment.values())

    assignment_by_user = {uid: aid for aid, uid in assignments}
    done_by_item: dict[uuid.UUID, set[uuid.UUID]] = {i.id: set() for i in items}
    awaiting_by_item: dict[uuid.UUID, set[uuid.UUID]] = {i.id: set() for i in items}
    if not items or not user_by_assignment:
        return done_by_item, awaiting_by_item, assigned_user_ids, assignment_by_user

    rows = (await db.execute(
        select(LmsProgramItemProgress.item_id, LmsProgramItemProgress.assignment_id, LmsProgramItemProgress.status)
        .where(
            LmsProgramItemProgress.item_id.in_([i.id for i in items]),
            LmsProgramItemProgress.assignment_id.in_(list(user_by_assignment)),
        )
    )).all()
    for item_id, assignment_id, status in rows:
        user_id = user_by_assignment.get(assignment_id)
        if user_id is None:
            continue
        if status == "done":
            done_by_item[item_id].add(user_id)
        elif status == "awaiting_confirmation":
            awaiting_by_item[item_id].add(user_id)

    # Reconcile the two auto-tracked types whose real state is batchable —
    # see the module docstring on why mission_run isn't one of them.
    user_ids = sorted(assigned_user_ids, key=str)
    course_items = [i for i in items if i.item_type == "course" and i.course_id]
    completion_cache: dict[uuid.UUID, dict[uuid.UUID, dict]] = {}
    for item in course_items:
        if item.course_id not in completion_cache:
            completion_cache[item.course_id] = await batch_course_completion(
                db, user_ids=user_ids, course_id=item.course_id,
            )
        for user_id, completion in completion_cache[item.course_id].items():
            if completion["modules_total"] > 0 and completion["modules_done"] == completion["modules_total"]:
                done_by_item[item.id].add(user_id)
                awaiting_by_item[item.id].discard(user_id)

    quiz_item_ids = [i.id for i in items if i.item_type == "quiz"]
    if quiz_item_ids:
        quiz_rows = (await db.execute(
            select(CohortQuizAttempt.program_item_id, CohortQuizAttempt.user_id).where(
                CohortQuizAttempt.program_item_id.in_(quiz_item_ids),
                CohortQuizAttempt.status == "submitted",
            )
        )).all()
        for item_id, user_id in quiz_rows:
            if user_id in assigned_user_ids:
                done_by_item[item_id].add(user_id)
                awaiting_by_item[item_id].discard(user_id)

    arcade_items = [i for i in items if i.item_type == "arcade_game" and getattr(i, "arcade_game_id", None)]
    if arcade_items and assigned_user_ids:
        game_ids = list({i.arcade_game_id for i in arcade_items})
        passed_rows = (await db.execute(
            select(ArcadeGameAttempt.user_id, ArcadeGameAttempt.game_id, ArcadeGameAttempt.mode).where(
                ArcadeGameAttempt.game_id.in_(game_ids),
                ArcadeGameAttempt.user_id.in_(list(assigned_user_ids)),
                ArcadeGameAttempt.passed.is_(True),
            )
        )).all()
        passed_pairs = {(uid, gid, gmode) for uid, gid, gmode in passed_rows}
        passed_any_mode = {(uid, gid) for uid, gid, _ in passed_rows}
        for item in arcade_items:
            req_mode = getattr(item, "arcade_game_mode", None)
            for uid in assigned_user_ids:
                if (req_mode and (uid, item.arcade_game_id, req_mode) in passed_pairs) or (
                    not req_mode and (uid, item.arcade_game_id) in passed_any_mode
                ):
                    done_by_item[item.id].add(uid)
                    awaiting_by_item[item.id].discard(uid)

    return done_by_item, awaiting_by_item, assigned_user_ids, assignment_by_user


def _mission_attempt_lookup(
    items: list[LmsProgramItem], team_progress: list[LmsProgramTeamItemProgress],
) -> tuple[dict[uuid.UUID, uuid.UUID], dict[uuid.UUID, set[uuid.UUID]], set[uuid.UUID]]:
    """item_id -> mission_id, mission_id -> set of attempt ids sourced from
    `team_progress` (already fetched for the whole cohort, includes
    mission_run item rows — see cohort_team_analytics's progress_item_ids
    comment), and the set of team-scoped mission ids. Individual-scoped
    attempt ids aren't included here — `_mission_blocks` queries those
    itself, since only the cohort-wide aggregate needs them."""
    mission_items = [i for i in items if i.item_type == "mission_run" and i.mission_id]
    team_scoped_mission_ids = {i.mission_id for i in mission_items if i.scope == "team"}
    item_mission = {i.id: i.mission_id for i in mission_items}

    attempt_ids_by_mission: dict[uuid.UUID, set[uuid.UUID]] = {}
    for row in team_progress:
        mission_id = item_mission.get(row.item_id)
        if mission_id is not None and row.mission_attempt_id is not None:
            attempt_ids_by_mission.setdefault(mission_id, set()).add(row.mission_attempt_id)

    return item_mission, attempt_ids_by_mission, team_scoped_mission_ids


async def _mission_blocks(
    db: AsyncSession, *, items: list[LmsProgramItem], team_progress: list[LmsProgramTeamItemProgress],
    team_count: int, assigned_user_count: int, assigned_assignment_ids: set[uuid.UUID] | None = None,
) -> tuple[list[dict], dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """One row per (mission_id, scope) mission_run — team-scoped and
    individual-scoped runs are kept strictly separate even if both reference
    the same Mission. Team-scoped runs read `team_progress`; individual-scoped
    runs read `LmsProgramItemProgress` filtered to `assigned_assignment_ids`."""
    mission_items = [i for i in items if i.item_type == "mission_run" and i.mission_id]
    if not mission_items:
        return [], {}, {}

    item_scope_mission: dict[uuid.UUID, tuple[uuid.UUID, str]] = {
        i.id: (i.mission_id, "team" if i.scope == "team" else "individual")
        for i in mission_items
    }
    attempt_ids_by_scope_mission: dict[tuple[uuid.UUID, str], set[uuid.UUID]] = {}

    for row in team_progress:
        key = item_scope_mission.get(row.item_id)
        if key is not None and key[1] == "team" and row.mission_attempt_id is not None:
            attempt_ids_by_scope_mission.setdefault(key, set()).add(row.mission_attempt_id)

    individual_item_ids = [i.id for i in mission_items if i.scope != "team"]
    if individual_item_ids and (assigned_assignment_ids is None or len(assigned_assignment_ids) > 0):
        stmt = select(LmsProgramItemProgress.item_id, LmsProgramItemProgress.mission_attempt_id).where(
            LmsProgramItemProgress.item_id.in_(individual_item_ids),
            LmsProgramItemProgress.mission_attempt_id.isnot(None),
        )
        if assigned_assignment_ids is not None:
            stmt = stmt.where(LmsProgramItemProgress.assignment_id.in_(assigned_assignment_ids))
        rows = (await db.execute(stmt)).all()
        for item_id, attempt_id in rows:
            key = item_scope_mission.get(item_id)
            if key is not None and key[1] == "individual":
                attempt_ids_by_scope_mission.setdefault(key, set()).add(attempt_id)

    all_attempt_ids = {aid for ids in attempt_ids_by_scope_mission.values() for aid in ids}
    attempts = (
        (await db.execute(select(MissionAttempt).where(MissionAttempt.id.in_(all_attempt_ids)))).scalars().all()
        if all_attempt_ids else []
    )
    attempt_status = {a.id: a.status for a in attempts}

    designs = (
        (await db.execute(select(Design).where(Design.attempt_id.in_(all_attempt_ids)))).scalars().all()
        if all_attempt_ids else []
    )
    design_by_attempt = {d.attempt_id: d for d in designs}

    mission_ids = sorted({i.mission_id for i in mission_items}, key=str)
    missions = (await db.execute(select(Mission).where(Mission.id.in_(mission_ids)))).scalars().all()
    title_by_id = {m.id: m.title for m in missions}

    MADAR_STEP_LABELS = [
        ("setup", "Setup"),
        ("orbit", "Orbit"),
        ("components", "Components"),
        ("power", "Power"),
        ("thermal", "Thermal"),
        ("comms", "Comms"),
        ("mass", "Mass"),
        ("simulation", "Simulation"),
        ("downlink", "Downlink"),
    ]

    scope_mission_keys = sorted(
        {(i.mission_id, "team" if i.scope == "team" else "individual") for i in mission_items},
        key=lambda k: (k[1], str(k[0])),
    )

    out = []
    for mission_id, scope_str in scope_mission_keys:
        is_team = scope_str == "team"
        total = team_count if is_team else assigned_user_count
        m_attempt_ids = attempt_ids_by_scope_mission.get((mission_id, scope_str), set())
        statuses = [attempt_status.get(aid) for aid in m_attempt_ids]
        passed = sum(1 for s in statuses if s == "passed")
        started = sum(1 for s in statuses if s is not None and s != "passed")

        m_designs = [design_by_attempt[aid] for aid in m_attempt_ids if aid in design_by_attempt]
        step_funnel = []
        if m_designs:
            prev_count: int | None = None
            for step_key, label in MADAR_STEP_LABELS:
                confirmed_count = sum(1 for d in m_designs if step_key in (d.confirmed_steps or []))
                pct_val = _pct(confirmed_count, total)
                dropoff = (
                    max(0, round(100 * (prev_count - confirmed_count) / prev_count))
                    if prev_count and prev_count > 0
                    else 0
                )
                prev_count = confirmed_count
                step_funnel.append({
                    "step_key": step_key,
                    "label": label,
                    "confirmed_count": confirmed_count,
                    "pct": pct_val,
                    "dropoff_from_prev_pct": dropoff,
                })

        out.append({
            "mission_id": mission_id,
            "title": title_by_id.get(mission_id, "Mission"),
            "scope": scope_str,
            "total": total,
            "passed": passed,
            "in_progress": started,
            "not_started": max(total - passed - started, 0),
            "step_funnel": step_funnel,
        })
    return out, attempt_status, title_by_id


def _team_mission_runs(
    *, items: list[LmsProgramItem], progress_by_team_item: dict[tuple[uuid.UUID, uuid.UUID], LmsProgramTeamItemProgress],
    team_ids: list[uuid.UUID],
    attempt_status: dict[uuid.UUID, str], title_by_id: dict[uuid.UUID, str],
) -> dict[uuid.UUID, list[dict]]:
    """Per-team breakdown of the same team-scoped mission runs
    `_mission_blocks` already aggregates cohort-wide — costs no new
    queries, since `progress_by_team_item` already carries every
    team-scoped item's row (mission_run included) and `attempt_status`/
    `title_by_id` are handed down from `_mission_blocks`.

    Grouped by mission_id, same as `_mission_blocks`/`team_mission_run_items`
    — several checklist items can split one run into steps via
    `mission_step_key` and all share one MissionAttempt. Returns `{}`
    outright when the cohort's checklist has no team-scoped mission_run
    items at all (most cohorts today); once it has even one, every team
    gets an entry, with a "not_started"/no-attempt placeholder row for any
    mission it hasn't been assigned yet — never a team selectively missing
    from the dict."""
    team_scoped_mission_items = [
        i for i in items if i.item_type == "mission_run" and i.scope == "team" and i.mission_id
    ]
    if not team_scoped_mission_items:
        return {}

    # Preserve first-seen order, same as _mission_blocks's grouping.
    mission_ids: list[uuid.UUID] = []
    items_by_mission: dict[uuid.UUID, list[LmsProgramItem]] = {}
    for item in team_scoped_mission_items:
        if item.mission_id not in items_by_mission:
            items_by_mission[item.mission_id] = []
            mission_ids.append(item.mission_id)
        items_by_mission[item.mission_id].append(item)

    out: dict[uuid.UUID, list[dict]] = {}
    for team_id in team_ids:
        runs = []
        for mission_id in mission_ids:
            attempt_id = None
            for item in items_by_mission[mission_id]:
                progress = progress_by_team_item.get((team_id, item.id))
                if progress is not None and progress.mission_attempt_id is not None:
                    attempt_id = progress.mission_attempt_id
                    break
            runs.append({
                "mission_id": mission_id,
                "title": title_by_id.get(mission_id, "Mission"),
                "attempt_id": attempt_id,
                "status": attempt_status.get(attempt_id, "not_started") if attempt_id else "not_started",
            })
        out[team_id] = runs
    return out


async def cohort_team_analytics(db: AsyncSession, *, cohort_id: uuid.UUID, mode: str = "participant") -> dict | None:
    """Returns None if the cohort doesn't exist — the router turns that
    into a 404, mirroring every other admin cohort lookup here.

    A cohort with no LMS checklist resolved (no program checklist, no
    override) is NOT an error: it still has teams and a roster, and those
    stats are the reason half of this page exists. Those cohorts come back
    with populated `totals`/`teams` and empty `items`/`missions`."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None

    team_query = select(Team).where(Team.cohort_id == cohort_id)
    if mode == "participant":
        team_query = team_query.where(Team.is_observer.is_(False))
    elif mode == "observer":
        team_query = team_query.where(Team.is_observer.is_(True))
    teams = list((await db.execute(team_query.order_by(Team.name))).scalars().all())
    team_ids = [t.id for t in teams]
    members_by_team, users_by_id = await _team_rosters(db, team_ids=team_ids)
    missing_locked_by = {t.final_locked_by for t in teams if t.final_locked_by and t.final_locked_by not in users_by_id}
    if missing_locked_by:
        more_users = (await db.execute(select(User).where(User.id.in_(missing_locked_by)))).scalars().all()
        for u in more_users:
            users_by_id[u.id] = u

    registered_user_ids = await _cohort_roster_user_ids(db, cohort_id=cohort_id, mode=mode)
    on_a_team = {uid for ids in members_by_team.values() for uid in ids}

    resolved = await effective_cohort_program_items(db, cohort_id)
    items = list(resolved[1]) if resolved is not None else []

    team_items = [i for i in items if i.scope == "team" and i.item_type != "mission_run"]
    individual_items = [i for i in items if i.scope != "team" and i.item_type != "mission_run"]
    # Includes mission_run rows: `_mission_blocks` reads their
    # `mission_attempt_id` off the same fetch rather than re-querying.
    progress_item_ids = [i.id for i in items if i.scope == "team"]
    team_progress = list((await db.execute(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id.in_(progress_item_ids),
            LmsProgramTeamItemProgress.team_id.in_(team_ids),
        )
    )).scalars().all()) if progress_item_ids and team_ids else []
    progress_by_team_item = {(p.team_id, p.item_id): p for p in team_progress}

    missing_updater_ids = {
        p.updated_by_user_id for p in team_progress if p.updated_by_user_id and p.updated_by_user_id not in users_by_id
    }
    if missing_updater_ids:
        more_updaters = (await db.execute(select(User).where(User.id.in_(missing_updater_ids)))).scalars().all()
        for u in more_updaters:
            users_by_id[u.id] = u

    checkpoint_items = sorted(
        [i for i in items if i.item_type == "checkpoint"], key=lambda i: i.position,
    )

    done_users_by_item, awaiting_users_by_item, assigned_user_ids, assignment_by_user = await _individual_done_user_ids(
        db, items=individual_items, cohort_id=cohort_id, mode=mode,
    )

    quiz_items = [i for i in items if i.item_type == "quiz"]
    quiz_attempts_by_user_item: dict[tuple[uuid.UUID, uuid.UUID], CohortQuizAttempt] = {}
    if quiz_items and on_a_team:
        quiz_item_ids = [i.id for i in quiz_items]
        quiz_attempts = (await db.execute(
            select(CohortQuizAttempt).where(
                CohortQuizAttempt.program_item_id.in_(quiz_item_ids),
                (CohortQuizAttempt.cohort_id == cohort_id) | (CohortQuizAttempt.user_id.in_(list(on_a_team))),
            )
        )).scalars().all()
        for att in quiz_attempts:
            quiz_attempts_by_user_item[(att.user_id, att.program_item_id)] = att

    # ── per-item completion rate ────────────────────────────────────────
    item_rows = []
    for item in items:
        if item.item_type == "mission_run":
            continue
        if item.scope == "team":
            total = len(teams)
            done = sum(
                1 for t in teams
                if (
                    ((p := progress_by_team_item.get((t.id, item.id))) is not None and p.status == "done")
                    or (item.item_type == "team_setup" and bool(t.name) and (t.roster_team_id is None or t.name != t.roster_team_id))
                )
            )
            awaiting = sum(
                1 for t in teams
                if (p := progress_by_team_item.get((t.id, item.id))) is not None
                and p.status == "awaiting_confirmation"
            )
        else:
            total = len(assigned_user_ids)
            done = len(done_users_by_item.get(item.id, set()))
            awaiting = len(awaiting_users_by_item.get(item.id, set()))
        item_rows.append({
            "item_id": item.id,
            "title": item.title,
            "item_type": item.item_type,
            "scope": "team" if item.scope == "team" else "individual",
            "position": item.position,
            "optional": item.optional,
            "deadline_at": item.deadline_at,
            "denominator": "teams" if item.scope == "team" else "students",
            "total": total,
            "done": done,
            "awaiting": awaiting,
            "pending": max(total - done - awaiting, 0),
            "pct": _pct(done, total),
        })

    # ── per-team progress ───────────────────────────────────────────────
    required_team_items = [i for i in team_items if not i.optional]
    optional_team_items = [i for i in team_items if i.optional]
    required_individual_items = [i for i in individual_items if not i.optional]
    optional_individual_items = [i for i in individual_items if i.optional]
    ind_total = len(required_individual_items)
    ind_opt_total = len(optional_individual_items)
    now = datetime.now(timezone.utc)
    team_rows = []
    for team in teams:
        member_ids = members_by_team.get(team.id, [])
        members = [users_by_id[uid] for uid in member_ids if uid in users_by_id]
        done = 0
        awaiting = 0
        for item in required_team_items:
            progress = progress_by_team_item.get((team.id, item.id))
            status = progress.status if progress is not None else "pending"
            if item.item_type == "team_setup" and status == "pending" and team.name and (team.roster_team_id is None or team.name != team.roster_team_id):
                status = "done"
            if status == "done":
                done += 1
            elif status == "awaiting_confirmation":
                awaiting += 1

        opt_done = 0
        for item in optional_team_items:
            progress = progress_by_team_item.get((team.id, item.id))
            status = progress.status if progress is not None else "pending"
            if item.item_type == "team_setup" and status == "pending" and team.name and (team.roster_team_id is None or team.name != team.roster_team_id):
                status = "done"
            if status == "done":
                opt_done += 1

        # Every deliverable (required and optional), not just the missing ones — ops asked
        # to see what a team actually submitted here (link/text), not just
        # a bare "still missing" title, so a done or submitted item carries its content
        # straight from the shared team-progress row rather than making
        # ops click through to the checklist for it.
        deliverables: list[dict] = []
        last_activity: datetime | None = None
        for item in team_items:
            progress = progress_by_team_item.get((team.id, item.id))
            status = progress.status if progress is not None else "pending"
            if item.item_type == "team_setup" and status == "pending" and team.name and (team.roster_team_id is None or team.name != team.roster_team_id):
                status = "done"
            updater = users_by_id.get(progress.updated_by_user_id) if (progress and progress.updated_by_user_id) else None
            is_cp_locked = status == "done" and item.item_type == "checkpoint"
            deliverables.append({
                "item_id": item.id,
                "title": item.title,
                "status": status,
                "item_type": item.item_type,
                "optional": item.optional,
                "submitted_url": progress.submitted_url if progress is not None else None,
                "submitted_text": progress.submitted_text if progress is not None else None,
                "submitted_links": progress.submitted_links if progress is not None else None,
                "locked_at": (progress.completed_at or progress.updated_at) if (progress and is_cp_locked) else None,
                "locked_by_name": updater.full_name if (updater and is_cp_locked) else None,
                "updated_at": progress.updated_at if progress is not None else None,
                "updated_by_name": updater.full_name if (updater and item.scope == "team") else None,
            })
            if progress is not None and progress.updated_at is not None:
                if last_activity is None or progress.updated_at > last_activity:
                    last_activity = progress.updated_at

        checkpoints_for_team: list[dict] = []
        for cp in checkpoint_items:
            cp_prog = progress_by_team_item.get((team.id, cp.id))
            cp_status = cp_prog.status if cp_prog is not None else "pending"
            is_locked = cp_status == "done"
            cp_locked_at = (cp_prog.completed_at or cp_prog.updated_at) if (cp_prog and is_locked) else None
            cp_updater = users_by_id.get(cp_prog.updated_by_user_id) if (cp_prog and cp_prog.updated_by_user_id) else None
            cp_penalty_pts = cp_prog.penalty_points if (cp_prog and is_locked) else None
            cp_penalty_notes = cp_prog.penalty_notes if (cp_prog and is_locked) else None
            checkpoints_for_team.append({
                "item_id": cp.id,
                "title": cp.title,
                "position": cp.position,
                "status": cp_status,
                "locked": is_locked,
                "locked_at": cp_locked_at,
                "locked_by_name": cp_updater.full_name if cp_updater else None,
                "locked_by_email": cp_updater.email if cp_updater else None,
                "locked_by_id": cp_prog.updated_by_user_id if cp_prog else None,
                "penalty_points": cp_penalty_pts,
                "penalty_notes": cp_penalty_notes,
            })

        quiz_subs = []
        for q_item in quiz_items:
            for uid in member_ids:
                u = users_by_id.get(uid)
                att = quiz_attempts_by_user_item.get((uid, q_item.id))
                quiz_subs.append({
                    "user_id": uid,
                    "student_name": u.full_name if u else "Student",
                    "assignment_id": assignment_by_user.get(uid),
                    "item_id": q_item.id,
                    "quiz_title": q_item.title,
                    "status": att.status if att else "not_started",
                    "score": att.score if att else None,
                    "total": att.total if att else None,
                    "submitted_at": att.submitted_at if att else None,
                })

        total = len(required_team_items)
        team_pct_val = _pct(done, total)
        is_stalled = (
            done < total
            and (last_activity is None or (now - last_activity) > timedelta(days=STALLED_AFTER_DAYS))
        )
        member_stats = [
            {
                "user_id": m.id,
                "assignment_id": assignment_by_user.get(m.id),
                "name": m.full_name,
                "student_id": getattr(m, "student_id", None),
                "last_login_at": m.last_login_at,
                "items_total": ind_total,
                "items_done": sum(1 for item in required_individual_items if m.id in done_users_by_item.get(item.id, set())),
                "optional_total": ind_opt_total,
                "optional_done": sum(1 for item in optional_individual_items if m.id in done_users_by_item.get(item.id, set())),
                "all_total": ind_total + ind_opt_total,
                "all_done": (
                    sum(1 for item in required_individual_items if m.id in done_users_by_item.get(item.id, set()))
                    + sum(1 for item in optional_individual_items if m.id in done_users_by_item.get(item.id, set()))
                ),
                "pct": _pct(
                    sum(1 for item in required_individual_items if m.id in done_users_by_item.get(item.id, set())),
                    ind_total,
                ),
            }
            for m in members
        ]
        active_member_count = sum(
            1 for ms in member_stats
            if ms["last_login_at"] is not None and (ms["items_done"] > 0 or ind_total == 0)
        )
        distinct_submitter_count = len({
            p.updated_by_user_id
            for item in team_items
            if (p := progress_by_team_item.get((team.id, item.id))) is not None and p.updated_by_user_id is not None
        })
        member_pcts = [ms["pct"] for ms in member_stats] if member_stats else [0]
        if (
            len(members) >= 2
            and team_pct_val >= 50
            and distinct_submitter_count <= 1
            and (any(ms["last_login_at"] is None for ms in member_stats) or min(member_pcts) < 20)
        ):
            collab_status = "solo_carried"
        elif is_stalled:
            collab_status = "stalled"
        elif len(members) >= 2 and (max(member_pcts) - min(member_pcts)) >= 50:
            collab_status = "imbalanced"
        else:
            collab_status = "balanced"

        locked_by_user = users_by_id.get(team.final_locked_by) if team.final_locked_by else None
        team_rows.append({
            "team_id": team.id,
            "team_name": team.name,
            "roster_team_id": team.roster_team_id,
            "is_observer": bool(team.is_observer),
            "member_count": len(member_ids),
            "members": member_stats,
            "never_logged_in": sum(1 for m in members if m.last_login_at is None),
            "items_total": total,
            "items_done": done,
            "optional_total": len(optional_team_items),
            "optional_done": opt_done,
            "all_total": total + len(optional_team_items),
            "all_done": done + opt_done,
            "awaiting": awaiting,
            "pct": team_pct_val,
            "checkpoints": checkpoints_for_team,
            "deliverables": deliverables,
            "quiz_submissions": quiz_subs,
            "last_activity_at": last_activity,
            "stalled": is_stalled,
            "collaboration_status": collab_status,
            "active_member_count": active_member_count,
            "distinct_submitter_count": distinct_submitter_count,
            "locked": team.final_locked_at is not None,
            "locked_at": team.final_locked_at,
            "locked_by_name": locked_by_user.full_name if locked_by_user else None,
            "locked_by_email": locked_by_user.email if locked_by_user else None,
            "locked_by_id": team.final_locked_by,
            "final_lock_penalty": getattr(team, "final_lock_penalty", None) if team.final_locked_at is not None else None,
            "final_lock_notes": getattr(team, "final_lock_notes", None) if team.final_locked_at is not None else None,
        })
    team_rows.sort(key=lambda r: (-r["pct"], r["team_name"].lower()))

    missions, attempt_status, title_by_id = await _mission_blocks(
        db, items=items, team_progress=team_progress,
        team_count=len(teams), assigned_user_count=len(assigned_user_ids),
        assigned_assignment_ids=set(assignment_by_user.values()),
    )
    team_mission_runs = _team_mission_runs(
        items=items, progress_by_team_item=progress_by_team_item, team_ids=team_ids,
        attempt_status=attempt_status, title_by_id=title_by_id,
    )
    for row in team_rows:
        row["mission_runs"] = team_mission_runs.get(row["team_id"], [])

    # ── multi-signal activity window ────────────────────────────────────
    window_start = (now - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)).date()
    team_deliv_by_day: dict[date, int] = {}
    for progress in team_progress:
        if progress.updated_at is None:
            continue
        day = progress.updated_at.astimezone(timezone.utc).date()
        if day >= window_start:
            team_deliv_by_day[day] = team_deliv_by_day.get(day, 0) + 1

    quiz_by_day: dict[date, int] = {}
    for att in quiz_attempts_by_user_item.values():
        if att.submitted_at is None:
            continue
        day = att.submitted_at.astimezone(timezone.utc).date()
        if day >= window_start:
            quiz_by_day[day] = quiz_by_day.get(day, 0) + 1

    course_by_day: dict[date, int] = {}
    if assignment_by_user:
        ind_prog_rows = (await db.execute(
            select(LmsProgramItemProgress.completed_at).where(
                LmsProgramItemProgress.assignment_id.in_(list(assignment_by_user.values())),
                LmsProgramItemProgress.completed_at.isnot(None),
            )
        )).scalars().all()
        for completed_at in ind_prog_rows:
            day = completed_at.astimezone(timezone.utc).date()
            if day >= window_start:
                course_by_day[day] = course_by_day.get(day, 0) + 1

    activity = []
    for offset in range(ACTIVITY_WINDOW_DAYS):
        d = window_start + timedelta(days=offset)
        td = team_deliv_by_day.get(d, 0)
        qs = quiz_by_day.get(d, 0)
        cc = course_by_day.get(d, 0)
        activity.append({
            "date": d,
            "updates": td + qs + cc,
            "team_deliverables": td,
            "quiz_submissions": qs,
            "course_completions": cc,
        })

    # ── individual roster summary ───────────────────────────────────────
    assigned_users_rows = (
        (await db.execute(select(User).where(User.id.in_(list(assigned_user_ids))))).scalars().all()
        if assigned_user_ids else []
    )
    ind_started_count = 0
    ind_completed_count = 0
    ind_pct_sum = 0
    ind_req_count = len(required_individual_items)
    for uid in assigned_user_ids:
        u_done = sum(1 for item in required_individual_items if uid in done_users_by_item.get(item.id, set()))
        if u_done > 0:
            ind_started_count += 1
        if ind_req_count > 0 and u_done == ind_req_count:
            ind_completed_count += 1
        ind_pct_sum += _pct(u_done, ind_req_count)
    ind_never_logged_in = sum(1 for u in assigned_users_rows if u.last_login_at is None)

    required_total_per_team = len(required_team_items)
    return {
        "cohort_id": cohort_id,
        "cohort_name": cohort.name,
        "totals": {
            "teams": len(teams),
            "students_on_teams": len(on_a_team),
            "avg_team_size": round(len(on_a_team) / len(teams), 1) if teams else 0.0,
            "empty_teams": sum(1 for t in teams if not members_by_team.get(t.id)),
            "registered_students": len(registered_user_ids),
            "students_without_team": len(registered_user_ids - on_a_team),
            "assigned_students": len(assigned_user_ids),
            "never_logged_in": sum(
                1 for uid in on_a_team
                if uid in users_by_id and users_by_id[uid].last_login_at is None
            ),
            "deliverables_per_team": required_total_per_team,
            "deliverables_done": sum(r["items_done"] for r in team_rows),
            "deliverables_awaiting": sum(r["awaiting"] for r in team_rows),
            "teams_complete": sum(
                1 for r in team_rows if r["items_total"] > 0 and r["items_done"] == r["items_total"]
            ),
            "teams_not_started": sum(1 for r in team_rows if r["items_done"] == 0),
            "teams_stalled": sum(1 for r in team_rows if r["stalled"]),
            "avg_team_pct": _pct(
                sum(r["items_done"] for r in team_rows),
                sum(r["items_total"] for r in team_rows),
            ),
        },
        "individual_summary": {
            "registered_count": max(len(registered_user_ids), len(assigned_user_ids)),
            "assigned_count": len(assigned_user_ids),
            "started_count": ind_started_count,
            "completed_count": ind_completed_count,
            "never_logged_in_count": ind_never_logged_in,
            "avg_pct": round(ind_pct_sum / len(assigned_user_ids)) if assigned_user_ids else 0,
        },
        "items": item_rows,
        "missions": missions,
        "teams": team_rows,
        "activity": activity,
        "stalled_after_days": STALLED_AFTER_DAYS,
    }
