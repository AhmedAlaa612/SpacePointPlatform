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


# Student signup became invite-only on 2026-08-13, so every signup payload
# below needs a valid student-pool code. Seeded per-test rather than once for
# the module so `used_count` assertions can't be polluted by other tests.
BATCH_CODE = "TESTBATCH"


@pytest.fixture(autouse=True)
async def _student_batch_code(db):
    existing = (await db.execute(
        select(InvitationCode).where(InvitationCode.code == BATCH_CODE)
    )).scalars().first()
    if existing is None:
        db.add(InvitationCode(
            id=uuid.uuid4(), code=BATCH_CODE, kind="student", label="Test Batch",
            is_active=True, max_uses=10_000, used_count=0,
        ))
        await db.commit()
    return BATCH_CODE



@pytest.mark.asyncio
async def test_signup_creates_user_contact_and_alias(db, client):
    resp = await client.post("/auth/signup", json={
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
        "full_name": "Mariam",
        "email": "mariam@example.com",
        "password": "pass-one",
    })
    assert first.status_code == http_status.HTTP_201_CREATED

    second = await client.post("/auth/signup", json={
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
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
    code = InvitationCode(
        id=uuid.uuid4(), code="STUDENT1", kind="student", is_active=True, max_uses=5, used_count=0,
    )
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
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
        "full_name": "Farah", "email": "farah@example.com", "password": "pass-farah",
        "country": "AE", "city_id": str(city.id),
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
    body = resp.json()["user"]
    assert body["country"] == "AE"
    assert body["city_id"] == str(city.id)
    assert body["city_name"] == city.name

    user = (await db.execute(select(User).where(User.email == "farah@example.com"))).scalars().first()
    assert user.country == "AE"
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
        "invite_code": BATCH_CODE,
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
        "invite_code": BATCH_CODE,
        "full_name": "Layla", "email": "layla@example.com", "password": "pass-layla",
        "country": "EG", "city_other": "Alexandria",
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

# ── invite-code gate + pool split (2026-08-13) ──────────────────────────────

@pytest.mark.asyncio
async def test_signup_without_an_invite_code_is_refused(db, client):
    """The gate itself. Ported from Madar, where registration required a
    valid, active, non-exhausted code."""
    resp = await client.post("/auth/signup", json={
        "full_name": "No Code", "email": "nocode@example.com", "password": "pass-nocode",
    })
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST
    assert "invite code" in resp.json()["detail"].lower()
    assert (await db.execute(
        select(User).where(User.email == "nocode@example.com")
    )).scalars().first() is None


@pytest.mark.asyncio
async def test_a_blank_invite_code_is_refused_too(db, client):
    resp = await client.post("/auth/signup", json={
        "invite_code": "   ",
        "full_name": "Blank Code", "email": "blank@example.com", "password": "pass-blank",
    })
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_an_instructor_pool_code_does_not_open_student_signup(db, client):
    """The whole point of splitting the pool — a code issued for instructor
    applications must not admit a student."""
    db.add(InvitationCode(
        id=uuid.uuid4(), code="INSTRONLY", kind="instructor", is_active=True, max_uses=50, used_count=0,
    ))
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "invite_code": "INSTRONLY",
        "full_name": "Wrong Pool", "email": "wrongpool@example.com", "password": "pass-wrong",
    })
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST
    assert (await db.execute(
        select(User).where(User.email == "wrongpool@example.com")
    )).scalars().first() is None


@pytest.mark.asyncio
async def test_an_inactive_or_exhausted_student_code_is_refused(db, client):
    db.add(InvitationCode(
        id=uuid.uuid4(), code="DISABLED", kind="student", is_active=False, max_uses=50, used_count=0,
    ))
    db.add(InvitationCode(
        id=uuid.uuid4(), code="FULLUP", kind="student", is_active=True, max_uses=2, used_count=2,
    ))
    await db.commit()

    off = await client.post("/auth/signup", json={
        "invite_code": "DISABLED",
        "full_name": "A", "email": "disabled-code@example.com", "password": "pass-a",
    })
    assert off.status_code == http_status.HTTP_400_BAD_REQUEST

    full = await client.post("/auth/signup", json={
        "invite_code": "FULLUP",
        "full_name": "B", "email": "full-code@example.com", "password": "pass-b",
    })
    assert full.status_code == http_status.HTTP_400_BAD_REQUEST
    assert "limit" in full.json()["detail"].lower()


@pytest.mark.asyncio
async def test_the_code_is_stamped_onto_the_student(db, client):
    """Madar's "code stamped onto the user permanently" — this is what makes
    the students-management batch filter possible."""
    resp = await client.post("/auth/signup", json={
        "invite_code": BATCH_CODE.lower(),  # case-insensitive on the way in
        "full_name": "Stamped", "email": "stamped@example.com", "password": "pass-stamp",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(
        select(User).where(User.email == "stamped@example.com")
    )).scalars().first()
    assert user.invitation_code_used == BATCH_CODE, "stored uppercase, regardless of what was typed"


@pytest.mark.asyncio
async def test_an_ambassador_referral_code_still_admits_a_student(db, client):
    """Operator's call (2026-08-13): the gate must not break the referral
    pipeline — an ambassador's personal code is kind-agnostic."""
    db.add(User(
        id=uuid.uuid4(), full_name="Amb", email=f"amb-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="x", roles=["ambassador"], status="active", invite_code="AMBGATE",
    ))
    await db.commit()

    resp = await client.post("/auth/signup", json={
        "invite_code": "ambgate",
        "full_name": "Referred", "email": "referred@example.com", "password": "pass-ref",
    })
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text
