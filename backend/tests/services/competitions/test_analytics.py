"""Cohort team analytics (2026-09-16) — `services/competitions/analytics.py`,
behind the Judging page's Analysis tab.

Focused on the three things that are actually easy to get wrong here and
that no other test covers: which denominator each item's completion rate
is measured against (teams vs. students), that `awaiting_confirmation`
never counts as done, and that a `mission_run` item is reported as a
mission rather than as a completion-rate bar.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status as http_status
from sqlalchemy import delete

from app.core.security import create_access_token
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.team import TeamMember
from app.models.user import User
from app.services.competitions.analytics import STALLED_AFTER_DAYS, cohort_team_analytics
from app.services.sessions.registration import register
from app.services.teams import create_team


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Analysis Ops", email=f"anaops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _student(db, name="Analysis Student", *, cohort: Cohort | None = None) -> User:
    """A student with a real Contact — the analytics roster count hops
    Registration.contact_id -> User.contact_id, so a contact-less user
    would silently never be counted as registered."""
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"anastu-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    if cohort is not None:
        # The real service, not a hand-built row — it owns ticket_token
        # and the rest of the column defaults.
        await register(
            db, contact_id=contact.id, cohort_id=cohort.id,
            registered_via="desk", payment_status="waived",
        )
        await db.flush()
    return user


async def _program_and_cohort(db) -> tuple[Program, Cohort]:
    program = Program(
        id=uuid.uuid4(), code=f"ANA-{uuid.uuid4().hex[:8]}", name="Ru'ya Space Race",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Qualifier", status="running")
    db.add(cohort)
    await db.flush()
    return program, cohort


async def _checklist(db, program: Program, items: list[dict]) -> tuple[LmsProgram, list[LmsProgramItem]]:
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Stage Checklist")
    db.add(lms_program)
    await db.flush()
    created = []
    for position, spec in enumerate(items, start=1):
        item = LmsProgramItem(
            id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=position,
            item_type=spec.get("item_type", "submission"), title=spec["title"],
            scope=spec.get("scope", "individual"), optional=spec.get("optional", False),
            **({"mission_id": spec["mission_id"]} if spec.get("mission_id") else {}),
        )
        db.add(item)
        created.append(item)
    await db.flush()
    return lms_program, created


# ── denominators ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_team_item_counts_teams_and_an_individual_item_counts_students(db):
    """The one thing a reader of this chart must be able to trust: which
    population each bar's `total` is out of."""
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    lms_program, (team_item, solo_item) = await _checklist(db, program, [
        {"title": "Poster", "scope": "team"},
        {"title": "Reflection", "scope": "individual"},
    ])

    # Three students across two teams; all three hold the checklist.
    students = [await _student(db, f"Student {i}", cohort=cohort) for i in range(3)]
    # `create_team` always adds its creator as a member, so the teams are
    # created *by a member* rather than by ops — the ops-created shell is
    # `create_empty_team`'s job, and an ops account on the roster would
    # skew every count here.
    team_a = await create_team(db, name="Alpha", created_by=students[0].id, cohort_id=cohort.id)
    await create_team(db, name="Beta", created_by=students[1].id, cohort_id=cohort.id, member_ids=[students[2].id])
    for student in students:
        db.add(LmsProgramAssignment(
            id=uuid.uuid4(), user_id=student.id, lms_program_id=lms_program.id, cohort_id=cohort.id,
        ))
    await db.flush()
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    by_title = {row["title"]: row for row in result["items"]}

    assert by_title["Poster"]["denominator"] == "teams"
    assert by_title["Poster"]["total"] == 2
    assert by_title["Reflection"]["denominator"] == "students"
    assert by_title["Reflection"]["total"] == 3
    assert by_title["Poster"]["item_id"] == team_item.id
    assert by_title["Reflection"]["item_id"] == solo_item.id
    assert team_a.cohort_id == cohort.id
    _ = ops


@pytest.mark.asyncio
async def test_awaiting_confirmation_is_its_own_bucket_and_never_counts_as_done(db):
    """A submitted-but-unconfirmed deliverable is outstanding *ops* work,
    so it must not inflate the completion rate — but it must also be
    visible, not lumped in with "nobody submitted"."""
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    _lms_program, (poster,) = await _checklist(db, program, [{"title": "Poster", "scope": "team"}])

    student_a = await _student(db, "A", cohort=cohort)
    student_b = await _student(db, "B", cohort=cohort)
    student_c = await _student(db, "C", cohort=cohort)
    done_team = await create_team(db, name="Done", created_by=student_a.id, cohort_id=cohort.id)
    waiting_team = await create_team(db, name="Waiting", created_by=student_b.id, cohort_id=cohort.id)
    await create_team(db, name="Silent", created_by=student_c.id, cohort_id=cohort.id)

    now = datetime.now(timezone.utc)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=done_team.id, status="done",
        completed_at=now, updated_at=now,
    ))
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=waiting_team.id, status="awaiting_confirmation",
        submitted_url="https://example.com/poster.pdf", updated_at=now,
    ))
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    bar = result["items"][0]
    assert (bar["done"], bar["awaiting"], bar["pending"]) == (1, 1, 1)
    assert bar["pct"] == 33  # 1 of 3, NOT 2 of 3

    teams = {row["team_name"]: row for row in result["teams"]}
    assert teams["Done"]["pct"] == 100
    assert teams["Waiting"]["pct"] == 0
    assert teams["Waiting"]["awaiting"] == 1
    # The unconfirmed item is still what the team is missing, so ops sees it,
    # along with the link the team actually submitted for it.
    waiting_deliverable = teams["Waiting"]["deliverables"][0]
    assert waiting_deliverable["title"] == "Poster"
    assert waiting_deliverable["status"] == "awaiting_confirmation"
    assert waiting_deliverable["submitted_url"] == "https://example.com/poster.pdf"
    assert result["totals"]["deliverables_awaiting"] == 1
    assert result["totals"]["teams_complete"] == 1
    assert result["totals"]["teams_not_started"] == 2
    _ = ops


@pytest.mark.asyncio
async def test_optional_items_get_a_bar_but_never_move_a_team_percentage(db):
    """Mirrors `_assignment_summary`'s own rule — an optional step nobody
    did is not a cohort running behind."""
    program, cohort = await _program_and_cohort(db)
    _lms_program, (required, _optional) = await _checklist(db, program, [
        {"title": "Poster", "scope": "team"},
        {"title": "Bonus video", "scope": "team", "optional": True},
    ])
    student = await _student(db, "Solo", cohort=cohort)
    team = await create_team(db, name="Alpha", created_by=student.id, cohort_id=cohort.id)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=required.id, team_id=team.id, status="done",
        completed_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    assert {row["title"] for row in result["items"]} == {"Poster", "Bonus video"}
    assert result["teams"][0]["items_total"] == 1  # the optional one is not counted
    assert result["teams"][0]["pct"] == 100


# ── mission runs ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_mission_run_item_is_reported_as_a_mission_not_as_a_completion_bar(db):
    """Its real completion is per-design-step and can't be read off the
    stored checklist status, so it deliberately gets its own block."""
    from app.models.missions.mission import Mission

    program, cohort = await _program_and_cohort(db)
    author = await _ops(db)
    mission = Mission(
        id=uuid.uuid4(), title="CubeSat Design", slug=f"cubesat-{uuid.uuid4().hex[:8]}",
        kind="design", team_policy="team", status="published", access_mode="open",
        authored_by=author.id,
    )
    db.add(mission)
    await db.flush()
    await _checklist(db, program, [
        {"title": "Poster", "scope": "team"},
        {"title": "Design run", "scope": "team", "item_type": "mission_run", "mission_id": mission.id},
    ])
    student = await _student(db, "Solo", cohort=cohort)
    await create_team(db, name="Alpha", created_by=student.id, cohort_id=cohort.id)
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    assert [row["title"] for row in result["items"]] == ["Poster"]
    assert len(result["missions"]) == 1
    assert result["missions"][0]["title"] == "CubeSat Design"
    assert result["missions"][0]["scope"] == "team"
    # No attempt assigned yet, so the one team is "not started" — not
    # silently dropped for having no attempt id.
    assert result["missions"][0]["not_started"] == 1


# ── roster stats ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_roster_totals_dedupe_members_and_count_who_is_left_over(db):
    program, cohort = await _program_and_cohort(db)
    on_team = [await _student(db, f"On {i}", cohort=cohort) for i in range(3)]
    await _student(db, "Unassigned", cohort=cohort)
    await _checklist(db, program, [{"title": "Poster", "scope": "team"}])

    await create_team(db, name="Alpha", created_by=on_team[0].id, cohort_id=cohort.id, member_ids=[on_team[1].id])
    await create_team(db, name="Beta", created_by=on_team[2].id, cohort_id=cohort.id)
    shell = await create_team(db, name="Empty shell", created_by=on_team[2].id, cohort_id=cohort.id)
    # `create_team` always adds its creator, so the shell starts with one
    # member; drop it to exercise the genuinely-empty branch (which is
    # what ops's own `create_empty_team` produces).
    await db.execute(delete(TeamMember).where(TeamMember.team_id == shell.id))
    await db.commit()

    totals = (await cohort_team_analytics(db, cohort_id=cohort.id))["totals"]
    assert totals["teams"] == 3
    assert totals["students_on_teams"] == 3
    assert totals["empty_teams"] == 1
    assert totals["registered_students"] == 4
    assert totals["students_without_team"] == 1


@pytest.mark.asyncio
async def test_a_team_with_no_recent_activity_is_flagged_stalled(db):
    program, cohort = await _program_and_cohort(db)
    _lms_program, (poster,) = await _checklist(db, program, [{"title": "Poster", "scope": "team"}])
    quiet_student = await _student(db, "Quiet", cohort=cohort)
    busy_student = await _student(db, "Busy", cohort=cohort)
    quiet = await create_team(db, name="Quiet", created_by=quiet_student.id, cohort_id=cohort.id)
    busy = await create_team(db, name="Busy", created_by=busy_student.id, cohort_id=cohort.id)

    long_ago = datetime.now(timezone.utc) - timedelta(days=STALLED_AFTER_DAYS + 3)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=quiet.id, status="pending", updated_at=long_ago,
    ))
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=busy.id, status="pending",
        updated_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    teams = {row["team_name"]: row for row in (await cohort_team_analytics(db, cohort_id=cohort.id))["teams"]}
    assert teams["Quiet"]["stalled"] is True
    assert teams["Busy"]["stalled"] is False


@pytest.mark.asyncio
async def test_a_completed_team_is_never_stalled_however_long_it_has_been_quiet(db):
    """Finished is finished — flagging a done team as needing chasing is
    exactly the false positive that makes an attention list ignorable."""
    program, cohort = await _program_and_cohort(db)
    _lms_program, (poster,) = await _checklist(db, program, [{"title": "Poster", "scope": "team"}])
    student = await _student(db, "Finished", cohort=cohort)
    team = await create_team(db, name="Finished", created_by=student.id, cohort_id=cohort.id)
    long_ago = datetime.now(timezone.utc) - timedelta(days=STALLED_AFTER_DAYS + 30)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=team.id, status="done",
        completed_at=long_ago, updated_at=long_ago,
    ))
    await db.commit()

    row = (await cohort_team_analytics(db, cohort_id=cohort.id))["teams"][0]
    assert row["pct"] == 100
    assert row["stalled"] is False


# ── degenerate cohorts ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_cohort_with_no_checklist_still_reports_its_teams(db):
    """Half this page is roster stats, which are real whether or not an
    LMS checklist has been authored yet — this must not 404 or blow up."""
    _program, cohort = await _program_and_cohort(db)
    student = await _student(db, "Solo", cohort=cohort)
    await create_team(db, name="Alpha", created_by=student.id, cohort_id=cohort.id)
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    assert result["totals"]["teams"] == 1
    assert result["totals"]["students_on_teams"] == 1
    assert result["items"] == []
    assert result["missions"] == []
    assert result["teams"][0]["items_total"] == 0
    assert result["teams"][0]["pct"] == 0


@pytest.mark.asyncio
async def test_unknown_cohort_is_a_404_through_the_router(db, client):
    ops = await _ops(db)
    await db.commit()
    resp = await client.get(
        f"/competitions/admin/cohorts/{uuid.uuid4()}/team-analytics", headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_the_endpoint_returns_the_whole_payload_for_ops(db, client):
    ops = await _ops(db)
    program, cohort = await _program_and_cohort(db)
    _lms_program, (poster,) = await _checklist(db, program, [{"title": "Poster", "scope": "team"}])
    student = await _student(db, "Solo", cohort=cohort)
    team = await create_team(db, name="Alpha", created_by=student.id, cohort_id=cohort.id)
    db.add(LmsProgramTeamItemProgress(
        id=uuid.uuid4(), item_id=poster.id, team_id=team.id, status="done",
        completed_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    resp = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/team-analytics", headers=_headers(ops),
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["cohort_name"] == "Qualifier"
    assert body["totals"]["teams"] == 1
    assert body["items"][0]["pct"] == 100
    assert body["teams"][0]["team_name"] == "Alpha"
    assert len(body["activity"]) == 30
    # Today's own update lands in the last bucket of the window.
    assert body["activity"][-1]["updates"] == 1
    assert body["stalled_after_days"] == STALLED_AFTER_DAYS


@pytest.mark.asyncio
async def test_an_individual_item_is_measured_against_assigned_students_only(db):
    """A student registered but never assigned the checklist has no
    progress row for anything — counting them in every bar's denominator
    would read as the cohort failing rather than as an assignment gap."""
    program, cohort = await _program_and_cohort(db)
    lms_program, (reflection,) = await _checklist(db, program, [
        {"title": "Reflection", "scope": "individual"},
    ])
    assigned = await _student(db, "Assigned", cohort=cohort)
    await _student(db, "Registered only", cohort=cohort)

    assignment = LmsProgramAssignment(
        id=uuid.uuid4(), user_id=assigned.id, lms_program_id=lms_program.id, cohort_id=cohort.id,
    )
    db.add(assignment)
    await db.flush()
    db.add(LmsProgramItemProgress(
        id=uuid.uuid4(), assignment_id=assignment.id, item_id=reflection.id, status="done",
        completed_at=datetime.now(timezone.utc),
    ))
    await db.commit()

    result = await cohort_team_analytics(db, cohort_id=cohort.id)
    bar = result["items"][0]
    assert bar["total"] == 1  # not 2
    assert bar["done"] == 1
    assert bar["pct"] == 100
    assert result["totals"]["registered_students"] == 2
    assert result["totals"]["assigned_students"] == 1
