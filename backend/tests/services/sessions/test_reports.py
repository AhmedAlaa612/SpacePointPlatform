"""Mandatory tests for V2 W5 S5-2 (see MASTER_EXECUTION_PLAN_V2.md): assigned
instructor or ops can upload a session-scoped report; only ops can upload a
cohort-level report (no session_id); listing scopes correctly.

Storage I/O is monkeypatched — this tests the service's own logic (who can
upload, how it's linked, filename recovery), not the storage backend, which
has no test coverage precedent either way in this codebase yet.
"""

import uuid
from datetime import date

import pytest
from fastapi import HTTPException

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.user import User
from app.services.sessions import reports


async def _role_id(db, name: str = "Lead Facilitator"):
    """I5-3: roles are rows now. The three are seeded by migration
    `c2a7b49e0022`, so tests look them up rather than inventing their own."""
    from sqlalchemy import select

    from app.models.sessions.delivery_role import DeliveryRole

    return await db.scalar(select(DeliveryRole.id).where(DeliveryRole.name == name))



@pytest.fixture(autouse=True)
def _stub_storage(monkeypatch):
    async def _fake_upload(bucket, path, data, content_type):
        return path

    async def _fake_signed_url(bucket, path, expires_in=3600):
        return f"https://storage.test/{bucket}/{path}"

    monkeypatch.setattr(reports.storage, "upload_to_path", _fake_upload)
    monkeypatch.setattr(reports.storage, "get_signed_url", _fake_signed_url)


async def _make_cohort_with_session(db) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"RPT-{uuid.uuid4().hex[:8]}", name="Reports Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Reports Test Cohort", status="running", visibility="public")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 5))
    db.add(session)
    await db.flush()
    return cohort, session


async def _make_user(db, roles: list[str]) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Test User", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=roles,
    )
    db.add(user)
    await db.flush()
    return user


# ── display_filename ─────────────────────────────────────────────────────────

def test_display_filename_recovers_original_name():
    stored = f"{uuid.uuid4().hex}_field_report.pdf"
    assert reports.display_filename(stored) == "field_report.pdf"


def test_display_filename_handles_no_underscore():
    assert reports.display_filename("noname") == "noname"


# ── upload_report ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ops_can_upload_session_scoped_report(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])

    report = await reports.upload_report(db, cohort.id, session.id, b"data", "photo.jpg", "image/jpeg", "great session", ops)

    assert report.cohort_id == cohort.id
    assert report.session_id == session.id
    assert report.notes == "great session"
    assert report.uploaded_by == ops.id


@pytest.mark.asyncio
async def test_ops_can_upload_cohort_level_report_without_session(db):
    cohort, _ = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])

    report = await reports.upload_report(db, cohort.id, None, b"data", "summary.pdf", "application/pdf", None, ops)

    assert report.session_id is None


@pytest.mark.asyncio
async def test_assigned_instructor_can_upload_session_report(db):
    cohort, session = await _make_cohort_with_session(db)
    instructor = await _make_user(db, ["instructor"])
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=await _role_id(db)))
    await db.flush()

    report = await reports.upload_report(db, cohort.id, session.id, b"data", "photo.jpg", "image/jpeg", None, instructor)
    assert report.uploaded_by == instructor.id


@pytest.mark.asyncio
async def test_unassigned_instructor_cannot_upload_session_report(db):
    cohort, session = await _make_cohort_with_session(db)
    instructor = await _make_user(db, ["instructor"])

    with pytest.raises(HTTPException) as exc:
        await reports.upload_report(db, cohort.id, session.id, b"data", "photo.jpg", "image/jpeg", None, instructor)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_instructor_cannot_upload_cohort_level_report(db):
    cohort, _ = await _make_cohort_with_session(db)
    instructor = await _make_user(db, ["instructor"])

    with pytest.raises(HTTPException) as exc:
        await reports.upload_report(db, cohort.id, None, b"data", "summary.pdf", "application/pdf", None, instructor)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_session_from_other_cohort_rejected(db):
    cohort_a, _ = await _make_cohort_with_session(db)
    _, session_b = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])

    with pytest.raises(HTTPException) as exc:
        await reports.upload_report(db, cohort_a.id, session_b.id, b"data", "x.jpg", "image/jpeg", None, ops)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_unknown_cohort_404(db):
    ops = await _make_user(db, ["operations"])
    with pytest.raises(HTTPException) as exc:
        await reports.upload_report(db, uuid.uuid4(), None, b"data", "x.jpg", "image/jpeg", None, ops)
    assert exc.value.status_code == 404


# ── list_reports / list_session_reports / report_count_for_cohort ───────────

@pytest.mark.asyncio
async def test_list_reports_scoped_to_cohort(db):
    cohort_a, session_a = await _make_cohort_with_session(db)
    cohort_b, _ = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    await reports.upload_report(db, cohort_a.id, session_a.id, b"d", "a.jpg", "image/jpeg", None, ops)
    await reports.upload_report(db, cohort_b.id, None, b"d", "b.jpg", "image/jpeg", None, ops)

    rows = await reports.list_reports(db, cohort_a.id)
    assert len(rows) == 1
    assert rows[0][0].cohort_id == cohort_a.id
    assert rows[0][1] == ops.full_name


@pytest.mark.asyncio
async def test_list_session_reports_scoped_to_session(db):
    cohort, session = await _make_cohort_with_session(db)
    other_session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 12))
    db.add(other_session)
    await db.flush()
    ops = await _make_user(db, ["operations"])
    await reports.upload_report(db, cohort.id, session.id, b"d", "a.jpg", "image/jpeg", None, ops)
    await reports.upload_report(db, cohort.id, other_session.id, b"d", "b.jpg", "image/jpeg", None, ops)

    rows = await reports.list_session_reports(db, session.id)
    assert len(rows) == 1
    assert rows[0][0].session_id == session.id


@pytest.mark.asyncio
async def test_report_count_for_cohort(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    assert await reports.report_count_for_cohort(db, cohort.id) == 0

    await reports.upload_report(db, cohort.id, session.id, b"d", "a.jpg", "image/jpeg", None, ops)
    assert await reports.report_count_for_cohort(db, cohort.id) == 1


@pytest.mark.asyncio
async def test_resolve_report_url(db):
    cohort, session = await _make_cohort_with_session(db)
    ops = await _make_user(db, ["operations"])
    report = await reports.upload_report(db, cohort.id, session.id, b"d", "a.jpg", "image/jpeg", None, ops)

    url = await reports.resolve_report_url(report)
    assert url == f"https://storage.test/session-reports/{report.file_ref}"
