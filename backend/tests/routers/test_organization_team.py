"""Organization self-service team management (`/organization/team`).

Regression coverage for the "Add Team Member" blank screen:
- the password is optional in the UI, so the API must accept a missing one
  instead of returning a 422 whose `detail` is a list.
- adding a member emails them a set-password link (best effort).
"""

import uuid

import pytest

from app.core.security import create_access_token, verify_password
from app.models.spine.organization import Organization
from app.models.user import User


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.fixture
def sent_emails(monkeypatch):
    """Capture outbound mail instead of reaching SMTP."""
    outbox: list[tuple[str, str, str]] = []

    async def fake_send_email(to, subject, body, **kwargs):
        outbox.append((to, subject, body))

    monkeypatch.setattr("app.services.email.send_email", fake_send_email)
    return outbox


async def _make_user(db, *, roles: list[str], email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Org Owner",
        email=email or f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _seed_org(db) -> tuple[User, Organization]:
    owner = await _make_user(db, roles=["organization"])
    org = Organization(
        id=uuid.uuid4(),
        name_latin="Test Partner Org",
        org_type="university",
        country="uae",
        owner_user_id=owner.id,
    )
    db.add(org)
    await db.flush()
    owner.organization_id = org.id
    await db.flush()
    return owner, org


async def test_add_team_member_without_password(db, client, sent_emails):
    owner, org = await _seed_org(db)
    member_email = f"sarah-{uuid.uuid4().hex[:8]}@example.com"

    resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sarah Jenkins", "email": member_email},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["full_name"] == "Sarah Jenkins"
    assert body["is_owner"] is False
    assert body["invite_email_sent"] is True

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Test Partner Org" in subject
    assert "/set-password?token=" in mail_body


async def test_add_team_member_with_password(db, client, sent_emails):
    owner, org = await _seed_org(db)

    resp = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={
            "full_name": "Sarah Jenkins",
            "email": f"sarah-{uuid.uuid4().hex[:8]}@example.com",
            "password": "Initial-Pass-123",
        },
    )

    assert resp.status_code == 201, resp.text
    created = await db.get(User, uuid.UUID(resp.json()["id"]))
    assert verify_password("Initial-Pass-123", created.password_hash)
    assert created.organization_id == org.id


async def test_team_member_reset_link(db, client, sent_emails):
    owner, org = await _seed_org(db)

    added = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sarah Jenkins", "email": f"sarah-{uuid.uuid4().hex[:8]}@example.com"},
    )
    assert added.status_code == 201, added.text

    resp = await client.post(
        f"/organization/team/{added.json()['id']}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == added.json()["id"]
    assert "/set-password?token=" in body["reset_url"]


async def test_team_member_reset_link_rejects_outsider(db, client, sent_emails):
    owner, org = await _seed_org(db)
    outsider = await _make_user(db, roles=["organization"])

    resp = await client.post(
        f"/organization/team/{outsider.id}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 404, resp.text
