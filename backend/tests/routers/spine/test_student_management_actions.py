"""P3-3 (LMS Phase 2 Stage 3, 2026-08-10) — student management actions:
create account & invite, password reset. Both are new HTTP entry points
onto the same functions sync_registration_lms already uses
(services/lms/ops_integration.py), not new business logic. Redis-free.
"""

import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.spine.contact import Contact
from app.models.user import User


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Ops", email=f"ops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["operations"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_create_lms_account_for_a_contact_with_no_registration(db, client):
    ops = await _ops(db)
    contact = Contact(
        id=uuid.uuid4(), full_name="Direct Onboard", contact_roles=["student"],
        email="direct.onboard@example.com",
    )
    db.add(contact)
    await db.commit()

    resp = await client.post(f"/spine/contacts/{contact.id}/lms-account", headers=_headers(ops))
    assert resp.status_code == 200, resp.text
    assert resp.json()["learning"]["has_account"] is True

    user = (await db.execute(select(User).where(User.contact_id == contact.id))).scalars().first()
    assert user is not None
    assert user.email == "direct.onboard@example.com"
    assert "student" in user.role_values
    assert user.must_change_password is True


@pytest.mark.asyncio
async def test_create_lms_account_is_idempotent(db, client):
    ops = await _ops(db)
    contact = Contact(
        id=uuid.uuid4(), full_name="Twice Onboarded", contact_roles=["student"],
        email="twice@example.com",
    )
    db.add(contact)
    await db.commit()

    first = await client.post(f"/spine/contacts/{contact.id}/lms-account", headers=_headers(ops))
    second = await client.post(f"/spine/contacts/{contact.id}/lms-account", headers=_headers(ops))
    assert first.status_code == 200 and second.status_code == 200

    users = (await db.execute(select(User).where(User.contact_id == contact.id))).scalars().all()
    assert len(users) == 1


@pytest.mark.asyncio
async def test_create_lms_account_400s_without_an_email(db, client):
    ops = await _ops(db)
    contact = Contact(id=uuid.uuid4(), full_name="No Email", contact_roles=["student"])
    db.add(contact)
    await db.commit()

    resp = await client.post(f"/spine/contacts/{contact.id}/lms-account", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_reset_password_404s_with_no_linked_account(db, client):
    ops = await _ops(db)
    contact = Contact(id=uuid.uuid4(), full_name="No Account", contact_roles=["student"])
    db.add(contact)
    await db.commit()

    resp = await client.post(f"/spine/contacts/{contact.id}/lms-account/reset-password", headers=_headers(ops))
    assert resp.status_code == http_status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_reset_password_for_an_existing_account_returns_sent_flag(db, client):
    ops = await _ops(db)
    contact = Contact(
        id=uuid.uuid4(), full_name="Has Account", contact_roles=["student"], email="has.account@example.com",
    )
    db.add(contact)
    await db.flush()
    student = User(
        id=uuid.uuid4(), full_name="Has Account", email="has.account@example.com",
        password_hash="x", roles=["student"], status="active", contact_id=contact.id,
    )
    db.add(student)
    await db.commit()

    resp = await client.post(f"/spine/contacts/{contact.id}/lms-account/reset-password", headers=_headers(ops))
    assert resp.status_code == 200
    assert "sent" in resp.json()  # SMTP isn't configured in tests, so the value itself is env-dependent


@pytest.mark.asyncio
async def test_student_management_actions_require_operations_role(db, client):
    stranger = User(
        id=uuid.uuid4(), full_name="Stranger", email=f"stranger-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x", roles=["instructor"], status="active",
    )
    db.add(stranger)
    contact = Contact(id=uuid.uuid4(), full_name="Someone", contact_roles=["student"], email="s@example.com")
    db.add(contact)
    await db.commit()

    resp = await client.post(f"/spine/contacts/{contact.id}/lms-account", headers=_headers(stranger))
    assert resp.status_code == http_status.HTTP_403_FORBIDDEN
