import io
import json
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.enums import UserRole
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.internship import InternProfile, RoleRequest
from app.models.user import User

pytestmark = pytest.mark.asyncio


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _make_user(
    db,
    *,
    roles: list[UserRole],
    birthdate: date | None = None,
    org: str | None = None,
    student_id: str | None = None,
    email: str | None = None,
) -> User:
    org_id = None
    if org:
        from app.services.spine.identity import resolve_or_create_organization
        org_row = await resolve_or_create_organization(db, org, org_type="university")
        org_id = org_row.id

    user = User(
        full_name="Test Student",
        email=email or f"{uuid.uuid4()}@example.com",
        password_hash=get_password_hash("pw12345"),
        roles=roles,
        status="active",
        birthdate=birthdate,
        organization_id=org_id,
        student_id=student_id,
    )
    db.add(user)
    await db.flush()
    return user


async def test_student_intake_eligibility_checks(db, client):
    # Case 1: Student without birthdate
    s1 = await _make_user(db, roles=[UserRole.student])
    resp1 = await client.get("/internship/intake-eligibility", headers=_auth(s1))
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["eligible"] is False
    assert data1["has_birthdate"] is False

    # Case 2: Under 18 student
    today = date.today()
    underage_dob = date(today.year - 17, today.month, min(today.day, 28))
    s2 = await _make_user(db, roles=[UserRole.student], birthdate=underage_dob)
    resp2 = await client.get("/internship/intake-eligibility", headers=_auth(s2))
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["eligible"] is False
    assert data2["has_birthdate"] is True

    # Case 3: 20 year old student (eligible)
    adult_dob = date(today.year - 20, today.month, min(today.day, 28))
    s3 = await _make_user(
        db,
        roles=[UserRole.student],
        birthdate=adult_dob,
        org="Khartoum University",
        student_id="KU-9988",
    )
    resp3 = await client.get("/internship/intake-eligibility", headers=_auth(s3))
    assert resp3.status_code == 200
    data3 = resp3.json()
    assert data3["eligible"] is True
    assert data3["has_birthdate"] is True
    assert data3["university"] == "Khartoum University"
    assert data3["student_id"] == "KU-9988"


async def test_student_apply_and_profile_sync(db, client):
    today = date.today()
    adult_dob = date(today.year - 21, 1, 1)
    student = await _make_user(db, roles=[UserRole.student], birthdate=adult_dob)

    payload = {
        "university": "Sudan University of Science and Technology",
        "university_id_number": "SUST-2024-554",
        "major": "Mechanical Engineering",
        "requested_duration_weeks": 8,
    }

    cv_bytes = b"%PDF-1.4 mock cv content"
    files = {"cv": ("cv.pdf", cv_bytes, "application/pdf")}
    data = {"payload": json.dumps(payload)}

    resp = await client.post(
        "/internship/apply-as-student",
        data=data,
        files=files,
        headers=_auth(student),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["target_role"] == "intern"
    assert body["status"] == "pending"
    assert body["details"]["university"] == "Sudan University of Science and Technology"
    assert body["details"]["university_id_number"] == "SUST-2024-554"
    assert body["details"]["major"] == "Mechanical Engineering"

    # Verify user profile was synced with university and student ID
    await db.refresh(student)
    assert student.organization_id is not None
    from app.models.spine.organization import Organization
    org = await db.get(Organization, student.organization_id)
    assert org is not None
    assert org.name_latin == "Sudan University of Science and Technology"
    assert student.student_id == "SUST-2024-554"

    # Duplicate application is rejected
    dup_resp = await client.post(
        "/internship/apply-as-student",
        data=data,
        files=files,
        headers=_auth(student),
    )
    assert dup_resp.status_code == 400


async def test_route_student_role_request_to_onboarding(db, client):
    admin = await _make_user(db, roles=[UserRole.admin])
    today = date.today()
    adult_dob = date(today.year - 22, 1, 1)
    student = await _make_user(
        db,
        roles=[UserRole.student],
        birthdate=adult_dob,
        org="Nile University",
        student_id="NU-123",
    )

    payload = {
        "university": "Nile University",
        "university_id_number": "NU-123",
        "major": "Computer Science",
    }
    app_resp = await client.post(
        "/internship/apply-as-student",
        data={"payload": json.dumps(payload)},
        headers=_auth(student),
    )
    assert app_resp.status_code == 201
    req_id = app_resp.json()["id"]

    # Admin routes to instructor onboarding
    onboard_body = {
        "salutation": "Dear Colleague,",
        "activity_description": "Robotics & Space Systems Research Intern",
        "supervisor_title": "Dr.",
        "supervisor_name": "Supervisor Sarah",
        "supervisor_email": "sarah@example.com",
        "supervisor_phone": "+249912345678",
    }
    onboard_resp = await client.post(
        f"/admin/role-requests/{req_id}/onboard-to-instructor",
        json=onboard_body,
        headers=_auth(admin),
    )
    assert onboard_resp.status_code == 200, onboard_resp.text
    assert onboard_resp.json()["status"] == "approved"
    assert onboard_resp.json()["resolution"]["routed_to_onboarding"] is True

    # Verify student roles: must have both applicant and student: ['applicant', 'student']
    await db.refresh(student)
    roles = {r.value if hasattr(r, "value") else str(r) for r in student.roles}
    assert "applicant" in roles
    assert "student" in roles

    # Verify ApplicantProfile was created with also_grant_role='intern' and pending_intern_details
    profile = await db.get(ApplicantProfile, student.id)
    assert profile is not None
    assert profile.also_grant_role == "intern"
    assert profile.pending_intern_details["university_id_number"] == "NU-123"


async def test_direct_approve_converts_student_to_clean_intern(db, client):
    admin = await _make_user(db, roles=[UserRole.admin])
    today = date.today()
    adult_dob = date(today.year - 23, 1, 1)
    student = await _make_user(
        db,
        roles=[UserRole.student],
        birthdate=adult_dob,
        org="Bahri University",
        student_id="BU-777",
    )

    payload = {
        "university": "Bahri University",
        "university_id_number": "BU-777",
        "major": "Physics",
    }
    app_resp = await client.post(
        "/internship/apply-as-student",
        data={"payload": json.dumps(payload)},
        headers=_auth(student),
    )
    assert app_resp.status_code == 201
    req_id = app_resp.json()["id"]

    # Admin approves directly
    approve_body = {
        "salutation": "Dear Colleague,",
        "activity_description": "Astrophysics Lab Intern",
        "supervisor_title": "Prof.",
        "supervisor_name": "Dr. Kamal",
        "supervisor_email": "kamal@example.com",
        "supervisor_phone": "+249911111111",
    }
    approve_resp = await client.post(
        f"/admin/role-requests/{req_id}/approve",
        json=approve_body,
        headers=_auth(admin),
    )
    assert approve_resp.status_code == 200, approve_resp.text

    # Verify user roles: student role is removed, clean [intern] is granted
    await db.refresh(student)
    role_values = [r.value if hasattr(r, "value") else str(r) for r in student.roles]
    assert role_values == ["intern"]
