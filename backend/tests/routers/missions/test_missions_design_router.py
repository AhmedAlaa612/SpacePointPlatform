"""P7-5 router tests — the design mission HTTP surface end to end.
Redis-free (uses the `client` fixture).
"""

import uuid
from datetime import date, timedelta

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.design import DesignComponentLibrary
from app.models.missions.gate import MissionStepGate
from app.models.missions.mission import Mission, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions.registration import register


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Design Router User", email=f"dr-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _design_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Router CubeSat Mission", slug=f"router-design-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=2, points=200,
        config={
            "max_storage_kb": 1000.0, "required_storage_margin_kb": 50.0,
            "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
            "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
            "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _library_component(db) -> DesignComponentLibrary:
    comp = DesignComponentLibrary(
        id=uuid.uuid4(), component_name="Router Test Battery", subsystem="EPS",
        scaled_mass_g=100.0, length_mm=50.0, width_mm=50.0, height_mm=30.0,
        voltage_v=5.0, current_ma=100.0, assumed_cost_usd=50.0, is_active=True,
    )
    db.add(comp)
    await db.flush()
    return comp


@pytest.mark.asyncio
async def test_get_design_state_auto_creates_a_design(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert start.status_code == 201, start.text
    attempt_id = start.json()["id"]

    resp = await client.get(f"/missions/design/attempts/{attempt_id}", headers=_headers(student))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["attempt_id"] == attempt_id
    assert body["dashboard"]["all_valid"] is False
    assert len(body["modes"]) == 4  # default CONOPS modes


@pytest.mark.asyncio
async def test_library_listing_is_reachable_and_not_swallowed_by_attempt_route(db, client):
    author = await _user(db, roles=["operations"])
    await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    resp = await client.get("/missions/design/library", headers=_headers(student))
    assert resp.status_code == 200
    assert any(c["component_name"] == "Router Test Battery" for c in resp.json())


@pytest.mark.asyncio
async def test_complete_design_end_to_end_through_http(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]
    h = _headers(student)

    # Not ready yet — no components.
    incomplete = await client.post(f"/missions/design/attempts/{attempt_id}/complete", headers=h)
    assert incomplete.status_code == http_status.HTTP_400_BAD_REQUEST

    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=h)
    assert state.json()["attempt_status"] == "in_progress"  # 400 never touched it

    # Add the component.
    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=h,
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    assert add.status_code == 201, add.text
    dc_id = add.json()["components"][0]["id"]
    mode_ids = [m["id"] for m in add.json()["modes"]]

    # CONOPS: even split of 90 min across 4 modes, component ON in one.
    conops = await client.post(
        f"/missions/design/attempts/{attempt_id}/conops", headers=h,
        json={
            "mode_durations": {mid: 22.5 for mid in mode_ids},
            "cell_states": {dc_id: {mode_ids[0]: True}},
        },
    )
    assert conops.status_code == 200, conops.text

    await client.patch(
        f"/missions/design/attempts/{attempt_id}", headers=h,
        json={"orbit_duration_min": 90.0, "orbits_per_day": 15.0, "selected_solar_cells": 5,
              "battery_capacity_wh": 10.0},
    )

    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/data-budget", headers=h,
        json={"data_size_per_measurement_kb": 0.1, "measurements_per_minute": 1.0, "storage_mode": "Both"},
    )
    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/power-budget", headers=h,
        json={"voltage_v": 5.0, "current_ma": 100.0},
    )
    await client.post(f"/missions/design/attempts/{attempt_id}/components/{dc_id}/mass-budget", headers=h, json={})
    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=h,
        json={"cost_per_unit_aed": 50.0},
    )
    link = await client.post(
        f"/missions/design/attempts/{attempt_id}/link-budget", headers=h,
        json={
            "band_profile": "UHF", "downlink_frequency_mhz": 437.5, "uplink_frequency_mhz": 145.8,
            "satellite_antenna_gain_dbi": 2.0, "data_rate_kbps": 9.6, "required_signal_quality_db": 9.6,
        },
    )
    assert link.status_code == 200, link.text
    assert link.json()["dashboard"]["all_valid"] is True, link.json()["dashboard"]["steps"]

    complete = await client.post(f"/missions/design/attempts/{attempt_id}/complete", headers=h)
    assert complete.status_code == 200, complete.text
    assert complete.json()["attempt_status"] == "passed"


@pytest.mark.asyncio
async def test_confirming_every_step_auto_finalizes_without_a_separate_complete_call(db, client):
    """2026-09 — a separate "Mark design complete" click is redundant once
    every step has been explicitly self-checked: confirm_design_step itself
    finalizes the attempt the moment the last required step is confirmed
    and the design is fully valid, exactly what /complete used to require
    a distinct call for. Same data-fill sequence as
    test_complete_design_end_to_end_through_http, but this one never calls
    POST .../complete at all."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]
    h = _headers(student)

    setup = await client.patch(f"/missions/design/attempts/{attempt_id}", headers=h, json={"design_objective": "Track weather."})
    assert setup.status_code == 200, setup.text
    confirm_setup = await client.post(f"/missions/design/attempts/{attempt_id}/steps/setup/confirm", headers=h)
    assert confirm_setup.status_code == 200, confirm_setup.text

    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=h,
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    dc_id = add.json()["components"][0]["id"]
    mode_ids = [m["id"] for m in add.json()["modes"]]
    confirm_components = await client.post(f"/missions/design/attempts/{attempt_id}/steps/components/confirm", headers=h)
    assert confirm_components.status_code == 200, confirm_components.text

    conops = await client.post(
        f"/missions/design/attempts/{attempt_id}/conops", headers=h,
        json={"mode_durations": {mid: 22.5 for mid in mode_ids}, "cell_states": {dc_id: {mode_ids[0]: True}}},
    )
    assert conops.status_code == 200, conops.text

    # Must land before confirming CONOPS — its own validity is checked
    # against orbit_duration_min (mode_durations must sum to it), which
    # isn't set until this PATCH.
    await client.patch(
        f"/missions/design/attempts/{attempt_id}", headers=h,
        json={"orbit_duration_min": 90.0, "orbits_per_day": 15.0, "selected_solar_cells": 5,
              "battery_capacity_wh": 10.0},
    )
    confirm_conops = await client.post(f"/missions/design/attempts/{attempt_id}/steps/conops/confirm", headers=h)
    assert confirm_conops.status_code == 200, confirm_conops.text

    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/data-budget", headers=h,
        json={"data_size_per_measurement_kb": 0.1, "measurements_per_minute": 1.0, "storage_mode": "Both"},
    )
    confirm_data = await client.post(f"/missions/design/attempts/{attempt_id}/steps/data_budget/confirm", headers=h)
    assert confirm_data.status_code == 200, confirm_data.text

    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/power-budget", headers=h,
        json={"voltage_v": 5.0, "current_ma": 100.0},
    )
    confirm_power = await client.post(f"/missions/design/attempts/{attempt_id}/steps/power_budget/confirm", headers=h)
    assert confirm_power.status_code == 200, confirm_power.text

    await client.post(f"/missions/design/attempts/{attempt_id}/components/{dc_id}/mass-budget", headers=h, json={})
    confirm_mass = await client.post(f"/missions/design/attempts/{attempt_id}/steps/mass_budget/confirm", headers=h)
    assert confirm_mass.status_code == 200, confirm_mass.text

    await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=h,
        json={"cost_per_unit_aed": 50.0},
    )
    confirm_cost = await client.post(f"/missions/design/attempts/{attempt_id}/steps/cost_budget/confirm", headers=h)
    assert confirm_cost.status_code == 200, confirm_cost.text

    link = await client.post(
        f"/missions/design/attempts/{attempt_id}/link-budget", headers=h,
        json={
            "band_profile": "UHF", "downlink_frequency_mhz": 437.5, "uplink_frequency_mhz": 145.8,
            "satellite_antenna_gain_dbi": 2.0, "data_rate_kbps": 9.6, "required_signal_quality_db": 9.6,
        },
    )
    assert link.status_code == 200, link.text
    assert link.json()["dashboard"]["all_valid"] is True, link.json()["dashboard"]["steps"]

    # link_budget is the last unconfirmed required step — confirming it
    # alone (no call to /complete anywhere in this test) must flip the
    # attempt straight to "passed".
    confirm_link = await client.post(f"/missions/design/attempts/{attempt_id}/steps/link_budget/confirm", headers=h)
    assert confirm_link.status_code == 200, confirm_link.text
    assert confirm_link.json()["attempt_status"] == "passed"


@pytest.mark.asyncio
async def test_cannot_act_on_another_students_design_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    await db.commit()
    alice = await _user(db)
    bob = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(alice), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.get(f"/missions/design/attempts/{attempt_id}", headers=_headers(bob))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


# ── per-cohort step gating (2026-08-17) ──────────────────────────────────

async def _cohort(db, **overrides) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"DGP-{uuid.uuid4().hex[:8]}", name="Design Gating Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    defaults = dict(id=uuid.uuid4(), program_id=program.id, name="Design Gating Cohort", status="running")
    defaults.update(overrides)
    cohort = Cohort(**defaults)
    db.add(cohort)
    await db.flush()
    return cohort


async def _registered_student(db, *, cohort: Cohort) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Gated Student", contact_roles=["student"],
        secondary_phones=[], preferred_language="en", lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    await register(db, contact_id=contact.id, cohort_id=cohort.id, registered_via="form")
    user = User(
        id=uuid.uuid4(), full_name="Gated Student", email=f"gated-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(user)
    await db.flush()
    return user


async def _assign_attempt(client, *, ops: User, student: User, mission: Mission, variant: MissionVariant, cohort: Cohort) -> str:
    """2026-08-21 (LMS Program redesign): a solo student-started attempt no
    longer auto-scopes to their registration's cohort — this is now the
    only way an attempt gets a cohort_id (besides the team path), so every
    gate/poster/deadline test below goes through it instead of the plain
    `POST /missions/{id}/attempts` a student would use for an independent run."""
    resp = await client.post(
        "/missions/admin/attempts/assign", headers=_headers(ops),
        json={"user_id": str(student.id), "mission_id": str(mission.id), "cohort_id": str(cohort.id), "variant_id": str(variant.id)},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_locked_step_blocks_the_write_endpoint(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    cohort = await _cohort(db)
    student = await _registered_student(db, cohort=cohort)
    db.add(MissionStepGate(cohort_id=cohort.id, mission_id=mission.id, step_key="components", is_unlocked=False))
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    # The gate's own step_key is explicitly locked.
    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=_headers(student),
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    assert add.status_code == http_status.HTTP_403_FORBIDDEN, add.text

    # A different step, with no gate row at all, is unaffected — missing
    # row means unlocked, not locked.
    conops = await client.post(
        f"/missions/design/attempts/{attempt_id}/conops", headers=_headers(student),
        json={"mode_durations": {}, "cell_states": {}},
    )
    assert conops.status_code == 200, conops.text


@pytest.mark.asyncio
async def test_unlocking_the_gate_allows_the_write(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    cohort = await _cohort(db)
    student = await _registered_student(db, cohort=cohort)
    db.add(MissionStepGate(cohort_id=cohort.id, mission_id=mission.id, step_key="components", is_unlocked=True))
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=_headers(student),
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    assert add.status_code == 201, add.text


@pytest.mark.asyncio
async def test_an_ungated_attempt_is_unaffected_by_gating_at_all(db, client):
    """Regression check: a student with no cohort (self-service, outside
    any workshop) never gets gated, even if the mission has gates set for
    other cohorts."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    other_cohort = await _cohort(db)
    db.add(MissionStepGate(cohort_id=other_cohort.id, mission_id=mission.id, step_key="components", is_unlocked=False))
    await db.commit()
    student = await _user(db)  # no Contact/Registration — no cohort at all
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=_headers(student),
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    assert add.status_code == 201, add.text


@pytest.mark.asyncio
async def test_design_state_reports_step_gates(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    cohort = await _cohort(db)
    student = await _registered_student(db, cohort=cohort)
    db.add(MissionStepGate(cohort_id=cohort.id, mission_id=mission.id, step_key="power_budget", is_unlocked=False))
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=_headers(student))
    gates = state.json()["step_gates"]
    assert gates["power_budget"] is False
    assert gates["components"] is True  # no row for this step -> unlocked
    assert gates["mass_budget"] is True  # no row for this step either -> unlocked


# ── Poster/Canva link fields (August Build Brief, Branch 3) ─────────────────

@pytest.mark.asyncio
async def test_design_state_resolves_poster_template_url_from_cohort(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    cohort = await _cohort(db, poster_template_url="https://canva.com/design/master-template")
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=_headers(student))
    assert state.json()["poster_template_url"] == "https://canva.com/design/master-template"
    assert state.json()["poster_url"] is None


@pytest.mark.asyncio
async def test_design_state_has_no_poster_template_url_outside_any_cohort(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)  # no Contact/Registration — no cohort at all
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=_headers(student))
    assert state.json()["poster_template_url"] is None


@pytest.mark.asyncio
async def test_update_design_rejects_an_absurd_solar_cell_count(db, client):
    """selected_solar_cells has no realistic upper bound in the domain, but
    the DB column is a 32-bit Integer — an unbounded schema used to let a
    huge pasted value sail past validation and 500 at the driver layer
    (OverflowError) instead of a clean 422."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.patch(
        f"/missions/design/attempts/{attempt_id}",
        headers=_headers(student), json={"selected_solar_cells": 400_000_000_000_000_000},
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, resp.text


@pytest.mark.asyncio
async def test_update_design_accepts_poster_url_with_no_deadline(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)  # no cohort, so never a deadline to violate
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.patch(
        f"/missions/design/attempts/{attempt_id}",
        headers=_headers(student), json={"poster_url": "https://canva.com/design/my-copy"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["poster_url"] == "https://canva.com/design/my-copy"


@pytest.mark.asyncio
async def test_update_design_accepts_poster_url_when_cohort_ends_in_the_future(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    cohort = await _cohort(db, ends_on=date.today() + timedelta(days=7))
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    resp = await client.patch(
        f"/missions/design/attempts/{attempt_id}",
        headers=_headers(student), json={"poster_url": "https://canva.com/design/my-copy"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["poster_url"] == "https://canva.com/design/my-copy"


@pytest.mark.asyncio
async def test_update_design_allows_poster_url_after_cohort_ends(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    cohort = await _cohort(db, ends_on=date.today() - timedelta(days=1))
    student = await _registered_student(db, cohort=cohort)
    await db.commit()

    attempt_id = await _assign_attempt(client, ops=author, student=student, mission=mission, variant=variant, cohort=cohort)

    resp = await client.patch(
        f"/missions/design/attempts/{attempt_id}",
        headers=_headers(student), json={"poster_url": "https://canva.com/design/my-copy"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["poster_url"] == "https://canva.com/design/my-copy"

    # A field-only PATCH untouched by the deadline (e.g. design_name) also goes through fine
    other = await client.patch(
        f"/missions/design/attempts/{attempt_id}",
        headers=_headers(student), json={"design_name": "Renamed"},
    )
    assert other.status_code == 200, other.text


async def _attempt_with_component(client, *, mission, variant, student, library):
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]
    add = await client.post(
        f"/missions/design/attempts/{attempt_id}/components", headers=_headers(student),
        json={"library_component_id": str(library.id), "quantity": 1},
    )
    return attempt_id, add.json()["components"][0]["id"]


@pytest.mark.asyncio
async def test_cost_budget_rejects_an_overlong_purchase_link(db, client):
    """DesignCostBudgetEntry.purchase_link is a DB String(512) — a pasted
    marketplace/tracking URL past that length used to sail through
    CostEntrySaveIn's unbounded str and crash at the driver layer
    (StringDataRightTruncationError -> 500) instead of a clean 422."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    attempt_id, dc_id = await _attempt_with_component(client, mission=mission, variant=variant, student=student, library=library)

    resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=_headers(student),
        json={"purchase_link": "https://example.com/" + "x" * 500},
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, resp.text


@pytest.mark.asyncio
async def test_cost_budget_accepts_a_purchase_link_at_the_max_length(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    attempt_id, dc_id = await _attempt_with_component(client, mission=mission, variant=variant, student=student, library=library)

    link = "https://example.com/" + "x" * (512 - len("https://example.com/"))
    assert len(link) == 512
    resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=_headers(student),
        json={"purchase_link": link},
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_cost_budget_rejects_an_overlong_vendor_or_priority(db, client):
    """Same unbounded-string-into-fixed-column bug as purchase_link, on
    DesignCostBudgetEntry's other two DB-capped columns (String(80) and
    String(12)) — found by a follow-up review pass, not the original log
    triage."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    attempt_id, dc_id = await _attempt_with_component(client, mission=mission, variant=variant, student=student, library=library)

    vendor_resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=_headers(student),
        json={"vendor": "x" * 81},
    )
    assert vendor_resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, vendor_resp.text

    priority_resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/cost-budget", headers=_headers(student),
        json={"priority": "x" * 13},
    )
    assert priority_resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, priority_resp.text


@pytest.mark.asyncio
async def test_data_budget_rejects_an_overlong_data_type_or_priority(db, client):
    """Same bug, on DesignDataBudgetEntry's String(60)/String(12) columns."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    library = await _library_component(db)
    await db.commit()
    student = await _user(db)
    await db.commit()

    attempt_id, dc_id = await _attempt_with_component(client, mission=mission, variant=variant, student=student, library=library)

    data_type_resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/data-budget", headers=_headers(student),
        json={"data_type": "x" * 61},
    )
    assert data_type_resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, data_type_resp.text

    priority_resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/components/{dc_id}/data-budget", headers=_headers(student),
        json={"priority": "x" * 13},
    )
    assert priority_resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, priority_resp.text


@pytest.mark.asyncio
async def test_link_budget_rejects_an_overlong_band_profile(db, client):
    """Same bug, on DesignLinkBudgetEntry's String(12) band_profile column."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    resp = await client.post(
        f"/missions/design/attempts/{attempt_id}/link-budget", headers=_headers(student),
        json={
            "band_profile": "x" * 13,
            "downlink_frequency_mhz": 437.5, "uplink_frequency_mhz": 145.8,
            "satellite_antenna_gain_dbi": 2.0, "data_rate_kbps": 9.6, "required_signal_quality_db": 9.6,
        },
    )
    assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, resp.text


@pytest.mark.asyncio
async def test_update_design_rejects_an_overlong_name_or_orbit_type_or_poster_url(db, client):
    """Same bug, on Design's String(128)/String(20)/String(512) columns."""
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    attempt_id = start.json()["id"]

    for field, value in (
        ("design_name", "x" * 129),
        ("orbit_type", "x" * 21),
        ("poster_url", "https://example.com/" + "x" * 500),
    ):
        resp = await client.patch(
            f"/missions/design/attempts/{attempt_id}", headers=_headers(student), json={field: value},
        )
        assert resp.status_code == http_status.HTTP_422_UNPROCESSABLE_CONTENT, (field, resp.text)
