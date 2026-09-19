"""The team mission_run audit script (scripts/lms_audit_team_missions.py).

An audit is only worth running if it actually fires, so each test builds
one specific broken state — the real ones seen in production on
2026-09-19 plus the neighbouring invariants — and asserts the matching
code comes out, and that a healthy team produces no blockers at all.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.team import TeamMember
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.teams import create_team, join_team

_spec = importlib.util.spec_from_file_location(
    "lms_audit_team_missions",
    Path(__file__).resolve().parents[2] / "scripts" / "lms_audit_team_missions.py",
)
audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(audit)


async def _user(db, name="Auditee") -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name=name, contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    user = User(
        id=uuid.uuid4(), full_name=name, email=f"a-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _scenario(db):
    """A cohort with one team-scoped mission_run item and a two-person team,
    fully wired the way a healthy production team looks."""
    author = await _user(db, "Author")
    program = Program(
        id=uuid.uuid4(), code=f"AUD-{uuid.uuid4().hex[:8]}", name="Audit Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Audit Cohort", status="running")
    db.add(cohort)
    await db.flush()

    mission = Mission(
        id=uuid.uuid4(), title="CubeSat Mission Design", slug=f"aud-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=10)
    db.add(variant)
    await db.flush()

    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Audit Checklist")
    db.add(lms_program)
    await db.flush()
    item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=23,
        item_type="mission_run", title="Team's mission components", mission_id=mission.id,
        variant_id=variant.id, scope="team", mission_step_key="components",
    )
    db.add(item)
    await db.flush()

    alice, bob = await _user(db, "Alice"), await _user(db, "Bob")
    team = await create_team(db, name="Orbit3", created_by=alice.id, cohort_id=cohort.id)
    await join_team(db, team_id=team.id, user_id=bob.id)
    for u in (alice, bob):
        await assign_lms_program(db, user_id=u.id, cohort_id=cohort.id)
    await db.flush()
    return cohort, item, team, mission, variant, alice, bob


async def _run(db, cohort, team):
    items = await audit._team_run_items(db, cohort.id)
    f = audit.Findings()
    await audit.audit_team(db, team=team, items=items, f=f)
    return f


def _codes(f, severity=None):
    return {code for sev, code, _w, _d in f.rows if severity is None or sev == severity}


@pytest.mark.asyncio
async def test_healthy_team_produces_no_blockers(db):
    cohort, item, team, *_ = await _scenario(db)
    f = await _run(db, cohort, team)
    assert _codes(f, audit.BLOCKER) == set(), f.rows
    assert _codes(f, audit.WARN) == set(), f.rows


@pytest.mark.asyncio
async def test_missing_team_row_is_a_blocker(db):
    """Bug 1, exactly as team Orbit3 looked: individual placeholders present,
    no team row at all."""
    cohort, item, team, *_ = await _scenario(db)
    row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    await db.delete(row)
    await db.flush()

    f = await _run(db, cohort, team)
    assert "NO_TEAM_ROW" in _codes(f, audit.BLOCKER), f.rows


@pytest.mark.asyncio
async def test_team_row_without_an_attempt_is_a_blocker(db):
    cohort, item, team, *_ = await _scenario(db)
    row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    row.mission_attempt_id = None
    await db.flush()

    f = await _run(db, cohort, team)
    assert "NO_ATTEMPT" in _codes(f, audit.BLOCKER), f.rows


@pytest.mark.asyncio
async def test_member_missing_from_the_frozen_snapshot_is_a_blocker(db):
    """Bug 2, as Reem hit it: on the team, absent from
    mission_attempt_members, so `_own_attempt` 404s her."""
    cohort, item, team, _mission, _variant, _alice, bob = await _scenario(db)
    row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    snapshot_row = await db.get(MissionAttemptMember, (row.mission_attempt_id, bob.id))
    await db.delete(snapshot_row)
    await db.flush()

    f = await _run(db, cohort, team)
    assert "MEMBER_LOCKED_OUT" in _codes(f, audit.BLOCKER), f.rows
    assert any("Bob" in detail for _s, code, _w, detail in f.rows if code == "MEMBER_LOCKED_OUT")


@pytest.mark.asyncio
async def test_empty_snapshot_is_a_blocker(db):
    cohort, item, team, _mission, _variant, alice, bob = await _scenario(db)
    row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item.id, LmsProgramTeamItemProgress.team_id == team.id,
        )
    )
    for u in (alice, bob):
        await db.delete(await db.get(MissionAttemptMember, (row.mission_attempt_id, u.id)))
    await db.flush()

    f = await _run(db, cohort, team)
    assert "EMPTY_SNAPSHOT" in _codes(f, audit.BLOCKER), f.rows


@pytest.mark.asyncio
async def test_a_former_member_left_frozen_in_is_info_not_a_blocker(db):
    """The deliberate half of the snapshot's design — someone who left keeps
    access so their grade still means something. Must never read as a bug."""
    cohort, item, team, _mission, _variant, _alice, bob = await _scenario(db)
    membership = await db.scalar(
        select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == bob.id)
    )
    await db.delete(membership)
    await db.flush()

    f = await _run(db, cohort, team)
    assert "STALE_SNAPSHOT_MEMBER" in _codes(f, audit.INFO), f.rows
    assert _codes(f, audit.BLOCKER) == set(), f.rows


@pytest.mark.asyncio
async def test_empty_team_is_info_not_a_blocker(db):
    cohort, _item, team, _mission, _variant, alice, bob = await _scenario(db)
    for u in (alice, bob):
        await db.delete(await db.scalar(
            select(TeamMember).where(TeamMember.team_id == team.id, TeamMember.user_id == u.id)
        ))
    await db.flush()

    f = await _run(db, cohort, team)
    assert _codes(f, audit.INFO) == {"EMPTY_TEAM"}, f.rows
    assert _codes(f, audit.BLOCKER) == set(), f.rows


@pytest.mark.asyncio
async def test_duplicate_live_attempts_are_flagged(db):
    cohort, item, team, mission, variant, *_ = await _scenario(db)
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, team_id=team.id,
        attempt_no=99, status="in_progress", payload={}, cohort_id=cohort.id,
    ))
    await db.flush()

    f = await _run(db, cohort, team)
    assert "DUPLICATE_ATTEMPTS" in _codes(f, audit.WARN), f.rows


@pytest.mark.asyncio
async def test_missing_individual_row_is_flagged(db):
    """The tile doesn't render at all for that student, even though the team
    side is healthy."""
    cohort, item, team, _mission, _variant, _alice, bob = await _scenario(db)
    assignment = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == bob.id, LmsProgramAssignment.cohort_id == cohort.id,
        )
    )
    await db.delete(await db.scalar(
        select(LmsProgramItemProgress).where(
            LmsProgramItemProgress.assignment_id == assignment.id,
            LmsProgramItemProgress.item_id == item.id,
        )
    ))
    await db.flush()

    f = await _run(db, cohort, team)
    assert "NO_INDIVIDUAL_ROW" in _codes(f, audit.WARN), f.rows
