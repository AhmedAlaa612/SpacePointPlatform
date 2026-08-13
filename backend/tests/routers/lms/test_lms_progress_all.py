"""2026-08-12 — GET /lms/admin/progress/courses and
GET /lms/admin/progress/missions/{mission_id}: the all-students single-item
progress views that replaced the cohort-first funnel for day-to-day use.
Redis-free.
"""

import uuid
from datetime import date

import pytest
from fastapi import status as http_status

from app.core.security import create_access_token
from app.models.lms import Course, CourseModule, ModuleItem
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll, item_progress


async def _staff(db, *, roles=None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Progress Staff", email=f"ps-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=list(roles) if roles else ["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _student(db, *, cohort_id: uuid.UUID | None, name: str) -> User:
    contact = Contact(id=uuid.uuid4(), full_name=name, contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name=name, email=f"{name.lower().replace(' ', '')}-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()
    if cohort_id is not None:
        db.add(Registration(
            id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort_id, status="registered",
            ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
        ))
        await db.flush()
    return student


async def _cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"PG-{uuid.uuid4().hex[:8]}", name="Progress Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Progress Cohort", status="running",
        starts_on=date(2026, 9, 1), ends_on=date(2026, 9, 5),
    )
    db.add(cohort)
    await db.flush()
    return cohort


@pytest.mark.asyncio
async def test_course_progress_all_defaults_to_every_enrolled_student(db, client):
    ops = await _staff(db)
    course = Course(id=uuid.uuid4(), title="All-Students Course", created_by=ops.id, is_published=True)
    db.add(course)
    await db.flush()
    module = CourseModule(id=uuid.uuid4(), course_id=course.id, title="M1", position=1)
    db.add(module)
    await db.flush()
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text", content={"body": "x"})
    db.add(item)
    await db.flush()

    cohort_a = await _cohort(db)
    cohort_b = await _cohort(db)
    finisher = await _student(db, cohort_id=cohort_a.id, name="Finisher Fran")
    other_cohort = await _student(db, cohort_id=cohort_b.id, name="Other Cohort Otto")

    await enroll(db, user_id=finisher.id, course_id=course.id, source="self")
    await item_progress(db, user_id=finisher.id, item_id=item.id, action="text-viewed")
    await enroll(db, user_id=other_cohort.id, course_id=course.id, source="self")
    await db.commit()

    # No cohort filter — both enrolled students across different cohorts show up.
    resp = await client.get(f"/lms/admin/progress/courses?course_id={course.id}", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["course_id"] == str(course.id)
    names = {row["full_name"]: row["pct"] for row in body["rows"]}
    assert names == {"Finisher Fran": 100, "Other Cohort Otto": 0}

    # Cohort filter narrows to just that cohort's roster.
    resp = await client.get(
        f"/lms/admin/progress/courses?course_id={course.id}&cohort_id={cohort_a.id}", headers=_headers(ops),
    )
    assert resp.status_code == 200, resp.text
    filtered_names = {row["full_name"] for row in resp.json()["rows"]}
    assert filtered_names == {"Finisher Fran"}


@pytest.mark.asyncio
async def test_course_progress_all_404s_for_unknown_course(db, client):
    ops = await _staff(db)
    await db.commit()
    resp = await client.get(f"/lms/admin/progress/courses?course_id={uuid.uuid4()}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_mission_progress_all_lists_every_attempting_student(db, client):
    ops = await _staff(db)
    mission = Mission(
        id=uuid.uuid4(), title="All-Students Mission", slug=f"asm-{uuid.uuid4().hex[:8]}",
        kind="submission", status="published", authored_by=ops.id,
    )
    db.add(mission)
    await db.flush()
    variant = MissionVariant(id=uuid.uuid4(), mission_id=mission.id, label="Standard", position=1, points=25)
    db.add(variant)
    await db.flush()

    student = await _student(db, cohort_id=None, name="Attempting Amy")
    db.add(MissionAttempt(
        id=uuid.uuid4(), mission_id=mission.id, variant_id=variant.id, user_id=student.id,
        attempt_no=1, status="passed", score=88, payload={},
    ))
    await db.commit()

    resp = await client.get(f"/lms/admin/progress/missions/{mission.id}", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["mission_id"] == str(mission.id)
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["full_name"] == "Attempting Amy"
    assert row["status"] == "passed"
    assert row["score"] == 88.0


@pytest.mark.asyncio
async def test_mission_progress_all_404s_for_unknown_mission(db, client):
    ops = await _staff(db)
    await db.commit()
    resp = await client.get(f"/lms/admin/progress/missions/{uuid.uuid4()}", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_progress_all_requires_content_role(db, client):
    student = await _staff(db, roles=["student"])
    await db.commit()
    resp = await client.get(f"/lms/admin/progress/courses?course_id={uuid.uuid4()}", headers=_headers(student))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN
