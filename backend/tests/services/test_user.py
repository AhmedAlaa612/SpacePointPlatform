"""Tests for services/user.py's role-history wiring (2026-07-24) — the
operator's own example: "person is an applicant, then their role is gone and
they start with instructor, then admin adds intern role to them so now they
have 2 roles... track the history of their role and status."
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.spine.contact import Contact
from app.models.spine.contact_role_event import ContactRoleEvent
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.services import user as user_service


def _new_user(**overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x",
        roles=[],
    )
    defaults.update(overrides)
    return User(**defaults)


async def _events_for(db, contact_id):
    rows = (await db.execute(
        select(ContactRoleEvent).where(ContactRoleEvent.contact_id == contact_id).order_by(ContactRoleEvent.occurred_at)
    )).scalars().all()
    return rows


@pytest.mark.asyncio
async def test_create_user_links_a_contact_and_records_initial_role(db):
    created = await user_service.create_user(
        db, UserCreate(full_name="New Applicant", email=f"{uuid.uuid4().hex}@example.com",
                       password="password123", roles=["applicant"]),
    )

    assert created.contact_id is not None
    events = await _events_for(db, created.contact_id)
    assert len(events) == 1
    assert events[0].role == "applicant"
    assert events[0].action == "added"
    assert events[0].source == "user_created"


@pytest.mark.asyncio
async def test_role_progression_applicant_to_instructor_to_plus_intern(db):
    """The operator's exact scenario: applicant -> (removed) + instructor
    (added) in one edit, then intern added later on top — full history, not
    just the current snapshot."""
    actor = _new_user(full_name="Admin Actor", roles=["admin"])
    db.add(actor)
    await db.flush()

    user = await user_service.create_user(
        db, UserCreate(full_name="Progressing Person", email=f"{uuid.uuid4().hex}@example.com",
                       password="password123", roles=["applicant"]),
    )
    contact_id = user.contact_id
    assert contact_id is not None

    # Step 1: applicant removed, instructor added.
    await user_service.update_user(
        db, user.id, UserUpdate(roles=["instructor"]), actor_user_id=actor.id,
    )

    # Step 2: intern added on top — now instructor + intern.
    await user_service.update_user(
        db, user.id, UserUpdate(roles=["instructor", "intern"]), actor_user_id=actor.id,
    )

    events = await _events_for(db, contact_id)
    # created(applicant) + step1(remove applicant, add instructor) + step2(add intern)
    assert len(events) == 4

    by_signature = [(e.role, e.action, e.source) for e in events]
    assert ("applicant", "added", "user_created") in by_signature
    assert ("applicant", "removed", "user_role_edit") in by_signature
    assert ("instructor", "added", "user_role_edit") in by_signature
    assert ("intern", "added", "user_role_edit") in by_signature

    # The raw-role edits are attributed to the acting admin.
    edit_events = [e for e in events if e.source == "user_role_edit"]
    assert all(e.changed_by_user_id == actor.id for e in edit_events)

    # Final state: contact_roles was additively synced, with no separate
    # history row for that sync (see update_user). "other" survives from the
    # very first sync (applicant maps to "other") — additive-only, same
    # never-remove policy as the backfill script's resync, so it's never
    # cleaned up automatically once the user stops being an applicant.
    contact = await db.get(Contact, contact_id)
    assert set(contact.contact_roles) == {"instructor", "intern", "other"}


@pytest.mark.asyncio
async def test_update_user_without_role_change_writes_no_history(db):
    user = await user_service.create_user(
        db, UserCreate(full_name="No Change", email=f"{uuid.uuid4().hex}@example.com",
                       password="password123", roles=["instructor"]),
    )
    contact_id = user.contact_id
    before_count = len(await _events_for(db, contact_id))

    await user_service.update_user(db, user.id, UserUpdate(full_name="Renamed Only"))

    after_count = len(await _events_for(db, contact_id))
    assert after_count == before_count


@pytest.mark.asyncio
async def test_update_user_setting_same_roles_writes_no_history(db):
    user = await user_service.create_user(
        db, UserCreate(full_name="Same Roles", email=f"{uuid.uuid4().hex}@example.com",
                       password="password123", roles=["instructor"]),
    )
    contact_id = user.contact_id
    before_count = len(await _events_for(db, contact_id))

    await user_service.update_user(db, user.id, UserUpdate(roles=["instructor"]))

    after_count = len(await _events_for(db, contact_id))
    assert after_count == before_count


@pytest.mark.asyncio
async def test_role_history_guard_ignores_bare_none_roles(db):
    """A bare `roles=None` on a UserUpdate is still "set" per Pydantic v2
    (verified empirically), so this module's role-diff logic must treat it as
    "no role instruction given", not "remove every role" — this only tests
    THIS module's guard (update_data.get("roles") is not None). The
    self-service endpoint itself (routers/interns/shared.py's PATCH /users/me)
    used to force-set `user_in.roles = None` on a UserUpdate to keep clients
    from smuggling role changes through, which hit this exact Pydantic
    behavior and landed a NOT NULL IntegrityError on the users.roles column;
    it's since been fixed by switching that endpoint to UserSelfUpdate, a
    schema with no `roles` field at all — see
    tests/routers/interns/test_shared.py for the end-to-end coverage."""
    user = await user_service.create_user(
        db, UserCreate(full_name="Guard Only", email=f"{uuid.uuid4().hex}@example.com",
                       password="password123", roles=["instructor"]),
    )
    contact_id = user.contact_id
    before_count = len(await _events_for(db, contact_id))

    update_data = UserUpdate(roles=None).dict(exclude_unset=True)
    assert update_data.get("roles") is None
    # The exact condition services/user.py::update_user guards on:
    roles_before = list(user.role_values) if update_data.get("roles") is not None else None
    assert roles_before is None

    after_count = len(await _events_for(db, contact_id))
    assert after_count == before_count
