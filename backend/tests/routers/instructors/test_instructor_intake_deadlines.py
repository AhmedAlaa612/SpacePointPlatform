import io
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.enums import ApplicationStatus, UserRole
from app.models.instructors.application_review import ApplicationReview
from app.models.user import User
from app.services.instructors.deadlines import (
    compute_phase_deadline,
    get_instructor_settings,
    is_student_eligible_to_apply,
)
from app.workers.tasks.applicant_expiration import process_expired_applications


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_intake_eligibility_logic():
    settings = {
        "instructor_intake_enabled": True,
        "instructor_intake_min_age": 18,
        "instructor_intake_require_university": False,
    }

    # 1. Under-18 user
    today = date.today()
    minor_user = User(
        id=uuid.uuid4(),
        full_name="Minor Student",
        email="minor@example.com",
        password_hash="x",
        roles=[UserRole.student],
        birthdate=date(today.year - 16, today.month, today.day),
    )
    eligible, reason = is_student_eligible_to_apply(minor_user, settings)
    assert not eligible
    assert "at least 18" in reason

    # 2. User with no birthdate
    no_dob_user = User(
        id=uuid.uuid4(),
        full_name="No DOB Student",
        email="nodob@example.com",
        password_hash="x",
        roles=[UserRole.student],
        birthdate=None,
    )
    eligible, reason = is_student_eligible_to_apply(no_dob_user, settings)
    assert not eligible
    assert "Birthdate is not set" in reason

    # 3. Adult user (20 years old)
    adult_user = User(
        id=uuid.uuid4(),
        full_name="Adult Student",
        email="adult@example.com",
        password_hash="x",
        roles=[UserRole.student],
        birthdate=date(today.year - 20, today.month, today.day),
    )
    eligible, reason = is_student_eligible_to_apply(adult_user, settings)
    assert eligible
    assert reason is None

    # 4. Master toggle disabled
    disabled_settings = {**settings, "instructor_intake_enabled": False}
    eligible, reason = is_student_eligible_to_apply(adult_user, disabled_settings)
    assert not eligible
    assert "currently closed" in reason


@pytest.mark.asyncio
async def test_apply_as_student_and_extension(db, client):
    today = date.today()
    student = User(
        id=uuid.uuid4(),
        full_name="Adult Test Student",
        email=f"adult-student-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass123"),
        roles=[UserRole.student],
        status="active",
        birthdate=date(today.year - 21, today.month, today.day),
    )
    db.add(student)
    await db.commit()
    await db.refresh(student)

    # Check eligibility endpoint
    res = await client.get("/instructors/intake-eligibility", headers=_headers(student))
    assert res.status_code == http_status.HTTP_200_OK
    data = res.json()
    assert data["eligible"] is True
    assert data["has_birthdate"] is True

    # Submit application
    payload = {
        "university": "Space University",
        "highest_degree": "Bachelors",
        "background_areas": ["Engineering"],
        "has_own_transportation": True,
    }
    cv_file = ("cv.pdf", io.BytesIO(b"%PDF-dummy content"), "application/pdf")
    res = await client.post(
        "/instructors/apply-as-student",
        headers=_headers(student),
        data={"payload": json.dumps(payload)},
        files={"cv": cv_file},
    )
    assert res.status_code == http_status.HTTP_201_CREATED
    resp_data = res.json()
    assert "access_token" in resp_data
    assert "applicant" in resp_data["user"]["roles"]

    # Verify review and deadline in DB
    review = (await db.execute(
        select(ApplicationReview).where(ApplicationReview.user_id == student.id)
    )).scalars().first()
    assert review is not None
    assert review.phase_deadline is not None
    assert review.extension_used is False

    # Get status endpoint
    headers_applicant = {"Authorization": f"Bearer {resp_data['access_token']}"}
    status_res = await client.get("/instructors/status", headers=headers_applicant)
    assert status_res.status_code == http_status.HTTP_200_OK
    status_data = status_res.json()
    assert status_data["can_extend"] is True
    assert status_data["extension_used"] is False
    assert status_data["hours_remaining"] is not None

    # Request extension
    ext_res = await client.post("/instructors/request-extension", headers=headers_applicant)
    assert ext_res.status_code == http_status.HTTP_200_OK
    ext_data = ext_res.json()
    assert ext_data["extension_used"] is True
    assert ext_data["can_extend"] is False

    # Second extension attempt must be rejected
    second_ext = await client.post("/instructors/request-extension", headers=headers_applicant)
    assert second_ext.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_process_expired_applications_worker(db):
    now = datetime.now(timezone.utc)
    expired_user = User(
        id=uuid.uuid4(),
        full_name="Expired Applicant",
        email=f"expired-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=[UserRole.student, UserRole.applicant],
        status="active",
    )
    db.add(expired_user)
    await db.flush()

    past_deadline = now - timedelta(hours=2)
    review = ApplicationReview(
        user_id=expired_user.id,
        status=ApplicationStatus.in_progress,
        phase_deadline=past_deadline,
        extension_used=True,
        created_at=now - timedelta(days=8),
        last_status_change_at=now - timedelta(days=8),
    )
    db.add(review)
    await db.commit()

    # Run worker job
    result = await process_expired_applications(db_session=db)
    assert result["expired_count"] >= 1

    # Reload from DB
    await db.refresh(review)
    await db.refresh(expired_user)
    assert review.status == ApplicationStatus.rejected
    assert "applicant" not in expired_user.role_values
    assert "student" in expired_user.role_values
