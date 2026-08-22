"""LMS Program checklist authoring (2026-08-21 redesign) —
`/lms/admin/programs/*` and `/lms/admin/cohorts/{cohort_id}/program-override/*`.
Redis-free (uses the `client` fixture).
"""

import uuid

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.missions.mission import Mission, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User


async def _user(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Checklist Admin", email=f"cka-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _program(db) -> Program:
    program = Program(
        id=uuid.uuid4(), code=f"CKA-{uuid.uuid4().hex[:8]}", name="Checklist Admin Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    return program


async def _cohort(db, program: Program) -> Cohort:
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Checklist Admin Cohort", status="running")
    db.add(cohort)
    await db.flush()
    return cohort


async def _course(db, *, author) -> Course:
    course = Course(id=uuid.uuid4(), title=f"Course {uuid.uuid4().hex[:6]}", created_by=author.id, is_published=True)
    db.add(course)
    await db.flush()
    return course


async def _mission(db, *, author) -> tuple[Mission, MissionVariant]:
    mission = Mission(
        id=uuid.uuid4(), title="Admin Test Mission", slug=f"admin-test-{uuid.uuid4().hex[:8]}",
        kind="submission", authored_by=author.id, status="published", team_policy="solo",
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Cadet", position=1, points=10)
    db.add(variant)
    await db.flush()
    return mission, variant


# ── program CRUD ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_get_update_delete_lms_program(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()

    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops),
        json={"program_id": str(program.id), "name": "TDRA Summer Sprint", "description": "A sprint."},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "TDRA Summer Sprint" and body["certificate_required"] is True and body["items"] == []
    lms_program_id = body["id"]

    dup = await client.post(
        "/lms/admin/programs", headers=_headers(ops),
        json={"program_id": str(program.id), "name": "Second Checklist For Same Program"},
    )
    assert dup.status_code == http_status.HTTP_409_CONFLICT

    got = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert got.status_code == 200 and got.json()["name"] == "TDRA Summer Sprint"

    updated = await client.patch(
        f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops),
        json={"certificate_required": False},
    )
    assert updated.status_code == 200
    assert updated.json()["certificate_required"] is False
    assert updated.json()["name"] == "TDRA Summer Sprint"  # untouched field survives a partial patch

    deleted = await client.delete(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    gone = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_student_cannot_create_a_program(db, client):
    student = await _user(db, roles=["student"])
    await db.commit()
    resp = await client.post("/lms/admin/programs", headers=_headers(student), json={"name": "Nope"})
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN


# ── item CRUD + validation ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_items_of_every_type_in_order(db, client):
    ops = await _user(db)
    program = await _program(db)
    course = await _course(db, author=ops)
    mission, variant = await _mission(db, author=ops)
    await db.commit()

    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Full Checklist"},
    )
    lms_program_id = created.json()["id"]

    course_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )
    assert course_item.status_code == 201 and course_item.json()["position"] == 1

    mission_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={
            "item_type": "mission_run", "title": mission.title,
            "mission_id": str(mission.id), "variant_id": str(variant.id),
        },
    )
    assert mission_item.status_code == 201 and mission_item.json()["position"] == 2

    manual_item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Attend the ceremony", "requires_confirmation": True},
    )
    assert manual_item.status_code == 201 and manual_item.json()["position"] == 3

    listed = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["item_type"] for i in listed.json()["items"]] == ["course", "mission_run", "manual"]


@pytest.mark.asyncio
async def test_add_item_rejects_a_missing_required_field(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": "No course_id"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_add_item_rejects_an_unknown_course(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]

    resp = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": "Ghost course", "course_id": str(uuid.uuid4())},
    )
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_add_item_rejects_a_duplicate_course_and_a_taken_position(db, client):
    ops = await _user(db)
    program = await _program(db)
    course = await _course(db, author=ops)
    other_course = await _course(db, author=ops)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )

    dup_course = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": course.title, "course_id": str(course.id)},
    )
    assert dup_course.status_code == http_status.HTTP_409_CONFLICT

    taken_position = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": other_course.title, "course_id": str(other_course.id), "position": 1},
    )
    assert taken_position.status_code == http_status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_delete_item_removes_it(db, client):
    ops = await _user(db)
    program = await _program(db)
    await db.commit()
    created = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Checklist"},
    )
    lms_program_id = created.json()["id"]
    item = await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Check-off"},
    )
    item_id = item.json()["id"]

    deleted = await client.delete(f"/lms/admin/programs/{lms_program_id}/items/{item_id}", headers=_headers(ops))
    assert deleted.status_code == 204
    listed = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert listed.json()["items"] == []


# ── cohort override ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cohort_override_requires_a_program_checklist_to_override(db, client):
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "manual", "title": "Nope"},
    )
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_cohort_override_created_on_first_item_and_lists_separately(db, client):
    ops = await _user(db)
    program = await _program(db)
    cohort = await _cohort(db, program)
    program_course = await _course(db, author=ops)
    override_course = await _course(db, author=ops)
    await db.commit()

    program_checklist = await client.post(
        "/lms/admin/programs", headers=_headers(ops), json={"program_id": str(program.id), "name": "Base Checklist"},
    )
    lms_program_id = program_checklist.json()["id"]
    await client.post(
        f"/lms/admin/programs/{lms_program_id}/items", headers=_headers(ops),
        json={"item_type": "course", "title": program_course.title, "course_id": str(program_course.id)},
    )

    missing = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert missing.status_code == 404

    added = await client.post(
        f"/lms/admin/cohorts/{cohort.id}/program-override/items", headers=_headers(ops),
        json={"item_type": "course", "title": override_course.title, "course_id": str(override_course.id)},
    )
    assert added.status_code == 201

    override = await client.get(f"/lms/admin/cohorts/{cohort.id}/program-override", headers=_headers(ops))
    assert override.status_code == 200
    assert [i["course_id"] for i in override.json()["items"]] == [str(override_course.id)]

    # The program-level checklist itself is untouched by the override.
    program_after = await client.get(f"/lms/admin/programs/{lms_program_id}", headers=_headers(ops))
    assert [i["course_id"] for i in program_after.json()["items"]] == [str(program_course.id)]
