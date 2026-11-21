"""Tests for Ops cohort-wide default checklist import, Switch Days, cohort-creation import options, and progress-safe checklist editing."""

import uuid
from datetime import date, time

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.sessions.checklist import DeliveryChecklistItem, InstructorSessionDay
from app.models.sessions.cohort import Cohort
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment, PreSessionQuizPreset
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.spine.organization import Organization
from app.models.user import User
from app.services.sessions import day as day_svc


async def _program(db, *, name: str = "Test Program") -> Program:
    p = Program(
        id=uuid.uuid4(),
        code=f"CHK-{uuid.uuid4().hex[:8]}",
        name=name,
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(p)
    await db.flush()
    return p


async def _role_id(db, name: str = "Lead Facilitator") -> uuid.UUID:
    rid = await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))
    assert rid is not None
    return rid


@pytest.mark.asyncio
async def test_inplace_checklist_reorder_preserves_item_ids_and_progress(
    db, client, operations_headers, operations_user, instructor_headers, instructor_user,
):
    program = await _program(db)
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Inplace Cohort", status="running")
    db.add(cohort)
    await db.flush()
    sess = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 10, 1))
    db.add(sess)
    await db.flush()
    lead_id = await _role_id(db, "Lead Facilitator")
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=sess.id, user_id=instructor_user.id, role_id=lead_id))
    await db.flush()
    await db.commit()

    # 1. Create instructor & internal checklist items on session
    inst_put = await client.put(
        f"/sessions/sessions/{sess.id}/checklist-items",
        json={
            "items": [
                {
                    "title": "Step A",
                    "is_required": True,
                    "sub_items": [{"title": "Sub A1", "is_required": True}],
                },
                {"title": "Step B", "is_required": True},
            ]
        },
        headers=operations_headers,
    )
    assert inst_put.status_code == 200, inst_put.text
    inst_items = inst_put.json()
    item_a_id = inst_items[0]["id"]
    item_b_id = inst_items[1]["id"]
    sub_a1_id = inst_items[0]["sub_items"][0]["id"]

    int_put = await client.put(
        f"/sessions/sessions/{sess.id}/checklist-items",
        params={"target_audience": "internal"},
        json={"items": [{"title": "Ops 1"}, {"title": "Ops 2"}]},
        headers=operations_headers,
    )
    assert int_put.status_code == 200, int_put.text
    ops1_id = int_put.json()[0]["id"]
    ops2_id = int_put.json()[1]["id"]

    # 2. Instructor & Ops record progress
    ci_resp = await client.post(
        f"/sessions/{sess.id}/delivery/check-in",
        json={"att_status": "present"},
        headers=instructor_headers,
    )
    assert ci_resp.status_code == 200
    prog_resp = await client.put(
        f"/sessions/{sess.id}/delivery/checklist/{item_a_id}",
        json={"is_done": True, "note": "Verified setup", "completed_sub_items": [sub_a1_id]},
        headers=instructor_headers,
    )
    assert prog_resp.status_code == 200

    ops_prog_resp = await client.post(
        f"/sessions/{sess.id}/internal-checklist/{ops1_id}",
        json={"is_done": True, "note": "Printed badges"},
        headers=operations_headers,
    )
    assert ops_prog_resp.status_code == 200

    # 3. Reorder & edit items passing their existing IDs
    reorder_inst = await client.put(
        f"/sessions/sessions/{sess.id}/checklist-items",
        json={
            "items": [
                {"id": item_b_id, "title": "Step B", "is_required": True},
                {
                    "id": item_a_id,
                    "title": "Step A (Renamed)",
                    "is_required": True,
                    "sub_items": [{"id": sub_a1_id, "title": "Sub A1", "is_required": True}],
                },
            ]
        },
        headers=operations_headers,
    )
    assert reorder_inst.status_code == 200, reorder_inst.text
    reordered = reorder_inst.json()
    assert [i["id"] for i in reordered] == [item_b_id, item_a_id]
    assert reordered[1]["title"] == "Step A (Renamed)"

    reorder_int = await client.put(
        f"/sessions/sessions/{sess.id}/checklist-items",
        params={"target_audience": "internal"},
        json={"items": [{"id": ops2_id, "title": "Ops 2"}, {"id": ops1_id, "title": "Ops 1"}]},
        headers=operations_headers,
    )
    assert reorder_int.status_code == 200
    assert [i["id"] for i in reorder_int.json()] == [ops2_id, ops1_id]

    # 4. Verify progress survived!
    day_resp = await client.get(f"/sessions/{sess.id}/delivery/day", headers=instructor_headers)
    assert day_resp.status_code == 200
    lines = day_resp.json()["checklist"]
    assert [l["title"] for l in lines] == ["Step B", "Step A (Renamed)"]
    assert lines[1]["is_done"] is True
    assert lines[1]["note"] == "Verified setup"
    assert lines[1]["completed_sub_items"] == [sub_a1_id]

    int_get = await client.get(f"/sessions/{sess.id}/internal-checklist", headers=operations_headers)
    assert int_get.status_code == 200
    int_lines = int_get.json()
    assert [l["title"] for l in int_lines] == ["Ops 2", "Ops 1"]
    assert int_lines[1]["is_done"] is True
    assert int_lines[1]["note"] == "Printed badges"

    # 5. Clearing with empty list still reverts to cohort fallback
    await client.put(
        f"/sessions/cohorts/{cohort.id}/checklist-items",
        json={"items": [{"title": "Cohort Fallback"}]},
        headers=operations_headers,
    )
    clear_resp = await client.put(
        f"/sessions/sessions/{sess.id}/checklist-items",
        json={"items": []},
        headers=operations_headers,
    )
    assert clear_resp.status_code == 200
    assert clear_resp.json() == []
    fallback_day = await client.get(f"/sessions/{sess.id}/delivery/day", headers=instructor_headers)
    assert [l["title"] for l in fallback_day.json()["checklist"]] == ["Cohort Fallback"]


@pytest.mark.asyncio
async def test_create_cohort_default_import_options_and_strict_template_matching(
    db, client, operations_headers,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    prog_a = await _program(db, name="Program A")
    prog_b = await _program(db, name="Program B")

    # Add a misleading non-draft cohort in prog_a whose name contains "template"
    real_misleading = Cohort(
        id=uuid.uuid4(),
        program_id=prog_a.id,
        name="Spring Template Run",
        status="planned",
        visibility="public",
    )
    db.add(real_misleading)
    await db.flush()
    misleading_sess = Session(id=uuid.uuid4(), cohort_id=real_misleading.id, meeting_date=date(2026, 5, 1), title="Wrong Day")
    db.add(misleading_sess)
    await db.flush()
    db.add(DeliveryChecklistItem(id=uuid.uuid4(), session_id=misleading_sess.id, title="Wrong Item"))
    await db.flush()

    # Configure official template on prog_a (Pre-Workshop + 2 days)
    await client.put(
        f"/sessions/programs/{prog_a.id}/checklist-items",
        json={"items": [{"title": "Prog A Pre", "attachments": [{"type": "link", "title": "Doc", "url": "https://example.com"}]}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/programs/{prog_a.id}/checklist-items",
        params={"role_id": str(lead_id)},
        json={"items": [{"title": "Prog A Lead Pre"}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/programs/{prog_a.id}/checklist-items",
        params={"target_audience": "internal"},
        json={"items": [{"title": "Prog A Internal Pre"}]},
        headers=operations_headers,
    )

    d1 = (await client.post(
        f"/sessions/programs/{prog_a.id}/template-days",
        json={"title": "Intro Day"},
        headers=operations_headers,
    )).json()
    d2 = (await client.post(
        f"/sessions/programs/{prog_a.id}/template-days",
        json={"title": "Build Day"},
        headers=operations_headers,
    )).json()
    await client.put(
        f"/sessions/sessions/{d1['id']}/checklist-items",
        json={"items": [{"title": "A Day 1 Inst", "sub_items": [{"title": "Sub 1"}]}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/sessions/{d1['id']}/checklist-items",
        params={"target_audience": "internal"},
        json={"items": [{"title": "A Day 1 Int"}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/sessions/{d2['id']}/checklist-items",
        params={"role_id": str(lead_id)},
        json={"items": [{"title": "A Day 2 Lead"}]},
        headers=operations_headers,
    )

    # Configure official template on prog_b
    await client.put(
        f"/sessions/programs/{prog_b.id}/checklist-items",
        json={"items": [{"title": "Prog B Pre"}]},
        headers=operations_headers,
    )
    b1 = (await client.post(
        f"/sessions/programs/{prog_b.id}/template-days",
        json={"title": "B Day 1"},
        headers=operations_headers,
    )).json()
    await client.put(
        f"/sessions/sessions/{b1['id']}/checklist-items",
        json={"items": [{"title": "B Day 1 Inst"}]},
        headers=operations_headers,
    )

    # 1. Default creation in prog_a copies prog_a (NOT real_misleading)
    c_default = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(prog_a.id), "name": "Cohort Default", "starts_on": "2026-10-10"},
        headers=operations_headers,
    )).json()
    c_default_id = uuid.UUID(c_default["id"])
    sess_a = (await client.get(f"/sessions/cohorts/{c_default_id}/sessions", headers=operations_headers)).json()
    assert [s["title"] for s in sess_a] == ["Intro Day", "Build Day"]
    assert [i["title"] for i in (await client.get(f"/sessions/cohorts/{c_default_id}/checklist-items", headers=operations_headers)).json()] == ["Prog A Pre"]
    assert [i["title"] for i in (await client.get(f"/sessions/cohorts/{c_default_id}/checklist-items", params={"role_id": str(lead_id)}, headers=operations_headers)).json()] == ["Prog A Lead Pre"]
    assert [i["title"] for i in (await client.get(f"/sessions/cohorts/{c_default_id}/checklist-items", params={"target_audience": "internal"}, headers=operations_headers)).json()] == ["Prog A Internal Pre"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{sess_a[0]['id']}/checklist-items", headers=operations_headers)).json()] == ["A Day 1 Inst"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{sess_a[0]['id']}/checklist-items", params={"target_audience": "internal"}, headers=operations_headers)).json()] == ["A Day 1 Int"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{sess_a[1]['id']}/checklist-items", params={"role_id": str(lead_id)}, headers=operations_headers)).json()] == ["A Day 2 Lead"]

    # 2. Create in prog_a with checklist_source_program_id=prog_b
    c_cross = (await client.post(
        "/sessions/cohorts",
        json={
            "program_id": str(prog_a.id),
            "name": "Cohort From B",
            "starts_on": "2026-10-20",
            "import_default_checklists": True,
            "checklist_source_program_id": str(prog_b.id),
        },
        headers=operations_headers,
    )).json()
    sess_b = (await client.get(f"/sessions/cohorts/{c_cross['id']}/sessions", headers=operations_headers)).json()
    assert [s["title"] for s in sess_b] == ["B Day 1"]
    assert [i["title"] for i in (await client.get(f"/sessions/cohorts/{c_cross['id']}/checklist-items", headers=operations_headers)).json()] == ["Prog B Pre"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{sess_b[0]['id']}/checklist-items", headers=operations_headers)).json()] == ["B Day 1 Inst"]

    # 3. Create with import_default_checklists=False creates 0 sessions & 0 checklist items
    c_blank = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(prog_a.id), "name": "Cohort Blank", "import_default_checklists": False},
        headers=operations_headers,
    )).json()
    assert (await client.get(f"/sessions/cohorts/{c_blank['id']}/sessions", headers=operations_headers)).json() == []
    assert (await client.get(f"/sessions/cohorts/{c_blank['id']}/checklist-items", headers=operations_headers)).json() == []


@pytest.mark.asyncio
async def test_import_default_summary_and_fill_empty_and_cohort_source(
    db, client, operations_headers, instructor_headers, instructor_user,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    program = await _program(db)

    # Program template: 2 days
    await client.put(
        f"/sessions/programs/{program.id}/checklist-items",
        json={"items": [{"title": "Pre Inst"}]},
        headers=operations_headers,
    )
    await client.put(
        f"/sessions/programs/{program.id}/checklist-items",
        params={"target_audience": "internal"},
        json={"items": [{"title": "Pre Int"}]},
        headers=operations_headers,
    )
    td1 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl Day 1"}, headers=operations_headers)).json()
    td2 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl Day 2"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", json={"items": [{"title": "Tpl D1 Inst"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": "Tpl D1 Int"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{td2['id']}/checklist-items", json={"items": [{"title": "Tpl D2 Inst 1"}, {"title": "Tpl D2 Inst 2"}]}, headers=operations_headers)

    # Target inheriting cohort with 2 sessions (Day 1 custom direct, Day 2 inherited)
    cohort_obj = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Manual Cohort",
        status="planned",
        inherit_default_checklists=True,
    )
    db.add(cohort_obj)
    await db.flush()
    s1_obj = Session(id=uuid.uuid4(), cohort_id=cohort_obj.id, meeting_date=date(2026, 11, 1), title="Existing 1")
    s2_obj = Session(id=uuid.uuid4(), cohort_id=cohort_obj.id, meeting_date=date(2026, 11, 2), title="Existing 2")
    db.add_all([s1_obj, s2_obj])
    await db.flush()
    cohort = {"id": str(cohort_obj.id)}
    s1 = {"id": str(s1_obj.id)}
    s2 = {"id": str(s2_obj.id)}
    await client.put(f"/sessions/sessions/{s1['id']}/checklist-items", json={"items": [{"title": "Custom D1"}]}, headers=operations_headers)

    # Add progress on s1 so summary flags it
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=uuid.UUID(s1["id"]), user_id=instructor_user.id, role_id=lead_id))
    await db.commit()
    await client.post(f"/sessions/{s1['id']}/delivery/check-in", json={"att_status": "present"}, headers=instructor_headers)
    s1_item_id = (await client.get(f"/sessions/sessions/{s1['id']}/checklist-items", headers=operations_headers)).json()[0]["id"]
    await client.put(f"/sessions/{s1['id']}/delivery/checklist/{s1_item_id}", json={"is_done": True}, headers=instructor_headers)

    # Instructor cannot call summary or import-default
    assert (await client.get(f"/sessions/cohorts/{cohort['id']}/checklists/summary", headers=instructor_headers)).status_code == 403
    assert (await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/import-default",
        json={"source_type": "program"},
        headers=instructor_headers,
    )).status_code == 403

    # Summary checks direct + inherited + progress
    sum_resp = await client.get(f"/sessions/cohorts/{cohort['id']}/checklists/summary", headers=operations_headers)
    assert sum_resp.status_code == 200, sum_resp.text
    sum_body = sum_resp.json()
    assert len(sum_body["sessions"]) == 2
    assert sum_body["sessions"][0]["instructor_items_count"] == 1
    assert sum_body["sessions"][0]["has_instructor_progress"] is True
    assert sum_body["sessions"][1]["instructor_items_count"] == 0
    assert sum_body["sessions"][1]["is_instructor_inherited"] is True
    assert sum_body["sessions"][1]["effective_instructor_items_count"] == 2

    # 1. Import with mode="fill_empty" preserves s1 ("Custom D1") and fills s2
    fill_resp = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/import-default",
        json={
            "source_type": "program",
            "mode": "fill_empty",
            "include_titles": False,
        },
        headers=operations_headers,
    )
    assert fill_resp.status_code == 200, fill_resp.text
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s1['id']}/checklist-items", headers=operations_headers)).json()] == ["Custom D1"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s2['id']}/checklist-items", headers=operations_headers)).json()] == ["Tpl D2 Inst 1", "Tpl D2 Inst 2"]

    # 2. Import with custom day_mappings (swap td2 -> s1, skip s2) & replace & include_titles
    map_resp = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/import-default",
        json={
            "source_type": "program",
            "mode": "replace",
            "include_titles": True,
            "day_mappings": [
                {"target_session_id": s1["id"], "source_session_id": td2["id"]},
                {"target_session_id": s2["id"], "source_session_id": None},
            ],
        },
        headers=operations_headers,
    )
    assert map_resp.status_code == 200, map_resp.text
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s1['id']}/checklist-items", headers=operations_headers)).json()] == ["Tpl D2 Inst 1", "Tpl D2 Inst 2"]
    # s2 was skipped so it still has its items
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s2['id']}/checklist-items", headers=operations_headers)).json()] == ["Tpl D2 Inst 1", "Tpl D2 Inst 2"]
    updated_sessions = (await client.get(f"/sessions/cohorts/{cohort['id']}/sessions", headers=operations_headers)).json()
    assert updated_sessions[0]["title"] == "Tpl Day 2"
    assert updated_sessions[1]["title"] == "Existing 2"

    # 3. create_missing_sessions=True on an empty cohort + import from cohort source
    empty_cohort = (await client.post(
        "/sessions/cohorts",
        json={"program_id": str(program.id), "name": "Empty Target", "starts_on": "2026-12-01", "import_default_checklists": False},
        headers=operations_headers,
    )).json()
    create_resp = await client.post(
        f"/sessions/cohorts/{empty_cohort['id']}/checklists/import-default",
        json={
            "source_type": "cohort",
            "source_id": cohort["id"],
            "create_missing_sessions": True,
            "include_titles": True,
        },
        headers=operations_headers,
    )
    assert create_resp.status_code == 200, create_resp.text
    assert create_resp.json()["sessions_created"] == 2
    created_sess = (await client.get(f"/sessions/cohorts/{empty_cohort['id']}/sessions", headers=operations_headers)).json()
    assert len(created_sess) == 2
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{created_sess[0]['id']}/checklist-items", headers=operations_headers)).json()] == ["Tpl D2 Inst 1", "Tpl D2 Inst 2"]


@pytest.mark.asyncio
async def test_switch_days_scopes_inheritance_materialization_and_fixed_dates(
    db, client, operations_headers, instructor_headers, instructor_user,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    facilitator_id = await _role_id(db, "Facilitator")
    program = await _program(db)

    # Program template with 3 days (no direct rows on cohort sessions initially -> tests materialization!)
    t1 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Day One"}, headers=operations_headers)).json()
    t2 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Day Two"}, headers=operations_headers)).json()
    t3 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Day Three"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{t1['id']}/checklist-items", json={"items": [{"title": "Inst 1"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t1['id']}/checklist-items", params={"role_id": str(lead_id)}, json={"items": [{"title": "Lead 1"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t1['id']}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": "Int 1"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t2['id']}/checklist-items", json={"items": [{"title": "Inst 2"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t2['id']}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": "Int 2"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t3['id']}/checklist-items", json={"items": [{"title": "Inst 3"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{t3['id']}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": "Int 3"}]}, headers=operations_headers)

    # Build inheriting cohort with 3 empty sessions (so they inherit from template days!) and assign instructor to session 1
    cohort_obj = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Switch Cohort",
        status="planned",
        inherit_default_checklists=True,
    )
    db.add(cohort_obj)
    await db.flush()
    cohort = {"id": str(cohort_obj.id)}
    s1 = Session(id=uuid.uuid4(), cohort_id=uuid.UUID(cohort["id"]), meeting_date=date(2026, 11, 10), starts_at=time(9, 0), title="Day One")
    s2 = Session(id=uuid.uuid4(), cohort_id=uuid.UUID(cohort["id"]), meeting_date=date(2026, 11, 12), starts_at=time(10, 0), title="Day Two")
    s3 = Session(id=uuid.uuid4(), cohort_id=uuid.UUID(cohort["id"]), meeting_date=date(2026, 11, 14), starts_at=time(11, 0), title="Day Three")
    db.add_all([s1, s2, s3])
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=s1.id, user_id=instructor_user.id, role_id=facilitator_id))
    await db.commit()

    # Role guard + validation
    assert (await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/switch-days",
        json={"session_plan_order": [str(s3.id), str(s1.id), str(s2.id)]},
        headers=instructor_headers,
    )).status_code == 403

    bad_perm = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/switch-days",
        json={"session_plan_order": [str(s1.id), str(s1.id), str(s2.id)]},
        headers=operations_headers,
    )
    assert bad_perm.status_code == 400

    # 1. Switch inherited days with scope="both" -> [s3, s1, s2]
    sw1 = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/switch-days",
        json={"session_plan_order": [str(s3.id), str(s1.id), str(s2.id)], "scope": "both", "include_titles": True},
        headers=operations_headers,
    )
    assert sw1.status_code == 200, sw1.text
    assert sw1.json()["sessions_switched"] == 3

    # Verify dates, starts_at, and instructor assignment on s1 did NOT move!
    sess_after = (await client.get(f"/sessions/cohorts/{cohort['id']}/sessions", headers=operations_headers)).json()
    assert [(s["id"], s["meeting_date"], s["starts_at"], s["title"]) for s in sess_after] == [
        (str(s1.id), "2026-11-10", "09:00:00", "Day Three"),
        (str(s2.id), "2026-11-12", "10:00:00", "Day One"),
        (str(s3.id), "2026-11-14", "11:00:00", "Day Two"),
    ]
    assert len(sess_after[0]["instructors"]) == 1
    assert sess_after[0]["instructors"][0]["user_id"] == str(instructor_user.id)

    # Check resolved instructor & internal checklists match swapped plan (including Lead role item that moved to s2!)
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s1.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 3"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s2.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 1"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s2.id}/checklist-items", params={"role_id": str(lead_id)}, headers=operations_headers)).json()] == ["Lead 1"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s3.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 2"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/delivery/day", headers=instructor_headers)).json()["checklist"]] == ["Inst 3"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 3"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s2.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 1"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s3.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 2"]

    # 2. Switch scope="instructor" only (swap s1 and s2 back) -> internal must stay [Int 3, Int 1, Int 2]
    sw2 = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/switch-days",
        json={"session_plan_order": [str(s2.id), str(s1.id), str(s3.id)], "scope": "instructor", "include_titles": False},
        headers=operations_headers,
    )
    assert sw2.status_code == 200
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s1.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 1"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s2.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 3"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 3"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s2.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 1"]

    # 3. Switch scope="internal" only (swap s1 and s3) -> instructor must stay [Inst 1, Inst 3, Inst 2]
    sw3 = await client.post(
        f"/sessions/cohorts/{cohort['id']}/checklists/switch-days",
        json={"session_plan_order": [str(s3.id), str(s2.id), str(s1.id)], "scope": "internal", "include_titles": False},
        headers=operations_headers,
    )
    assert sw3.status_code == 200
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s1.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 1"]
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{s3.id}/checklist-items", headers=operations_headers)).json()] == ["Inst 2"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 2"]
    assert [l["title"] for l in (await client.get(f"/sessions/{s3.id}/internal-checklist", headers=operations_headers)).json()] == ["Int 3"]



@pytest.mark.asyncio
async def test_cohort_opt_out_stays_blank_and_add_session_does_not_clobber_cleared_days(
    db, client, operations_headers, instructor_headers, instructor_user,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    program = await _program(db, name="Opt-Out Program")

    # Program Pre-Workshop + 2 template days
    await client.put(
        f"/sessions/programs/{program.id}/checklist-items",
        json={"items": [{"title": "Prog Pre"}]},
        headers=operations_headers,
    )
    td1 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl 1"}, headers=operations_headers)).json()
    td2 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl 2"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", json={"items": [{"title": "Tpl D1 Item"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": "Tpl D1 Int"}]}, headers=operations_headers)
    await client.put(f"/sessions/sessions/{td2['id']}/checklist-items", json={"items": [{"title": "Tpl D2 Item"}]}, headers=operations_headers)

    # 1. Opt-out cohort: adding & generating sessions on Step 2 must keep everything blank
    opt_out = (await client.post(
        "/sessions/cohorts",
        json={
            "program_id": str(program.id),
            "name": "Blank Opt-Out",
            "starts_on": "2026-12-07",
            "import_default_checklists": False,
        },
        headers=operations_headers,
    )).json()
    assert opt_out["inherit_default_checklists"] is False

    added = (await client.post(
        f"/sessions/cohorts/{opt_out['id']}/sessions",
        json={"meeting_date": "2026-12-07"},
        headers=operations_headers,
    )).json()
    gen = (await client.post(
        f"/sessions/cohorts/{opt_out['id']}/sessions:generate",
        json={"weekdays": [2], "count": 1},
        headers=operations_headers,
    )).json()
    assert len(gen["created"]) == 1

    db.add(SessionInstructor(id=uuid.uuid4(), session_id=uuid.UUID(added["id"]), user_id=instructor_user.id, role_id=lead_id))
    await db.commit()

    day_resp = await client.get(f"/sessions/{added['id']}/delivery/day", headers=instructor_headers)
    assert day_resp.status_code == 200
    assert day_resp.json()["checklist"] == []
    assert (await client.get(f"/sessions/{added['id']}/internal-checklist", headers=operations_headers)).json() == []

    summary = (await client.get(f"/sessions/cohorts/{opt_out['id']}/checklists/summary", headers=operations_headers)).json()
    assert len(summary["sessions"]) == 2
    for row in summary["sessions"]:
        assert row["instructor_items_count"] == 0
        assert row["effective_instructor_items_count"] == 0
        assert row["is_instructor_inherited"] is False
        assert row["internal_items_count"] == 0
        assert row["effective_internal_items_count"] == 0
        assert row["is_internal_inherited"] is False

    # 2. Inheriting cohort: adding a 3rd session later must NOT re-seed earlier sessions cleared by Ops
    inheriting = (await client.post(
        "/sessions/cohorts",
        json={
            "program_id": str(program.id),
            "name": "Inheriting Run",
            "starts_on": "2026-12-14",
            "import_default_checklists": True,
        },
        headers=operations_headers,
    )).json()
    sess_list = (await client.get(f"/sessions/cohorts/{inheriting['id']}/sessions", headers=operations_headers)).json()
    assert len(sess_list) == 2

    await client.put(f"/sessions/sessions/{sess_list[0]['id']}/checklist-items", json={"items": []}, headers=operations_headers)
    await client.post(
        f"/sessions/cohorts/{inheriting['id']}/sessions",
        json={"meeting_date": "2026-12-20"},
        headers=operations_headers,
    )
    assert (await client.get(f"/sessions/sessions/{sess_list[0]['id']}/checklist-items", headers=operations_headers)).json() == []


@pytest.mark.asyncio
async def test_cross_program_checklist_source_does_not_copy_quizzes(db, client, operations_headers):
    prog_a = await _program(db, name="Quiz Prog A")
    prog_b = await _program(db, name="Quiz Prog B")
    preset_a = PreSessionQuizPreset(id=uuid.uuid4(), name="Preset A")
    preset_b = PreSessionQuizPreset(id=uuid.uuid4(), name="Preset B")
    db.add_all([preset_a, preset_b])
    await db.flush()
    db.add(PreSessionQuizAssignment(id=uuid.uuid4(), program_id=prog_a.id, preset_id=preset_a.id))
    db.add(PreSessionQuizAssignment(id=uuid.uuid4(), program_id=prog_b.id, preset_id=preset_b.id))
    await db.commit()

    b1 = (await client.post(f"/sessions/programs/{prog_b.id}/template-days", json={"title": "B Day 1"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{b1['id']}/checklist-items", json={"items": [{"title": "B Check"}]}, headers=operations_headers)
    db.add(PreSessionQuizAssignment(id=uuid.uuid4(), variation_id=uuid.UUID(b1["cohort_id"]), preset_id=preset_b.id))
    db.add(PreSessionQuizAssignment(id=uuid.uuid4(), variation_day_id=uuid.UUID(b1["id"]), preset_id=preset_b.id))
    await db.commit()

    created = (await client.post(
        "/sessions/cohorts",
        json={
            "program_id": str(prog_a.id),
            "name": "Cross Program Cohort",
            "starts_on": "2026-12-01",
            "import_default_checklists": True,
            "checklist_source_program_id": str(prog_b.id),
        },
        headers=operations_headers,
    )).json()
    assert created["inherit_default_checklists"] is False
    cid = uuid.UUID(created["id"])

    sessions = (await client.get(f"/sessions/cohorts/{cid}/sessions", headers=operations_headers)).json()
    assert len(sessions) == 1
    assert [i["title"] for i in (await client.get(f"/sessions/sessions/{sessions[0]['id']}/checklist-items", headers=operations_headers)).json()] == ["B Check"]

    cohort_quizzes = (await db.execute(
        select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id == cid)
    )).scalars().all()
    assert [q.preset_id for q in cohort_quizzes] == [preset_a.id]
    sess_quizzes = (await db.execute(
        select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id == uuid.UUID(sessions[0]["id"]))
    )).scalars().all()
    assert sess_quizzes == []


@pytest.mark.asyncio
async def test_switch_populated_day_with_empty_day_and_revert_and_role_only_summary(
    db, client, operations_headers, instructor_headers, instructor_user,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    program = await _program(db, name="Swap Empty Program")

    # Template Day 1 has ONLY a Lead role item (no General items) -> tests role-only summary count too
    td1 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl Only 1"}, headers=operations_headers)).json()
    await client.put(
        f"/sessions/sessions/{td1['id']}/checklist-items",
        params={"role_id": str(lead_id)},
        json={"items": [{"title": "Lead Tpl Item"}]},
        headers=operations_headers,
    )

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Swap Empty Cohort",
        status="planned",
        inherit_default_checklists=True,
    )
    db.add(cohort)
    await db.flush()
    s1 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 12, 1), title="Day 1")
    s2 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 12, 2), title="Day 2")
    db.add_all([s1, s2])
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=s1.id, user_id=instructor_user.id, role_id=lead_id))
    await db.commit()

    # Role-only inherited day must report effective_instructor_items_count == 1 (not 0)
    pre_sum = (await client.get(f"/sessions/cohorts/{cohort.id}/checklists/summary", headers=operations_headers)).json()
    assert pre_sum["sessions"][0]["effective_instructor_items_count"] == 1
    assert pre_sum["sessions"][0]["is_instructor_inherited"] is True
    assert pre_sum["sessions"][1]["effective_instructor_items_count"] == 0

    # Swap Day 1 (populated via template) and Day 2 (genuinely empty)
    sw = await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/switch-days",
        json={"session_plan_order": [str(s2.id), str(s1.id)], "scope": "instructor", "include_titles": False},
        headers=operations_headers,
    )
    assert sw.status_code == 200

    # Day 1 must stay empty (overridden=True), NOT silently fall back to Template Day 1!
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/delivery/day", headers=instructor_headers)).json()["checklist"]] == []
    post_sum = (await client.get(f"/sessions/cohorts/{cohort.id}/checklists/summary", headers=operations_headers)).json()
    assert post_sum["sessions"][0]["effective_instructor_items_count"] == 0
    assert post_sum["sessions"][0]["is_instructor_inherited"] is False
    assert post_sum["sessions"][1]["effective_instructor_items_count"] == 1

    # Explicit Revert (PUT []) clears the override flag and restores inheritance
    rev = await client.put(
        f"/sessions/sessions/{s1.id}/checklist-items",
        json={"items": []},
        headers=operations_headers,
    )
    assert rev.status_code == 200
    assert [l["title"] for l in (await client.get(f"/sessions/{s1.id}/delivery/day", headers=instructor_headers)).json()["checklist"]] == ["Lead Tpl Item"]


@pytest.mark.asyncio
async def test_switch_days_progress_cleanup_and_approved_day_guards(
    db, client, operations_headers, operations_user, instructor_headers, instructor_user,
):
    lead_id = await _role_id(db, "Lead Facilitator")
    program = await _program(db, name="Progress Guard Program")
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Progress Cohort", status="running")
    db.add(cohort)
    await db.flush()
    s1 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 12, 1), title="D1")
    s2 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 12, 2), title="D2")
    s3 = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 12, 3), title="D3")
    db.add_all([s1, s2, s3])
    await db.flush()
    for s in (s1, s2, s3):
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=s.id, user_id=instructor_user.id, role_id=lead_id))
    await db.commit()

    # Set 1 instructor + 1 internal item on each session
    inst_ids = {}
    int_ids = {}
    for s in (s1, s2, s3):
        r1 = (await client.put(f"/sessions/sessions/{s.id}/checklist-items", json={"items": [{"title": f"Inst {s.title}"}]}, headers=operations_headers)).json()
        r2 = (await client.put(f"/sessions/sessions/{s.id}/checklist-items", params={"target_audience": "internal"}, json={"items": [{"title": f"Int {s.title}"}]}, headers=operations_headers)).json()
        inst_ids[s.id] = r1[0]["id"]
        int_ids[s.id] = r2[0]["id"]

    # Record instructor check-in + ticks and ops internal ticks on s1 and s3
    for s in (s1, s3):
        await client.post(f"/sessions/{s.id}/delivery/check-in", json={"att_status": "present"}, headers=instructor_headers)
        await client.put(f"/sessions/{s.id}/delivery/checklist/{inst_ids[s.id]}", json={"is_done": True}, headers=instructor_headers)
        await client.post(f"/sessions/{s.id}/internal-checklist/{int_ids[s.id]}", json={"is_done": True}, headers=operations_headers)

    reviews_before = (await client.get("/sessions/day-reviews", params={"status_filter": "draft", "cohort_id": str(cohort.id)}, headers=operations_headers)).json()
    assert {r["session_id"]: (r["checklist_done"], r["checklist_total"]) for r in reviews_before} == {
        str(s1.id): (1, 1),
        str(s3.id): (1, 1),
    }

    # Switch s1 and s2 for instructors ONLY (s3 untouched, internal untouched)
    sw = await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/switch-days",
        json={"session_plan_order": [str(s2.id), str(s1.id), str(s3.id)], "scope": "instructor", "include_titles": False},
        headers=operations_headers,
    )
    assert sw.status_code == 200

    # Stale instructor progress on s1 is cleared (0/1, NOT 1/1), while s3 & internal progress on s1 survive!
    reviews_after = (await client.get("/sessions/day-reviews", params={"status_filter": "draft", "cohort_id": str(cohort.id)}, headers=operations_headers)).json()
    review_map = {r["session_id"]: r for r in reviews_after}
    assert review_map[str(s1.id)]["checklist_done"] == 0
    assert review_map[str(s1.id)]["checklist_total"] == 1
    assert review_map[str(s1.id)]["att_status"] == "present"
    assert review_map[str(s3.id)]["checklist_done"] == 1

    post_sum = (await client.get(f"/sessions/cohorts/{cohort.id}/checklists/summary", headers=operations_headers)).json()
    assert post_sum["sessions"][0]["has_instructor_progress"] is False
    assert post_sum["sessions"][0]["has_internal_progress"] is True
    assert post_sum["sessions"][2]["has_instructor_progress"] is True

    # Approve s1's instructor day -> switching or replacing instructors on s1 returns 409, internal/fill_empty still succeed
    s1_day = await db.scalar(select(InstructorSessionDay).where(InstructorSessionDay.session_id == s1.id))
    assert s1_day is not None
    app_resp = await client.post(f"/sessions/day-reviews/{s1_day.id}/approve", headers=operations_headers)
    assert app_resp.status_code == 200

    approved_sum = (await client.get(f"/sessions/cohorts/{cohort.id}/checklists/summary", headers=operations_headers)).json()
    assert approved_sum["sessions"][0]["has_approved_instructor_day"] is True
    assert approved_sum["sessions"][1]["has_approved_instructor_day"] is False

    assert (await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/switch-days",
        json={"session_plan_order": [str(s2.id), str(s1.id), str(s3.id)], "scope": "instructor"},
        headers=operations_headers,
    )).status_code == 409

    assert (await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/switch-days",
        json={"session_plan_order": [str(s2.id), str(s1.id), str(s3.id)], "scope": "internal", "include_titles": False},
        headers=operations_headers,
    )).status_code == 200

    td1 = (await client.post(f"/sessions/programs/{program.id}/template-days", json={"title": "Tpl 1"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", json={"items": [{"title": "Tpl Item"}]}, headers=operations_headers)

    assert (await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/import-default",
        json={"source_type": "program", "mode": "replace", "include_instructor": True},
        headers=operations_headers,
    )).status_code == 409

    assert (await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/import-default",
        json={"source_type": "program", "mode": "fill_empty", "include_instructor": True},
        headers=operations_headers,
    )).status_code == 200

    assert (await client.post(
        f"/sessions/cohorts/{cohort.id}/checklists/import-default",
        json={"source_type": "program", "mode": "replace", "include_instructor": False, "include_internal": True},
        headers=operations_headers,
    )).status_code == 200


@pytest.mark.asyncio
async def test_org_manager_on_shared_platform_program_can_read_template_and_import_default(
    db, client, operations_headers,
):
    org_owner = User(
        id=uuid.uuid4(),
        full_name="Partner Owner",
        email=f"partner-owner-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=["organization"],
        org_role="owner",
        org_roles=["owner"],
        status="active",
    )
    db.add(org_owner)
    await db.flush()
    org = Organization(
        id=uuid.uuid4(),
        name_latin="Partner Org",
        org_type="university",
        country="uae",
        owner_user_id=org_owner.id,
    )
    db.add(org)
    await db.flush()
    org_owner.organization_id = org.id
    await db.commit()
    org_headers = {"Authorization": f"Bearer {create_access_token(org_owner.id, org_owner.role_values)}"}

    # Platform programs (organization_id=None)
    shared_prog = await _program(db, name="Shared Platform Prog")
    other_prog = await _program(db, name="Unrelated Platform Prog")

    td1 = (await client.post(f"/sessions/programs/{shared_prog.id}/template-days", json={"title": "Shared D1"}, headers=operations_headers)).json()
    await client.put(f"/sessions/sessions/{td1['id']}/checklist-items", json={"items": [{"title": "Shared Check"}]}, headers=operations_headers)
    await client.post(f"/sessions/programs/{other_prog.id}/template-days", json={"title": "Other D1"}, headers=operations_headers)

    org_cohort = Cohort(
        id=uuid.uuid4(),
        program_id=shared_prog.id,
        organization_id=org.id,
        name="Org Shared Cohort",
        starts_on=date(2026, 12, 1),
        status="planned",
    )
    db.add(org_cohort)
    await db.commit()

    # Org manager can read their cohort's shared program template & import defaults onto their cohort
    tpl_ok = await client.get(f"/sessions/programs/{shared_prog.id}/template", headers=org_headers)
    assert tpl_ok.status_code == 200, tpl_ok.text
    assert len(tpl_ok.json()["sessions"]) == 1

    imp_ok = await client.post(
        f"/sessions/cohorts/{org_cohort.id}/checklists/import-default",
        json={"source_type": "program", "create_missing_sessions": True},
        headers=org_headers,
    )
    assert imp_ok.status_code == 200, imp_ok.text
    assert imp_ok.json()["sessions_created"] == 1

    # Unrelated platform program still blocked (403)
    assert (await client.get(f"/sessions/programs/{other_prog.id}/template", headers=org_headers)).status_code == 403
    assert (await client.post(
        f"/sessions/cohorts/{org_cohort.id}/checklists/import-default",
        json={"source_type": "program", "source_id": str(other_prog.id)},
        headers=org_headers,
    )).status_code == 403
