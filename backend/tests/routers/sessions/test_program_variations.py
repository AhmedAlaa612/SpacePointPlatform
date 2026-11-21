"""Comprehensive tests for Program Variations (Option A — first-class defaults per variant)."""

from datetime import date
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.missions.component_config import DesignComponentConfig
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment, PreSessionQuizPreset
from app.models.sessions.program import Program
from app.models.sessions.program_variation import ProgramVariation
from app.models.sessions.session import Session
from app.services.competitions import judging as judging_svc
from app.services.lms import program as lms_prog_svc
from app.services.missions import component_config as comp_cfg_svc
from app.services.sessions import delivery as delivery_svc
from app.services.sessions import registration as reg_svc


async def _make_program(db, *, name: str = "Shallow Flight", program_type: str = "competition") -> Program:
    p = Program(
        id=uuid.uuid4(),
        code=f"VAR-{uuid.uuid4().hex[:8]}",
        name=name,
        program_type=program_type,
        pricing_model="paid",
        price=Decimal("500.00"),
        duration_hours=Decimal("4.00"),
        default_capacity=20,
        completion_rule_type="percentage",
        completion_rule_value=Decimal("70"),
        active=True,
    )
    db.add(p)
    await db.flush()
    return p


@pytest.mark.asyncio
async def test_variations_crud_days_and_cohort_selection(db, client, operations_headers):
    program = await _make_program(db, name="Shallow Flight Workshop")
    role_id = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == "Lead Facilitator"))
    assert role_id is not None
    preset_4d = PreSessionQuizPreset(id=uuid.uuid4(), name="4D Readiness")
    preset_3d = PreSessionQuizPreset(id=uuid.uuid4(), name="3D Express Readiness")
    db.add_all([preset_4d, preset_3d])
    await db.commit()

    # 1. Create Variation A (4-Day Full) and configure days, checklists, openings, pre-quiz, scalar overrides
    v4 = (await client.post(
        f"/sessions/programs/{program.id}/variations",
        json={
            "name": "4-Day Full",
            "duration_hours": "5.00",
            "default_capacity": 24,
            "pricing_model": "paid",
            "price": "800.00",
            "completion_rule_type": "session_count",
            "completion_rule_value": "3",
        },
        headers=operations_headers,
    )).json()
    assert v4["is_default"] is True
    v4_id = v4["id"]

    d1 = (await client.post(
        f"/sessions/programs/{program.id}/variations/{v4_id}/days",
        json={"title": "Intro & Ground"},
        headers=operations_headers,
    )).json()
    d2 = (await client.post(
        f"/sessions/programs/{program.id}/variations/{v4_id}/days",
        json={"title": "Assembly"},
        headers=operations_headers,
    )).json()
    d3 = (await client.post(
        f"/sessions/programs/{program.id}/variations/{v4_id}/days",
        json={"title": "Integration"},
        headers=operations_headers,
    )).json()
    d4 = (await client.post(
        f"/sessions/programs/{program.id}/variations/{v4_id}/days",
        json={"title": "Flight Day"},
        headers=operations_headers,
    )).json()
    assert [d["day_number"] for d in (d1, d2, d3, d4)] == [1, 2, 3, 4]

    await client.put(
        f"/sessions/variation_days/{d1['id']}/checklist-items",
        json={"items": [{"title": "4D Day 1 Setup"}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/variations/{v4_id}/checklist-items",
        json={"items": [{"title": "4D Pre-Workshop Prep"}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/programs/{program.id}/openings-defaults",
        params={"variation_id": v4_id},
        json={"openings": [{"role_id": str(role_id), "slots": 3, "amount_aed": 950}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/pre-quiz/assignments/variations/{v4_id}",
        json={"preset_id": str(preset_4d.id)},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/pre-quiz/assignments/variation_days/{d4['id']}",
        json={"preset_id": str(preset_3d.id)},
        headers=operations_headers,
    )

    # 2. Duplicate to Variation B (3-Day Express) and remove Day 4
    v3 = (await client.post(
        f"/sessions/programs/{program.id}/variations",
        json={
            "name": "3-Day Express",
            "mode": "duplicate",
            "source_variation_id": v4_id,
            "pricing_model": "free",
        },
        headers=operations_headers,
    )).json()
    v3_id = v3["id"]
    assert v3["is_default"] is False
    assert v3["days_count"] == 4
    await client.delete(
        f"/sessions/programs/{program.id}/variations/{v3_id}/days/{v3['days'][3]['id']}",
        headers=operations_headers,
    )

    # 3. Create Cohort choosing 4-Day Full
    c4 = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(program.id), "name": "SF Oct 4D", "variation_id": v4_id, "starts_on": "2026-10-10"},
        headers=operations_headers,
    )).json()
    c4_id = uuid.UUID(c4["id"])
    assert c4["variation_id"] == v4_id
    assert c4["variation_name"] == "4-Day Full"
    assert c4["capacity"] == 24
    assert float(c4["duration_hours"]) == 5.0
    s4 = (await client.get(f"/sessions/cohorts/{c4_id}/sessions", headers=operations_headers)).json()
    assert [s["title"] for s in s4] == ["Intro & Ground", "Assembly", "Integration", "Flight Day"]
    assert [i["title"] for i in (await client.get(f"/sessions/cohorts/{c4_id}/checklist-items", headers=operations_headers)).json()] == ["4D Pre-Workshop Prep"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s4[0]['id']}/checklist-items", headers=operations_headers)).json()] == ["4D Day 1 Setup"]
    openings_4 = (await client.get(f"/sessions/cohorts/{c4_id}/openings-defaults", headers=operations_headers)).json()
    assert len(openings_4) == 1 and openings_4[0]["slots"] == 3 and float(openings_4[0]["amount_aed"]) == 950.0

    # Pricing & completion rule resolve through cohort -> variation -> program
    c4_obj = await db.get(Cohort, c4_id)
    assert await reg_svc.resolve_registration_price(db, program=program, cohort=c4_obj) == Decimal("800.00")
    v4_obj = await db.get(ProgramVariation, uuid.UUID(v4_id))
    assert delivery_svc._meets_completion_rule(program, 3, 10, cohort=c4_obj, variation=v4_obj) is True

    # 4. Create Cohort choosing 3-Day Express
    c3 = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(program.id), "name": "SF Oct 3D", "variation_id": v3_id, "starts_on": "2026-11-01"},
        headers=operations_headers,
    )).json()
    c3_id = uuid.UUID(c3["id"])
    assert c3["variation_name"] == "3-Day Express"
    s3 = (await client.get(f"/sessions/cohorts/{c3_id}/sessions", headers=operations_headers)).json()
    assert len(s3) == 3
    c3_obj = await db.get(Cohort, c3_id)
    assert await reg_svc.resolve_registration_price(db, program=program, cohort=c3_obj) == Decimal("0")

    # 5. Create Blank Cohort (no variation, no defaults) -> 0 sessions, 0 checklist items, 0 openings
    cb = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(program.id), "name": "SF Blank", "import_default_checklists": False},
        headers=operations_headers,
    )).json()
    cb_id = uuid.UUID(cb["id"])
    assert cb["variation_id"] is None
    assert (await client.get(f"/sessions/cohorts/{cb_id}/sessions", headers=operations_headers)).json() == []
    assert (await client.get(f"/sessions/cohorts/{cb_id}/openings-defaults", headers=operations_headers)).json() == []

    # 6. Import defaults with explicit source_variation_id onto Blank Cohort
    imp = (await client.post(
        f"/sessions/cohorts/{cb_id}/checklists/import-default",
        json={
            "source_type": "program",
            "source_id": str(program.id),
            "source_variation_id": v4_id,
            "create_missing_sessions": True,
        },
        headers=operations_headers,
    )).json()
    assert imp["sessions_created"] == 4


@pytest.mark.asyncio
async def test_variation_lms_components_hints_rubric_and_create_from_other_program_cohort(
    db, client, operations_headers,
):
    prog_src = await _make_program(db, name="Source Program", program_type="competition")
    prog_dst = await _make_program(db, name="Destination Program", program_type="competition")
    lms_src = LmsProgram(id=uuid.uuid4(), program_id=prog_src.id, name="Src LMS")
    lms_dst = LmsProgram(id=uuid.uuid4(), program_id=prog_dst.id, name="Dst LMS")
    db.add_all([lms_src, lms_dst])
    await db.flush()
    db.add(LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_src.id,
        position=1, item_type="manual", title="Base Program Task",
    ))

    # Build a variation on prog_src with its own LMS item, component config, hint challenge, rubric
    v_src = (await client.post(
        f"/sessions/programs/{prog_src.id}/variations",
        json={"name": "Custom Track"},
        headers=operations_headers,
    )).json()
    v_src_id = v_src["id"]

    await client.post(
        f"/lms/admin/programs/{lms_src.id}/items",
        params={"variation_id": v_src_id},
        json={"item_type": "manual", "title": "Variation Specific Task"},
        headers=operations_headers,
    )
    await client.put(
        f"/lms/admin/programs/{lms_src.id}/components",
        params={"variation_id": v_src_id},
        json={"disabled_subsystems": ["Thermal"], "disabled_tags": [], "disabled_component_ids": []},
        headers=operations_headers,
    )
    await client.post(
        "/lms/admin/hints/challenges",
        json={
            "owner_type": "variation",
            "owner_id": v_src_id,
            "title": "Variation Hint",
            "description": "Solve EPS",
        },
        headers=operations_headers,
    )
    r_rubric = await client.put(
        f"/competitions/admin/programs/{prog_src.id}/rubric",
        params={"variation_id": v_src_id},
        json={"name": "Variation Rubric", "criteria": [{"key": "design", "label": "Design", "max_points": 50}]},
        headers=operations_headers,
    )
    assert r_rubric.status_code == 200

    # Cohort under prog_src + v_src inherits all four domains
    src_cohort = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(prog_src.id), "name": "Gold Cohort", "variation_id": v_src_id, "starts_on": "2026-10-01"},
        headers=operations_headers,
    )).json()
    src_cohort_id = uuid.UUID(src_cohort["id"])
    # Add 2 sessions directly on src_cohort to verify day capture
    await client.post(f"/sessions/cohorts/{src_cohort_id}/sessions", json={"meeting_date": "2026-10-01", "title": "Gold Day 1"}, headers=operations_headers)
    await client.post(f"/sessions/cohorts/{src_cohort_id}/sessions", json={"meeting_date": "2026-10-02", "title": "Gold Day 2"}, headers=operations_headers)

    resolved_lms = await lms_prog_svc.resolve_cohort_program(db, src_cohort_id)
    assert resolved_lms is not None and [i.title for i in resolved_lms[1]] == ["Variation Specific Task"]
    eff_comp, is_inh, _ = await comp_cfg_svc.resolve_effective_component_config(db, cohort_id=src_cohort_id)
    assert is_inh is True and eff_comp["disabled_subsystems"] == ["Thermal"]
    eff_rubric = await judging_svc.get_rubric(db, cohort_id=src_cohort_id)
    assert eff_rubric is not None and eff_rubric[0].name == "Variation Rubric"

    # Now create a variation in prog_dst IMPORTED from src_cohort (cross-program cohort -> variation)
    v_dst = (await client.post(
        f"/sessions/programs/{prog_dst.id}/variations",
        json={
            "name": "Imported From Gold",
            "mode": "from_cohort",
            "source_cohort_id": str(src_cohort_id),
        },
        headers=operations_headers,
    )).json()
    assert [d["title"] for d in v_dst["days"]] == ["Gold Day 1", "Gold Day 2"]
    v_dst_id = uuid.UUID(v_dst["id"])
    dst_cohort = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(prog_dst.id), "name": "Dst Cohort", "variation_id": str(v_dst_id), "starts_on": "2026-12-01"},
        headers=operations_headers,
    )).json()
    dst_cohort_id = uuid.UUID(dst_cohort["id"])
    dst_lms = await lms_prog_svc.resolve_cohort_program(db, dst_cohort_id)
    assert dst_lms is not None and [i.title for i in dst_lms[1]] == ["Variation Specific Task"]
    dst_rubric = await judging_svc.get_rubric(db, cohort_id=dst_cohort_id)
    assert dst_rubric is not None and dst_rubric[0].name == "Variation Rubric"


@pytest.mark.asyncio
async def test_legacy_template_cohorts_hidden_while_planned_cohorts_remain(db, client, operations_headers):
    program = await _make_program(db, name="Shallow Flight")
    legacy_shell = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="[Template] Shallow Flight Template",
        status="draft",
        is_template_legacy=True,
    )
    planned_template_named = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Shallow Flight Cohort Template",
        status="planned",
        is_template_legacy=False,
    )
    db.add_all([legacy_shell, planned_template_named])
    await db.commit()

    cohorts = (await client.get("/sessions/cohorts", headers=operations_headers)).json()
    names = {c["name"] for c in cohorts}
    assert "[Template] Shallow Flight Template" not in names
    assert "Shallow Flight Cohort Template" in names
