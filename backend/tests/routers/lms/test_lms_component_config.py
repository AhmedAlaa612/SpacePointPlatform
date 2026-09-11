"""Tests for LMS Program and Cohort CubeSat Component Configuration endpoints and enforcement."""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.program import LmsProgram
from app.models.missions.design import Design, DesignComponentLibrary
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_assignment import CohortInstructorAssignment
from app.models.sessions.program import Program
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Component Config Admin",
        email=f"cca-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=list(roles) if roles else ["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _setup_program_and_cohort(db):
    author = await _user(db, roles=["operations"])
    program = Program(
        id=uuid.uuid4(),
        code=f"PRG-{uuid.uuid4().hex[:8]}",
        name="Test Component Program",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()

    lms_prog = LmsProgram(
        id=uuid.uuid4(),
        program_id=program.id,
        name="LMS Component Template",
    )
    db.add(lms_prog)
    await db.flush()

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Test Component Cohort",
        status="running",
    )
    db.add(cohort)
    await db.flush()

    return author, program, lms_prog, cohort


@pytest.mark.asyncio
async def test_program_component_config_crud(client, db):
    author, program, lms_prog, cohort = await _setup_program_and_cohort(db)
    headers = _headers(author)

    # 1. Initial GET — should return default configuration
    res = await client.get(f"/lms/admin/programs/{lms_prog.id}/components", headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["owner_type"] == "program"
    assert data["owner_id"] == str(lms_prog.id)
    assert data["has_override"] is False
    assert data["disabled_subsystems"] == []
    assert data["disabled_tags"] == []
    assert data["disabled_component_ids"] == []

    # 2. PUT — configure disabled subsystem and tag
    payload = {
        "disabled_subsystems": ["Thermal"],
        "disabled_tags": ["SatKit"],
        "disabled_component_ids": [],
    }
    res = await client.put(f"/lms/admin/programs/{lms_prog.id}/components", json=payload, headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["has_override"] is True
    assert data["disabled_subsystems"] == ["Thermal"]
    assert data["disabled_tags"] == ["SatKit"]

    # 3. GET after PUT
    res = await client.get(f"/lms/admin/programs/{lms_prog.id}/components", headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    assert res.json()["disabled_subsystems"] == ["Thermal"]

    # 4. DELETE — reset to default
    res = await client.delete(f"/lms/admin/programs/{lms_prog.id}/components", headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["has_override"] is False
    assert data["disabled_subsystems"] == []


@pytest.mark.asyncio
async def test_cohort_component_config_inherits_program_default(client, db):
    author, program, lms_prog, cohort = await _setup_program_and_cohort(db)
    headers = _headers(author)

    # Configure program default: disable Thermal
    await client.put(
        f"/lms/admin/programs/{lms_prog.id}/components",
        json={"disabled_subsystems": ["Thermal"], "disabled_tags": [], "disabled_component_ids": []},
        headers=headers,
    )

    # Check cohort components — should inherit from program
    res = await client.get(f"/lms/admin/cohorts/{cohort.id}/components", headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["owner_type"] == "cohort"
    assert data["owner_id"] == str(cohort.id)
    assert data["is_inherited"] is True
    assert data["has_override"] is False
    assert data["disabled_subsystems"] == ["Thermal"]


@pytest.mark.asyncio
async def test_cohort_component_config_override_and_reset(client, db):
    author, program, lms_prog, cohort = await _setup_program_and_cohort(db)
    headers = _headers(author)

    # 1. Set program default with Thermal disabled
    await client.put(
        f"/lms/admin/programs/{lms_prog.id}/components",
        json={"disabled_subsystems": ["Thermal"], "disabled_tags": [], "disabled_component_ids": []},
        headers=headers,
    )

    # 2. Save cohort override with ADCS disabled instead
    res = await client.put(
        f"/lms/admin/cohorts/{cohort.id}/components",
        json={"disabled_subsystems": ["ADCS"], "disabled_tags": [], "disabled_component_ids": []},
        headers=headers,
    )
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["is_inherited"] is False
    assert data["has_override"] is True
    assert data["disabled_subsystems"] == ["ADCS"]

    # 3. Reset cohort override -> should fall back to program default (Thermal disabled)
    res = await client.delete(f"/lms/admin/cohorts/{cohort.id}/components", headers=headers)
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["is_inherited"] is True
    assert data["has_override"] is False
    assert data["disabled_subsystems"] == ["Thermal"]


@pytest.mark.asyncio
async def test_instructor_cohort_component_config(client, db):
    author, program, lms_prog, cohort = await _setup_program_and_cohort(db)
    instructor = await _user(db, roles=["instructor"])

    from sqlalchemy import select
    from app.models.sessions.delivery_role import DeliveryRole
    from app.models.sessions.session import Session, SessionInstructor

    role = (await db.execute(select(DeliveryRole))).scalars().first()
    if not role:
        role = DeliveryRole(id=uuid.uuid4(), title="Lead Instructor", active=True)
        db.add(role)
        await db.flush()

    from datetime import date
    sess = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today())
    db.add(sess)
    await db.flush()

    db.add(SessionInstructor(id=uuid.uuid4(), session_id=sess.id, user_id=instructor.id, role_id=role.id))
    await db.commit()

    inst_headers = _headers(instructor)

    # Instructor gets cohort components
    res = await client.get(f"/lms/instructor/cohorts/{cohort.id}/components", headers=inst_headers)
    assert res.status_code == http_status.HTTP_200_OK
    assert res.json()["is_inherited"] is True

    # Instructor updates cohort components
    res = await client.put(
        f"/lms/instructor/cohorts/{cohort.id}/components",
        json={"disabled_subsystems": ["EPS"], "disabled_tags": [], "disabled_component_ids": []},
        headers=inst_headers,
    )
    assert res.status_code == http_status.HTTP_200_OK
    assert res.json()["disabled_subsystems"] == ["EPS"]
    assert res.json()["has_override"] is True

    # Instructor resets cohort components
    res = await client.delete(f"/lms/instructor/cohorts/{cohort.id}/components", headers=inst_headers)
    assert res.status_code == http_status.HTTP_200_OK
    assert res.json()["is_inherited"] is True


@pytest.mark.asyncio
async def test_student_library_filtering_and_add_component_enforcement(client, db):
    author, program, lms_prog, cohort = await _setup_program_and_cohort(db)
    student = await _user(db, roles=["student"])
    headers_author = _headers(author)
    headers_student = _headers(student)

    # Seed 2 test components in library
    comp1 = DesignComponentLibrary(
        id=uuid.uuid4(),
        component_name="Test Antenna COMMS",
        subsystem="COMMS",
        tag="SatKit",
        is_active=True,
    )
    comp2 = DesignComponentLibrary(
        id=uuid.uuid4(),
        component_name="Test Heater Thermal",
        subsystem="Thermal",
        tag="SatKit",
        is_active=True,
    )
    db.add_all([comp1, comp2])

    # Seed a design mission, variant, attempt, and design
    mission = Mission(
        id=uuid.uuid4(),
        title="CubeSat Test Mission",
        slug=f"cubesat-{uuid.uuid4().hex[:8]}",
        kind="design",
        authored_by=author.id,
        status="published",
        team_policy="solo",
    )
    db.add(mission)
    await db.flush()

    variant = MissionVariant(
        id=uuid.uuid4(),
        mission_id=mission.id,
        position=1,
        label="Easy",
        points=100,
        config={},
    )
    db.add(variant)
    await db.flush()

    attempt = MissionAttempt(
        id=uuid.uuid4(),
        mission_id=mission.id,
        variant_id=variant.id,
        attempt_no=1,
        user_id=student.id,
        cohort_id=cohort.id,
        status="in_progress",
    )
    db.add(attempt)
    await db.flush()

    design = Design(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        cohort_id=cohort.id,
        design_name="Student Satellite",
    )
    db.add(design)
    await db.commit()

    # Disable Thermal subsystem on cohort
    await client.put(
        f"/lms/admin/cohorts/{cohort.id}/components",
        json={"disabled_subsystems": ["Thermal"], "disabled_tags": [], "disabled_component_ids": []},
        headers=headers_author,
    )

    # Student requests library with attempt_id
    res = await client.get(f"/missions/design/library?attempt_id={attempt.id}", headers=headers_student)
    assert res.status_code == http_status.HTTP_200_OK
    items = res.json()
    subsystems_in_library = {item["subsystem"] for item in items}
    assert "Thermal" not in subsystems_in_library
    component_names = {item["component_name"] for item in items}
    assert "Test Antenna COMMS" in component_names
    assert "Test Heater Thermal" not in component_names

    # Student attempts to add the disabled Thermal component -> must receive 400 Bad Request
    res = await client.post(
        f"/missions/design/attempts/{attempt.id}/components",
        json={"library_component_id": str(comp2.id), "quantity": 1},
        headers=headers_student,
    )
    assert res.status_code == http_status.HTTP_400_BAD_REQUEST
    assert "not available" in res.json()["detail"].lower()

    # Student adds the allowed COMMS component -> must succeed with 201 Created
    res = await client.post(
        f"/missions/design/attempts/{attempt.id}/components",
        json={"library_component_id": str(comp1.id), "quantity": 1},
        headers=headers_student,
    )
    assert res.status_code == http_status.HTTP_201_CREATED
