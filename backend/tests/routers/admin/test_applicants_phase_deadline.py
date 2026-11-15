"""Admin applicants list exposes active phase time limits matching applicant status."""

from datetime import datetime, timedelta, timezone
import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.enums import ApplicationStatus
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User


@pytest_asyncio.fixture
async def admin_headers(db) -> dict:
    admin = User(
        id=uuid.uuid4(),
        full_name="Admin",
        email=f"admin-dl-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"),
        roles=["admin"],
        status="active",
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


async def _make_applicant(
    db,
    *,
    name: str,
    status: ApplicationStatus,
    phase_deadline: datetime | None,
    extension_used: bool = False,
) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=name,
        email=f"cand-dl-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"),
        roles=["applicant"],
        status="active",
    )
    db.add(user)
    await db.flush()
    db.add(
        ApplicationReview(
            user_id=user.id,
            status=status,
            phase_deadline=phase_deadline,
            extension_used=extension_used,
        )
    )
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_list_applicants_exposes_active_phase_deadlines(db, client, admin_headers):
    now = datetime.now(timezone.utc)
    future_dl = now + timedelta(hours=36)
    expired_dl = now - timedelta(hours=4)

    active_user = await _make_applicant(
        db,
        name="Active Phase1",
        status=ApplicationStatus.in_progress,
        phase_deadline=future_dl,
        extension_used=True,
    )
    expired_user = await _make_applicant(
        db,
        name="Expired Phase2",
        status=ApplicationStatus.phase_1_approved,
        phase_deadline=expired_dl,
        extension_used=False,
    )
    review_user = await _make_applicant(
        db,
        name="Waiting Admin",
        status=ApplicationStatus.under_review,
        phase_deadline=future_dl,
        extension_used=False,
    )
    approved_user = await _make_applicant(
        db,
        name="Final Approved",
        status=ApplicationStatus.approved,
        phase_deadline=None,
        extension_used=False,
    )
    await db.commit()

    resp = await client.get("/instructors/admin/applicants", headers=admin_headers)
    assert resp.status_code == 200
    by_id = {row["id"]: row for row in resp.json()}

    active_row = by_id[str(active_user.id)]
    assert active_row["phase_deadline"] is not None
    assert active_row["extension_used"] is True
    assert 35.5 <= active_row["hours_remaining"] <= 36.1

    expired_row = by_id[str(expired_user.id)]
    assert expired_row["phase_deadline"] is not None
    assert expired_row["extension_used"] is False
    assert expired_row["hours_remaining"] == 0.0

    # Deadlines are hidden once submitted for admin review or finalized.
    review_row = by_id[str(review_user.id)]
    assert review_row["phase_deadline"] is None
    assert review_row["hours_remaining"] is None

    approved_row = by_id[str(approved_user.id)]
    assert approved_row["phase_deadline"] is None
    assert approved_row["hours_remaining"] is None
