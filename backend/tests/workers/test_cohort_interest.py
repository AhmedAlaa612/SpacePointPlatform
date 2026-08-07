"""send_cohort_interest_notifications (2026-08-07) — the "we said we'd tell
you" half of the Notify-me / Register-now pair.

The task opens its own `AsyncSessionLocal()` (same shape as
send_import_batch_emails), so the `db` fixture's session — bound to
`join_transaction_mode="create_savepoint"` specifically so nested code's own
begin/commit cycles nest as savepoints instead of fighting the fixture's
outer transaction (see conftest.py) — is substituted in via monkeypatch
rather than opening a second, isolated connection that couldn't see this
test's un-committed setup rows at all.
"""

import uuid

import pytest

from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_interest import CohortInterest
from app.models.sessions.program import Program
from app.models.spine.contact import Contact
from app.workers.tasks import cohort_interest as cohort_interest_task


@pytest.fixture
def use_fixture_db_in_worker(monkeypatch, db):
    class _SessionCM:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(cohort_interest_task, "AsyncSessionLocal", lambda: _SessionCM())
    return db


async def _cohort_with_interest(db, *, notified=False) -> tuple[Cohort, CohortInterest, Contact]:
    program = Program(
        id=uuid.uuid4(), code=f"NOTIFY-{uuid.uuid4().hex[:8]}", name="Notify Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Notify Test Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()
    contact = Contact(id=uuid.uuid4(), full_name="Waiting Student", email="waiting@example.com")
    db.add(contact)
    await db.flush()
    from datetime import datetime, timezone
    interest = CohortInterest(
        id=uuid.uuid4(), contact_id=contact.id, cohort_id=cohort.id,
        notified_at=datetime.now(timezone.utc) if notified else None,
    )
    db.add(interest)
    await db.flush()
    return cohort, interest, contact


@pytest.mark.asyncio
async def test_notifies_each_unnotified_interested_contact_once(db, use_fixture_db_in_worker, monkeypatch):
    cohort, interest, contact = await _cohort_with_interest(db)
    sent: list[tuple[str, str, str]] = []

    async def _fake_send(to_email, name, program_name):
        sent.append((to_email, name, program_name))
        return True

    monkeypatch.setattr(cohort_interest_task, "send_cohort_interest_notification_email", _fake_send)

    result = await cohort_interest_task.send_cohort_interest_notifications(None, str(cohort.id))

    assert result == {"sent": 1, "failed": 0}
    assert sent == [("waiting@example.com", "Waiting Student", "Notify Test Program")]
    await db.refresh(interest)
    assert interest.notified_at is not None


@pytest.mark.asyncio
async def test_already_notified_rows_are_skipped_on_a_rerun(db, use_fixture_db_in_worker, monkeypatch):
    cohort, interest, contact = await _cohort_with_interest(db, notified=True)
    sent: list[str] = []

    async def _fake_send(to_email, name, program_name):
        sent.append(to_email)
        return True

    monkeypatch.setattr(cohort_interest_task, "send_cohort_interest_notification_email", _fake_send)

    result = await cohort_interest_task.send_cohort_interest_notifications(None, str(cohort.id))

    assert result == {"sent": 0, "failed": 0}
    assert sent == []


@pytest.mark.asyncio
async def test_failed_send_leaves_notified_at_null_for_a_future_retry(db, use_fixture_db_in_worker, monkeypatch):
    """Same posture as issue_ticket/ticket_sent_at: a failed send (SMTP down,
    say) must stay retryable, not get silently marked done — otherwise a
    transient outage means that contact is never emailed, ever."""
    cohort, interest, contact = await _cohort_with_interest(db)

    async def _failing_send(to_email, name, program_name):
        return False

    monkeypatch.setattr(cohort_interest_task, "send_cohort_interest_notification_email", _failing_send)

    result = await cohort_interest_task.send_cohort_interest_notifications(None, str(cohort.id))

    assert result == {"sent": 0, "failed": 1}
    await db.refresh(interest)
    assert interest.notified_at is None


@pytest.mark.asyncio
async def test_unknown_cohort_is_a_no_op(db, use_fixture_db_in_worker):
    result = await cohort_interest_task.send_cohort_interest_notifications(None, str(uuid.uuid4()))
    assert result == {"sent": 0, "failed": 0}
