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

    # Edit the definition (mass 65 -> 999): placed snapshot updates to match.
    patched = await client.patch(
        f"/missions/design/attempts/{attempt_id}/custom-components/{custom_id}",
        headers=h, json={"mass_g": 999.0},
    )
    assert patched.status_code == 200
    state = await client.get(f"/missions/design/attempts/{attempt_id}", headers=h)
    assert state.json()["components"][0]["mass_per_unit_g"] == pytest.approx(999.0)

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


@pytest.mark.asyncio
async def test_custom_component_allows_short_purpose_function(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    attempt_id = await _attempt(client, db, mission, variant, student)
    h = _headers(student)

    created = await client.post(
        f"/missions/design/attempts/{attempt_id}/custom-components",
        headers=h,
        json=_custom_body(purpose_function="Camera"),
    )
    assert created.status_code == 201, created.text
    assert created.json()["components"][0]["purpose_function"] == "Camera"


@pytest.mark.asyncio
async def test_cohort_mission_custom_component_available_in_same_cohort_team_mission(db, client):
    from app.models.sessions.cohort import Cohort
    from app.models.sessions.program import Program
    from app.services.teams import create_team, join_team
    from app.services.missions.attempts import start_attempt

    author = await _user(db, roles=["operations"])
    mission = Mission(
        id=uuid.uuid4(), title="Cohort Team Design Mission", slug=f"cohort-team-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", team_policy="team",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=200,
        config={
            "max_storage_kb": 1_000_000.0, "required_storage_margin_kb": 50.0,
            "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 200_000.0,
            "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
            "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
        },
    )
    db.add(variant)
    await db.flush()

    prog = Program(
        id=uuid.uuid4(), name="Test Program", program_type="workshop", pricing_model="free",
        active=True, code=f"PROG-{uuid.uuid4().hex[:6]}",
    )
    db.add(prog)
    await db.flush()

    cohort1 = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Cohort Alpha", status="running")
    cohort2 = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Cohort Beta", status="running")
    db.add_all([cohort1, cohort2])
    await db.flush()

    alice = await _user(db)
    bob = await _user(db)
    dave = await _user(db)
    charlie = await _user(db)

    # 1. Alice starts a solo cohort mission attempt in Cohort 1
    solo_attempt = await start_attempt(
        db, mission_id=mission.id, variant_id=variant.id, user_id=alice.id, cohort_id=cohort1.id,
    )
    await db.commit()

    # Alice creates a custom component in this cohort mission
    created = await client.post(
        f"/missions/design/attempts/{solo_attempt.id}/custom-components",
        headers=_headers(alice),
        json=_custom_body(component_name="Spectrometer SP-1"),
    )
    assert created.status_code == 201, created.text
    custom_comp_id = created.json()["components"][0]["custom_component_id"]

    # 2. Team 1 is formed in Cohort 1 with Bob and Alice as teammates
    team1 = await create_team(db, name="Alpha Team 1", created_by=bob.id, cohort_id=cohort1.id)
    await join_team(db, team_id=team1.id, user_id=alice.id)
    team1_attempt = await start_attempt(
        db, mission_id=mission.id, variant_id=variant.id, team_id=team1.id, cohort_id=cohort1.id,
    )
    await db.commit()

    # 3. Bob opens Team 1's mission in Cohort 1: Alice is his teammate, so her component is available!
    team1_customs = await client.get(
        f"/missions/design/attempts/{team1_attempt.id}/custom-components",
        headers=_headers(bob),
    )
    assert team1_customs.status_code == 200
    custom_names = [c["component_name"] for c in team1_customs.json()]
    assert "Spectrometer SP-1" in custom_names

    # 4. Bob adds Alice's custom component to Team 1's satellite design
    add_resp = await client.post(
        f"/missions/design/attempts/{team1_attempt.id}/components",
        headers=_headers(bob),
        json={"custom_component_id": custom_comp_id, "quantity": 1},
    )
    assert add_resp.status_code == 201, add_resp.text
    placed = add_resp.json()["components"]
    assert any(c["custom_component_id"] == custom_comp_id for c in placed)

    # 5. Dave is in Team 3 in the SAME cohort (Cohort 1), but NOT on Alice's team
    team3 = await create_team(db, name="Alpha Team 2", created_by=dave.id, cohort_id=cohort1.id)
    team3_attempt = await start_attempt(
        db, mission_id=mission.id, variant_id=variant.id, team_id=team3.id, cohort_id=cohort1.id,
    )
    await db.commit()

    # Dave must NOT see Alice's component even though they are in the same cohort
    team3_customs = await client.get(
        f"/missions/design/attempts/{team3_attempt.id}/custom-components",
        headers=_headers(dave),
    )
    assert team3_customs.status_code == 200
    assert not any(c["id"] == custom_comp_id for c in team3_customs.json())

    # Dave cannot add Alice's component to Team 3's design (404 Not Found)
    team3_steal = await client.post(
        f"/missions/design/attempts/{team3_attempt.id}/components",
        headers=_headers(dave),
        json={"custom_component_id": custom_comp_id, "quantity": 1},
    )
    assert team3_steal.status_code == 404

    # Dave also cannot see Alice's component in Dave's own solo attempt in Cohort 1
    dave_solo = await start_attempt(
        db, mission_id=mission.id, variant_id=variant.id, user_id=dave.id, cohort_id=cohort1.id,
    )
    await db.commit()
    dave_solo_customs = await client.get(
        f"/missions/design/attempts/{dave_solo.id}/custom-components",
        headers=_headers(dave),
    )
    assert dave_solo_customs.status_code == 200
    assert not any(c["id"] == custom_comp_id for c in dave_solo_customs.json())

    # 6. Charlie is in Team 2 in a DIFFERENT cohort (Cohort 2)
    team2 = await create_team(db, name="Beta Team 1", created_by=charlie.id, cohort_id=cohort2.id)
    team2_attempt = await start_attempt(
        db, mission_id=mission.id, variant_id=variant.id, team_id=team2.id, cohort_id=cohort2.id,
    )
    await db.commit()

    # Charlie must NOT see Alice's component from Cohort 1
    team2_customs = await client.get(
        f"/missions/design/attempts/{team2_attempt.id}/custom-components",
        headers=_headers(charlie),
    )
    assert team2_customs.status_code == 200
    assert not any(c["id"] == custom_comp_id for c in team2_customs.json())

    # Charlie cannot add Alice's component from Cohort 1
    steal_resp = await client.post(
        f"/missions/design/attempts/{team2_attempt.id}/components",
        headers=_headers(charlie),
        json={"custom_component_id": custom_comp_id, "quantity": 1},
    )
    assert steal_resp.status_code == 404


