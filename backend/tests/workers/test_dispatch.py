"""Tests for safe_enqueue's dispatch decision and issue_ticket's idempotency.

Both exist to stop one specific failure: a student receiving their QR ticket
twice. safe_enqueue used to hand the job to ARQ *and* always also start an
in-process send, so with a real worker consuming the queue both ran. That
combination never happened in dev — Docker/Redis wasn't reliably up, so no
worker was ever running alongside the API — meaning production would have
been the first place it fired.

These tests need no live Redis: the pool is a stub that records calls.
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest

from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.services.sessions import registration as registration_service
from app.workers import settings as worker_settings


class _StubArqRedis:
    """Records enqueue_job calls. Stands in for a live ARQ pool."""

    def __init__(self, raises: Exception | None = None):
        self.calls: list[tuple] = []
        self._raises = raises

    async def enqueue_job(self, function: str, *args, **kwargs):
        if self._raises is not None:
            raise self._raises
        self.calls.append((function, args, kwargs))
        return object()


@pytest.fixture
def captured_fallbacks(monkeypatch):
    """Replaces the in-process fallback so we can see whether it was started,
    without actually sending mail or touching the database."""
    started: list[tuple[str, bool]] = []

    async def _fake_fallback(registration_id: str, force: bool = False) -> None:
        started.append((registration_id, force))

    monkeypatch.setattr(worker_settings, "_fallback_send_ticket_email", _fake_fallback)
    return started


async def _let_tasks_run() -> None:
    """safe_enqueue's fallback goes through asyncio.create_task, which is only
    scheduled — not run — by the time safe_enqueue returns. Yield once so it
    actually executes before we assert on it."""
    await asyncio.sleep(0)


# ── safe_enqueue dispatch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_working_queue_does_not_also_send_in_process(captured_fallbacks):
    """The regression this whole file exists for: exactly one dispatch path."""
    stub = _StubArqRedis()

    result = await worker_settings.safe_enqueue(stub, "send_ticket_email", str(uuid.uuid4()))
    await _let_tasks_run()

    assert result == "queued"
    assert len(stub.calls) == 1
    assert captured_fallbacks == [], "queued the job AND sent it in-process — duplicate email"


@pytest.mark.asyncio
async def test_falls_back_in_process_when_no_queue(captured_fallbacks):
    registration_id = str(uuid.uuid4())

    result = await worker_settings.safe_enqueue(None, "send_ticket_email", registration_id)
    await _let_tasks_run()

    assert result == "inline"
    assert captured_fallbacks == [(registration_id, False)]


@pytest.mark.asyncio
async def test_falls_back_in_process_when_enqueue_raises(captured_fallbacks):
    stub = _StubArqRedis(raises=ConnectionError("redis went away mid-request"))
    registration_id = str(uuid.uuid4())

    result = await worker_settings.safe_enqueue(stub, "send_ticket_email", registration_id)
    await _let_tasks_run()

    assert result == "inline"
    assert captured_fallbacks == [(registration_id, False)]


@pytest.mark.asyncio
async def test_force_is_carried_into_the_in_process_fallback(captured_fallbacks):
    """The ops resend action passes force=True; losing it on the fallback path
    would make resend silently do nothing once ticket_sent_at is set."""
    registration_id = str(uuid.uuid4())

    await worker_settings.safe_enqueue(None, "send_ticket_email", registration_id, force=True)
    await _let_tasks_run()

    assert captured_fallbacks == [(registration_id, True)]


@pytest.mark.asyncio
async def test_job_without_a_fallback_is_reported_dropped(captured_fallbacks):
    """Only ticket emails have an in-process path. Import/assignment emails
    genuinely can't run without a worker — say so rather than claim success."""
    result = await worker_settings.safe_enqueue(None, "send_assignment_email", str(uuid.uuid4()))
    await _let_tasks_run()

    assert result == "dropped"
    assert captured_fallbacks == []


# ── issue_ticket idempotency ─────────────────────────────────────────────────

async def _make_registration(db, *, ticket_sent_at=None) -> Registration:
    program = Program(
        id=uuid.uuid4(), code=f"IDEM-{uuid.uuid4().hex[:8]}", name="Idempotency Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Idempotency Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()

    contact = Contact(id=uuid.uuid4(), full_name="Idempotency Student", email="idem@example.com")
    db.add(contact)
    await db.flush()

    registration = Registration(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        ticket_token=uuid.uuid4().hex, registered_via="desk",
        ticket_sent_at=ticket_sent_at,
    )
    db.add(registration)
    await db.flush()
    return registration


@pytest.fixture
def sent_emails(monkeypatch):
    sends: list[str] = []

    async def _fake_send(to, subject, body, **kwargs) -> bool:
        sends.append(to)
        return True

    monkeypatch.setattr(registration_service, "try_send_email", _fake_send)
    return sends


@pytest.mark.asyncio
async def test_issue_ticket_sends_once_then_no_ops(db, sent_emails):
    registration = await _make_registration(db)

    assert await registration_service.issue_ticket(db, registration.id) is True
    assert len(sent_emails) == 1
    assert registration.ticket_sent_at is not None

    # A redelivered job, a duplicate enqueue, or a re-run import batch.
    assert await registration_service.issue_ticket(db, registration.id) is True
    assert len(sent_emails) == 1, "second call re-sent the ticket"


@pytest.mark.asyncio
async def test_issue_ticket_force_resends(db, sent_emails):
    registration = await _make_registration(
        db, ticket_sent_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )

    assert await registration_service.issue_ticket(db, registration.id, force=True) is True

    assert len(sent_emails) == 1, "force=True should bypass the idempotency guard"
    assert registration.ticket_sent_at > datetime(2026, 7, 1, tzinfo=timezone.utc)
