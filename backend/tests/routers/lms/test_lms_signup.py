"""LM1-4 student signup tests — /auth/signup.

Pinning the plan's exact guarantees: signup creates a `student` user *and* a
linked contact with an identity alias (a public-form registrant who never made
an account gets linked, not duplicated); a duplicate email is a 409 with a
friendly message, never a raw IntegrityError; and the account then works
through the existing /auth/login unchanged. Redis-free.
"""

import hashlib
import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.models.instructors.invitation_code import InvitationCode
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.identity_alias import IdentityAlias
from app.models.user import User


@pytest.mark.asyncio
async def test_signup_creates_user_contact_and_alias(db, client):
    resp = await client.post("/auth/signup", json={
        "full_name": "Noor Al Ali",
        "email": "Noor.AlAli@Example.com",  # mixed case on purpose
        "phone": "+971 50 123 4567",
        "password": "s3cret-pass",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["access_token"] and body["token_type"] == "bearer"
    assert body["user"]["roles"] == ["student"]

    user = (await db.execute(
        select(User).where(User.email == "noor.alali@example.com")
    )).scalars().first()
    assert user is not None
    assert user.status == "active"
    assert user.contact_id is not None

    contact = await db.get(Contact, user.contact_id)
    assert contact is not None
    assert contact.full_name == "Noor Al Ali"
    assert "student" in contact.contact_roles

    alias = (await db.execute(
        select(IdentityAlias).where(
            IdentityAlias.contact_id == contact.id, IdentityAlias.alias_type == "email"
        )
    )).scalars().first()
    assert alias is not None, "the email alias is what makes the next signup link"


@pytest.mark.asyncio
async def test_signup_links_to_an_existing_contact_by_email(db, client):
    """A person who registered through the public workshop form (contact +
    alias, no account) must get *linked*, not duplicated — the whole point of
    identity evaluate before user creation."""
    contact = Contact(
        id=uuid.uuid4(), full_name="Rashid", contact_roles=["student"],
        email="rashid@example.com",
    )
    db.add(contact)
    db.add(IdentityAlias(
        id=uuid.uuid4(), contact_id=contact.id, alias_type="email",
        # the same sha256 of the normalized value identity.py stores.
        alias_value_hash=hashlib.sha256(b"rashid@example.com").hexdigest(),
        alias_value_plain="rashid@example.com",
        matched_by="deterministic_exact",
    ))
    await db.flush()
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "full_name": "Rashid",
        "email": "rashid@example.com",
        "password": "another-pass",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(
        select(User).where(User.email == "rashid@example.com")
    )).scalars().first()
    assert user is not None
    assert user.contact_id == contact.id

    contacts = (await db.execute(
        select(Contact).where(Contact.email == "rashid@example.com")
    )).scalars().all()
    assert len(contacts) == 1, "no duplicate contact was created"


@pytest.mark.asyncio
async def test_duplicate_email_is_a_friendly_409(db, client):
    first = await client.post("/auth/signup", json={
        "full_name": "Mariam",
        "email": "mariam@example.com",
        "password": "pass-one",
    })
    assert first.status_code == http_status.HTTP_201_CREATED

    second = await client.post("/auth/signup", json={
        "full_name": "Mariam Two",
        "email": "MARIAM@example.com",  # case-insensitive duplicate
        "password": "pass-two",
    })
    assert second.status_code == http_status.HTTP_409_CONFLICT
    assert "log in" in second.json()["detail"].lower()

    users = (await db.execute(select(User).where(User.email == "mariam@example.com"))).scalars().all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_signed_up_student_can_log_in(db, client):
    await client.post("/auth/signup", json={
        "full_name": "Hamdan",
        "email": "hamdan@example.com",
        "phone": "+971501111111",
        "password": "the-real-password",
    })

    resp = await client.post("/auth/login", json={
        "email": "hamdan@example.com",
        "password": "the-real-password",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["user"]["roles"] == ["student"]

    wrong = await client.post("/auth/login", json={
        "email": "hamdan@example.com",
        "password": "nope",
    })
    assert wrong.status_code == http_status.HTTP_401_UNAUTHORIZED


# ── 2026-08-08: date_of_birth, invite_code, parent/guardian ─────────────────

@pytest.mark.asyncio
async def test_signup_stores_date_of_birth_on_contact_and_exposes_it_via_me(db, client):
    resp = await client.post("/auth/signup", json={
        "full_name": "Dana", "email": "dana@example.com", "password": "pass-dana",
        "date_of_birth": "2012-03-14",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    assert resp.json()["user"]["date_of_birth"] == "2012-03-14"

    user = (await db.execute(select(User).where(User.email == "dana@example.com"))).scalars().first()
    contact = await db.get(Contact, user.contact_id)
    assert str(contact.date_of_birth) == "2012-03-14"

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert me.json()["date_of_birth"] == "2012-03-14"


@pytest.mark.asyncio
async def test_signup_with_valid_admin_invite_code_increments_usage(db, client):
    code = InvitationCode(id=uuid.uuid4(), code="STUDENT1", is_active=True, max_uses=5, used_count=0)
    db.add(code)
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "full_name": "Iman", "email": "iman@example.com", "password": "pass-iman",
        "invite_code": "student1",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == "iman@example.com"))).scalars().first()
    assert user.invitation_code_used == "STUDENT1"

    await db.refresh(code)
    assert code.used_count == 1


@pytest.mark.asyncio
async def test_signup_with_ambassador_referral_code_sets_invited_by(db, client):
    ambassador = User(
        id=uuid.uuid4(), full_name="Amb Referrer", email="ambref@example.com",
        password_hash="x", roles=["ambassador"], status="active", invite_code="REFER123",
    )
    db.add(ambassador)
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "full_name": "Zaid", "email": "zaid@example.com", "password": "pass-zaid",
        "invite_code": "refer123",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == "zaid@example.com"))).scalars().first()
    assert user.invited_by_id == ambassador.id


@pytest.mark.asyncio
async def test_signup_with_invalid_invite_code_is_400_and_creates_no_user(db, client):
    resp = await client.post("/auth/signup", json={
        "full_name": "Noone", "email": "noone@example.com", "password": "pass-noone",
        "invite_code": "TOTALLY-FAKE",
    })
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST

    user = (await db.execute(select(User).where(User.email == "noone@example.com"))).scalars().first()
    assert user is None


@pytest.mark.asyncio
async def test_signup_with_parent_info_creates_guardian_relationship(db, client):
    resp = await client.post("/auth/signup", json={
        "full_name": "Layla", "email": "layla@example.com", "password": "pass-layla",
        "parent_name": "Fatima", "parent_phone": "+971501234567", "parent_email": "fatima@example.com",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    student_user = (await db.execute(select(User).where(User.email == "layla@example.com"))).scalars().first()
    student_contact_id = student_user.contact_id

    guardian = (await db.execute(
        select(Contact).where(Contact.email == "fatima@example.com")
    )).scalars().first()
    assert guardian is not None
    assert "parent_guardian" in guardian.contact_roles

    relationship = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian.id,
            ContactRelationship.related_contact_id == student_contact_id,
            ContactRelationship.relation == "guardian_of",
        )
    )).scalars().first()
    assert relationship is not None


@pytest.mark.asyncio
async def test_signup_with_only_parent_name_does_not_create_guardian(db, client):
    """Mirrors PublicRegistrationRequest's rule exactly — both name and phone
    are required before a guardian contact/relationship is created."""
    resp = await client.post("/auth/signup", json={
        "full_name": "Omar", "email": "omar@example.com", "password": "pass-omar",
        "parent_name": "Someone",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    guardian = (await db.execute(
        select(Contact).where(Contact.contact_roles.any("parent_guardian"))
    )).scalars().first()
    assert guardian is None


# ── 2026-08-08: country + city_id (students, same `cities` table instructors use) ──

@pytest.mark.asyncio
async def test_signup_with_country_and_city_id_persists_and_exposes_via_me(db, client):
    from app.models.inventory.city import City

    city = City(id=uuid.uuid4(), name=f"City-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "full_name": "Farah", "email": "farah@example.com", "password": "pass-farah",
        "country": "United Arab Emirates", "city_id": str(city.id),
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    body = resp.json()["user"]
    assert body["country"] == "United Arab Emirates"
    assert body["city_id"] == str(city.id)
    assert body["city_name"] == city.name

    user = (await db.execute(select(User).where(User.email == "farah@example.com"))).scalars().first()
    assert user.country == "United Arab Emirates"
    assert user.city_id == city.id

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {resp.json()['access_token']}"})
    assert me.json()["city_name"] == city.name


@pytest.mark.asyncio
async def test_update_me_sets_city_id(db, client):
    from app.models.inventory.city import City

    city = City(id=uuid.uuid4(), name=f"City-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    signup = await client.post("/auth/signup", json={
        "full_name": "Update City Test", "email": "updatecity@example.com", "password": "pass-update",
    })
    token = signup.json()["access_token"]
    assert signup.json()["user"]["city_id"] is None

    resp = await client.patch(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}, json={"city_id": str(city.id)},
    )
    assert resp.status_code == http_status.HTTP_200_OK, resp.text
    assert resp.json()["city_id"] == str(city.id)


@pytest.mark.asyncio
async def test_signup_with_other_city_persists_and_updates(db, client):
    """2026-08-08 — "Other (type it)" free-text city: stored on users.city_other,
    gap-filled onto the contact's free-text city so CRM views show it, editable
    via PATCH /auth/me."""
    resp = await client.post("/auth/signup", json={
        "full_name": "Layla", "email": "layla@example.com", "password": "pass-layla",
        "country": "Egypt", "city_other": "Alexandria",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    assert resp.json()["user"]["city_other"] == "Alexandria"

    user = (await db.execute(select(User).where(User.email == "layla@example.com"))).scalars().first()
    assert user.city_other == "Alexandria"
    assert user.city_id is None
    contact = await db.get(Contact, user.contact_id)
    assert contact.city == "Alexandria"

    token = resp.json()["access_token"]
    updated = await client.patch(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}, json={"city_other": "Cairo"},
    )
    assert updated.status_code == http_status.HTTP_200_OK, updated.text
    assert updated.json()["city_other"] == "Cairo"