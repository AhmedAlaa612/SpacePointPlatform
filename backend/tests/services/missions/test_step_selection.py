"""Cohort-scoped Design step *selection* (2026-08-17) — the compositional
picker service, distinct from `test_missions_instructor_router.py`'s
router-level gate tests. Covers the prerequisite closure, server-side
expansion/validation, and the default-all-steps backward-compat path.
"""

import uuid

import pytest
from fastapi import HTTPException

from app.models.missions.mission import Mission, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.services.lms.admin_progress import SELECTABLE_STEP_KEYS
from app.services.missions.step_selection import (
    clear_selected_steps, expand_with_prereqs, selected_steps_for_cohort_mission, set_selected_steps,
)


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Step Selection Author", email=f"steps-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=roles or ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _mission(db, *, author) -> Mission:
    mission = Mission(
        id=uuid.uuid4(), title="Step Selection Mission", slug=f"step-sel-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published",
    )
    db.add(mission)
    await db.flush()
    db.add(MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=100))
    await db.flush()
    return mission


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"STP-{uuid.uuid4().hex[:8]}", name="Step Selection Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Step Selection Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


# ── expand_with_prereqs (pure closure logic) ─────────────────────────────

def test_components_and_link_budget_have_no_prereqs():
    assert expand_with_prereqs({"components"}) == {"components"}
    assert expand_with_prereqs({"link_budget"}) == {"link_budget"}  # genuinely independent


def test_conops_has_no_hard_prereq():
    assert expand_with_prereqs({"conops"}) == {"conops"}


def test_power_and_data_budget_pull_in_components_only_not_conops():
    """The correction that matters most: the TDRA Summer Camp case selects
    Power without CONOPS, because calc_power_budget's is_valid never reads
    modes/conops at all."""
    assert expand_with_prereqs({"power_budget"}) == {"power_budget", "components"}
    assert expand_with_prereqs({"data_budget"}) == {"data_budget", "components"}


def test_energy_budget_transitively_pulls_in_power_and_components():
    assert expand_with_prereqs({"energy_budget"}) == {"energy_budget", "power_budget", "components"}


def test_mass_and_cost_budget_pull_in_components_only():
    assert expand_with_prereqs({"mass_budget"}) == {"mass_budget", "components"}
    assert expand_with_prereqs({"cost_budget"}) == {"cost_budget", "components"}


def test_closure_of_everything_is_idempotent_and_complete():
    assert expand_with_prereqs(set(SELECTABLE_STEP_KEYS)) == set(SELECTABLE_STEP_KEYS)


def test_unknown_key_is_rejected():
    with pytest.raises(HTTPException) as exc:
        expand_with_prereqs({"components", "not_a_real_step"})
    assert exc.value.status_code == 400


def test_downlink_is_rejected_not_a_directly_selectable_step():
    with pytest.raises(HTTPException) as exc:
        expand_with_prereqs({"downlink"})
    assert exc.value.status_code == 400


# ── selected_steps_for_cohort_mission / set_selected_steps / clear ──────

@pytest.mark.asyncio
async def test_no_rows_means_every_selectable_step_is_the_default(db):
    author = await _user(db)
    mission = await _mission(db, author=author)
    cohort = await _cohort(db)
    await db.commit()

    included = await selected_steps_for_cohort_mission(db, cohort_id=cohort.id, mission_id=mission.id)
    assert included == set(SELECTABLE_STEP_KEYS)


@pytest.mark.asyncio
async def test_set_selected_steps_rejects_empty_set(db):
    author = await _user(db)
    mission = await _mission(db, author=author)
    cohort = await _cohort(db)
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await set_selected_steps(db, cohort_id=cohort.id, mission_id=mission.id, step_keys=[], created_by=author.id)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_set_selected_steps_replaces_not_merges(db):
    """A second PUT fully supersedes the first, rather than unioning with it."""
    author = await _user(db)
    mission = await _mission(db, author=author)
    cohort = await _cohort(db)
    await db.commit()

    first = await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id, step_keys=["mass_budget"], created_by=author.id,
    )
    await db.commit()
    assert first == {"mass_budget", "components"}

    second = await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id, step_keys=["link_budget"], created_by=author.id,
    )
    await db.commit()
    assert second == {"link_budget"}  # mass_budget/components from the first PUT are gone

    resolved = await selected_steps_for_cohort_mission(db, cohort_id=cohort.id, mission_id=mission.id)
    assert resolved == {"link_budget"}


@pytest.mark.asyncio
async def test_clear_selected_steps_resets_to_default(db):
    author = await _user(db)
    mission = await _mission(db, author=author)
    cohort = await _cohort(db)
    await db.commit()

    await set_selected_steps(
        db, cohort_id=cohort.id, mission_id=mission.id, step_keys=["cost_budget"], created_by=author.id,
    )
    await db.commit()
    await clear_selected_steps(db, cohort_id=cohort.id, mission_id=mission.id)
    await db.commit()

    included = await selected_steps_for_cohort_mission(db, cohort_id=cohort.id, mission_id=mission.id)
    assert included == set(SELECTABLE_STEP_KEYS)
