"""Checkpoint milestone gates (team-scoped `item_type="checkpoint"`):
- lock readiness is team-only (individual items never block the lock)
- everything below an unlocked checkpoint is hard-locked (409 on write)
- locking freezes team items above it, individual items stay editable
- checkpoints lock in sequence (no skipping ahead)
- design-mission slice: frozen phases 409 on step confirm, other edits stay open
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramTeamItemProgress,
)
from app.models.team import Team
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program
from app.services.teams import create_team

_VARIANT_CONFIG = {
    "max_storage_kb": 1_048_576.0, "required_storage_margin_kb": 0.0,
    "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
    "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
    "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
    "max_depth_of_discharge_pct": 30.0, "required_downlink_margin_fraction": 0.10,
}


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name=f"Checkpoint Student {uuid.uuid4().hex[:4]}", contact_roles=["student"],
        email=f"chk-std-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(contact)
    await db.flush()
    u = User(
        id=uuid.uuid4(), contact_id=contact.id, email=contact.email,
        full_name=contact.full_name, roles=["student"], password_hash="x", status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _ops(db) -> User:
    u = User(
        id=uuid.uuid4(), email=f"chk-ops-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Checkpoint Ops", roles=["operations"], password_hash="x", status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _program_and_cohort(db) -> tuple[Program, Cohort, LmsProgram]:
    program = Program(
        id=uuid.uuid4(), code=f"CHK-{uuid.uuid4().hex[:6]}", name="Checkpoint Program",
        program_type="competition", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Checkpoint Cohort", status="running",
        starts_on=date.today(), ends_on=date.today() + timedelta(days=7),
    )
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Checkpoint Checklist")
    db.add(lms_program)
    await db.flush()
    return program, cohort, lms_program


def _item(owner_id, position, item_type, title, **kw) -> LmsProgramItem:
    base = dict(
        id=uuid.uuid4(), owner_type="program", owner_id=owner_id, position=position,
        item_type=item_type, title=title, scope="team",
    )
    base.update(kw)
    return LmsProgramItem(**base)


@pytest.mark.asyncio
async def test_checkpoint_lock_team_only_freeze_and_sequence(db, client):
    """pos1 submission(team) → pos2 submission(individual, left undone) →
    pos3 checkpoint → pos4 manual(team) → pos5 checkpoint."""
    ops = await _ops(db)
    _, cohort, lms_program = await _program_and_cohort(db)
    db.add(_item(lms_program.id, 1, "submission", "Team deliverable",
                 external_url="https://example.com/spec", submission_prompt="Paste the link"))
    db.add(_item(lms_program.id, 2, "submission", "Personal note",
                 scope="individual", external_url="https://example.com/me", submission_prompt="Paste yours"))
    cp1 = _item(lms_program.id, 3, "checkpoint", "Gate 1")
    db.add(cp1)
    task_b = _item(lms_program.id, 4, "manual", "Task B")
    db.add(task_b)
    cp2 = _item(lms_program.id, 5, "checkpoint", "Gate 2")
    db.add(cp2)
    alice = await _student(db)
    bob = await _student(db)
    await create_team(db, name="Checkpoint Crew", created_by=alice.id, cohort_id=cohort.id, member_ids=[bob.id])
    await db.commit()
    a_alice = await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    a_bob = await assign_lms_program(db, user_id=bob.id, cohort_id=cohort.id)
    await db.commit()

    # Task B is hard-locked below the unlocked checkpoint (gated=False).
    checklist = (await client.get(f"/lms/programs/{a_alice.id}", headers=_headers(alice))).json()
    by_title = {i["title"]: i for i in checklist["items"]}
    assert by_title["Task B"]["locked"] is True
    assert by_title["Gate 1"]["locked"] is False  # own section incomplete, tile still open

    # Writes below the unlocked checkpoint 409.
    denied = await client.post(
        f"/lms/programs/{a_alice.id}/items/{task_b.id}/complete", headers=_headers(alice),
    )
    assert denied.status_code == http_status.HTTP_409_CONFLICT, denied.text

    # Skipping ahead to Gate 2 while Gate 1 is unlocked 409s.
    skip = await client.post(
        f"/lms/programs/{a_alice.id}/items/{cp2.id}/lock-checkpoint", headers=_headers(alice),
    )
    assert skip.status_code == http_status.HTTP_409_CONFLICT, skip.text

    # Section incomplete → 400.
    early = await client.post(
        f"/lms/programs/{a_alice.id}/items/{cp1.id}/lock-checkpoint", headers=_headers(alice),
    )
    assert early.status_code == http_status.HTTP_400_BAD_REQUEST, early.text
    assert "Team deliverable" in early.json()["detail"]

    # Finish the team section. The individual item stays undone on purpose.
    sub = await client.post(
        f"/lms/programs/{a_alice.id}/items/{by_title['Team deliverable']['id']}/submit",
        headers=_headers(alice), json={"url": "https://example.com/team-deliverable"},
    )
    assert sub.status_code == http_status.HTTP_200_OK, sub.text

    # Locks even though the individual item is still pending (team-only rule).
    lock = await client.post(
        f"/lms/programs/{a_alice.id}/items/{cp1.id}/lock-checkpoint", headers=_headers(alice),
    )
    assert lock.status_code == http_status.HTTP_200_OK, lock.text
    assert lock.json()["status"] == "done"
    row = await db.scalar(select(LmsProgramTeamItemProgress).where(
        LmsProgramTeamItemProgress.item_id == cp1.id,
    ))
    assert row is not None and row.status == "done" and row.confirmed_by_user_id == alice.id

    # Task B opens; the checkpoint itself can't be self-checked.
    checklist = (await client.get(f"/lms/programs/{a_alice.id}", headers=_headers(alice))).json()
    assert {i["title"]: i for i in checklist["items"]}["Task B"]["locked"] is False
    misuse = await client.post(
        f"/lms/programs/{a_alice.id}/items/{cp1.id}/complete", headers=_headers(alice),
    )
    assert misuse.status_code == http_status.HTTP_400_BAD_REQUEST, misuse.text

    # Team item above the locked checkpoint is frozen (409); the
    # individual item above it stays editable; items below stay open.
    frozen = await client.post(
        f"/lms/programs/{a_alice.id}/items/{by_title['Team deliverable']['id']}/submit",
        headers=_headers(alice), json={"url": "https://example.com/team-deliverable-v2"},
    )
    assert frozen.status_code == http_status.HTTP_409_CONFLICT, frozen.text
    personal = await client.post(
        f"/lms/programs/{a_alice.id}/items/{by_title['Personal note']['id']}/submit",
        headers=_headers(alice), json={"url": "https://example.com/my-note"},
    )
    assert personal.status_code == http_status.HTTP_200_OK, personal.text
    below = await client.post(
        f"/lms/programs/{a_alice.id}/items/{task_b.id}/complete", headers=_headers(alice),
    )
    assert below.status_code == http_status.HTTP_200_OK, below.text

    # Any teammate can lock the next gate — bob locks Gate 2 on his own assignment.
    lock2 = await client.post(
        f"/lms/programs/{a_bob.id}/items/{cp2.id}/lock-checkpoint", headers=_headers(bob),
    )
    assert lock2.status_code == http_status.HTTP_200_OK, lock2.text


@pytest.mark.asyncio
async def test_checkpoint_authoring_validation(db, client):
    ops = await _ops(db)
    _, _, lms_program = await _program_and_cohort(db)
    await db.commit()
    url = f"/lms/admin/programs/{lms_program.id}/items"

    individual = await client.post(
        url, headers=_headers(ops),
        json={"item_type": "checkpoint", "title": "Gate", "scope": "individual"},
    )
    assert individual.status_code == http_status.HTTP_400_BAD_REQUEST, individual.text

    optional = await client.post(
        url, headers=_headers(ops),
        json={"item_type": "checkpoint", "title": "Gate", "scope": "team", "optional": True},
    )
    assert optional.status_code == http_status.HTTP_400_BAD_REQUEST, optional.text

    linked = await client.post(
        url, headers=_headers(ops),
        json={"item_type": "checkpoint", "title": "Gate", "scope": "team",
              "external_url": "https://example.com/nope"},
    )
    assert linked.status_code == http_status.HTTP_400_BAD_REQUEST, linked.text

    ok = await client.post(
        url, headers=_headers(ops),
        json={"item_type": "checkpoint", "title": "Gate", "scope": "team",
              "description": "Finish phase one"},
    )
    assert ok.status_code == http_status.HTTP_201_CREATED, ok.text
    assert ok.json()["scope"] == "team" and ok.json()["optional"] is False


@pytest.mark.asyncio
async def test_checkpoint_freezes_design_confirm_but_not_edits(db, client):
    """Team design tile (setup phase) above a checkpoint: after the lock,
    confirming that phase 409s while plain design edits stay open."""
    ops = await _ops(db)
    mission = Mission(
        id=uuid.uuid4(), title="Frozen Design", slug=f"frozen-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=ops.id, status="published", summary="Design one.",
        team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=100,
        config=_VARIANT_CONFIG,
    )
    db.add(variant)
    await db.flush()
    _, cohort, lms_program = await _program_and_cohort(db)
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title=mission.title, mission_id=mission.id, variant_id=variant.id,
        scope="team", mission_step_key="setup",
    ))
    cp = _item(lms_program.id, 2, "checkpoint", "Design gate")
    db.add(cp)
    student = await _student(db)
    await db.commit()

    team = await create_team(db, name="Frozen Designers", created_by=student.id, cohort_id=cohort.id, member_ids=[])
    await db.commit()
    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    attempt = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.mission_id == mission.id)
    )).scalars().one()
    h = _headers(student)

    # The setup tile needs its objective set + explicit self-check before
    # it reads done (design tiles need both validity AND confirmation).
    objective = await client.patch(
        f"/missions/design/attempts/{attempt.id}", headers=h,
        json={"design_objective": "Map the southern highlands"},
    )
    assert objective.status_code == http_status.HTTP_200_OK, objective.text
    confirm = await client.post(
        f"/missions/design/attempts/{attempt.id}/steps/setup/confirm", headers=h,
    )
    assert confirm.status_code == http_status.HTTP_200_OK, confirm.text

    # Section done → lockable.
    lock = await client.post(
        f"/lms/programs/{assignment.id}/items/{cp.id}/lock-checkpoint", headers=h,
    )
    assert lock.status_code == http_status.HTTP_200_OK, lock.text

    # Re-confirming the frozen phase 409s (freeze fires before the
    # confirm endpoint's own idempotent path).
    frozen = await client.post(
        f"/missions/design/attempts/{attempt.id}/steps/setup/confirm", headers=h,
    )
    assert frozen.status_code == http_status.HTTP_409_CONFLICT, frozen.text
    assert "frozen by a locked checkpoint" in frozen.json()["detail"]

    # An unrelated phase is not frozen (fails readiness, not the freeze)…
    other = await client.post(
        f"/missions/design/attempts/{attempt.id}/steps/components/confirm", headers=h,
    )
    assert other.status_code != http_status.HTTP_409_CONFLICT, other.text

    # …and plain design edits on the shared attempt stay open.
    edit = await client.patch(
        f"/missions/design/attempts/{attempt.id}", headers=h,
        json={"design_name": "Still iterating downstream"},
    )
    assert edit.status_code == http_status.HTTP_200_OK, edit.text


@pytest.mark.asyncio
async def test_ops_unlock_checkpoint_cascades_and_clears_final_lock(db, client):
    """pos1 manual(team) → pos2 Gate 1 → pos3 manual(team) → pos4 Gate 2.
    Lock everything, final-submit, then ops unlocks Gate 1: both gates
    reset, the final lock clears (first lock kept for audit), section
    work stays done, and the team can re-lock forward."""
    ops = await _ops(db)
    _, cohort, lms_program = await _program_and_cohort(db)
    task_a = _item(lms_program.id, 1, "manual", "Task A")
    db.add(task_a)
    cp1 = _item(lms_program.id, 2, "checkpoint", "Gate 1")
    db.add(cp1)
    task_b = _item(lms_program.id, 3, "manual", "Task B")
    db.add(task_b)
    cp2 = _item(lms_program.id, 4, "checkpoint", "Gate 2")
    db.add(cp2)
    alice = await _student(db)
    await db.commit()
    team = await create_team(db, name="Cascade Crew", created_by=alice.id, cohort_id=cohort.id, member_ids=[])
    await db.commit()
    assignment = await assign_lms_program(db, user_id=alice.id, cohort_id=cohort.id)
    await db.commit()
    h = _headers(alice)

    for item in (task_a,):
        r = await client.post(f"/lms/programs/{assignment.id}/items/{item.id}/complete", headers=h)
        assert r.status_code == http_status.HTTP_200_OK, r.text
    r = await client.post(f"/lms/programs/{assignment.id}/items/{cp1.id}/lock-checkpoint", headers=h)
    assert r.status_code == http_status.HTTP_200_OK, r.text
    r = await client.post(f"/lms/programs/{assignment.id}/items/{task_b.id}/complete", headers=h)
    assert r.status_code == http_status.HTTP_200_OK, r.text
    r = await client.post(f"/lms/programs/{assignment.id}/items/{cp2.id}/lock-checkpoint", headers=h)
    assert r.status_code == http_status.HTTP_200_OK, r.text
    final = await client.post(f"/lms/programs/{assignment.id}/final-submit", headers=h)
    assert final.status_code == http_status.HTTP_200_OK, final.text

    team_row = await db.get(Team, team.id)
    assert team_row.final_locked_at is not None and team_row.first_locked_at is not None

    states = await client.get(
        f"/competitions/admin/teams/{team.id}/checkpoints", headers=_headers(ops),
    )
    assert states.status_code == http_status.HTTP_200_OK, states.text
    assert [(s["title"], s["status"]) for s in states.json()] == [("Gate 1", "done"), ("Gate 2", "done")]

    unlock = await client.post(
        f"/competitions/admin/teams/{team.id}/unlock-checkpoint/{cp1.id}", headers=_headers(ops),
    )
    assert unlock.status_code == http_status.HTTP_200_OK, unlock.text

    # Both gates reset; section work untouched.
    for cp in (cp1, cp2):
        row = await db.scalar(select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.team_id == team.id,
            LmsProgramTeamItemProgress.item_id == cp.id,
        ))
        assert row.status == "pending" and row.completed_at is None and row.confirmed_by_user_id is None
    kept = await db.scalar(select(LmsProgramTeamItemProgress).where(
        LmsProgramTeamItemProgress.team_id == team.id,
        LmsProgramTeamItemProgress.item_id == task_b.id,
    ))
    assert kept.status == "done"

    # Final lock cleared, first lock preserved for audit.
    await db.refresh(team_row)
    assert team_row.final_locked_at is None and team_row.final_locked_by is None
    assert team_row.first_locked_at is not None

    # Reopening Gate 1 re-locks everything below it; re-locking opens it again.
    checklist = (await client.get(f"/lms/programs/{assignment.id}", headers=h)).json()
    assert {i["title"]: i for i in checklist["items"]}["Task B"]["locked"] is True
    relock = await client.post(
        f"/lms/programs/{assignment.id}/items/{cp1.id}/lock-checkpoint", headers=h,
    )
    assert relock.status_code == http_status.HTTP_200_OK, relock.text
    reopened = (await client.get(f"/lms/programs/{assignment.id}", headers=h)).json()
    assert {i["title"]: i for i in reopened["items"]}["Task B"]["locked"] is False
    # The cascaded Gate 2 is lockable again (its section work survived).
    relock2 = await client.post(
        f"/lms/programs/{assignment.id}/items/{cp2.id}/lock-checkpoint", headers=h,
    )
    assert relock2.status_code == http_status.HTTP_200_OK, relock2.text

    # Misuse: not a checkpoint → 400; unknown item → 404; unknown team → 404.
    not_cp = await client.post(
        f"/competitions/admin/teams/{team.id}/unlock-checkpoint/{task_a.id}", headers=_headers(ops),
    )
    assert not_cp.status_code == http_status.HTTP_400_BAD_REQUEST, not_cp.text
    no_item = await client.post(
        f"/competitions/admin/teams/{team.id}/unlock-checkpoint/{uuid.uuid4()}", headers=_headers(ops),
    )
    assert no_item.status_code == http_status.HTTP_404_NOT_FOUND, no_item.text
    no_team = await client.post(
        f"/competitions/admin/teams/{uuid.uuid4()}/unlock-checkpoint/{cp1.id}", headers=_headers(ops),
    )
    assert no_team.status_code == http_status.HTTP_404_NOT_FOUND, no_team.text
