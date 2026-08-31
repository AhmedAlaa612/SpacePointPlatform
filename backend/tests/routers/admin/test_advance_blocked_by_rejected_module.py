"""An application must not be advanced (phase_1_approved / research_approved /
approved) while one of its modules is still sitting on an unresolved
rejection — otherwise an admin can approve the applicant past a document
that was flagged as needing changes, leaving them with no reason to ever
fix it.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.enums import ApplicationStatus, ModuleSubmissionStatus
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.checklist import ChecklistModule
from app.models.instructors.module_submission import ModuleSubmission
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


async def _applicant_with_rejected_module(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Candidate",
        email=f"cand-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["applicant"], status="active",
    )
    db.add(user)
    await db.flush()
    db.add(ApplicationReview(user_id=user.id, status=ApplicationStatus.under_review))

    module = ChecklistModule(id=uuid.uuid4(), title="Module 1", sort_order=1)
    db.add(module)
    await db.flush()

    submission = ModuleSubmission(
        id=uuid.uuid4(), user_id=user.id, module_id=module.id,
        file_url="https://example.com/doc.pdf", status=ModuleSubmissionStatus.rejected,
        feedback="Needs more detail on subsystems.",
    )
    db.add(submission)
    await db.flush()
    return user, submission


@pytest.mark.asyncio
async def test_advancing_is_blocked_while_a_module_is_rejected(db, client, admin_headers):
    user, _submission = await _applicant_with_rejected_module(db)
    await db.commit()

    resp = await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "phase_1_approved"}, headers=admin_headers,
    )
    assert resp.status_code == 400
    assert "rejected" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_advancing_succeeds_once_the_module_is_resubmitted(db, client, admin_headers):
    user, submission = await _applicant_with_rejected_module(db)
    submission.status = ModuleSubmissionStatus.submitted
    await db.commit()

    resp = await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "phase_1_approved"}, headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sending_back_to_under_review_is_never_blocked(db, client, admin_headers):
    user, _submission = await _applicant_with_rejected_module(db)
    await db.commit()

    resp = await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "under_review"}, headers=admin_headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_rejecting_outright_is_never_blocked(db, client, admin_headers):
    user, _submission = await _applicant_with_rejected_module(db)
    await db.commit()

    resp = await client.put(
        f"/instructors/admin/applicants/{user.id}/review",
        json={"status": "rejected", "feedback": "Not a fit."}, headers=admin_headers,
    )
    assert resp.status_code == 200
