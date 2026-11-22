"""Phase 2 tests for Unified Org Program Management, Shared SpacePoint Programs,
and Direct Ops Organization Program/Cohort Authoring.

Covers:
  - Group A: Shared SpacePoint Program Scope (`own` / `selected` / `all`) + read-only partner boundary
  - Group B: Launching Mode A cohort from shared SpacePoint program (inheritance, zero pay rates / zero Assessment Gate, quota clamp, status guards)
  - Group C: Partner org-owned program full management parity (PATCH/PUT/variations/days/checklists/openings/materials/prequiz/LMS/hints/certs + observer & cross-org isolation)
  - Group D: Ops creating org programs and launching Mode A / Mode B cohorts directly (warehouse redaction & unstaffed redaction)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.instructor_assessment.config import AssessmentConfig
from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride, LmsProgramItem
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment, PreSessionQuizPreset, PreSessionQuizQuestion
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.sessions.program_variation import ProgramVariation, ProgramVariationDay
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.fixture(autouse=True)
def _mock_email(monkeypatch):
    async def fake_send_email(*args, **kwargs):
        return None

    monkeypatch.setattr("app.services.email.send_email", fake_send_email)


async def _make_user(
    db,
    *,
    roles: list[str],
    full_name: str,
    organization_id=None,
    org_role: str | None = None,
    org_roles: list[str] | None = None,
) -> User:
    contact = Contact(
        id=uuid.uuid4(),
        full_name=full_name,
        email=f"c2-{uuid.uuid4().hex[:8]}@example.com",
        contact_roles=[],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()

    user = User(
        id=uuid.uuid4(),
        full_name=full_name,
        email=f"u2-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=roles,
        status="active",
        contact_id=contact.id,
        organization_id=organization_id,
        org_role=org_role,
        org_roles=org_roles if org_roles is not None else ([org_role] if org_role else []),
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_phase2_world(db):
    suffix = uuid.uuid4().hex[:6]

    city = City(id=uuid.uuid4(), name=f"Dubai {suffix}", country="AE", is_active=True)
    db.add(city)
    await db.flush()

    ops = await _make_user(db, roles=["operations"], full_name="Ops Phase2")
    admin = await _make_user(db, roles=["admin"], full_name="Admin Phase2")

    org_owner = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Owner P2",
        org_role="owner",
        org_roles=["owner"],
    )
    org = Organization(
        id=uuid.uuid4(),
        name_latin=f"Sharjah Space Academy {suffix}",
        org_type="university",
        country="uae",
        city="Dubai",
        owner_user_id=org_owner.id,
        is_approved=True,
        can_publish_events=True,
        can_author_courses=True,
        max_programs=5,
        max_cohorts=5,
        max_students_per_cohort=15,
        max_observers_per_cohort=3,
        readiness_scope="own",
        program_scope="own",
        allowed_program_ids=[],
    )
    db.add(org)
    await db.flush()
    org_owner.organization_id = org.id

    org_coordinator = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Coord P2",
        organization_id=org.id,
        org_role="coordinator",
        org_roles=["coordinator"],
    )
    org_observer = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Observer P2",
        organization_id=org.id,
        org_role="observer",
        org_roles=["observer"],
    )

    other_owner = await _make_user(
        db,
        roles=["organization"],
        full_name="Other Org P2",
        org_role="owner",
        org_roles=["owner"],
    )
    other_org = Organization(
        id=uuid.uuid4(),
        name_latin=f"Other Org P2 {suffix}",
        org_type="company",
        country="uae",
        city="Abu Dhabi",
        owner_user_id=other_owner.id,
        is_approved=True,
    )
    db.add(other_org)
    await db.flush()
    other_owner.organization_id = other_org.id

    global_loc = Location(
        id=uuid.uuid4(),
        name=f"SpacePoint HQ {suffix}",
        country="AE",
        city_id=city.id,
        organization_id=None,
        is_active=True,
    )
    org_loc = Location(
        id=uuid.uuid4(),
        name=f"Partner Lab {suffix}",
        country="AE",
        city_id=city.id,
        organization_id=org.id,
        is_active=True,
    )
    db.add_all([global_loc, org_loc])
    await db.flush()

    warehouse = Warehouse(
        id=uuid.uuid4(),
        location_id=global_loc.id,
        name=f"DXB Main Depot {suffix}",
        code=f"WH-{suffix.upper()}",
        is_active=True,
    )
    db.add(warehouse)
    await db.flush()

    role_lead = DeliveryRole(
        id=uuid.uuid4(),
        name=f"Lead {suffix}",
        description="Leads sessions",
        sort_order=1,
        default_rate_aed=Decimal("550.00"),
        is_active=True,
    )
    db.add(role_lead)
    await db.flush()

    assessment_cfg = AssessmentConfig(
        id=uuid.uuid4(),
        name=f"SpacePoint Gate {suffix}",
        created_by=ops.id,
        is_active=True,
        draw_size=5,
        critical_floor=1,
    )
    db.add(assessment_cfg)
    await db.flush()

    sp_prog_1 = Program(
        id=uuid.uuid4(),
        code=f"SP1-{suffix.upper()}",
        name="SpacePoint Flagship Cubesat",
        program_type="competition",
        pricing_model="free",
        default_capacity=50,
        duration_hours=3.0,
        default_assessment_config_id=assessment_cfg.id,
        active=True,
        organization_id=None,
    )
    sp_prog_2 = Program(
        id=uuid.uuid4(),
        code=f"SP2-{suffix.upper()}",
        name="SpacePoint Workshop Two",
        program_type="workshop",
        pricing_model="free",
        active=True,
        organization_id=None,
    )
    sp_prog_inactive = Program(
        id=uuid.uuid4(),
        code=f"SPINACT-{suffix.upper()}",
        name="SpacePoint Inactive Program",
        program_type="course",
        pricing_model="free",
        active=False,
        organization_id=None,
    )
    org_prog = Program(
        id=uuid.uuid4(),
        code=f"ORGP-{suffix.upper()}",
        name="Partner Own Program",
        program_type="competition",
        pricing_model="free",
        default_capacity=20,
        active=True,
        organization_id=org.id,
    )
    db.add_all([sp_prog_1, sp_prog_2, sp_prog_inactive, org_prog])
    await db.flush()

    # Variation + days + checklist + opening + LMS + quiz on sp_prog_1
    sp_var = ProgramVariation(
        id=uuid.uuid4(),
        program_id=sp_prog_1.id,
        name="Standard 2-Day Track",
        is_default=True,
        is_active=True,
        duration_hours=2.5,
        default_capacity=40,
    )
    db.add(sp_var)
    await db.flush()

    sp_day_1 = ProgramVariationDay(
        id=uuid.uuid4(),
        variation_id=sp_var.id,
        day_number=1,
        title="Launch Day 1",
        duration_hours=2.5,
    )
    sp_day_2 = ProgramVariationDay(
        id=uuid.uuid4(),
        variation_id=sp_var.id,
        day_number=2,
        title="Mission Day 2",
        duration_hours=3.5,
    )
    db.add_all([sp_day_1, sp_day_2])
    await db.flush()

    db.add_all([
        DeliveryChecklistItem(
            id=uuid.uuid4(),
            variation_id=sp_var.id,
            title="Pre-workshop lab inspection",
            sort_order=1,
            is_required=True,
            target_audience="instructor",
        ),
        DeliveryChecklistItem(
            id=uuid.uuid4(),
            variation_day_id=sp_day_1.id,
            title="Day 1 safety briefing",
            sort_order=1,
            is_required=True,
            target_audience="instructor",
        ),
    ])
    db.add(
        ProgramOpening(
            id=uuid.uuid4(),
            variation_id=sp_var.id,
            role_id=role_lead.id,
            slots=2,
            amount_aed=Decimal("500.00"),
        )
    )

    sp_lp = LmsProgram(id=uuid.uuid4(), program_id=sp_prog_1.id, name=sp_prog_1.name, certificate_required=False)
    org_lp = LmsProgram(id=uuid.uuid4(), program_id=org_prog.id, name=org_prog.name, certificate_required=False)
    db.add_all([sp_lp, org_lp])
    await db.flush()

    db.add(
        LmsProgramItem(
            id=uuid.uuid4(),
            owner_type="program",
            owner_id=sp_lp.id,
            position=1,
            title="Flagship Mission Milestone 1",
            item_type="manual",
            optional=False,
            scope="individual",
        )
    )

    q_global = PreSessionQuizQuestion(
        id=uuid.uuid4(),
        topic="Lab Safety",
        question_type="written",
        title="ESD Grounding",
        prompt="Why ground yourself?",
        options=[],
        points=1,
        is_active=True,
        organization_id=None,
        created_by=ops.id,
    )
    q_org = PreSessionQuizQuestion(
        id=uuid.uuid4(),
        topic="Partner Readiness",
        question_type="written",
        title="Partner Lab Rules",
        prompt="State lab rules.",
        options=[],
        points=1,
        is_active=True,
        organization_id=org.id,
        created_by=org_owner.id,
    )
    db.add_all([q_global, q_org])
    await db.flush()

    sp_preset = PreSessionQuizPreset(
        id=uuid.uuid4(),
        name=f"SP Preset {suffix}",
        preset_type="readiness_pipeline",
        draw_size=1,
        critical_floor=0,
        passing_score_percent=80,
        question_ids=[str(q_global.id)],
        reference_attachments=[],
        phases=[{"id": f"p-{suffix}", "phase_type": "quiz", "title": "Quiz", "question_ids": [str(q_global.id)]}],
        is_active=True,
        organization_id=None,
        created_by=ops.id,
    )
    org_preset = PreSessionQuizPreset(
        id=uuid.uuid4(),
        name=f"Org Preset {suffix}",
        preset_type="readiness_pipeline",
        draw_size=1,
        critical_floor=0,
        passing_score_percent=80,
        question_ids=[str(q_org.id)],
        reference_attachments=[],
        phases=[{"id": f"po-{suffix}", "phase_type": "quiz", "title": "Quiz", "question_ids": [str(q_org.id)]}],
        is_active=True,
        organization_id=org.id,
        created_by=org_owner.id,
    )
    db.add_all([sp_preset, org_preset])
    await db.flush()

    db.add(
        PreSessionQuizAssignment(
            id=uuid.uuid4(),
            variation_id=sp_var.id,
            preset_id=sp_preset.id,
        )
    )
    await db.commit()

    return {
        "city": city,
        "ops": ops,
        "admin": admin,
        "org": org,
        "other_org": other_org,
        "org_owner": org_owner,
        "org_coordinator": org_coordinator,
        "org_observer": org_observer,
        "other_owner": other_owner,
        "global_loc": global_loc,
        "org_loc": org_loc,
        "warehouse": warehouse,
        "role_lead": role_lead,
        "assessment_cfg": assessment_cfg,
        "sp_prog_1": sp_prog_1,
        "sp_prog_2": sp_prog_2,
        "sp_prog_inactive": sp_prog_inactive,
        "org_prog": org_prog,
        "sp_var": sp_var,
        "sp_day_1": sp_day_1,
        "sp_day_2": sp_day_2,
        "sp_lp": sp_lp,
        "org_lp": org_lp,
        "sp_preset": sp_preset,
        "org_preset": org_preset,
    }


@pytest.mark.asyncio
async def test_group_a_shared_program_scope_and_read_only_boundary(db, client):
    w = await _seed_phase2_world(db)
    ops_hdrs = _headers(w["ops"])
    coord_hdrs = _headers(w["org_coordinator"])

    # Invalid program_scope rejected with 422
    bad_scope = await client.put(
        f"/admin/website/organizations/{w['org'].id}",
        headers=ops_hdrs,
        json={"program_scope": "invalid_scope"},
    )
    assert bad_scope.status_code == 422

    # Default scope="own": shared SpacePoint programs invisible & forbidden
    ov_own = await client.get("/organization/programs-overview", headers=coord_hdrs)
    assert ov_own.status_code == 200
    assert {p["id"] for p in ov_own.json()["programs"]} == {str(w["org_prog"].id)}
    assert (await client.get(f"/sessions/programs/{w['sp_prog_1'].id}", headers=coord_hdrs)).status_code == 403

    # Ops shares sp_prog_1 via program_scope="selected"
    sel_resp = await client.put(
        f"/admin/website/organizations/{w['org'].id}",
        headers=ops_hdrs,
        json={"program_scope": "selected", "allowed_program_ids": [str(w["sp_prog_1"].id)]},
    )
    assert sel_resp.status_code == 200, sel_resp.text
    assert sel_resp.json()["program_scope"] == "selected"
    assert sel_resp.json()["shared_programs_count"] == 1

    detail_resp = await client.get(f"/admin/website/organizations/{w['org'].id}/detail", headers=ops_hdrs)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()
    assert [sp["id"] for sp in detail_data["shared_programs"]] == [str(w["sp_prog_1"].id)]

    # Overview exposes sp_prog_1 (with flags) and excludes unselected sp_prog_2 & sp_prog_inactive
    ov_sel = await client.get("/organization/programs-overview", headers=coord_hdrs)
    assert ov_sel.status_code == 200
    progs_map = {p["id"]: p for p in ov_sel.json()["programs"]}
    assert str(w["sp_prog_1"].id) in progs_map
    assert str(w["sp_prog_2"].id) not in progs_map
    assert str(w["sp_prog_inactive"].id) not in progs_map
    sp1_meta = progs_map[str(w["sp_prog_1"].id)]
    assert sp1_meta["is_org_owned"] is False
    assert sp1_meta["is_shared_program"] is True
    assert sp1_meta["can_create_cohort"] is True

    # Partner CAN READ shared SpacePoint program endpoints, with assessment & pay rates stripped
    p_read = await client.get(f"/sessions/programs/{w['sp_prog_1'].id}", headers=coord_hdrs)
    assert p_read.status_code == 200, p_read.text
    assert p_read.json()["default_assessment_config_id"] is None

    vars_read = await client.get(f"/sessions/programs/{w['sp_prog_1'].id}/variations", headers=coord_hdrs)
    assert vars_read.status_code == 200
    assert vars_read.json()[0]["default_assessment_config_id"] is None

    open_read = await client.get(
        f"/sessions/programs/{w['sp_prog_1'].id}/openings-defaults?variation_id={w['sp_var'].id}",
        headers=coord_hdrs,
    )
    assert open_read.status_code == 200, open_read.text
    assert len(open_read.json()) == 1
    assert open_read.json()[0]["amount_aed"] is None
    assert open_read.json()[0]["role_default_rate_aed"] is None

    for ok_url in [
        f"/sessions/programs/{w['sp_prog_1'].id}/template?variation_id={w['sp_var'].id}",
        f"/sessions/materials?program_id={w['sp_prog_1'].id}",
        f"/sessions/variations/{w['sp_var'].id}/checklist-items",
        f"/sessions/pre-quiz/assignments/variations/{w['sp_var'].id}",
        f"/lms/admin/programs?program_id={w['sp_prog_1'].id}",
        f"/lms/admin/hints/program/{w['sp_prog_1'].id}",
        f"/sessions/programs/{w['sp_prog_1'].id}/certificate-templates",
    ]:
        r = await client.get(ok_url, headers=coord_hdrs)
        assert r.status_code == 200, f"GET {ok_url} returned {r.status_code}: {r.text}"

    # Partner gets 403 trying ANY write against shared SpacePoint program
    forbidden_writes = [
        ("PATCH", f"/sessions/programs/{w['sp_prog_1'].id}", {"name": "Hacked"}),
        ("DELETE", f"/sessions/programs/{w['sp_prog_1'].id}", None),
        ("POST", f"/sessions/programs/{w['sp_prog_1'].id}/variations", {"name": "Var Hack", "mode": "blank"}),
        ("PUT", f"/sessions/programs/{w['sp_prog_1'].id}/openings-defaults", {"openings": [{"role_id": str(w["role_lead"].id), "slots": 1}]}),
        ("POST", f"/sessions/programs/{w['sp_prog_1'].id}/template-days", {"title": "Day Hack"}),
        ("POST", f"/sessions/materials/link?program_id={w['sp_prog_1'].id}", {"title": "Link", "url": "https://example.com"}),
        ("PUT", f"/sessions/variations/{w['sp_var'].id}/checklist-items", {"items": []}),
        ("PUT", f"/sessions/pre-quiz/assignments/variations/{w['sp_var'].id}", {"preset_id": str(w["org_preset"].id)}),
        ("POST", f"/lms/admin/programs/{w['sp_lp'].id}/items", {"title": "Item Hack", "item_type": "manual", "scope": "individual"}),
        ("POST", "/lms/admin/hints/challenges", {"owner_type": "program", "owner_id": str(w["sp_prog_1"].id), "title": "Hint Hack", "description": "x"}),
        ("POST", f"/sessions/programs/{w['sp_prog_1'].id}/certificate-templates", {"name": "Cert Hack"}),
    ]
    for method, url, payload in forbidden_writes:
        r = await client.request(method, url, headers=coord_hdrs, json=payload)
        assert r.status_code == 403, f"Expected 403 on {method} {url}, got {r.status_code}: {r.text}"

    # Ops switches program_scope="all": active sp_prog_1 & sp_prog_2 visible, inactive stays hidden
    await client.put(
        f"/admin/website/organizations/{w['org'].id}",
        headers=ops_hdrs,
        json={"program_scope": "all"},
    )
    ov_all = await client.get("/organization/programs-overview", headers=coord_hdrs)
    assert ov_all.status_code == 200
    all_ids = {p["id"] for p in ov_all.json()["programs"]}
    assert str(w["sp_prog_1"].id) in all_ids
    assert str(w["sp_prog_2"].id) in all_ids
    assert str(w["sp_prog_inactive"].id) not in all_ids

    # Partner creates cohort on sp_prog_1 while shared, then Ops revokes back to "own"
    c_ok = await client.post(
        "/organization/cohorts",
        headers=coord_hdrs,
        json={"program_id": str(w["sp_prog_1"].id), "name": "Temp Shared Cohort"},
    )
    assert c_ok.status_code == 201, c_ok.text

    await client.put(
        f"/admin/website/organizations/{w['org'].id}",
        headers=ops_hdrs,
        json={"program_scope": "own", "allowed_program_ids": []},
    )
    ov_revoked = await client.get("/organization/programs-overview", headers=coord_hdrs)
    assert ov_revoked.status_code == 200
    rev_map = {p["id"]: p for p in ov_revoked.json()["programs"]}
    assert str(w["sp_prog_2"].id) not in rev_map
    assert str(w["sp_prog_1"].id) in rev_map  # existing cohort keeps parent visible
    assert rev_map[str(w["sp_prog_1"].id)]["can_create_cohort"] is False
    assert rev_map[str(w["sp_prog_1"].id)]["is_shared_program"] is False

    # Launching a new cohort on revoked program returns 404
    c_denied = await client.post(
        "/organization/cohorts",
        headers=coord_hdrs,
        json={"program_id": str(w["sp_prog_1"].id), "name": "Blocked After Revoke"},
    )
    assert c_denied.status_code == 404


@pytest.mark.asyncio
async def test_group_b_shared_program_cohort_inheritance_and_caps(db, client):
    w = await _seed_phase2_world(db)
    ops_hdrs = _headers(w["ops"])
    coord_hdrs = _headers(w["org_coordinator"])

    await client.put(
        f"/admin/website/organizations/{w['org'].id}",
        headers=ops_hdrs,
        json={"program_scope": "selected", "allowed_program_ids": [str(w["sp_prog_1"].id)]},
    )

    # Partner launches Mode A cohort without explicit capacity (sp_var.default_capacity=40 > max 15 -> clamp to 15)
    create_resp = await client.post(
        "/organization/cohorts",
        headers=coord_hdrs,
        json={
            "program_id": str(w["sp_prog_1"].id),
            "variation_id": str(w["sp_var"].id),
            "name": "Fall Robotics Batch A",
            "location_id": str(w["org_loc"].id),
            "starts_on": date.today().isoformat(),
            "status": "registration_open",
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    cohort_id = uuid.UUID(created["id"])
    assert created["management_mode"] == "partner"
    assert created["capacity"] == 15  # clamped to max_students_per_cohort
    assert created["location_id"] == str(w["org_loc"].id)
    assert len(created["sessions"]) == 2

    # DB verification: sessions, checklists, pre-session quiz, LMS override, openings w/o AED rates, ZERO AssessmentCohortAssignment
    sessions = (await db.execute(select(Session).where(Session.cohort_id == cohort_id))).scalars().all()
    assert [s.title for s in sorted(sessions, key=lambda x: x.meeting_date)] == ["Launch Day 1", "Mission Day 2"]

    cohort_checks = (await db.execute(select(DeliveryChecklistItem).where(DeliveryChecklistItem.cohort_id == cohort_id))).scalars().all()
    assert len(cohort_checks) == 1
    assert cohort_checks[0].title == "Pre-workshop lab inspection"

    sess_day1 = min(sessions, key=lambda x: x.meeting_date)
    day1_checks = (await db.execute(select(DeliveryChecklistItem).where(DeliveryChecklistItem.session_id == sess_day1.id))).scalars().all()
    assert len(day1_checks) == 1
    assert day1_checks[0].title == "Day 1 safety briefing"

    cohort_openings = (await db.execute(select(CohortOpening).where(CohortOpening.cohort_id == cohort_id))).scalars().all()
    assert len(cohort_openings) == 1
    assert cohort_openings[0].slots == 2
    assert cohort_openings[0].amount_aed is None  # zero AED pay-rate leakage!

    gate_rows = (await db.execute(select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == cohort_id))).scalars().all()
    assert len(gate_rows) == 0

    pq_row = (await db.execute(select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id == cohort_id))).scalars().first()
    assert pq_row is not None and pq_row.preset_id == w["sp_preset"].id

    ov_row = (await db.execute(select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == cohort_id))).scalars().first()
    assert ov_row is not None

    # Explicit capacity exceeding cap is rejected with 400
    over_cap = await client.post(
        "/organization/cohorts",
        headers=coord_hdrs,
        json={"program_id": str(w["sp_prog_1"].id), "name": "Too Big Cohort", "capacity": 20},
    )
    assert over_cap.status_code == 400

    # Status transition guard: cannot set status="completed" directly on PATCH/PUT
    comp_try = await client.patch(
        f"/organization/cohorts/{cohort_id}",
        headers=coord_hdrs,
        json={"status": "completed"},
    )
    assert comp_try.status_code == 400

    # Status change on Mode B cohort by partner returns 403
    mode_b = Cohort(
        id=uuid.uuid4(),
        program_id=w["sp_prog_1"].id,
        organization_id=w["org"].id,
        management_mode="spacepoint",
        name="Mode B Guard Check",
        status="running",
        capacity=20,
    )
    db.add(mode_b)
    await db.commit()

    mode_b_status = await client.patch(
        f"/organization/cohorts/{mode_b.id}",
        headers=coord_hdrs,
        json={"status": "planned"},
    )
    assert mode_b_status.status_code == 403


@pytest.mark.asyncio
async def test_group_c_partner_org_program_management_parity(db, client):
    w = await _seed_phase2_world(db)
    coord_hdrs = _headers(w["org_coordinator"])
    obs_hdrs = _headers(w["org_observer"])
    other_hdrs = _headers(w["other_owner"])

    # Create org program via POST /organization/programs
    prog_resp = await client.post(
        "/organization/programs",
        headers=coord_hdrs,
        json={
            "name": "Partner CubeSat Track",
            "code": f"PCT-{uuid.uuid4().hex[:4].upper()}",
            "program_type": "competition",
            "default_capacity": 15,
            "duration_hours": 2.5,
        },
    )
    assert prog_resp.status_code == 201, prog_resp.text
    prog_data = prog_resp.json()
    pid = prog_data["id"]
    lp_id = prog_data["lms_program_id"]
    assert lp_id is not None

    # Update via PUT (fixed from 405), PATCH /organization/programs, and PATCH /sessions/programs
    put_resp = await client.put(f"/organization/programs/{pid}", headers=coord_hdrs, json={"name": "PCT Put Updated"})
    assert put_resp.status_code == 200, put_resp.text
    patch_org = await client.patch(f"/organization/programs/{pid}", headers=coord_hdrs, json={"description": "Updated desc"})
    assert patch_org.status_code == 200
    patch_sess = await client.patch(f"/sessions/programs/{pid}", headers=coord_hdrs, json={"name": "Partner CubeSat Master"})
    assert patch_sess.status_code == 200, patch_sess.text
    assert patch_sess.json()["name"] == "Partner CubeSat Master"

    # Variation + Template Day + Checklists + Materials + Pre-Session Quiz + Openings (AED stripped)
    var_resp = await client.post(
        f"/sessions/programs/{pid}/variations",
        headers=coord_hdrs,
        json={"name": "2-Day Intensive", "is_default": True, "mode": "blank"},
    )
    assert var_resp.status_code == 201, var_resp.text
    vid = var_resp.json()["id"]

    day_resp = await client.post(
        f"/sessions/programs/{pid}/template-days?variation_id={vid}",
        headers=coord_hdrs,
        json={"title": "Day 1 Fundamentals", "duration_hours": 3.0},
    )
    assert day_resp.status_code == 201, day_resp.text
    day_id = day_resp.json()["id"]

    chk_resp = await client.put(
        f"/sessions/variation_days/{day_id}/checklist-items",
        headers=coord_hdrs,
        json={"items": [{"title": "Prepare Lab Kit", "is_required": True, "requires_proof": False}]},
    )
    assert chk_resp.status_code == 200, chk_resp.text
    assert chk_resp.json()[0]["title"] == "Prepare Lab Kit"

    mat_resp = await client.post(
        f"/sessions/materials/link?program_id={pid}",
        headers=coord_hdrs,
        json={"title": "Slides", "url": "https://example.com/slides", "is_published": True},
    )
    assert mat_resp.status_code == 201, mat_resp.text

    pq_resp = await client.put(
        f"/sessions/pre-quiz/assignments/programs/{pid}",
        headers=coord_hdrs,
        json={"preset_id": str(w["org_preset"].id)},
    )
    assert pq_resp.status_code == 200, pq_resp.text

    open_resp = await client.put(
        f"/sessions/programs/{pid}/openings-defaults?variation_id={vid}",
        headers=coord_hdrs,
        json={"openings": [{"role_id": str(w["role_lead"].id), "slots": 3, "amount_aed": 999}]},
    )
    assert open_resp.status_code == 200, open_resp.text
    assert open_resp.json()[0]["slots"] == 3
    assert open_resp.json()[0]["amount_aed"] is None

    # LMS checklist item + hint challenge + certificate template
    lms_item_resp = await client.post(
        f"/lms/admin/programs/{lp_id}/items",
        headers=coord_hdrs,
        json={"title": "Complete Safety Check", "item_type": "manual", "optional": False, "scope": "individual"},
    )
    assert lms_item_resp.status_code == 201, lms_item_resp.text

    hint_resp = await client.post(
        "/lms/admin/hints/challenges",
        headers=coord_hdrs,
        json={"owner_type": "program", "owner_id": pid, "title": "Antenna Challenge", "description": "Align dipole"},
    )
    assert hint_resp.status_code == 200, hint_resp.text

    cert_resp = await client.post(
        f"/sessions/programs/{pid}/certificate-templates",
        headers=coord_hdrs,
        json={"name": "Org Custom Dark", "background_type": "dark", "is_default": True},
    )
    assert cert_resp.status_code == 201, cert_resp.text

    # Launch cohort to verify GET /sessions/cohorts?program_id=... for observer & coordinator
    coh_resp = await client.post(
        "/organization/cohorts",
        headers=coord_hdrs,
        json={"program_id": pid, "name": "Partner Parity Cohort"},
    )
    assert coh_resp.status_code == 201, coh_resp.text

    # Observer can READ everything (and warehouses redacted), blocked (403) on all writes
    for obs_get in [
        f"/sessions/programs/{pid}",
        f"/sessions/programs/{pid}/variations",
        f"/sessions/programs/{pid}/openings-defaults?variation_id={vid}",
        f"/sessions/cohorts?program_id={pid}",
        f"/lms/admin/hints/program/{pid}",
        f"/sessions/programs/{pid}/certificate-templates",
    ]:
        r = await client.get(obs_get, headers=obs_hdrs)
        assert r.status_code == 200, f"Observer GET {obs_get} -> {r.status_code}: {r.text}"

    obs_patch = await client.patch(f"/sessions/programs/{pid}", headers=obs_hdrs, json={"name": "Nope"})
    assert obs_patch.status_code == 403
    obs_lms = await client.post(
        f"/lms/admin/programs/{lp_id}/items",
        headers=obs_hdrs,
        json={"title": "Nope", "item_type": "manual", "scope": "individual"},
    )
    assert obs_lms.status_code == 403

    # Cross-org isolation: other_owner cannot read/edit Org A program or list its cohorts
    assert (await client.get(f"/sessions/programs/{pid}", headers=other_hdrs)).status_code == 403
    assert (await client.patch(f"/sessions/programs/{pid}", headers=other_hdrs, json={"name": "Cross"})).status_code == 403
    other_cohorts = await client.get(f"/sessions/cohorts?program_id={pid}", headers=other_hdrs)
    assert other_cohorts.status_code == 200
    assert other_cohorts.json() == []


@pytest.mark.asyncio
async def test_group_d_ops_manage_org_and_modes_directly(db, client):
    w = await _seed_phase2_world(db)
    ops_hdrs = _headers(w["ops"])
    owner_hdrs = _headers(w["org_owner"])

    # 1. Ops creates org-owned program directly via /organization/programs?organization_id=...
    ops_prog = await client.post(
        f"/organization/programs?organization_id={w['org'].id}",
        headers=ops_hdrs,
        json={"name": "Ops Provisioned Org Program", "program_type": "workshop", "default_capacity": 25},
    )
    assert ops_prog.status_code == 201, ops_prog.text
    ops_pid = uuid.UUID(ops_prog.json()["id"])
    prog_row = await db.get(Program, ops_pid)
    assert prog_row is not None and prog_row.organization_id == w["org"].id
    lp_row = (await db.execute(select(LmsProgram).where(LmsProgram.program_id == ops_pid))).scalars().first()
    assert lp_row is not None

    # 2. Ops creates Mode B cohort for org on SpacePoint program WITH warehouse
    mode_b_resp = await client.post(
        "/sessions/cohorts",
        headers=ops_hdrs,
        json={
            "program_id": str(w["sp_prog_1"].id),
            "variation_id": str(w["sp_var"].id),
            "organization_id": str(w["org"].id),
            "management_mode": "spacepoint",
            "warehouse_id": str(w["warehouse"].id),
            "location_id": str(w["global_loc"].id),
            "name": "Ops Mode B Cohort",
            "status": "running",
        },
    )
    assert mode_b_resp.status_code == 201, mode_b_resp.text
    mode_b_id = uuid.UUID(mode_b_resp.json()["id"])
    assert mode_b_resp.json()["warehouse_id"] == str(w["warehouse"].id)
    assert mode_b_resp.json()["management_mode"] == "spacepoint"

    # Mode B preserves AED rates & AssessmentCohortAssignment for SpacePoint Ops
    b_openings = (await db.execute(select(CohortOpening).where(CohortOpening.cohort_id == mode_b_id))).scalars().all()
    assert len(b_openings) == 1
    assert b_openings[0].amount_aed == Decimal("500.00")
    b_gates = (await db.execute(select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == mode_b_id))).scalars().all()
    assert len(b_gates) == 1

    # Partner reads GET /sessions/cohorts & GET /sessions/cohorts/{id}: warehouse & Mode B unstaffed count redacted
    p_list = await client.get(f"/sessions/cohorts?program_id={w['sp_prog_1'].id}", headers=owner_hdrs)
    assert p_list.status_code == 200, p_list.text
    b_item = next(c for c in p_list.json() if c["id"] == str(mode_b_id))
    assert b_item["warehouse_id"] is None
    assert b_item["effective_warehouse_id"] is None
    assert b_item["effective_warehouse_name"] is None
    assert b_item["unstaffed_count"] == 0

    p_detail = await client.get(f"/sessions/cohorts/{mode_b_id}", headers=owner_hdrs)
    assert p_detail.status_code == 200
    assert p_detail.json()["warehouse_id"] is None
    assert p_detail.json()["effective_warehouse_id"] is None
    assert p_detail.json()["effective_warehouse_name"] is None

    # 3. Ops creates Mode A cohort for org via POST /sessions/cohorts (even if warehouse_id sent, cleared; zero AED/gate)
    mode_a_resp = await client.post(
        "/sessions/cohorts",
        headers=ops_hdrs,
        json={
            "program_id": str(w["sp_prog_1"].id),
            "variation_id": str(w["sp_var"].id),
            "organization_id": str(w["org"].id),
            "management_mode": "partner",
            "warehouse_id": str(w["warehouse"].id),
            "location_id": str(w["org_loc"].id),
            "name": "Ops Mode A Cohort",
        },
    )
    assert mode_a_resp.status_code == 201, mode_a_resp.text
    mode_a_id = uuid.UUID(mode_a_resp.json()["id"])
    assert mode_a_resp.json()["management_mode"] == "partner"
    assert mode_a_resp.json()["warehouse_id"] is None

    a_openings = (await db.execute(select(CohortOpening).where(CohortOpening.cohort_id == mode_a_id))).scalars().all()
    assert len(a_openings) == 1 and a_openings[0].amount_aed is None
    a_gates = (await db.execute(select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == mode_a_id))).scalars().all()
    assert len(a_gates) == 0
