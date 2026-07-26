"""Tests for services/spine/role_history.py (operator request, 2026-07-24):
"in this date they were lead, in that date they became student, then intern,
then instructor" — a dated timeline of every role a contact has gained or
lost.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.spine.contact import Contact
from app.models.spine.contact_role_event import ContactRoleEvent
from app.models.user import User
from app.services.spine.role_history import record_role_diff


def _new_contact(**overrides) -> Contact:
    defaults = dict(
        id=uuid.uuid4(),
        full_name="Test Contact",
        contact_roles=[],
        secondary_phones=[],
        preferred_language="ar",
        lifecycle_stage="lead",
    )
    defaults.update(overrides)
    return Contact(**defaults)


async def _events_for(db, contact_id):
    rows = (await db.execute(
        select(ContactRoleEvent).where(ContactRoleEvent.contact_id == contact_id)
    )).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_record_role_diff_records_added_and_removed(db):
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    await record_role_diff(db, contact.id, ["applicant"], ["instructor"], source="user_role_edit")

    events = await _events_for(db, contact.id)
    assert len(events) == 2
    by_role = {e.role: e.action for e in events}
    assert by_role == {"applicant": "removed", "instructor": "added"}
    assert all(e.source == "user_role_edit" for e in events)


@pytest.mark.asyncio
async def test_record_role_diff_no_op_when_unchanged(db):
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    await record_role_diff(db, contact.id, ["instructor"], ["instructor"], source="user_role_edit")

    assert await _events_for(db, contact.id) == []


@pytest.mark.asyncio
async def test_record_role_diff_handles_multiple_added_and_removed_at_once(db):
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    await record_role_diff(
        db, contact.id, ["applicant", "leader"], ["instructor", "intern"], source="user_role_edit",
    )

    events = await _events_for(db, contact.id)
    added = {e.role for e in events if e.action == "added"}
    removed = {e.role for e in events if e.action == "removed"}
    assert added == {"instructor", "intern"}
    assert removed == {"applicant", "leader"}


@pytest.mark.asyncio
async def test_record_role_diff_records_changed_by(db):
    contact = _new_contact()
    actor = User(
        id=uuid.uuid4(), full_name="Actor", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["admin"],
    )
    db.add_all([contact, actor])
    await db.flush()

    await record_role_diff(
        db, contact.id, [], ["student"], source="contact_edit", changed_by_user_id=actor.id,
    )

    events = await _events_for(db, contact.id)
    assert len(events) == 1
    assert events[0].changed_by_user_id == actor.id


@pytest.mark.asyncio
async def test_record_role_diff_treats_none_before_as_empty(db):
    contact = _new_contact()
    db.add(contact)
    await db.flush()

    await record_role_diff(db, contact.id, None, ["student"], source="registration")

    events = await _events_for(db, contact.id)
    assert len(events) == 1
    assert events[0].role == "student"
    assert events[0].action == "added"
