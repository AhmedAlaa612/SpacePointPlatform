"""Phase 1 tests for Partner Organization Cohort Management Modes (Mode A vs Mode B).

Covers:
  - Group A: Ops queue isolation & Mode B visibility
  - Group B: Mode B exact partner write boundary & AED rate redaction
  - Group C: Mode B SpacePoint Ops & instructor delivery lifecycle
  - Group D: Mode A full partner parity (roles, openings, locations, check-in, contact edit, pre-quiz, complete)
  - Group E: Org observer strict read-only across all GET/write paths
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import uuid

import pytest

from app.core.security import create_access_token
from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem
from app.models.sessions.checklist import InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import PreSessionQuizAttempt, PreSessionQuizPreset, PreSessionQuizQuestion
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
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
        email=f"c-{uuid.uuid4().hex[:8]}@example.com",
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
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
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


async def _seed_phase1_world(db):
    suffix = uuid.uuid4().hex[:6]

    city = City(id=uuid.uuid4(), name=f"Abu Dhabi {suffix}", country="AE", is_active=True)
    db.add(city)
    await db.flush()

    ops = await _make_user(db, roles=["operations"], full_name="Ops Manager")
    sp_instructor = await _make_user(db, roles=["instructor"], full_name="SpacePoint Instructor")

    org_owner = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Owner",
        org_role="owner",
        org_roles=["owner"],
    )
    org = Organization(
        id=uuid.uuid4(),
        name_latin=f"Al Ain Robotics {suffix}",
        org_type="university",
        country="uae",
        city="Abu Dhabi",
        owner_user_id=org_owner.id,
        is_approved=True,
        can_publish_events=True,
        can_author_courses=True,
        max_programs=3,
        max_cohorts=3,
        max_students_per_cohort=1,
        max_observers_per_cohort=1,
        readiness_scope="own",
    )
    db.add(org)
    await db.flush()
    org_owner.organization_id = org.id

    other_owner = await _make_user(
        db,
        roles=["organization"],
        full_name="Other Org Owner",
        org_role="owner",
        org_roles=["owner"],
    )
    other_org = Organization(
        id=uuid.uuid4(),
        name_latin=f"Other Org {suffix}",
        org_type="company",
        country="uae",
        city="Dubai",
        owner_user_id=other_owner.id,
        is_approved=True,
    )
    db.add(other_org)
    await db.flush()
    other_owner.organization_id = other_org.id

    org_coordinator = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Coordinator",
        organization_id=org.id,
        org_role="coordinator",
        org_roles=["coordinator"],
    )
    org_instructor = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Instructor",
        organization_id=org.id,
        org_role="instructor",
        org_roles=["instructor"],
    )
    org_observer = await _make_user(
        db,
        roles=["organization"],
        full_name="Partner Observer",
        organization_id=org.id,
        org_role="observer",
        org_roles=["observer"],
    )

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
        name=f"Partner Innovation Lab {suffix}",
        country="AE",
        city_id=city.id,
        organization_id=org.id,
        is_active=True,
    )
    other_loc = Location(
        id=uuid.uuid4(),
        name=f"Other Org Venue {suffix}",
        country="AE",
        city_id=city.id,
        organization_id=other_org.id,
        is_active=True,
    )
    db.add_all([global_loc, org_loc, other_loc])
    await db.flush()

    role_lead = DeliveryRole(
        id=uuid.uuid4(),
        name=f"Lead {suffix}",
        description="Leads workshop delivery",
        sort_order=1,
        default_rate_aed=Decimal("550.00"),
        is_active=True,
    )
    role_fac = DeliveryRole(
        id=uuid.uuid4(),
        name=f"Facilitator {suffix}",
        description="Co-facilitates sessions",
        sort_order=2,
        default_rate_aed=Decimal("320.00"),
        is_active=True,
    )
    db.add_all([role_lead, role_fac])
    await db.flush()

    org_program = Program(
        id=uuid.uuid4(),
        code=f"ORGP-{suffix}",
        name="Partner Partner-Run Program",
        program_type="bootcamp",
        pricing_model="free",
        active=True,
        organization_id=org.id,
    )
    sp_program = Program(
        id=uuid.uuid4(),
        code=f"SPP-{suffix}",
        name="SpacePoint Managed Program",
        program_type="competition",
        pricing_model="free",
        active=True,
        organization_id=None,
    )
    db.add_all([org_program, sp_program])
    await db.flush()

    for prog, title in ((org_program, "Partner Checklist"), (sp_program, "SpacePoint Checklist")):
        lp = LmsProgram(id=uuid.uuid4(), program_id=prog.id, name=title, certificate_required=False)
        db.add(lp)
        await db.flush()
        db.add(
            LmsProgramItem(
                id=uuid.uuid4(),
                owner_type="program",
                owner_id=lp.id,
                position=1,
                title=f"{title} Item 1",
                item_type="note",
                optional=False,
                scope="individual",
            )
        )

    # Cohort ORM default for org cohorts must be "partner" (Mode A) unless specified "spacepoint" (Mode B)
    cohort_a = Cohort(
        id=uuid.uuid4(),
        program_id=org_program.id,
        organization_id=org.id,
        name=f"Mode A Cohort {suffix}",
        status="running",
        capacity=10,
        starts_on=date.today(),
    )
    assert cohort_a.management_mode == "partner"

    cohort_b = Cohort(
        id=uuid.uuid4(),
        program_id=sp_program.id,
        organization_id=org.id,
        management_mode="spacepoint",
        name=f"Mode B Cohort {suffix}",
        status="running",
        capacity=10,
        location_id=global_loc.id,
        starts_on=date.today(),
    )
    assert cohort_b.management_mode == "spacepoint"
    db.add_all([cohort_a, cohort_b])
    await db.flush()

    session_a = Session(
        id=uuid.uuid4(),
        cohort_id=cohort_a.id,
        meeting_date=date.today(),
        title="Mode A Session 1",
        staffing_status="unstaffed",
        started_at=datetime.now(timezone.utc),
    )
    session_b = Session(
        id=uuid.uuid4(),
        cohort_id=cohort_b.id,
        meeting_date=date.today(),
        title="Mode B Session 1",
        staffing_status="unstaffed",
        started_at=datetime.now(timezone.utc),
    )
    db.add_all([session_a, session_b])
    await db.flush()

    student_a_contact = Contact(
        id=uuid.uuid4(),
        full_name="Student Mode A",
        email=f"sa-{suffix}@example.com",
        primary_phone_e164="+971501111111",
        contact_roles=["student"],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="customer",
    )
    student_b_contact = Contact(
        id=uuid.uuid4(),
        full_name="Student Mode B",
        email=f"sb-{suffix}@example.com",
        primary_phone_e164="+971502222222",
        contact_roles=["student"],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="customer",
    )
    outside_contact = Contact(
        id=uuid.uuid4(),
        full_name="Outside Student",
        email=f"out-{suffix}@example.com",
        primary_phone_e164="+971503333333",
        contact_roles=["student"],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="lead",
    )
    db.add_all([student_a_contact, student_b_contact, outside_contact])
    await db.flush()

    reg_a = Registration(
        id=uuid.uuid4(),
        cohort_id=cohort_a.id,
        contact_id=student_a_contact.id,
        status="registered",
        ticket_token=f"TKA-{uuid.uuid4().hex[:10].upper()}",
        registered_via="desk",
    )
    reg_b = Registration(
        id=uuid.uuid4(),
        cohort_id=cohort_b.id,
        contact_id=student_b_contact.id,
        status="registered",
        ticket_token=f"TKB-{uuid.uuid4().hex[:10].upper()}",
        registered_via="desk",
    )
    db.add_all([reg_a, reg_b])
    await db.flush()

    written_q = PreSessionQuizQuestion(
        id=uuid.uuid4(),
        topic="Safety",
        question_type="written",
        title="Safety Check",
        prompt="Explain ESD grounding before powering the lab.",
        options=[],
        points=1,
        is_active=True,
        organization_id=org.id,
        created_by=org_owner.id,
    )
    db.add(written_q)
    await db.flush()

    org_preset = PreSessionQuizPreset(
        id=uuid.uuid4(),
        name=f"Org Readiness {suffix}",
        description="Org safety assessment",
        preset_type="readiness_pipeline",
        draw_size=1,
        critical_floor=0,
        passing_score_percent=80,
        question_ids=[str(written_q.id)],
        reference_attachments=[],
        phases=[
            {
                "id": f"phase-{suffix}",
                "phase_type": "quiz",
                "title": "Quiz",
                "subtitle": "",
                "instructions": [],
                "pass_percentage": 80,
                "cooldown_seconds": 0,
                "show_correct_on_fail": False,
                "show_explanation_on_fail": True,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [str(written_q.id)],
                "matching_config": None,
            }
        ],
        is_active=True,
        organization_id=org.id,
        created_by=org_owner.id,
    )
    db.add(org_preset)
    await db.commit()

    return {
        "city": city,
        "ops": ops,
        "sp_instructor": sp_instructor,
        "org": org,
        "other_org": other_org,
        "org_owner": org_owner,
        "org_coordinator": org_coordinator,
        "org_instructor": org_instructor,
        "org_observer": org_observer,
        "global_loc": global_loc,
        "org_loc": org_loc,
        "other_loc": other_loc,
        "role_lead": role_lead,
        "role_fac": role_fac,
        "org_program": org_program,
        "sp_program": sp_program,
        "cohort_a": cohort_a,
        "cohort_b": cohort_b,
        "session_a": session_a,
        "session_b": session_b,
        "student_a_contact": student_a_contact,
        "student_b_contact": student_b_contact,
        "outside_contact": outside_contact,
        "reg_a": reg_a,
        "reg_b": reg_b,
        "written_q": written_q,
        "org_preset": org_preset,
    }


@pytest.mark.asyncio
async def test_group_a_queue_isolation_and_mode_b_visibility(db, client):
    w = await _seed_phase1_world(db)

    # Assign instructors & submitted day rows on both modes
    db.add_all([
        SessionInstructor(id=uuid.uuid4(), session_id=w["session_a"].id, user_id=w["org_instructor"].id, role_id=w["role_lead"].id),
        SessionInstructor(id=uuid.uuid4(), session_id=w["session_b"].id, user_id=w["sp_instructor"].id, role_id=w["role_lead"].id),
        InstructorSessionDay(
            id=uuid.uuid4(),
            session_id=w["session_a"].id,
            user_id=w["org_instructor"].id,
            att_status="present",
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
        ),
        InstructorSessionDay(
            id=uuid.uuid4(),
            session_id=w["session_b"].id,
            user_id=w["sp_instructor"].id,
            att_status="present",
            status="submitted",
            submitted_at=datetime.now(timezone.utc),
        ),
    ])
    await db.commit()

    # 1. GET /sessions/cohorts default returns Mode B (not Mode A)
    default_resp = await client.get("/sessions/cohorts", headers=_headers(w["ops"]))
    assert default_resp.status_code == 200
    by_id = {c["id"]: c for c in default_resp.json()}
    assert str(w["cohort_b"].id) in by_id
    assert str(w["cohort_a"].id) not in by_id
    assert by_id[str(w["cohort_b"].id)]["management_mode"] == "spacepoint"
    assert by_id[str(w["cohort_b"].id)]["organization_name"] == w["org"].name_latin

    # ?management_mode=partner returns Mode A only; =all returns both
    partner_resp = await client.get("/sessions/cohorts?management_mode=partner", headers=_headers(w["ops"]))
    assert partner_resp.status_code == 200
    partner_ids = {c["id"] for c in partner_resp.json()}
    assert str(w["cohort_a"].id) in partner_ids
    assert str(w["cohort_b"].id) not in partner_ids

    all_resp = await client.get("/sessions/cohorts?management_mode=all", headers=_headers(w["ops"]))
    assert all_resp.status_code == 200
    all_ids = {c["id"] for c in all_resp.json()}
    assert str(w["cohort_a"].id) in all_ids
    assert str(w["cohort_b"].id) in all_ids

    # 2. Ops Day Reviews & Session Board exclude Mode A and include Mode B
    reviews_resp = await client.get("/sessions/day-reviews", headers=_headers(w["ops"]))
    assert reviews_resp.status_code == 200
    review_session_ids = {r["session_id"] for r in reviews_resp.json()}
    assert str(w["session_b"].id) in review_session_ids
    assert str(w["session_a"].id) not in review_session_ids

    board_resp = await client.get("/sessions/board", headers=_headers(w["ops"]))
    assert board_resp.status_code == 200
    board_session_ids = {s["session_id"] for s in board_resp.json()["running"]}
    assert str(w["session_b"].id) in board_session_ids
    assert str(w["session_a"].id) not in board_session_ids

    # 3. Ops dashboard excludes Mode A cohorts & sessions
    dash_resp = await client.get("/sessions/dashboard", headers=_headers(w["ops"]))
    assert dash_resp.status_code == 200
    assert dash_resp.json()["active_cohorts"] == 1
    assert dash_resp.json()["upcoming_meetings_7d"] == 1

    # 4. /sessions/mine scope filtering
    sp_mine = await client.get("/sessions/mine?scope=spacepoint", headers=_headers(w["sp_instructor"]))
    assert sp_mine.status_code == 200
    sp_mine_ids = {s["session_id"] for s in sp_mine.json()}
    assert str(w["session_b"].id) in sp_mine_ids
    assert str(w["session_a"].id) not in sp_mine_ids

    org_mine = await client.get("/sessions/mine?scope=org", headers=_headers(w["org_instructor"]))
    assert org_mine.status_code == 200
    org_mine_ids = {s["session_id"] for s in org_mine.json()}
    assert str(w["session_a"].id) in org_mine_ids
    assert str(w["session_b"].id) not in org_mine_ids

    # 5. Partner overview shows both Mode A & Mode B, quotas exclude Mode B & SP-owned program
    ov_resp = await client.get("/organization/programs-overview", headers=_headers(w["org_owner"]))
    assert ov_resp.status_code == 200
    ov = ov_resp.json()
    assert ov["quotas"]["programs_count"] == 1
    assert ov["quotas"]["cohorts_count"] == 1
    prog_map = {p["id"]: p for p in ov["programs"]}
    assert prog_map[str(w["org_program"].id)]["is_org_owned"] is True
    assert prog_map[str(w["sp_program"].id)]["is_org_owned"] is False
    cohort_modes = {
        c["id"]: c["management_mode"]
        for p in ov["programs"]
        for c in p["cohorts"]
    }
    assert cohort_modes[str(w["cohort_a"].id)] == "partner"
    assert cohort_modes[str(w["cohort_b"].id)] == "spacepoint"


@pytest.mark.asyncio
async def test_group_b_mode_b_partner_write_boundary_and_redaction(db, client):
    w = await _seed_phase1_world(db)

    day_b = InstructorSessionDay(
        id=uuid.uuid4(),
        session_id=w["session_b"].id,
        user_id=w["sp_instructor"].id,
        att_status="present",
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(day_b)
    await db.commit()

    coord_hdrs = _headers(w["org_coordinator"])

    # Partner CAN edit cohort details/dates/location and exceed student cap on Mode B
    patch_ok = await client.patch(
        f"/sessions/cohorts/{w['cohort_b'].id}",
        headers=coord_hdrs,
        json={"name": "Mode B Renamed", "location_id": str(w["org_loc"].id), "capacity": 50},
    )
    assert patch_ok.status_code == 200, patch_ok.text
    assert patch_ok.json()["name"] == "Mode B Renamed"
    assert patch_ok.json()["location_id"] == str(w["org_loc"].id)

    # Partner CAN add/edit/delete session on Mode B without duration_hours
    add_sess_ok = await client.post(
        f"/sessions/cohorts/{w['cohort_b'].id}/sessions",
        headers=coord_hdrs,
        json={"meeting_date": "2027-02-15", "title": "Partner Added Session"},
    )
    assert add_sess_ok.status_code == 201, add_sess_ok.text
    new_sid = add_sess_ok.json()["id"]

    edit_sess_ok = await client.patch(
        f"/sessions/cohorts/{w['cohort_b'].id}/sessions/{new_sid}",
        headers=coord_hdrs,
        json={"title": "Updated Title", "location_id": str(w["org_loc"].id)},
    )
    assert edit_sess_ok.status_code == 200, edit_sess_ok.text
    assert edit_sess_ok.json()["title"] == "Updated Title"

    del_sess_ok = await client.delete(
        f"/sessions/cohorts/{w['cohort_b'].id}/sessions/{new_sid}",
        headers=coord_hdrs,
    )
    assert del_sess_ok.status_code == 204

    # Partner CAN desk-register student on Mode B beyond max_students_per_cohort=1
    reg_ok = await client.post(
        f"/sessions/cohorts/{w['cohort_b'].id}/registrations",
        headers=coord_hdrs,
        json={
            "student_name": "Extra Mode B Student",
            "email": f"extra-b-{uuid.uuid4().hex[:6]}@example.com",
            "phone": "+971504444444",
        },
    )
    assert reg_ok.status_code == 201, reg_ok.text

    # Partner CAN add > max_observers_per_cohort=1 observers & try-as-observer on Mode B
    obs1 = await client.post(
        f"/organization/cohorts/{w['cohort_b'].id}/observers",
        headers=coord_hdrs,
        json={"user_id": str(w["org_observer"].id)},
    )
    assert obs1.status_code == 201, obs1.text
    obs2 = await client.post(
        f"/organization/cohorts/{w['cohort_b'].id}/observers",
        headers=coord_hdrs,
        json={"user_id": str(w["org_owner"].id)},
    )
    assert obs2.status_code == 201, obs2.text
    try_obs = await client.post(
        f"/lms/admin/cohorts/{w['cohort_b'].id}/try-as-observer",
        headers=coord_hdrs,
        json={},
    )
    assert try_obs.status_code == 200, try_obs.text
    del_obs = await client.delete(
        f"/organization/cohorts/{w['cohort_b'].id}/observers/{w['org_owner'].id}",
        headers=coord_hdrs,
    )
    assert del_obs.status_code == 204

    # Partner gets 403 on Mode B restricted delivery/staffing/rates/duration/complete/prequiz endpoints
    forbidden_calls = [
        ("PATCH", f"/sessions/cohorts/{w['cohort_b'].id}", {"duration_hours": 3}),
        ("POST", f"/sessions/cohorts/{w['cohort_b'].id}/sessions", {"meeting_date": "2027-03-01", "duration_hours": 3}),
        ("PATCH", f"/sessions/cohorts/{w['cohort_b'].id}/sessions/{w['session_b'].id}", {"duration_hours": 3}),
        ("POST", f"/organization/cohorts/{w['cohort_b'].id}/instructors", {"user_id": str(w["org_instructor"].id)}),
        ("PATCH", f"/organization/cohorts/{w['cohort_b'].id}/instructors/{w['sp_instructor'].id}", {"role_id": str(w["role_fac"].id)}),
        ("DELETE", f"/organization/cohorts/{w['cohort_b'].id}/instructors/{w['sp_instructor'].id}", None),
        ("POST", f"/sessions/cohorts/{w['cohort_b'].id}/sessions/{w['session_b'].id}/instructors", {"user_id": str(w["org_instructor"].id)}),
        ("PUT", f"/sessions/cohorts/{w['cohort_b'].id}/openings-defaults", {"openings": [{"role_id": str(w["role_lead"].id), "slots": 1}]}),
        ("PUT", f"/sessions/{w['session_b'].id}/openings", {"openings": [{"role_id": str(w["role_lead"].id), "slots": 1}]}),
        ("POST", f"/sessions/{w['session_b'].id}/delivery/start", None),
        ("POST", f"/sessions/{w['session_b'].id}/delivery/done", None),
        ("POST", f"/sessions/day-reviews/{day_b.id}/approve", None),
        ("POST", f"/sessions/day-reviews/{day_b.id}/return", {"comment": "Fix photo"}),
        ("POST", f"/sessions/cohorts/{w['cohort_b'].id}/complete", {"send_certificates": False}),
        ("PUT", f"/sessions/pre-quiz/assignments/cohorts/{w['cohort_b'].id}", {"preset_id": str(w["org_preset"].id)}),
        ("PUT", f"/organization/cohorts/{w['cohort_b'].id}/readiness", {"preset_id": str(w["org_preset"].id)}),
    ]
    for method, url, payload in forbidden_calls:
        resp = await client.request(method, url, headers=coord_hdrs, json=payload)
        assert resp.status_code == 403, f"Expected 403 for {method} {url}, got {resp.status_code}: {resp.text}"

    # Partner reads redacted AED rates (all null) even if Ops set amounts on Mode B
    await client.put(
        f"/sessions/cohorts/{w['cohort_b'].id}/openings-defaults",
        headers=_headers(w["ops"]),
        json={"openings": [{"role_id": str(w["role_lead"].id), "slots": 1, "amount_aed": 700}]},
    )
    roles_partner = await client.get("/sessions/delivery-roles", headers=coord_hdrs)
    assert roles_partner.status_code == 200
    assert all(r["default_rate_aed"] is None for r in roles_partner.json())

    cohort_openings_partner = await client.get(
        f"/sessions/cohorts/{w['cohort_b'].id}/openings-defaults", headers=coord_hdrs
    )
    assert cohort_openings_partner.status_code == 200
    for row in cohort_openings_partner.json():
        assert row["amount_aed"] is None
        assert row["role_default_rate_aed"] is None

    sess_openings_partner = await client.get(
        f"/sessions/{w['session_b'].id}/openings", headers=coord_hdrs
    )
    assert sess_openings_partner.status_code == 200
    for row in sess_openings_partner.json():
        assert row["amount_aed"] is None
        assert row["rate_source"] is None


@pytest.mark.asyncio
async def test_group_c_mode_b_spacepoint_ops_and_instructor_lifecycle(db, client):
    w = await _seed_phase1_world(db)
    ops_hdrs = _headers(w["ops"])
    inst_hdrs = _headers(w["sp_instructor"])

    # Reset started_at so instructor start transitions cleanly
    w["session_b"].started_at = None
    await db.commit()

    # Ops assigns SP instructor with DeliveryRole
    assign_resp = await client.post(
        f"/sessions/cohorts/{w['cohort_b'].id}/sessions/{w['session_b'].id}/instructors",
        headers=ops_hdrs,
        json={"user_id": str(w["sp_instructor"].id), "role_id": str(w["role_lead"].id)},
    )
    assert assign_resp.status_code == 201, assign_resp.text

    # Ops sets openings with AED rate & reads non-null AED amount back
    openings_resp = await client.put(
        f"/sessions/cohorts/{w['cohort_b'].id}/openings-defaults",
        headers=ops_hdrs,
        json={"openings": [{"role_id": str(w["role_lead"].id), "slots": 1, "amount_aed": "450.00"}]},
    )
    assert openings_resp.status_code == 200
    assert Decimal(str(openings_resp.json()[0]["amount_aed"])) == Decimal("450.00")

    # Ops updates duration_hours on Mode B cohort
    dur_resp = await client.patch(
        f"/sessions/cohorts/{w['cohort_b'].id}",
        headers=ops_hdrs,
        json={"duration_hours": "2.5"},
    )
    assert dur_resp.status_code == 200

    # SP instructor can start and mark done on Mode B session
    start_resp = await client.post(f"/sessions/{w['session_b'].id}/delivery/start", headers=inst_hdrs)
    assert start_resp.status_code == 200, start_resp.text
    done_resp = await client.post(f"/sessions/{w['session_b'].id}/delivery/done", headers=inst_hdrs)
    assert done_resp.status_code == 200, done_resp.text

    # Ops approves submitted day review & completes Mode B cohort
    day_row = InstructorSessionDay(
        id=uuid.uuid4(),
        session_id=w["session_b"].id,
        user_id=w["sp_instructor"].id,
        att_status="present",
        status="submitted",
        submitted_at=datetime.now(timezone.utc),
    )
    db.add(day_row)
    await db.commit()

    approve_resp = await client.post(f"/sessions/day-reviews/{day_row.id}/approve", headers=ops_hdrs)
    assert approve_resp.status_code == 200, approve_resp.text
    assert approve_resp.json()["status"] == "approved"

    comp_resp = await client.post(
        f"/sessions/cohorts/{w['cohort_b'].id}/complete",
        headers=ops_hdrs,
        json={"send_certificates": False},
    )
    assert comp_resp.status_code == 200, comp_resp.text
    assert comp_resp.json()["cohort"]["status"] == "completed"


@pytest.mark.asyncio
async def test_group_d_mode_a_full_parity_and_redaction(db, client):
    w = await _seed_phase1_world(db)
    coord_hdrs = _headers(w["org_coordinator"])
    inst_hdrs = _headers(w["org_instructor"])

    # 1. Roles list redacted + Mode A openings strip any AED amounts even when submitted
    roles_resp = await client.get("/sessions/delivery-roles", headers=coord_hdrs)
    assert roles_resp.status_code == 200
    assert len(roles_resp.json()) >= 2
    assert all(r["default_rate_aed"] is None for r in roles_resp.json())

    put_defaults = await client.put(
        f"/sessions/cohorts/{w['cohort_a'].id}/openings-defaults",
        headers=coord_hdrs,
        json={"openings": [{"role_id": str(w["role_lead"].id), "slots": 2, "amount_aed": 999}]},
    )
    assert put_defaults.status_code == 200, put_defaults.text
    assert put_defaults.json()[0]["slots"] == 2
    assert put_defaults.json()[0]["amount_aed"] is None
    assert put_defaults.json()[0]["role_default_rate_aed"] is None

    put_sess_open = await client.put(
        f"/sessions/{w['session_a'].id}/openings",
        headers=coord_hdrs,
        json={"openings": [{"role_id": str(w["role_fac"].id), "slots": 1, "amount_aed": 888}]},
    )
    assert put_sess_open.status_code == 200, put_sess_open.text
    assert put_sess_open.json()[0]["amount_aed"] is None
    assert put_sess_open.json()[0]["rate_source"] is None

    # 2. Assign org instructor with role + PATCH role via org sandbox endpoint
    assign_org = await client.post(
        f"/organization/cohorts/{w['cohort_a'].id}/instructors",
        headers=coord_hdrs,
        json={"user_id": str(w["org_instructor"].id), "role_id": str(w["role_lead"].id)},
    )
    assert assign_org.status_code == 201, assign_org.text

    patch_role = await client.patch(
        f"/organization/cohorts/{w['cohort_a'].id}/instructors/{w['org_instructor'].id}",
        headers=coord_hdrs,
        json={"role_id": str(w["role_fac"].id)},
    )
    assert patch_role.status_code == 200, patch_role.text
    assert patch_role.json()["role_name"] == w["role_fac"].name

    # 3. Org-scoped Location CRUD isolated from global & other org locations
    create_loc = await client.post(
        "/inventory/locations",
        headers=coord_hdrs,
        json={"name": "Partner Annex Room", "city_id": str(w["city"].id)},
    )
    assert create_loc.status_code == 201, create_loc.text
    assert create_loc.json()["organization_id"] == str(w["org"].id)

    list_loc = await client.get("/inventory/locations", headers=coord_hdrs)
    assert list_loc.status_code == 200
    loc_ids = {l["id"] for l in list_loc.json()}
    assert str(w["org_loc"].id) in loc_ids
    assert create_loc.json()["id"] in loc_ids
    assert str(w["global_loc"].id) not in loc_ids
    assert str(w["other_loc"].id) not in loc_ids

    # 4. /sessions/today & /sessions/checkin work on org session
    today_resp = await client.get("/sessions/today", headers=coord_hdrs)
    assert today_resp.status_code == 200
    today_ids = {s["id"] for s in today_resp.json()}
    assert str(w["session_a"].id) in today_ids
    assert str(w["session_b"].id) in today_ids

    checkin_resp = await client.post(
        "/sessions/checkin",
        headers=coord_hdrs,
        json={"token": w["reg_a"].ticket_token, "session_id": str(w["session_a"].id)},
    )
    assert checkin_resp.status_code == 200, checkin_resp.text
    assert checkin_resp.json()["att_status"] == "present"

    # 5. Contact edit succeeds for in-org student, 404 outside org, 403 disallowed field
    edit_student = await client.patch(
        f"/spine/contacts/{w['student_a_contact'].id}",
        headers=coord_hdrs,
        json={"full_name": "Student Mode A Edited", "grade": "Grade 11"},
    )
    assert edit_student.status_code == 200, edit_student.text
    assert edit_student.json()["full_name"] == "Student Mode A Edited"

    edit_outside = await client.patch(
        f"/spine/contacts/{w['outside_contact'].id}",
        headers=coord_hdrs,
        json={"full_name": "Hack Name"},
    )
    assert edit_outside.status_code == 404

    edit_bad_field = await client.patch(
        f"/spine/contacts/{w['student_a_contact'].id}",
        headers=coord_hdrs,
        json={"contact_roles": ["instructor"]},
    )
    assert edit_bad_field.status_code == 403

    # 6. Pre-session quiz assign & written review on Mode A
    assign_pq = await client.put(
        f"/sessions/pre-quiz/assignments/cohorts/{w['cohort_a'].id}",
        headers=coord_hdrs,
        json={"preset_id": str(w["org_preset"].id)},
    )
    assert assign_pq.status_code == 200, assign_pq.text

    phase_id = w["org_preset"].phases[0]["id"]
    start_pq = await client.post(
        f"/sessions/cohorts/{w['cohort_a'].id}/pre-quiz/phases/{phase_id}/start",
        headers=inst_hdrs,
    )
    assert start_pq.status_code == 200, start_pq.text
    attempt_id = start_pq.json()["id"]

    submit_pq = await client.post(
        f"/sessions/cohorts/{w['cohort_a'].id}/pre-quiz/phases/{phase_id}/submit",
        headers=inst_hdrs,
        json={
            "client_duration_seconds": 5,
            "answers": [{"question_id": str(w["written_q"].id), "written_text": "Use wrist strap"}],
        },
    )
    assert submit_pq.status_code == 200, submit_pq.text

    review_pq = await client.patch(
        f"/sessions/pre-quiz/attempts/{attempt_id}/review",
        headers=coord_hdrs,
        json={"question_id": str(w["written_q"].id), "is_correct": True, "review_comment": "Good"},
    )
    assert review_pq.status_code == 200, review_pq.text
    assert review_pq.json()["pending_review_count"] == 0

    # 7. Mode A complete cohort succeeds
    complete_a = await client.post(
        f"/sessions/cohorts/{w['cohort_a'].id}/complete",
        headers=coord_hdrs,
        json={"send_certificates": False},
    )
    assert complete_a.status_code == 200, complete_a.text
    assert complete_a.json()["cohort"]["status"] == "completed"


@pytest.mark.asyncio
async def test_group_e_org_observer_strict_read_only(db, client):
    w = await _seed_phase1_world(db)
    await db.commit()

    obs_hdrs = _headers(w["org_observer"])

    # Observer CAN GET all read endpoints
    get_urls = [
        "/organization/programs-overview",
        f"/sessions/cohorts/{w['cohort_a'].id}",
        f"/sessions/cohorts/{w['cohort_a'].id}/sessions",
        f"/sessions/cohorts/{w['cohort_a'].id}/registrations",
        f"/organization/cohorts/{w['cohort_a'].id}/staff",
        f"/organization/cohorts/{w['cohort_a'].id}/observers",
        f"/sessions/cohorts/{w['cohort_a'].id}/checklists/summary",
        f"/sessions/day-reviews?cohort_id={w['cohort_a'].id}&status_filter=",
        f"/sessions/cohorts/{w['cohort_a'].id}/openings-defaults",
        f"/sessions/cohorts/{w['cohort_a'].id}/pre-quiz",
        "/inventory/locations",
    ]
    for url in get_urls:
        r = await client.get(url, headers=obs_hdrs)
        assert r.status_code == 200, f"Observer GET {url} returned {r.status_code}: {r.text}"

    # Observer gets 403 on ALL write endpoints
    write_calls = [
        ("PATCH", f"/sessions/cohorts/{w['cohort_a'].id}", {"name": "Blocked"}),
        ("POST", f"/sessions/cohorts/{w['cohort_a'].id}/sessions", {"meeting_date": "2027-04-01"}),
        ("POST", f"/sessions/cohorts/{w['cohort_a'].id}/registrations", {"student_name": "X", "email": "x@y.com", "phone": "+971509999999"}),
        ("PATCH", f"/spine/contacts/{w['student_a_contact'].id}", {"full_name": "Blocked"}),
        ("POST", f"/organization/cohorts/{w['cohort_a'].id}/instructors", {"user_id": str(w["org_instructor"].id)}),
        ("PUT", f"/sessions/cohorts/{w['cohort_a'].id}/openings-defaults", {"openings": [{"role_id": str(w["role_lead"].id), "slots": 1}]}),
        ("PUT", f"/sessions/{w['session_a'].id}/openings", {"openings": [{"role_id": str(w["role_lead"].id), "slots": 1}]}),
        ("POST", "/sessions/checkin", {"token": w["reg_a"].ticket_token, "session_id": str(w["session_a"].id)}),
        ("POST", f"/sessions/cohorts/{w['cohort_a'].id}/complete", {"send_certificates": False}),
        ("POST", "/inventory/locations", {"name": "Blocked Loc", "city_id": str(w["city"].id)}),
        ("PUT", f"/sessions/pre-quiz/assignments/cohorts/{w['cohort_a'].id}", {"preset_id": str(w["org_preset"].id)}),
    ]
    for method, url, payload in write_calls:
        r = await client.request(method, url, headers=obs_hdrs, json=payload)
        assert r.status_code == 403, f"Observer {method} {url} expected 403, got {r.status_code}: {r.text}"
