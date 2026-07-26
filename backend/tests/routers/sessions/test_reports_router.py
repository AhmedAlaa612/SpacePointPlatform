"""Endpoint tests for session reports (V2 W5 S5-2): role guards, real
multipart upload, cohort-scoped list, and the complete_cohort zero-reports
warning. Redis-free — nothing here touches ARQ.
"""

import uuid
from datetime import date

import httpx
import pytest

from app.db.session import get_db
from app.main import app
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.services.sessions import reports as reports_service


@pytest.fixture(autouse=True)
def _stub_storage(monkeypatch):
    async def _fake_upload(bucket, path, data, content_type):
        return path

    async def _fake_signed_url(bucket, path, expires_in=3600):
        return f"https://storage.test/{bucket}/{path}"

    monkeypatch.setattr(reports_service.storage, "upload_to_path", _fake_upload)
    monkeypatch.setattr(reports_service.storage, "get_signed_url", _fake_signed_url)


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_cohort_with_session(db) -> tuple[Cohort, Session]:
    program = Program(
        id=uuid.uuid4(), code=f"RPTR-{uuid.uuid4().hex[:8]}", name="Reports Router Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Reports Router Test Cohort", status="running", visibility="public")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date(2026, 9, 8))
    db.add(session)
    await db.flush()
    return cohort, session


# ── upload ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_report_requires_authentication(db, client):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/reports", files={"file": ("r.jpg", b"data", "image/jpeg")},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_report_rejects_wrong_role(db, client, other_role_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/reports", files={"file": ("r.jpg", b"data", "image/jpeg")},
        headers=other_role_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unassigned_instructor_cannot_upload(db, client, instructor_headers):
    cohort, session = await _make_cohort_with_session(db)
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/reports",
        data={"session_id": str(session.id)},
        files={"file": ("r.jpg", b"data", "image/jpeg")},
        headers=instructor_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_assigned_instructor_can_upload_with_notes(db, client, instructor_headers, instructor_user):
    cohort, session = await _make_cohort_with_session(db)
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor_user.id, role="lead"))
    await db.flush()

    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/reports",
        data={"session_id": str(session.id), "notes": "Great turnout"},
        files={"file": ("field_report.jpg", b"data", "image/jpeg")},
        headers=instructor_headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["notes"] == "Great turnout"
    assert body["filename"] == "field_report.jpg"
    assert body["uploaded_by_name"] == instructor_user.full_name
    assert body["file_url"].startswith("https://storage.test/session-reports/")


@pytest.mark.asyncio
async def test_ops_can_upload_cohort_level_report(db, client, operations_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(
        f"/sessions/cohorts/{cohort.id}/reports",
        files={"file": ("summary.pdf", b"data", "application/pdf")},
        headers=operations_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["session_id"] is None


# ── list (ops only) ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_reports_requires_operations(db, client, instructor_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.get(f"/sessions/cohorts/{cohort.id}/reports", headers=instructor_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_reports_returns_uploaded(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    await client.post(
        f"/sessions/cohorts/{cohort.id}/reports",
        data={"session_id": str(session.id)},
        files={"file": ("a.jpg", b"data", "image/jpeg")},
        headers=operations_headers,
    )

    resp = await client.get(f"/sessions/cohorts/{cohort.id}/reports", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1


# ── complete_cohort zero-reports warning ─────────────────────────────────────

@pytest.mark.asyncio
async def test_complete_cohort_warns_when_zero_reports(db, client, operations_headers):
    cohort, _ = await _make_cohort_with_session(db)
    resp = await client.post(f"/sessions/cohorts/{cohort.id}/complete", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["cohort"]["status"] == "completed"
    assert len(body["warnings"]) == 1


@pytest.mark.asyncio
async def test_complete_cohort_no_warning_when_report_exists(db, client, operations_headers):
    cohort, session = await _make_cohort_with_session(db)
    await client.post(
        f"/sessions/cohorts/{cohort.id}/reports",
        data={"session_id": str(session.id)},
        files={"file": ("a.jpg", b"data", "image/jpeg")},
        headers=operations_headers,
    )

    resp = await client.post(f"/sessions/cohorts/{cohort.id}/complete", headers=operations_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["warnings"] == []
