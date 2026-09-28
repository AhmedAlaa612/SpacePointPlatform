import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token, get_password_hash
from app.models.birthday_log import BirthdayEmailLog
from app.models.user import User


@pytest.mark.asyncio
async def test_admin_birthdays_upcoming_and_stats(db, client):
    today = datetime.now(timezone.utc).date()
    # User with birthday in 3 days
    bday_soon = today + timedelta(days=3)

    admin = User(
        id=uuid.uuid4(),
        full_name="Admin Boss",
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=["admin"],
        status="active",
        birthdate=date(1990, 1, 1),
    )

    student = User(
        id=uuid.uuid4(),
        full_name="Birthday Student",
        email=f"student-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=["student"],
        status="active",
        birthdate=date(2005, bday_soon.month, bday_soon.day),
    )

    db.add_all([admin, student])
    await db.flush()

    headers = {"Authorization": f"Bearer {create_access_token(admin.id, ['admin'])}"}

    # Test upcoming on /admin/birthdays/upcoming
    resp = await client.get("/admin/birthdays/upcoming?days=7", headers=headers)
    assert resp.status_code == 200, resp.text
    upcoming = resp.json()
    assert any(u["id"] == str(student.id) for u in upcoming)
    student_entry = next(u for u in upcoming if u["id"] == str(student.id))
    assert student_entry["days_until"] == 3

    # Test also on /api/v1/admin/birthdays/upcoming
    resp_v1 = await client.get("/api/v1/admin/birthdays/upcoming?days=7", headers=headers)
    assert resp_v1.status_code == 200

    # Test stats
    stats_resp = await client.get("/admin/birthdays/stats", headers=headers)
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_with_birthdays"] >= 2
    assert stats["upcoming_7_days"] >= 1


@pytest.mark.asyncio
async def test_admin_birthdays_logs_and_retry(db, client):
    today = datetime.now(timezone.utc).date()

    admin = User(
        id=uuid.uuid4(),
        full_name="Admin Two",
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=["admin"],
        status="active",
    )

    instructor = User(
        id=uuid.uuid4(),
        full_name="Instructor Star",
        email=f"instructor-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=["instructor"],
        status="active",
        birthdate=date(1992, today.month, today.day),
    )

    db.add_all([admin, instructor])
    await db.flush()

    # Create a failed log
    failed_log = BirthdayEmailLog(
        user_id=instructor.id,
        sent_at=datetime.now(timezone.utc),
        sent_at_year=today.year,
        birth_year_referenced=2010,
        nasa_image_url="https://example.com/star.jpg",
        nasa_title="Star Formation",
        status="failed",
        error_message="SMTP connection timed out",
    )
    db.add(failed_log)
    await db.flush()
    await db.refresh(failed_log)

    headers = {"Authorization": f"Bearer {create_access_token(admin.id, ['admin'])}"}

    # 1. Fetch logs
    resp = await client.get("/admin/birthdays/logs", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    found_log = next(item for item in data["items"] if item["id"] == str(failed_log.id))
    assert found_log["status"] == "failed"
    assert found_log["user_full_name"] == "Instructor Star"

    # 2. Retry send via API
    with patch("app.workers.tasks.birthdays.send_birthday_greeting_email", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        retry_resp = await client.post(f"/admin/birthdays/retry/{failed_log.id}", headers=headers)
        assert retry_resp.status_code == 200, retry_resp.text
        updated = retry_resp.json()
        assert updated["status"] == "sent"
        assert updated["user_id"] == str(instructor.id)


@pytest.mark.asyncio
async def test_admin_birthday_test_send_does_not_log_to_db(db, client):
    admin = User(
        id=uuid.uuid4(),
        full_name="Admin TestSender",
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=["admin"],
        status="active",
    )
    db.add(admin)
    await db.flush()

    headers = {"Authorization": f"Bearer {create_access_token(admin.id, ['admin'])}"}

    # Count logs before
    initial_log_count = await db.scalar(select(func.count(BirthdayEmailLog.id))) or 0

    with patch("app.routers.admin.birthdays.send_birthday_greeting_email", new_callable=AsyncMock) as mock_send, \
         patch("app.routers.admin.birthdays.get_nasa_birthday_picture", new_callable=AsyncMock) as mock_apod:
        mock_send.return_value = True
        mock_apod.return_value = {
            "title": "Cosmic Wonder",
            "year": 2012,
            "image_url": "https://example.com/wonder.jpg",
            "explanation": "Stunning stars",
        }

        payload = {
            "email": "mytest@example.com",
            "full_name": "My Personal Test",
            "birthdate": "2000-09-30",
        }

        resp = await client.post("/admin/birthdays/test-send", json=payload, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["success"] is True
        assert data["recipient_email"] == "mytest@example.com"
        assert data["nasa_title"] == "Cosmic Wonder"

        mock_send.assert_called_once()
        _, kwargs = mock_send.call_args
        assert kwargs["to_email"] == "mytest@example.com"
        assert kwargs["full_name"] == "My Personal Test"

    # Count logs after: MUST REMAIN UNCHANGED
    after_log_count = await db.scalar(select(func.count(BirthdayEmailLog.id))) or 0
    assert after_log_count == initial_log_count

