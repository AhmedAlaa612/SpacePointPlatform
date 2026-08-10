"""P3-1 (LMS Phase 2 Stage 3, 2026-08-10) — the learning panel on
GET /spine/contacts/{id}: "what is this student's situation" in one place.
Redis-free.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.security import create_access_token
from app.models.lms.course import Course
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session as DeliverySession
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.lms import enroll
from app.services.lms.points import award_points


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_non_student_contact_has_no_learning_panel(db, client):
    ops = await _ops(db)
    contact = Contact(id=uuid.uuid4(), full_name="Just A Lead", contact_roles=["lead"])
    db.add(contact)
    await db.commit()

    resp = await client.get(f"/spine/contacts/{contact.id}", headers=_headers(ops))
    assert resp.status_code == 200
    assert resp.json()["learning"] is None


@pytest.mark.asyncio
async def test_student_contact_with_no_account_reports_has_account_false(db, client):
    ops = await _ops(db)
    contact = Contact(id=uuid.uuid4(), full_name="No Account Yet", contact_roles=["student"])
    db.add(contact)
    await db.commit()

    resp = await client.get(f"/spine/contacts/{contact.id}", headers=_headers(ops))
    assert resp.status_code == 200
    learning = resp.json()["learning"]
    assert learning is not None
    assert learning["has_account"] is False
    assert learning["enrollments"] == []


@pytest.mark.asyncio
async def test_learning_panel_shows_enrollments_points_and_registrations(db, client):
    ops = await _ops(db)
    contact = Contact(id=uuid.uuid4(), full_name="Full Picture Student", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="Full Picture Student", email=f"fp-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.flush()

    course = Course(id=uuid.uuid4(), title="Orbital Mechanics", created_by=ops.id, is_published=True)
    db.add(course)
    await db.flush()
    await enroll(db, user_id=student.id, course_id=course.id, source="ops", granted_by=ops.id)
    await award_points(db, user_id=student.id, source="quiz", points=50, idempotency_key="q1")

    program = Program(
        id=uuid.uuid4(), code=f"LP-{uuid.uuid4().hex[:8]}", name="Learning Panel Program",
        program_type="workshop", pricing_model="paid", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="LP Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    registration = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id, status="attended",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="paid",
        price_charged=Decimal("250.00"),
    )
    db.add(registration)
    await db.flush()
    delivery_session = DeliverySession(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 1))
    db.add(delivery_session)
    await db.flush()
    db.add(AttendanceRecord(
        id=uuid.uuid4(), registration_id=registration.id, session_id=delivery_session.id,
        att_status="present", recorded_by_user_id=ops.id,
    ))
    await db.commit()

    resp = await client.get(f"/spine/contacts/{contact.id}", headers=_headers(ops))
    assert resp.status_code == 200
    learning = resp.json()["learning"]

    assert learning["has_account"] is True
    assert learning["user_id"] == str(student.id)
    assert learning["points_total"] == 50

    assert len(learning["enrollments"]) == 1
    enrollment = learning["enrollments"][0]
    assert enrollment["course_title"] == "Orbital Mechanics"
    assert enrollment["source"] == "ops"
    assert enrollment["granted_by_name"] == "Ops"

    assert len(learning["registrations"]) == 1
    reg = learning["registrations"][0]
    assert reg["cohort_name"] == "LP Cohort"
    assert reg["program_name"] == "Learning Panel Program"
    assert reg["price_charged"] == "250.00"
    assert reg["attended_sessions"] == 1
    assert reg["total_sessions"] == 1
