"""Both paths from a public intern Application to a generated internship
letter (HANDOFF_INTERNSHIP.md):

- Path 1: admin approves the application directly (POST .../approve) —
  the letter fields are required in the same request, letter generated
  immediately.
- Path 2: admin routes it to instructor onboarding (POST .../onboard) with
  the letter fields, then instructor approval (PUT .../review) auto-
  generates the letter later, in that request, using what was stashed.

Real Postgres + real LibreOffice rendering (same stack test_internship.py
already exercises) — no mocks on the generation path.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.internship import InternProfile
from app.models.user import User

pytestmark = pytest.mark.asyncio

_LETTER_FIELDS = {
    "salutation": "Ms.", "activity_description": "research and development",
    "supervisor_title": "Mr.", "supervisor_name": "Abdullah AlSalmani",
    "supervisor_email": "abdel.alsalmani@gmail.com", "supervisor_phone": "+971562987005",
}


@pytest_asyncio.fixture
async def admin_headers(db) -> dict:
    admin = User(
        id=uuid.uuid4(), full_name="Admin",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["admin"], status="active",
    )
    db.add(admin)
    await db.flush()
    return {"Authorization": f"Bearer {create_access_token(admin.id, ['admin'])}"}


@pytest_asyncio.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_intern_application(db, **answers) -> Application:
    application = Application(
        id=uuid.uuid4(), role="intern", status="pending",
        full_name="Amna Khairi", email=f"amna-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"),
        answers={
            "university_id_number": "1092579", "requested_duration_weeks": 8,
            **answers,
        },
    )
    db.add(application)
    await db.flush()
    return application


# ── Path 1 ────────────────────────────────────────────────────────────────

async def test_direct_approve_requires_internship_fields(db, client, admin_headers):
    application = await _make_intern_application(db)
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/approve", json={}, headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_direct_approve_generates_the_letter(db, client, admin_headers):
    application = await _make_intern_application(db)
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/approve",
        json={"internship": {**_LETTER_FIELDS, "duration_weeks": 8, "hours_per_week": 40}},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    user_id = uuid.UUID(resp.json()["user_id"])
    user = await db.get(User, user_id)
    assert "intern" in user.role_values

    profile = await db.get(InternProfile, user_id)
    assert profile is not None
    assert profile.university_id_number == "1092579"  # carried from Application.answers
    assert profile.duration_weeks == 8
    assert profile.ref_number
    assert profile.letter_path
    assert profile.letter_signed_at is None


# ── Path 2 ────────────────────────────────────────────────────────────────

async def test_onboarding_requires_internship_fields(db, client, admin_headers):
    application = await _make_intern_application(db)
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/onboard", json={}, headers=admin_headers,
    )
    assert resp.status_code == 400


async def test_onboarding_then_instructor_approval_auto_generates_the_letter(db, client, admin_headers):
    application = await _make_intern_application(db, requested_start_date="2026-09-01")
    await db.commit()

    onboard = await client.post(
        f"/admin/applications/{application.id}/onboard",
        json={"internship": {**_LETTER_FIELDS, "duration_weeks": 8, "hours_per_week": 40}},
        headers=admin_headers,
    )
    assert onboard.status_code == 200, onboard.text
    user_id = uuid.UUID(onboard.json()["user_id"])

    # Not generated yet — only stashed, per the agreed design.
    assert await db.get(InternProfile, user_id) is None
    profile = await db.get(ApplicantProfile, user_id)
    assert profile.also_grant_role == "intern"
    assert profile.pending_intern_details["university_id_number"] == "1092579"
    assert profile.pending_intern_details["start_date"] == "2026-09-01"
    assert profile.pending_intern_details["approve"]["supervisor_name"] == "Abdullah AlSalmani"

    review = await client.put(
        f"/instructors/admin/applicants/{user_id}/review",
        json={"status": "approved"}, headers=admin_headers,
    )
    assert review.status_code == 200, review.text

    user = await db.get(User, user_id)
    assert set(user.role_values) == {"instructor", "intern"}

    intern_profile = await db.get(InternProfile, user_id)
    assert intern_profile is not None
    assert intern_profile.university_id_number == "1092579"
    assert str(intern_profile.start_date) == "2026-09-01"
    assert intern_profile.duration_weeks == 8
    assert intern_profile.ref_number
    assert intern_profile.letter_path


async def test_also_grant_role_without_pending_details_still_just_grants_the_role(db, client, admin_headers):
    """Pre-existing behavior (ApplicantProfile built without going through
    onboard_application, e.g. seeded directly) must be unaffected — no
    letter, no crash, same as before this feature existed."""
    user = User(
        id=uuid.uuid4(), full_name="Candidate",
        email=f"cand-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["applicant"], status="active",
    )
    db.add(user)
    await db.flush()
    db.add(ApplicantProfile(user_id=user.id, country="AE", also_grant_role="intern"))
    db.add(ApplicationReview(user_id=user.id, status=ApplicationStatus.under_review))
    await db.commit()

    resp = await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "approved"}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    await db.refresh(user)
    assert set(user.role_values) == {"instructor", "intern"}
    assert await db.get(InternProfile, user.id) is None
