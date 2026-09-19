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

- `scope="team"` items (`submission`/`external_link`/`manual`/`team_setup`)
  — `lms_program_team_item_progress.status` is the literal truth. Nothing
  auto-tracks these; a self-check or an ops confirmation is what writes them.
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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.cohort_quiz import CohortQuizAttempt
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
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


async def _cohort_roster_user_ids(db: AsyncSession, *, cohort_id: uuid.UUID) -> set[uuid.UUID]:
    """Every student with an active Registration in this cohort, as user
    ids — the denominator for "registered but not on a team". Same
    contact_id -> User hop (and the same active-status filter) every other
    roster query in this codebase uses."""
    contact_ids = (await db.execute(
        select(Registration.contact_id).where(
            Registration.cohort_id == cohort_id,
            Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )).scalars().all()
    if not contact_ids:
        return set()
    return set((await db.execute(
        select(User.id).where(User.contact_id.in_(contact_ids))
    )).scalars().all())


async def _individual_done_user_ids(
    db: AsyncSession, *, items: list[LmsProgramItem], cohort_id: uuid.UUID,
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
    assignments = (await db.execute(
        select(LmsProgramAssignment.id, LmsProgramAssignment.user_id)
        .where(LmsProgramAssignment.cohort_id == cohort_id)
    )).all()
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
    team_count: int, assigned_user_count: int,
) -> tuple[list[dict], dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """One row per mission_run mission (not per checklist item — several
    items can split one run into design steps via `mission_step_key`, the
    same grouping `team_mission_run_items` and the authoring Missions tab
    already use), counting the shared `MissionAttempt.status` behind it.

    Team-scoped runs count teams; individual-scoped runs count students.
    Both read the attempt row directly — no design-dashboard cascade, see
    the module docstring.

    Also returns `attempt_status`/`title_by_id` — the same lookups this
    needs to build its own cohort-wide rows are exactly what
    cohort_team_analytics's per-team pass needs too (_team_mission_runs
    below), so they're handed back rather than requeried."""
    mission_items = [i for i in items if i.item_type == "mission_run" and i.mission_id]
    if not mission_items:
        return [], {}, {}

    item_mission, attempt_ids_by_mission, team_scoped_mission_ids = _mission_attempt_lookup(items, team_progress)

    individual_item_ids = [i.id for i in mission_items if i.scope != "team"]
    if individual_item_ids:
        rows = (await db.execute(
            select(LmsProgramItemProgress.item_id, LmsProgramItemProgress.mission_attempt_id).where(
                LmsProgramItemProgress.item_id.in_(individual_item_ids),
                LmsProgramItemProgress.mission_attempt_id.isnot(None),
            )
        )).all()
        for item_id, attempt_id in rows:
            mission_id = item_mission.get(item_id)
            if mission_id is not None:
                attempt_ids_by_mission.setdefault(mission_id, set()).add(attempt_id)

    all_attempt_ids = {aid for ids in attempt_ids_by_mission.values() for aid in ids}
    attempts = (
        (await db.execute(select(MissionAttempt).where(MissionAttempt.id.in_(all_attempt_ids)))).scalars().all()
        if all_attempt_ids else []
    )
    attempt_status = {a.id: a.status for a in attempts}

    mission_ids = sorted({i.mission_id for i in mission_items}, key=str)
    missions = (await db.execute(select(Mission).where(Mission.id.in_(mission_ids)))).scalars().all()
    title_by_id = {m.id: m.title for m in missions}

    out = []
    for mission_id in mission_ids:
        is_team = mission_id in team_scoped_mission_ids
        total = team_count if is_team else assigned_user_count
        statuses = [attempt_status.get(aid) for aid in attempt_ids_by_mission.get(mission_id, set())]
        passed = sum(1 for s in statuses if s == "passed")
        # Everything that has an attempt but hasn't passed is "started" —
        # submitted/failed/abandoned included. A failed run is still a
        # team that showed up, and lumping it with "never opened it" would
        # hide exactly the teams worth chasing.
        started = sum(1 for s in statuses if s is not None and s != "passed")
        out.append({
            "mission_id": mission_id,
            "title": title_by_id.get(mission_id, "Mission"),
            "scope": "team" if is_team else "individual",
            "total": total,
            "passed": passed,
            "in_progress": started,
            "not_started": max(total - passed - started, 0),
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


async def cohort_team_analytics(db: AsyncSession, *, cohort_id: uuid.UUID) -> dict | None:
    """Returns None if the cohort doesn't exist — the router turns that
    into a 404, mirroring every other admin cohort lookup here.

    A cohort with no LMS checklist resolved (no program checklist, no
    override) is NOT an error: it still has teams and a roster, and those
    stats are the reason half of this page exists. Those cohorts come back
    with populated `totals`/`teams` and empty `items`/`missions`."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None

    teams = list((await db.execute(
        select(Team).where(Team.cohort_id == cohort_id).order_by(Team.name)
    )).scalars().all())
    team_ids = [t.id for t in teams]
    members_by_team, users_by_id = await _team_rosters(db, team_ids=team_ids)
    missing_locked_by = {t.final_locked_by for t in teams if t.final_locked_by and t.final_locked_by not in users_by_id}
    if missing_locked_by:
        more_users = (await db.execute(select(User).where(User.id.in_(missing_locked_by)))).scalars().all()
        for u in more_users:
            users_by_id[u.id] = u

    registered_user_ids = await _cohort_roster_user_ids(db, cohort_id=cohort_id)
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

    done_users_by_item, awaiting_users_by_item, assigned_user_ids, assignment_by_user = await _individual_done_user_ids(
        db, items=individual_items, cohort_id=cohort_id,
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
                if (p := progress_by_team_item.get((t.id, item.id))) is not None and p.status == "done"
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
    now = datetime.now(timezone.utc)
    team_rows = []
    for team in teams:
        member_ids = members_by_team.get(team.id, [])
        members = [users_by_id[uid] for uid in member_ids if uid in users_by_id]
        done = 0
        awaiting = 0
        # Every required deliverable, not just the missing ones — ops asked
        # to see what a team actually submitted here (link/text), not just
        # a bare "still missing" title, so a done item carries its content
        # straight from the shared team-progress row rather than making
        # ops click through to the checklist for it.
        deliverables: list[dict] = []
        last_activity: datetime | None = None
        for item in required_team_items:
            progress = progress_by_team_item.get((team.id, item.id))
            status = progress.status if progress is not None else "pending"
            if status == "done":
                done += 1
            elif status == "awaiting_confirmation":
                awaiting += 1
            deliverables.append({
                "item_id": item.id,
                "title": item.title,
                "status": status,
                "submitted_url": progress.submitted_url if progress is not None else None,
                "submitted_text": progress.submitted_text if progress is not None else None,
                "submitted_links": progress.submitted_links if progress is not None else None,
            })
        for item in team_items:
            progress = progress_by_team_item.get((team.id, item.id))
            if progress is not None and progress.updated_at is not None:
                if last_activity is None or progress.updated_at > last_activity:
                    last_activity = progress.updated_at

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
        locked_by_user = users_by_id.get(team.final_locked_by) if team.final_locked_by else None
        team_rows.append({
            "team_id": team.id,
            "team_name": team.name,
            "roster_team_id": team.roster_team_id,
            "member_count": len(member_ids),
            "members": [{"name": m.full_name, "last_login_at": m.last_login_at} for m in members],
            "never_logged_in": sum(1 for m in members if m.last_login_at is None),
            "items_total": total,
            "items_done": done,
            "awaiting": awaiting,
            "pct": _pct(done, total),
            "deliverables": deliverables,
            "quiz_submissions": quiz_subs,
            "last_activity_at": last_activity,
            "stalled": (
                done < total
                and (last_activity is None or (now - last_activity) > timedelta(days=STALLED_AFTER_DAYS))
            ),
            "locked": team.final_locked_at is not None,
            "locked_at": team.final_locked_at,
            "locked_by_name": locked_by_user.full_name if locked_by_user else None,
            "locked_by_email": locked_by_user.email if locked_by_user else None,
            "locked_by_id": team.final_locked_by,
        })
    team_rows.sort(key=lambda r: (-r["pct"], r["team_name"].lower()))

    missions, attempt_status, title_by_id = await _mission_blocks(
        db, items=items, team_progress=team_progress,
        team_count=len(teams), assigned_user_count=len(assigned_user_ids),
    )
    team_mission_runs = _team_mission_runs(
        items=items, progress_by_team_item=progress_by_team_item, team_ids=team_ids,
        attempt_status=attempt_status, title_by_id=title_by_id,
    )
    for row in team_rows:
        row["mission_runs"] = team_mission_runs.get(row["team_id"], [])

    # ── activity window ─────────────────────────────────────────────────
    # `updated_at` is a last-write timestamp, not an event log — a team
    # that replaced a link three times shows up once, on the last day it
    # touched that deliverable. Enough to see the deadline crunch and the
    # teams that went quiet, which is what this chart is for; it is
    # deliberately not billed as a submission count.
    window_start = (now - timedelta(days=ACTIVITY_WINDOW_DAYS - 1)).date()
    by_day: dict[date, int] = {}
    for progress in team_progress:
        if progress.updated_at is None:
            continue
        day = progress.updated_at.astimezone(timezone.utc).date()
        if day >= window_start:
            by_day[day] = by_day.get(day, 0) + 1
    activity = [
        {"date": window_start + timedelta(days=offset), "updates": by_day.get(window_start + timedelta(days=offset), 0)}
        for offset in range(ACTIVITY_WINDOW_DAYS)
    ]

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
        "items": item_rows,
        "missions": missions,
        "teams": team_rows,
        "activity": activity,
        "stalled_after_days": STALLED_AFTER_DAYS,
    }
