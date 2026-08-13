"""Design v2 (7D-4 … 7D-8) router tests — the teaching surfaces, the
component library manager, and the D8 freeze split. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.missions.design import DesignComponentLibrary
from app.models.missions.manager import MissionManager
from app.models.missions.mission import Mission, MissionVariant
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Design V2 User", email=f"dv2-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["student"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _h(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _design_mission(db, *, author, status_="published", disclosure="full"):
    mission = Mission(
        id=uuid.uuid4(), title="Build Your CubeSat", slug=f"design-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status=status_, summary="Design one.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=200,
        config={
            "max_storage_kb": 1_048_576.0, "required_storage_margin_kb": 0.0,
            "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
            "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
            "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
            "max_depth_of_discharge_pct": 30.0, "required_downlink_margin_fraction": 0.10,
            "handbook_disclosure": disclosure,
        },
    )
    db.add(variant)
    await db.flush()
    return mission, variant


async def _library_row(db, **over) -> DesignComponentLibrary:
    row = DesignComponentLibrary(
        id=uuid.uuid4(), component_name=over.pop("component_name", "Test Part"),
        subsystem=over.pop("subsystem", "EPS"), is_active=over.pop("is_active", True), **over,
    )
    db.add(row)
    await db.flush()
    return row


# ── Briefing (7D-4) ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_briefing_is_readable_without_creating_an_attempt(db, client):
    author = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    res = await client.get(f"/missions/design/briefing/{mission.id}", headers=_h(student))
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["variant_label"] == "Engineer"
    assert "budget" in body["what_is_a_budget"].lower()
    assert len(body["step_order"]) >= 9
    assert body["limits"] and body["cubesat_sizes"] and body["budgets"] and body["assumptions"]

    detail = await client.get(f"/missions/{mission.id}", headers=_h(student))
    assert detail.json()["attempts"] == []


@pytest.mark.asyncio
async def test_the_briefing_states_the_variants_limits_up_front(db, client):
    """Discovering a threshold on the report screen is not a design
    exercise."""
    author = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    limits = (await client.get(f"/missions/design/briefing/{mission.id}", headers=_h(student))).json()["limits"]
    keys = {limit["key"] for limit in limits}
    assert {"storage", "cost", "link", "battery", "downlink"} <= keys


@pytest.mark.asyncio
async def test_briefing_404s_for_a_non_design_mission(db, client):
    author = await _user(db, roles=["operations"])
    quiz = Mission(id=uuid.uuid4(), title="Q", slug=f"q-{uuid.uuid4().hex[:8]}",
                   kind="quiz", authored_by=author.id, status="published")
    db.add(quiz)
    student = await _user(db)
    await db.commit()
    res = await client.get(f"/missions/design/briefing/{quiz.id}", headers=_h(student))
    assert res.status_code == http_status.HTTP_404_NOT_FOUND


# ── Handbook (7D-5) ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handbook_disclosure_follows_the_variant(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author, disclosure="reference")
    student = await _user(db)
    await db.commit()
    attempt_id = (await client.post(
        f"/missions/{mission.id}/attempts", headers=_h(student), json={"variant_id": str(variant.id)},
    )).json()["id"]

    body = (await client.get(
        f"/missions/design/attempts/{attempt_id}/handbook", headers=_h(student),
    )).json()
    assert body["disclosure"] == "reference"
    assert all("fix" not in b for b in body["budgets"])
    # Never withheld: the formula and what each budget checks.
    assert all(b["formula"] and b["checks"] for b in body["budgets"])
    assert len(body["data_types"]) == 8


@pytest.mark.asyncio
async def test_full_disclosure_spells_out_the_fix(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = (await client.post(
        f"/missions/{mission.id}/attempts", headers=_h(student), json={"variant_id": str(variant.id)},
    )).json()["id"]

    body = (await client.get(
        f"/missions/design/attempts/{attempt_id}/handbook", headers=_h(student),
    )).json()
    assert all("fix" in b for b in body["budgets"])
    assert all("fix" in m for m in body["mistakes"])


# ── The report (7D-3) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_design_state_carries_the_whole_report(db, client):
    author = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=author)
    student = await _user(db)
    await db.commit()
    attempt_id = (await client.post(
        f"/missions/{mission.id}/attempts", headers=_h(student), json={"variant_id": str(variant.id)},
    )).json()["id"]

    body = (await client.get(f"/missions/design/attempts/{attempt_id}", headers=_h(student))).json()
    dash = body["dashboard"]

    assert dash["overall"]["label"]
    assert dash["margins"], "the margin table is the payoff screen"
    assert all(m["interpretation"] for m in dash["margins"])
    assert dash["module_cards"] and dash["alerts"] is not None
    assert "power_by_subsystem" in dash["charts"]
    assert body["assumptions"], "F9 — say what the model simplifies"
    # The two new steps exist and start unstarted.
    assert dash["steps"]["energy_budget"]["has_data"] is False
    assert dash["steps"]["downlink"]["has_data"] is False


# ── D8: content editable, grading frozen (7D-8) ─────────────────────────

@pytest.mark.asyncio
async def test_grading_criteria_are_frozen_while_published(db, client):
    staff = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=staff, status_="published")
    await db.commit()

    res = await client.patch(
        f"/missions/admin/{mission.id}/variants/{variant.id}",
        headers=_h(staff), json={"config": {"maximum_budget_aed": 99999.0}},
    )
    assert res.status_code == http_status.HTTP_409_CONFLICT
    assert "draft" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_points_are_frozen_too(db, client):
    staff = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=staff, status_="published")
    await db.commit()
    res = await client.patch(
        f"/missions/admin/{mission.id}/variants/{variant.id}", headers=_h(staff), json={"points": 999},
    )
    assert res.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_a_draft_mission_can_still_be_retuned(db, client):
    staff = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=staff, status_="draft")
    await db.commit()
    res = await client.patch(
        f"/missions/admin/{mission.id}/variants/{variant.id}", headers=_h(staff), json={"points": 250},
    )
    assert res.status_code == 200
    assert res.json()["points"] == 250


@pytest.mark.asyncio
async def test_content_stays_editable_on_a_published_mission(db, client):
    """The D8 split: changing how a budget is explained cannot re-grade
    anybody, so it is not frozen."""
    staff = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=staff, status_="published")
    await db.commit()

    res = await client.put(
        f"/missions/manager/{mission.id}/content", headers=_h(staff),
        json={"content": {"what_is_a_budget": "A budget is a share-out of something finite."}},
    )
    assert res.status_code == 200, res.text
    editable = res.json()["editable"]
    assert editable["what_is_a_budget"]["overridden"] is True
    assert editable["what_is_a_budget"]["default"] != editable["what_is_a_budget"]["value"]


@pytest.mark.asyncio
async def test_authored_content_reaches_the_student(db, client):
    staff = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=staff)
    student = await _user(db)
    await db.commit()

    await client.put(
        f"/missions/manager/{mission.id}/content", headers=_h(staff),
        json={"content": {"budgets": {"conops": {"fix": "Make the durations add up."}}}},
    )
    attempt_id = (await client.post(
        f"/missions/{mission.id}/attempts", headers=_h(student), json={"variant_id": str(variant.id)},
    )).json()["id"]
    body = (await client.get(
        f"/missions/design/attempts/{attempt_id}/handbook", headers=_h(student),
    )).json()
    conops = next(b for b in body["budgets"] if b["key"] == "conops")
    assert conops["fix"] == "Make the durations add up."


@pytest.mark.asyncio
async def test_clearing_an_override_restores_the_default(db, client):
    staff = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=staff)
    await db.commit()

    await client.put(f"/missions/manager/{mission.id}/content", headers=_h(staff),
                     json={"content": {"what_is_a_budget": "Custom."}})
    res = await client.put(f"/missions/manager/{mission.id}/content", headers=_h(staff),
                           json={"content": {"what_is_a_budget": "   "}})
    assert res.json()["editable"]["what_is_a_budget"]["overridden"] is False


@pytest.mark.asyncio
async def test_a_mission_manager_may_edit_content_but_a_stranger_may_not(db, client):
    staff = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=staff)
    manager = await _user(db)
    stranger = await _user(db)
    db.add(MissionManager(mission_id=mission.id, user_id=manager.id, granted_by=staff.id))
    await db.commit()

    assert (await client.get(f"/missions/manager/{mission.id}/content", headers=_h(manager))).status_code == 200
    assert (await client.get(
        f"/missions/manager/{mission.id}/content", headers=_h(stranger),
    )).status_code == http_status.HTTP_403_FORBIDDEN


# ── The component library manager (7D-7) ────────────────────────────────

@pytest.mark.asyncio
async def test_staff_can_create_and_edit_a_component(db, client):
    staff = await _user(db, roles=["operations"])
    await db.commit()

    created = await client.post("/missions/library", headers=_h(staff), json={
        "component_name": "Torque Rod", "subsystem": "ADCS", "scaled_mass_g": 30.0,
        "voltage_v": 5.0, "current_ma": 120.0, "component_code": f"ADCS-TR-{uuid.uuid4().hex[:4]}",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["is_active"] is True
    assert body["updated_by_name"] == staff.full_name

    updated = await client.patch(f"/missions/library/{body['id']}", headers=_h(staff),
                                 json={"scaled_mass_g": 35.0})
    assert updated.status_code == 200
    assert updated.json()["scaled_mass_g"] == 35.0


@pytest.mark.asyncio
async def test_there_is_no_delete_only_retire(db, client):
    """Madar's delete cascaded into every student's design and their budget
    entries (F1, Critical). There is deliberately no DELETE route."""
    staff = await _user(db, roles=["operations"])
    row = await _library_row(db)
    await db.commit()

    gone = await client.delete(f"/missions/library/{row.id}", headers=_h(staff))
    assert gone.status_code in (405, 404)

    retired = await client.post(f"/missions/library/{row.id}/retire", headers=_h(staff),
                                params={"retired": True})
    assert retired.status_code == 200
    assert retired.json()["is_active"] is False

    restored = await client.post(f"/missions/library/{row.id}/retire", headers=_h(staff),
                                 params={"retired": False})
    assert restored.json()["is_active"] is True


@pytest.mark.asyncio
async def test_a_retired_component_leaves_the_student_picker_but_stays_in_admin(db, client):
    staff = await _user(db, roles=["operations"])
    student = await _user(db)
    row = await _library_row(db, component_name="Retired Widget")
    await db.commit()

    await client.post(f"/missions/library/{row.id}/retire", headers=_h(staff), params={"retired": True})

    picker = (await client.get("/missions/design/library", headers=_h(student))).json()
    assert all(c["component_name"] != "Retired Widget" for c in picker)

    admin = (await client.get("/missions/library", headers=_h(staff))).json()
    assert any(c["component_name"] == "Retired Widget" for c in admin)


@pytest.mark.asyncio
async def test_a_design_mission_manager_may_edit_the_library(db, client):
    """D7 — the operator's call, overriding the safer staff-only default."""
    staff = await _user(db, roles=["operations"])
    mission, _ = await _design_mission(db, author=staff)
    manager = await _user(db)
    db.add(MissionManager(mission_id=mission.id, user_id=manager.id, granted_by=staff.id))
    await db.commit()

    res = await client.post("/missions/library", headers=_h(manager), json={
        "component_name": "Intern-added part", "subsystem": "Payload",
    })
    assert res.status_code == 201, res.text
    assert res.json()["updated_by_name"] == manager.full_name


@pytest.mark.asyncio
async def test_a_plain_student_cannot_touch_the_library(db, client):
    student = await _user(db)
    await db.commit()
    res = await client.post("/missions/library", headers=_h(student), json={
        "component_name": "Nope", "subsystem": "EPS",
    })
    assert res.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_managing_a_non_design_mission_does_not_grant_library_access(db, client):
    staff = await _user(db, roles=["operations"])
    quiz = Mission(id=uuid.uuid4(), title="Q", slug=f"q-{uuid.uuid4().hex[:8]}",
                   kind="quiz", authored_by=staff.id, status="published")
    db.add(quiz)
    await db.flush()
    manager = await _user(db)
    db.add(MissionManager(mission_id=quiz.id, user_id=manager.id, granted_by=staff.id))
    await db.commit()

    res = await client.post("/missions/library", headers=_h(manager), json={
        "component_name": "Nope", "subsystem": "EPS",
    })
    assert res.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_bulk_import_creates_and_updates_by_code(db, client):
    staff = await _user(db, roles=["operations"])
    code = f"EPS-BAT-{uuid.uuid4().hex[:4]}"
    await db.commit()

    first = await client.post("/missions/library/bulk", headers=_h(staff), json={"components": [
        {"component_name": "Battery", "subsystem": "EPS", "component_code": code, "scaled_mass_g": 100.0},
        {"component_name": "Radio", "subsystem": "COMMS"},
    ]})
    assert first.status_code == 200, first.text
    assert first.json()["created"] == 2

    again = await client.post("/missions/library/bulk", headers=_h(staff), json={"components": [
        {"component_name": "Battery v2", "subsystem": "EPS", "component_code": code, "scaled_mass_g": 120.0},
    ]})
    assert again.json() == {"created": 0, "updated": 1, "errors": []}

    rows = (await client.get("/missions/library", headers=_h(staff), params={"search": code})).json()
    assert rows[0]["component_name"] == "Battery v2"
    assert rows[0]["scaled_mass_g"] == 120.0


@pytest.mark.asyncio
async def test_the_admin_list_reports_how_many_designs_use_a_component(db, client):
    """So an editor can see the blast radius before changing a spec."""
    staff = await _user(db, roles=["operations"])
    mission, variant = await _design_mission(db, author=staff)
    student = await _user(db)
    row = await _library_row(db, component_name="Used Part")
    await db.commit()

    attempt_id = (await client.post(
        f"/missions/{mission.id}/attempts", headers=_h(student), json={"variant_id": str(variant.id)},
    )).json()["id"]
    await client.post(f"/missions/design/attempts/{attempt_id}/components", headers=_h(student),
                      json={"library_component_id": str(row.id), "quantity": 1})

    rows = (await client.get("/missions/library", headers=_h(staff), params={"search": "Used Part"})).json()
    assert rows[0]["used_in_designs"] == 1


# ── The chained written report (D6) ─────────────────────────────────────

async def _report_mission(db, *, author, requires: Mission | None = None):
    """A `submission`-kind report mission, optionally gated behind another."""
    from app.models.curriculum import Prerequisite

    report = Mission(
        id=uuid.uuid4(), title="CubeSat Design Report", slug=f"report-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="either",
    )
    db.add(report)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=report.id, label="Design Review", position=1, points=150,
        config={
            "brief": "Write up the CubeSat you designed.",
            "deliverables": [{"title": "Mission and orbit", "detail": "What it does and why."}],
            "rubric": [{"criterion": "The numbers are yours", "detail": "They must agree with your design."}],
            "accepted_formats": "A link to a Doc or PDF.",
            # A reviewer-only note has no business reaching a student.
            "internal_marking_notes": "Fail anything under 500 words.",
        },
    )
    db.add(variant)
    await db.flush()
    if requires is not None:
        db.add(Prerequisite(item_type="mission", item_id=report.id,
                            requires_type="mission", requires_id=requires.id))
        await db.flush()
    return report, variant


@pytest.mark.asyncio
async def test_the_report_brief_reaches_the_student(db, client):
    """A submission mission used to be a URL box: no statement of what to
    hand in or how it would be judged."""
    author = await _user(db, roles=["operations"])
    report, _ = await _report_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    body = (await client.get(f"/missions/{report.id}", headers=_h(student))).json()
    config = body["variants"][0]["config"]
    assert config["brief"].startswith("Write up")
    assert config["deliverables"][0]["title"] == "Mission and orbit"
    assert config["rubric"][0]["criterion"] == "The numbers are yours"
    assert config["accepted_formats"]


@pytest.mark.asyncio
async def test_reviewer_only_notes_never_reach_the_student(db, client):
    """The serializer rebuilds the brief field by field rather than passing
    the config through, so an authoring mistake can't leak marking notes."""
    author = await _user(db, roles=["operations"])
    report, _ = await _report_mission(db, author=author)
    student = await _user(db)
    await db.commit()

    config = (await client.get(f"/missions/{report.id}", headers=_h(student))).json()["variants"][0]["config"]
    assert "internal_marking_notes" not in config
    assert "500 words" not in str(config)


@pytest.mark.asyncio
async def test_the_report_is_locked_until_the_design_passes(db, client):
    author = await _user(db, roles=["operations"])
    design, design_variant = await _design_mission(db, author=author)
    report, report_variant = await _report_mission(db, author=author, requires=design)
    student = await _user(db)
    await db.commit()

    detail = (await client.get(f"/missions/{report.id}", headers=_h(student))).json()
    assert detail["locked"] is True
    assert any(p["title"] == design.title for p in detail["prerequisites"])

    blocked = await client.post(f"/missions/{report.id}/attempts", headers=_h(student),
                                json={"variant_id": str(report_variant.id)})
    assert blocked.status_code == http_status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_passing_the_design_unlocks_the_report(db, client):
    from app.models.missions.mission import MissionAttempt

    author = await _user(db, roles=["operations"])
    design, design_variant = await _design_mission(db, author=author)
    report, report_variant = await _report_mission(db, author=author, requires=design)
    student = await _user(db)
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=design.id, variant_id=design_variant.id,
        user_id=student.id, attempt_no=1, status="passed", score=100,
    ))
    await db.commit()

    detail = (await client.get(f"/missions/{report.id}", headers=_h(student))).json()
    assert detail["locked"] is False

    started = await client.post(f"/missions/{report.id}/attempts", headers=_h(student),
                                json={"variant_id": str(report_variant.id)})
    assert started.status_code == 201, started.text


@pytest.mark.asyncio
async def test_a_quiz_variant_still_hides_its_answers(db, client):
    """Adding the submission branch to the serializer must not have loosened
    the quiz one — that is the original answer-leakage guarantee."""
    author = await _user(db, roles=["operations"])
    quiz = Mission(id=uuid.uuid4(), title="Quiz", slug=f"quiz-{uuid.uuid4().hex[:8]}",
                   kind="quiz", authored_by=author.id, status="published")
    db.add(quiz)
    await db.flush()
    db.add(MissionVariant(
        id=uuid.uuid4(), mission_id=quiz.id, label="Only", position=1, points=10,
        config={"pass_threshold": 50, "questions": [{
            "prompt": "2 + 2?",
            "options": [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
            "explanation": "It is four.",
        }]},
    ))
    student = await _user(db)
    await db.commit()

    config = (await client.get(f"/missions/{quiz.id}", headers=_h(student))).json()["variants"][0]["config"]
    assert "is_correct" not in str(config)
    assert "explanation" not in str(config)
