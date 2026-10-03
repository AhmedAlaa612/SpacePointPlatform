"""Custom components (student-defined parts) — privacy, snapshot, and ops visibility.

Attempt-scoped by design: only the owning attempt's student (or teammates)
can list or place a custom part; any other student gets 404/empty. Ops sees
everything via design-detail and the admin explorer.
"""

import uuid

import pytest

from app.core.security import create_access_token
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Custom Parts User", email=f"cc-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _design_mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Custom Parts Mission", slug=f"custom-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=2, points=200,
        config={
            "max_storage_kb": 1_000_000.0, "required_storage_margin_kb": 50.0,
            "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 200_000.0,
            "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
            "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


def _custom_body(**over) -> dict:
    body = {
        "component_name": "Optical Camera HS-100",
        "subsystem": "payload",  # lowercase on purpose — must normalize to Payload
        "purpose_function": "Captures multispectral Earth imagery during Nadir mode passes.",
        "voltage_v": 3.3,
        "current_ma": 150.0,
        "pins_used": "Pin 1: 3V3, Pin 2: GND, Pin 3: SPI_MOSI",
        "measurement_output": "1080p raw spectral frames",
        "measurement_range": "400nm - 900nm",
        "datasheet_reference": "https://vendor.example/hs100.pdf",
        "mass_g": 65.0,
        "length_mm": 38.0,
        "width_mm": 38.0,
        "height_mm": 25.0,
        "cost_aed": 450.0,
        "quantity": 1,
    }
    body.update(over)
    return body


async def _attempt(client, db, mission, variant, student) -> str:
    await db.commit()
    start = await client.post(
        f"/missions/{mission.id}/attempts", headers=_headers(student), json={"variant_id": str(variant.id)},
    )
    assert start.status_code == 201, start.text
    return start.json()["id"]


@pytest.mark.asyncio
async def test_custom_component_create_lists_and_powers_budgets(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt_id = await _attempt(client, db, mission, variant, student)
    h = _headers(student)

    created = await client.post(
        f"/missions/design/attempts/{attempt_id}/custom-components", headers=h, json=_custom_body(),
    )
    assert created.status_code == 201, created.text
    comps = created.json()["components"]
    assert len(comps) == 1
    snap = comps[0]
    assert snap["is_custom"] is True
    assert snap["library_component_id"] is None
    assert snap["custom_component_id"] is not None
    assert snap["subsystem"] == "Payload"  # normalized casing
    assert snap["power_computed_mw"] == pytest.approx(3.3 * 150.0)
    assert snap["cost_per_unit_aed"] == pytest.approx(450.0)  # AED verbatim, no conversion
    assert snap["purpose_function"].startswith("Captures multispectral")

    # Own list endpoint returns it with derived power.
    listed = await client.get(f"/missions/design/attempts/{attempt_id}/custom-components", headers=h)
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["power_computed_mw"] == pytest.approx(495.0)

    # Power budget reflects V*I through the snapshot (495 mW peak).
    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=h)
    assert state.json()["dashboard"]["power"]["total_power_mw"] == pytest.approx(495.0)


@pytest.mark.asyncio
async def test_custom_component_private_to_owning_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    alice = await _user(db)
    bob = await _user(db)
    attempt_a = await _attempt(client, db, mission, variant, alice)
    attempt_b = await _attempt(client, db, mission, variant, bob)

    created = await client.post(
        f"/missions/design/attempts/{attempt_a}/custom-components",
        headers=_headers(alice), json=_custom_body(),
    )
    assert created.status_code == 201, created.text
    custom_id = created.json()["components"][0]["custom_component_id"]

    # Bob's list is empty and Bob can't steal the part (404, not 403).
    bob_list = await client.get(
        f"/missions/design/attempts/{attempt_b}/custom-components", headers=_headers(bob),
    )
    assert bob_list.status_code == 200 and bob_list.json() == []
    steal = await client.post(
        f"/missions/design/attempts/{attempt_b}/components",
        headers=_headers(bob), json={"custom_component_id": custom_id, "quantity": 1},
    )
    assert steal.status_code == 404, steal.text

    # Re-add after cart removal works through the standard components endpoint.
    design_comp_id = created.json()["components"][0]["id"]
    removed = await client.delete(
        f"/missions/design/attempts/{attempt_a}/components/{design_comp_id}", headers=_headers(alice),
    )
    assert removed.status_code == 200 and removed.json()["components"] == []
    readded = await client.post(
        f"/missions/design/attempts/{attempt_a}/components",
        headers=_headers(alice), json={"custom_component_id": custom_id, "quantity": 2},
    )
    assert readded.status_code == 201, readded.text
    assert readded.json()["components"][0]["quantity"] == 2


@pytest.mark.asyncio
async def test_custom_edit_does_not_rewrite_snapshot_and_ops_can_inspect(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    ops = await _user(db, roles=["operations"])
    attempt_id = await _attempt(client, db, mission, variant, student)
    h = _headers(student)

    created = await client.post(
        f"/missions/design/attempts/{attempt_id}/custom-components", headers=h, json=_custom_body(),
    )
    custom_id = created.json()["components"][0]["custom_component_id"]

    # Edit the definition (mass 65 -> 999): the placed snapshot must not move.
    patched = await client.patch(
        f"/missions/design/attempts/{attempt_id}/custom-components/{custom_id}",
        headers=h, json={"mass_g": 999.0},
    )
    assert patched.status_code == 200
    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=h)
    assert state.json()["components"][0]["mass_per_unit_g"] == pytest.approx(65.0)

    # Ops sees the custom row in design-detail with the full spec.
    detail = await client.get(f"/missions/admin/attempts/{attempt_id}/design-detail", headers=_headers(ops))
    assert detail.status_code == 200, detail.text
    row = detail.json()["components"][0]
    assert row["is_custom"] is True and row["pins_used"].startswith("Pin 1")

    # Ops explorer lists it with attribution + filters.
    explorer = await client.get("/missions/admin/custom-components", headers=_headers(ops))
    assert explorer.status_code == 200
    assert any(r["component_name"] == "Optical Camera HS-100" for r in explorer.json())
    filtered = await client.get(
        "/missions/admin/custom-components", headers=_headers(ops),
        params={"subsystem": "Payload", "search": "HS-100"},
    )
    assert len(filtered.json()) == 1
    assert filtered.json()[0]["student_name"] is not None
    empty = await client.get(
        "/missions/admin/custom-components", headers=_headers(ops), params={"subsystem": "EPS"},
    )
    assert empty.json() == []
