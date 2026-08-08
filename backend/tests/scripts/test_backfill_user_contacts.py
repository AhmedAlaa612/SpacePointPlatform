"""Mandatory tests for V2 R2-6 (see MASTER_EXECUTION_PLAN.md P2-4)."""

import uuid

import pytest
from sqlalchemy import select

from app.models.spine.contact import Contact
from app.models.spine.identity_alias import IdentityAlias
from app.models.user import User
from scripts.backfill_user_contacts import _contact_roles_for, backfill_user_contacts


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


# ── _contact_roles_for ──────────────────────────────────────────────────────

def test_role_mapping_instructor():
    assert _contact_roles_for(_new_user(roles=["instructor"])) == ["instructor"]


def test_role_mapping_admin_maps_to_other():
    assert _contact_roles_for(_new_user(roles=["admin"])) == ["other"]


def test_role_mapping_no_roles_maps_to_other():
    assert _contact_roles_for(_new_user(roles=[])) == ["other"]


def test_role_mapping_multiple_roles_dedupes_and_sorts():
    assert _contact_roles_for(_new_user(roles=["instructor", "facilitator", "ambassador"])) == [
        "ambassador", "instructor", "other",
    ]


# ── backfill_user_contacts ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_backfill_creates_contact_and_links_user(db):
    user = _new_user(
        full_name="Jane Instructor", email="jane.instructor@example.com",
        phone="0501234567", country="AE", roles=["instructor"],
    )
    db.add(user)
    await db.flush()

    linked = await backfill_user_contacts(db)
    assert linked == 1

    await db.refresh(user)
    assert user.contact_id is not None

    contact = await db.get(Contact, user.contact_id)
    assert contact.full_name == "Jane Instructor"
    assert contact.contact_roles == ["instructor"]
    assert contact.primary_phone_e164 == "+971501234567"
    assert contact.email == "jane.instructor@example.com"
    # `user.country` is an ISO code (2026-08-08 country-code migration);
    # `Contact.country` stays free text on its own, older convention, so
    # find_or_create_contact resolves it to a display name on the way in.
    assert contact.country == "United Arab Emirates"
    assert contact.owner_user_id is None


@pytest.mark.asyncio
async def test_backfill_writes_identity_aliases(db):
    user = _new_user(email="alias.check@example.com", phone="0509876543", roles=["teacher"])
    db.add(user)
    await db.flush()

    await backfill_user_contacts(db)
    await db.refresh(user)

    result = await db.execute(select(IdentityAlias).where(IdentityAlias.contact_id == user.contact_id))
    aliases = result.scalars().all()
    alias_types = {a.alias_type for a in aliases}
    assert alias_types == {"email", "phone"}


@pytest.mark.asyncio
async def test_backfill_skips_users_that_already_have_a_contact_id(db):
    existing_contact = Contact(
        id=uuid.uuid4(), full_name="Pre-existing Contact", contact_roles=["other"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(existing_contact)
    await db.flush()

    user = _new_user(email="already.linked@example.com", contact_id=existing_contact.id)
    db.add(user)
    await db.flush()

    linked = await backfill_user_contacts(db)
    assert linked == 0

    await db.refresh(user)
    assert user.contact_id == existing_contact.id  # untouched, not repointed to a new contact


@pytest.mark.asyncio
async def test_backfill_is_idempotent_on_immediate_rerun(db):
    user = _new_user(email="rerun.check@example.com", roles=["ambassador"])
    db.add(user)
    await db.flush()

    first_run = await backfill_user_contacts(db)
    assert first_run == 1
    await db.refresh(user)
    first_contact_id = user.contact_id

    second_run = await backfill_user_contacts(db)
    assert second_run == 0
    await db.refresh(user)
    assert user.contact_id == first_contact_id


@pytest.mark.asyncio
async def test_backfill_resyncs_roles_for_already_linked_user_whose_roles_changed(db):
    """A user's roles can change well after their contact was first created
    (e.g. an admin account later gains "instructor") — the contact's
    contact_roles must catch up on the next run, not stay frozen at
    whatever the roles were the day it was first linked."""
    existing_contact = Contact(
        id=uuid.uuid4(), full_name="Grew More Roles", contact_roles=["other"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(existing_contact)
    await db.flush()

    user = _new_user(email="grew.roles@example.com", contact_id=existing_contact.id, roles=["instructor", "teacher"])
    db.add(user)
    await db.flush()

    linked = await backfill_user_contacts(db)
    assert linked == 0  # not a NEW link — this counts only new contacts

    await db.refresh(existing_contact)
    assert existing_contact.contact_roles == ["instructor", "other", "teacher"]


@pytest.mark.asyncio
async def test_backfill_role_resync_never_removes_an_existing_role(db):
    """A contact's roles might include something a human added manually
    (e.g. "alumnus") that has nothing to do with the user's current account
    roles — re-syncing must be additive-only, never drop it."""
    existing_contact = Contact(
        id=uuid.uuid4(), full_name="Manually Tagged", contact_roles=["alumnus"],
        secondary_phones=[], preferred_language="ar", lifecycle_stage="lead",
    )
    db.add(existing_contact)
    await db.flush()

    user = _new_user(email="manually.tagged@example.com", contact_id=existing_contact.id, roles=["teacher"])
    db.add(user)
    await db.flush()

    await backfill_user_contacts(db)

    await db.refresh(existing_contact)
    assert existing_contact.contact_roles == ["alumnus", "teacher"]


@pytest.mark.asyncio
async def test_backfill_handles_user_with_no_phone_or_email_alias_target(db):
    # phone/email columns on User are themselves nullable except email (NOT
    # NULL, unique) — but normalize_phone(None) must not blow up, and a user
    # with an unparseable phone should still get linked, just without a
    # phone alias.
    user = _new_user(email="no.phone@example.com", phone=None, roles=[])
    db.add(user)
    await db.flush()

    linked = await backfill_user_contacts(db)
    assert linked == 1
    await db.refresh(user)

    result = await db.execute(select(IdentityAlias).where(IdentityAlias.contact_id == user.contact_id))
    alias_types = {a.alias_type for a in result.scalars().all()}
    assert alias_types == {"email"}
