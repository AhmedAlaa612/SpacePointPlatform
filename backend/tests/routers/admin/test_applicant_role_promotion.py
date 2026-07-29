"""Approving an instructor applicant must not destroy their other roles.

Reported 2026-07-27: completing instructor onboarding assigned a fresh role
set, so anyone who already held a role lost it. It also made dual roles
impossible in general — `also_grant_role` exists only as a single-role escape
hatch through that wipe.

'applicant' is pipeline state, not a capability (the real state lives on
application_reviews.status). Promotion means swapping that one value for
'instructor' and leaving everything else alone.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.enums import ApplicationStatus
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User


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


async def _applicant(db, roles: list[str], *, also_grant: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Candidate",
        email=f"cand-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=roles, status="active",
    )
    db.add(user)
    await db.flush()
    db.add(ApplicantProfile(
        user_id=user.id, country="United Arab Emirates", also_grant_role=also_grant,
    ))
    db.add(ApplicationReview(user_id=user.id, status=ApplicationStatus.under_review))
    await db.flush()
    return user


async def _approve(client, headers, user: User):
    return await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "approved"}, headers=headers,
    )


@pytest.mark.asyncio
async def test_approval_keeps_roles_the_person_already_held(db, client, admin_headers):
    """The reported bug: an ambassador who becomes an instructor stopped
    being an ambassador."""
    user = await _applicant(db, ["applicant", "ambassador"])
    await db.commit()

    resp = await _approve(client, admin_headers, user)
    assert resp.status_code == 200, resp.text

    await db.refresh(user)
    assert set(user.role_values) == {"ambassador", "instructor"}


@pytest.mark.asyncio
async def test_applicant_is_the_only_role_dropped(db, client, admin_headers):
    user = await _applicant(db, ["applicant"])
    await db.commit()

    resp = await _approve(client, admin_headers, user)
    assert resp.status_code == 200, resp.text

    await db.refresh(user)
    assert set(user.role_values) == {"instructor"}


@pytest.mark.asyncio
async def test_also_grant_role_still_adds_a_role_never_held(db, client, admin_headers):
    """An intern application routed into this pipeline: the person never had
    the intern role, so it can't be preserved — it has to be granted."""
    user = await _applicant(db, ["applicant"], also_grant="intern")
    await db.commit()

    resp = await _approve(client, admin_headers, user)
    assert resp.status_code == 200, resp.text

    await db.refresh(user)
    assert set(user.role_values) == {"instructor", "intern"}


@pytest.mark.asyncio
async def test_a_teacher_and_ambassador_keeps_both_plus_the_granted_role(db, client, admin_headers):
    user = await _applicant(db, ["applicant", "teacher", "ambassador"], also_grant="intern")
    await db.commit()

    resp = await _approve(client, admin_headers, user)
    assert resp.status_code == 200, resp.text

    await db.refresh(user)
    assert set(user.role_values) == {"teacher", "ambassador", "instructor", "intern"}
