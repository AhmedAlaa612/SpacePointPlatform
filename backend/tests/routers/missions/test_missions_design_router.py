"""P7-5 router tests — the design mission HTTP surface end to end.
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.design import DesignComponentLibrary
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


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
