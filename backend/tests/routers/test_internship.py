"""End-to-end: instructor requests the intern role -> admin approves (letter
generated) -> intern signs (signed letter generated, role held). Exercises
routers/internship.py + services/internship/{approval,ref_number}.py against
a real Postgres test DB and real LibreOffice conversion (the same stack
scripts/bulk_import_interns.py was verified against)."""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.enums import UserRole
from app.models.internship import InternProfile, RoleRequest
from app.models.user import User

pytestmark = pytest.mark.asyncio

_TEST_SIG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _make_user(db, *, roles: list[UserRole], email: str | None = None) -> User:
    user = User(
        full_name="Test Instructor",
        email=email or f"{uuid.uuid4()}@example.com",
        password_hash=get_password_hash("pw12345"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def test_instructor_can_request_intern_role(db, client):
    instructor = await _make_user(db, roles=[UserRole.instructor])
    await db.flush()

    resp = await client.post(
        "/me/role-requests",
        json={"target_role": "intern", "details": {
            "university_id_number": "12345", "requested_duration_weeks": 8,
        }},
        headers=_auth(instructor),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["target_role"] == "intern"
    assert body["status"] == "pending"


async def test_disallowed_role_request_is_rejected(db, client):
    student = await _make_user(db, roles=[UserRole.student])
    resp = await client.post(
        "/me/role-requests",
        json={"target_role": "intern", "details": {}},
        headers=_auth(student),
    )
    assert resp.status_code == 403


async def test_duplicate_pending_request_is_rejected(db, client):
    instructor = await _make_user(db, roles=[UserRole.instructor])
    body = {"target_role": "intern", "details": {}}
    r1 = await client.post("/me/role-requests", json=body, headers=_auth(instructor))
    assert r1.status_code == 201
    r2 = await client.post("/me/role-requests", json=body, headers=_auth(instructor))
    assert r2.status_code == 400


async def test_full_approve_and_sign_flow(db, client):
    admin = await _make_user(db, roles=[UserRole.admin])
    instructor = await _make_user(db, roles=[UserRole.instructor], email="amna@example.com")
    instructor.full_name = "Amna Khairi"
    await db.flush()

    submit = await client.post(
        "/me/role-requests",
        json={"target_role": "intern", "details": {
            "university_id_number": "1092579", "requested_duration_weeks": 8,
        }},
        headers=_auth(instructor),
    )
    assert submit.status_code == 201, submit.text
    req_id = submit.json()["id"]

    approve = await client.post(
        f"/admin/role-requests/{req_id}/approve",
        json={
            "salutation": "Ms.", "activity_description": "research and development",
            "supervisor_title": "Mr.", "supervisor_name": "Abdullah AlSalmani",
            "supervisor_email": "abdel.alsalmani@gmail.com", "supervisor_phone": "+971562987005",
            "duration_weeks": 8, "hours_per_week": 40,
        },
        headers=_auth(admin),
    )
    assert approve.status_code == 200, approve.text
    approved = approve.json()
    assert approved["status"] == "approved"
    assert approved["resolution"]["ref_number"]

    # Role actually granted + profile actually populated.
    await db.refresh(instructor)
    assert "intern" in instructor.role_values
    profile = await db.get(InternProfile, instructor.id)
    assert profile is not None
    assert profile.ref_number == approved["resolution"]["ref_number"]
    assert profile.letter_path
    assert profile.letter_date is not None
    frozen_letter_date = profile.letter_date

    letter_status = await client.get("/intern/internship-letter", headers=_auth(instructor))
    assert letter_status.status_code == 200
    assert letter_status.json()["letter_url"]
    assert letter_status.json()["signed_letter_url"] is None

    sign = await client.post(
        "/intern/internship-letter/sign", json={"signature": _TEST_SIG}, headers=_auth(instructor),
    )
    assert sign.status_code == 200, sign.text
    signed = sign.json()
    assert signed["signed_letter_url"]
    assert signed["letter_signed_at"]

    await db.refresh(profile)
    assert profile.letter_signed_at is not None
    assert profile.letter_date == frozen_letter_date  # never drifts on re-render

    # Signing twice is rejected.
    sign_again = await client.post(
        "/intern/internship-letter/sign", json={"signature": _TEST_SIG}, headers=_auth(instructor),
    )
    assert sign_again.status_code == 400


async def test_ref_numbers_increment_within_a_year(db, client):
    admin = await _make_user(db, roles=[UserRole.admin])
    approvals = []
    for i in range(2):
        instructor = await _make_user(db, roles=[UserRole.instructor], email=f"seq{i}@example.com")
        await db.flush()
        submit = await client.post(
            "/me/role-requests", json={"target_role": "intern", "details": {}}, headers=_auth(instructor),
        )
        req_id = submit.json()["id"]
        approve = await client.post(
            f"/admin/role-requests/{req_id}/approve",
            json={
                "salutation": "Mr.", "activity_description": "engineering",
                "supervisor_title": "Mr.", "supervisor_name": "Test Supervisor",
                "supervisor_email": "sup@example.com", "supervisor_phone": "+971500000000",
                "duration_weeks": 4, "hours_per_week": 20,
            },
            headers=_auth(admin),
        )
        assert approve.status_code == 200, approve.text
        approvals.append(approve.json()["resolution"]["ref_number"])

    n1 = int(approvals[0].split("/")[0])
    n2 = int(approvals[1].split("/")[0])
    assert n2 == n1 + 1


async def test_admin_can_reject_request(db, client):
    admin = await _make_user(db, roles=[UserRole.admin])
    instructor = await _make_user(db, roles=[UserRole.instructor])
    submit = await client.post(
        "/me/role-requests", json={"target_role": "intern", "details": {}}, headers=_auth(instructor),
    )
    req_id = submit.json()["id"]

    reject = await client.post(
        f"/admin/role-requests/{req_id}/reject", json={"admin_notes": "not eligible"}, headers=_auth(admin),
    )
    assert reject.status_code == 200
    assert reject.json()["status"] == "rejected"

    await db.refresh(instructor)
    assert "intern" not in instructor.role_values

    # A rejected request doesn't block a fresh one.
    resubmit = await client.post(
        "/me/role-requests", json={"target_role": "intern", "details": {}}, headers=_auth(instructor),
    )
    assert resubmit.status_code == 201


async def test_approval_before_requested_date_uses_the_requested_date(db, client):
    """Boss spec (2026-08-20): approving on/before what was requested honors
    that date exactly. resolve_start_date's exhaustive branch logic is unit
    tested in tests/services/test_internship_start_date.py — this just
    proves the wiring through the real approve endpoint."""
    from datetime import date, timedelta

    admin = await _make_user(db, roles=[UserRole.admin])
    instructor = await _make_user(db, roles=[UserRole.instructor], email="future-start@example.com")
    requested = (date.today() + timedelta(days=30)).isoformat()

    submit = await client.post(
        "/me/role-requests",
        json={"target_role": "intern", "details": {"requested_start_date": requested}},
        headers=_auth(instructor),
    )
    req_id = submit.json()["id"]

    approve = await client.post(
        f"/admin/role-requests/{req_id}/approve",
        json={
            "salutation": "Mr.", "activity_description": "engineering",
            "supervisor_title": "Mr.", "supervisor_name": "Test Supervisor",
            "supervisor_email": "sup@example.com", "supervisor_phone": "+971500000000",
        },
        headers=_auth(admin),
    )
    assert approve.status_code == 200, approve.text

    profile = await db.get(InternProfile, instructor.id)
    assert profile.start_date.isoformat() == requested


async def test_admin_start_date_override_wins_over_requested_date(db, client):
    from datetime import date, timedelta

    admin = await _make_user(db, roles=[UserRole.admin])
    instructor = await _make_user(db, roles=[UserRole.instructor], email="override-start@example.com")
    requested = (date.today() + timedelta(days=30)).isoformat()
    override = (date.today() + timedelta(days=90)).isoformat()

    submit = await client.post(
        "/me/role-requests",
        json={"target_role": "intern", "details": {"requested_start_date": requested}},
        headers=_auth(instructor),
    )
    req_id = submit.json()["id"]

    approve = await client.post(
        f"/admin/role-requests/{req_id}/approve",
        json={
            "salutation": "Mr.", "activity_description": "engineering",
            "supervisor_title": "Mr.", "supervisor_name": "Test Supervisor",
            "supervisor_email": "sup@example.com", "supervisor_phone": "+971500000000",
            "start_date_override": override,
        },
        headers=_auth(admin),
    )
    assert approve.status_code == 200, approve.text

    profile = await db.get(InternProfile, instructor.id)
    assert profile.start_date.isoformat() == override
