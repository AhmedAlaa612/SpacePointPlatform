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

from app.models.spine.contact import Contact
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