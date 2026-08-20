"""Routing an intern application into the instructor onboarding pipeline.

Reported from production (2026-07-27): a bare 500, `duplicate key value
violates unique constraint "ix_users_email"`. The endpoint always inserted a
brand-new User from the application, but `users.email` is unique while
`applications.email` is only indexed — so the moment the applicant already had
an account, it blew up.

That isn't an edge case, it's the normal shape of what this endpoint is for:
someone who applied through the instructor flow already has a User with the
applicant role, and routing their *intern* application into the same pipeline
is exactly how they come to hold both roles.

Redis-free — nothing here enqueues.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.application import Application
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User

_INTERNSHIP_BODY = {
    "internship": {
        "salutation": "Mr.", "activity_description": "engineering",
        "supervisor_title": "Mr.", "supervisor_name": "Test Supervisor",
        "supervisor_email": "sup@example.com", "supervisor_phone": "+971500000000",
    }
}


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Admin",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["admin"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin_user.id, ['admin'])}"}


@pytest_asyncio.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_application(db, email: str) -> Application:
    application = Application(
        id=uuid.uuid4(), role="intern", status="pending",
        full_name="Bilal Ayyad", email=email,
        password_hash=get_password_hash("applicant-password"),
        answers={},
    )
    db.add(application)
    await db.flush()
    return application


@pytest.mark.asyncio
async def test_onboards_an_applicant_who_has_no_account_yet(db, client, admin_headers):
    application = await _make_application(db, f"fresh-{uuid.uuid4().hex[:8]}@example.com")
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/onboard", json=_INTERNSHIP_BODY, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    user = await db.get(User, uuid.UUID(resp.json()["user_id"]))
    assert "applicant" in user.role_values
    profile = await db.get(ApplicantProfile, user.id)
    assert profile is not None and profile.also_grant_role == "intern"


@pytest.mark.asyncio
async def test_onboards_an_applicant_who_already_has_an_account(db, client, admin_headers):
    """The production 500. They're already in the instructor pipeline; routing
    the intern application must reuse that account, not insert a second one."""
    email = f"dual-{uuid.uuid4().hex[:8]}@example.com"
    existing = User(
        id=uuid.uuid4(), full_name="Bilal Ayyad", email=email,
        password_hash=get_password_hash("x"), roles=["applicant"], status="active",
    )
    db.add(existing)
    await db.flush()
    application = await _make_application(db, email)
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/onboard", json=_INTERNSHIP_BODY, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_id"] == str(existing.id), "must reuse the account, not create a second"

    profile = await db.get(ApplicantProfile, existing.id)
    assert profile is not None and profile.also_grant_role == "intern"
    await db.refresh(application)
    assert application.status == "onboarding"


@pytest.mark.asyncio
async def test_onboarding_someone_already_in_the_instructor_pipeline_is_not_a_duplicate(
    db, client, admin_headers,
):
    """applicant_profiles.user_id is the PK and application_reviews.user_id is
    unique — inserting rather than updating either would 500 just as loudly."""
    email = f"inpipe-{uuid.uuid4().hex[:8]}@example.com"
    existing = User(
        id=uuid.uuid4(), full_name="Already Applying", email=email,
        password_hash=get_password_hash("x"), roles=["applicant"], status="active",
    )
    db.add(existing)
    await db.flush()
    db.add(ApplicantProfile(user_id=existing.id, country="AE", cv_path="cvs/existing.pdf"))
    db.add(ApplicationReview(user_id=existing.id))
    application = await _make_application(db, email)
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/onboard", json=_INTERNSHIP_BODY, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    profile = await db.get(ApplicantProfile, existing.id)
    assert profile.also_grant_role == "intern", "routing here is what grants the second role"
    assert profile.cv_path == "cvs/existing.pdf", "an existing CV shouldn't be clobbered"


@pytest.mark.asyncio
async def test_only_intern_applications_can_be_routed(db, client, admin_headers):
    application = await _make_application(db, f"amb-{uuid.uuid4().hex[:8]}@example.com")
    application.role = "ambassador"
    await db.commit()

    resp = await client.post(
        f"/admin/applications/{application.id}/onboard", json={}, headers=admin_headers,
    )
    assert resp.status_code == 400, resp.text
