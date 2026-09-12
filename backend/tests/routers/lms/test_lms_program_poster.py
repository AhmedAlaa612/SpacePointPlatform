"""LMS Program poster tracking tests (2026-09):
- Poster template inheritance (Program -> Cohort override)
- Poster step visibility and template in student checklist
- Student submission via /submit endpoint and sync to Design
- Instructor / ops item detail with poster status and submitted_url
"""

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram, LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress
from app.models.missions.design import Design
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms.program import assign_lms_program

_VARIANT_CONFIG = {
    "max_storage_kb": 1_048_576.0, "required_storage_margin_kb": 0.0,
    "power_per_solar_cell_w": 1.1, "maximum_budget_aed": 2000.0,
    "assumed_distance_km": 500.0, "transmit_power_dbm": 30.0,
    "good_link_margin_threshold_db": 3.0, "weak_link_margin_threshold_db": 0.0,
    "max_depth_of_discharge_pct": 30.0, "required_downlink_margin_fraction": 0.10,
}


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _user(db, *, roles: list[str]) -> User:
    u = User(
        id=uuid.uuid4(), email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        full_name=f"User {uuid.uuid4().hex[:4]}", roles=roles, password_hash="x", status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _student(db) -> User:
    contact = Contact(
        id=uuid.uuid4(), full_name="Poster Student", contact_roles=["student"],
        email=f"poster-std-{uuid.uuid4().hex[:8]}@example.com",
    )
    db.add(contact)
    await db.flush()
    u = User(
        id=uuid.uuid4(), contact_id=contact.id, email=contact.email,
        full_name=contact.full_name, roles=["student"], password_hash="x", status="active",
    )
    db.add(u)
    await db.flush()
    return u


async def _design_mission(db, *, author: User) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Madar CubeSat", slug=f"madar-poster-{uuid.uuid4().hex[:8]}",
        kind="design", authored_by=author.id, status="published", summary="Design one.",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(
        id=uuid.uuid4(), mission_id=mission.id, label="Engineer", position=1, points=200, config=_VARIANT_CONFIG,
    )
    db.add(variant)
    await db.flush()
    return mission, variant


@pytest.mark.asyncio
async def test_poster_template_inheritance_and_submission(db, client):
    ops = await _user(db, roles=["operations"])
    student = await _student(db)

    mission, variant = await _design_mission(db, author=ops)

    # 1. Create sessions Program with poster_template_url
    program = Program(
        id=uuid.uuid4(), code=f"PRG-{uuid.uuid4().hex[:6]}", name="Space Mission Program",
        program_type="workshop", pricing_model="free", poster_template_url="https://canva.com/program-poster-template",
    )
    db.add(program)
    await db.flush()

    # 2. Create LMS Program linked to Program
    lms_program = LmsProgram(
        id=uuid.uuid4(), program_id=program.id, name="Space Mission LMS",
        certificate_required=False,
    )
    db.add(lms_program)
    await db.flush()

    # 3. Add poster mission step item
    poster_item = LmsProgramItem(
        id=uuid.uuid4(), owner_type="program", owner_id=lms_program.id, position=1,
        item_type="mission_run", title="Design Mission Poster", mission_id=mission.id,
        mission_step_key="poster",
    )
    db.add(poster_item)
    await db.flush()

    # 4. Create Cohort without override (inherits from program)
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Cohort Alpha",
        status="running", starts_on=date.today(), ends_on=date.today() + timedelta(days=7),
    )
    db.add(cohort)
    await db.flush()

    # Assign student
    assignment = await assign_lms_program(
        db, user_id=student.id, cohort_id=cohort.id,
    )
    await db.commit()

    # Verify student checklist inherits program poster_template_url
    resp = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    data = resp.json()
    assert data["poster_template_url"] == "https://canva.com/program-poster-template"
    items = data["items"]
    assert len(items) == 1
    assert items[0]["mission_step_key"] == "poster"
    assert items[0]["poster_template_url"] == "https://canva.com/program-poster-template"
    assert items[0]["status"] == "pending"
    assert items[0]["submitted_url"] is None

    # Verify cohort override inherits correctly in instructor/ops endpoint
    resp_override = await client.get(f"/lms/instructor/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert resp_override.status_code == 200, resp_override.text
    override_data = resp_override.json()
    assert override_data["inherited_poster_template_url"] == "https://canva.com/program-poster-template"
    assert override_data["poster_template_url"] is None

    # Now override poster_template_url on cohort via ops endpoint
    resp_patch = await client.patch(
        f"/lms/admin/cohorts/{cohort.id}/poster-template",
        headers=_headers(ops),
        json={"poster_template_url": "https://canva.com/cohort-override-template"},
    )
    assert resp_patch.status_code == 200, resp_patch.text
    assert resp_patch.json()["poster_template_url"] == "https://canva.com/cohort-override-template"

    # Verify student checklist now reflects the cohort override
    resp = await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_200_OK
    assert resp.json()["poster_template_url"] == "https://canva.com/cohort-override-template"
    assert resp.json()["items"][0]["poster_template_url"] == "https://canva.com/cohort-override-template"

    # 5. Student submits their poster URL via the checklist submit endpoint
    sub_resp = await client.post(
        f"/lms/programs/{assignment.id}/items/{poster_item.id}/submit",
        headers=_headers(student),
        json={"url": "https://canva.com/design/student-finished-poster"},
    )
    assert sub_resp.status_code == http_status.HTTP_200_OK, sub_resp.text
    item_data = sub_resp.json()
    assert item_data["status"] == "done"
    assert item_data["submitted_url"] == "https://canva.com/design/student-finished-poster"
    assert item_data["poster_template_url"] == "https://canva.com/cohort-override-template"

    # Verify Design.poster_url is synced
    progress_row = await db.scalar(
        select(LmsProgramItemProgress).where(
            LmsProgramItemProgress.assignment_id == assignment.id,
            LmsProgramItemProgress.item_id == poster_item.id,
        )
    )
    assert progress_row is not None
    assert progress_row.mission_attempt_id is not None
    design = await db.scalar(select(Design).where(Design.attempt_id == progress_row.mission_attempt_id))
    assert design is not None
    assert design.poster_url == "https://canva.com/design/student-finished-poster"

    # 6. Instructor / ops views student checklist progress detail
    detail_resp = await client.get(
        f"/lms/instructor/cohorts/{cohort.id}/program-progress/{assignment.id}/items",
        headers=_headers(ops),
    )
    assert detail_resp.status_code == http_status.HTTP_200_OK, detail_resp.text
    detail_items = detail_resp.json()
    assert len(detail_items) == 1
    assert detail_items[0]["item_id"] == str(poster_item.id)
    assert detail_items[0]["status"] == "done"
    assert detail_items[0]["submitted_url"] == "https://canva.com/design/student-finished-poster"
    assert detail_items[0]["mission_step_key"] == "poster"
