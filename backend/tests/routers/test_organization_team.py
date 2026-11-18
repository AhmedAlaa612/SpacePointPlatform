"""Organization self-service team management (`/organization/team`).

Regression coverage for the "Add Team Member" blank screen:
- the password is optional in the UI, so the API must accept a missing one
  instead of returning a 422 whose `detail` is a list.
- adding a member emails them a set-password link (best effort).
"""

import uuid
from datetime import datetime, timezone

import pytest
from jose import jwt

from app.core.config import settings
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


async def test_team_member_reset_link_emails_seven_day_link(db, client, sent_emails):
    owner, org = await _seed_org(db)
    member_email = f"sarah-{uuid.uuid4().hex[:8]}@example.com"

    added = await client.post(
        "/organization/team",
        headers=_headers(owner),
        json={"full_name": "Sarah Jenkins", "email": member_email},
    )
    assert added.status_code == 201, added.text
    sent_emails.clear()

    resp = await client.post(
        f"/organization/team/{added.json()['id']}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["user_id"] == added.json()["id"]
    assert body["email_sent"] is True
    assert "/set-password?token=" in body["reset_url"]

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Set your SpacePoint password" in subject
    assert "valid for 7 days" in mail_body

    token = body["reset_url"].split("token=", 1)[1]
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    remaining_days = (payload["exp"] - datetime.now(timezone.utc).timestamp()) / 86400
    assert 6.9 < remaining_days <= 7.0


async def test_team_member_reset_link_rejects_outsider(db, client, sent_emails):
    owner, org = await _seed_org(db)
    outsider = await _make_user(db, roles=["organization"])

    resp = await client.post(
        f"/organization/team/{outsider.id}/reset-link",
        headers=_headers(owner),
    )

    assert resp.status_code == 404, resp.text


async def test_ops_can_invite_member_and_track_join_status(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    member_email = f"coord-{uuid.uuid4().hex[:8]}@example.com"

    created = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Ops Invited Coordinator", "email": member_email},
    )

    assert created.status_code == 201, created.text
    assert created.json()["invite_email_sent"] is True

    assert len(sent_emails) == 1
    to, subject, mail_body = sent_emails[0]
    assert to == member_email
    assert "Test Partner Org" in subject
    assert "valid for 7 days" in mail_body

    detail = await client.get(
        f"/admin/website/organizations/{org.id}/detail", headers=_headers(ops)
    )
    assert detail.status_code == 200, detail.text
    row = next(m for m in detail.json()["team"] if m["email"] == member_email)
    assert row["invite_pending"] is True

    # The emailed link works and flips the row from "invite pending" to joined.
    token = mail_body.split("set-password?token=", 1)[1].split()[0].strip()
    set_password = await client.post(
        "/auth/set-password", json={"token": token, "new_password": "Joined-Pass-123"}
    )
    assert set_password.status_code == 200, set_password.text

    detail = await client.get(
        f"/admin/website/organizations/{org.id}/detail", headers=_headers(ops)
    )
    row = next(m for m in detail.json()["team"] if m["email"] == member_email)
    assert row["invite_pending"] is False


async def test_org_account_cannot_use_admin_invite_endpoint(db, client, sent_emails):
    owner, org = await _seed_org(db)

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(owner),
        json={"full_name": "Nope", "email": f"nope-{uuid.uuid4().hex[:8]}@example.com"},
    )

    assert resp.status_code == 403, resp.text


async def test_invite_attaches_existing_lms_account(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])
    student = await _make_user(db, roles=["student"])
    old_hash = student.password_hash

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Existing Student", "email": student.email},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["existing_account"] is True
    assert body["invite_email_sent"] is True

    await db.refresh(student)
    assert "organization" in student.role_values
    assert student.organization_id == org.id
    # Existing credentials are untouched.
    assert student.password_hash == old_hash
    assert student.must_change_password is False

    assert len(sent_emails) == 1
    _, subject, mail_body = sent_emails[0]
    assert "You've been added to Test Partner Org on SpacePoint" == subject
    assert "/login" in mail_body
    assert "set-password" not in mail_body


async def test_invite_moves_account_from_another_org(db, client, sent_emails):
    owner, org = await _seed_org(db)
    ops = await _make_user(db, roles=["operations"])

    other_org = Organization(
        id=uuid.uuid4(),
        name_latin="Other University",
        org_type="university",
        country="uae",
    )
    db.add(other_org)
    await db.flush()

    student = await _make_user(db, roles=["student"])
    student.organization_id = other_org.id
    await db.flush()

    resp = await client.post(
        f"/admin/website/organizations/{org.id}/members",
        headers=_headers(ops),
        json={"full_name": "Other Uni Student", "email": student.email},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["existing_account"] is True
    await db.refresh(student)
    # Last-in-wins: the new assignment overrides the previous organization.
    assert student.organization_id == org.id
    assert "organization" in student.role_values
    assert len(sent_emails) == 1
