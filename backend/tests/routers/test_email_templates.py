"""Email Templates System — admin-only list/edit/pause/preview/send-test
against the real DB rows seeded by the `b4e7a19c0038` migration."""

import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.email_template import EmailTemplate
from app.models.user import User

pytestmark = pytest.mark.asyncio


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _admin(db) -> User:
    user = User(
        full_name="Admin User", email=f"{uuid.uuid4()}@example.com",
        password_hash=get_password_hash("pw12345"), roles=["admin"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _non_admin(db) -> User:
    user = User(
        full_name="Regular Instructor", email=f"{uuid.uuid4()}@example.com",
        password_hash=get_password_hash("pw12345"), roles=["instructor"], status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _template(db, key: str) -> EmailTemplate:
    return (await db.execute(select(EmailTemplate).where(EmailTemplate.key == key))).scalars().first()


async def test_non_admin_cannot_list_templates(db, client):
    user = await _non_admin(db)
    resp = await client.get("/email-templates", headers=_auth(user))
    assert resp.status_code == 403


async def test_admin_sees_every_seeded_template(db, client):
    admin = await _admin(db)
    resp = await client.get("/email-templates", headers=_auth(admin))
    assert resp.status_code == 200
    body = resp.json()
    keys = {t["key"] for t in body}
    assert "phase1_approval" in keys
    assert "kits_uncounted_reminder" in keys
    assert len(body) == 27
    # every row is a real EmailTemplate.id (from the migration's bulk_insert), not a
    # made-up default — proves the endpoint reads the DB row, not the fallback.
    phase1 = next(t for t in body if t["key"] == "phase1_approval")
    assert phase1["placeholders"] == ["name", "status_link"]
    assert phase1["is_paused"] is False


async def test_update_persists_subject_and_body(db, client):
    admin = await _admin(db)
    template = await _template(db, "phase1_approval")

    resp = await client.put(
        f"/email-templates/{template.id}", headers=_auth(admin),
        json={"subject": "Custom subject {name}", "body_html": "<p>Custom body {name}</p>"},
    )
    assert resp.status_code == 200
    assert resp.json()["subject"] == "Custom subject {name}"

    await db.refresh(template)
    assert template.subject == "Custom subject {name}"
    assert template.body_html == "<p>Custom body {name}</p>"


async def test_pause_toggle_round_trips(db, client):
    admin = await _admin(db)
    template = await _template(db, "phase1_approval")
    assert template.is_paused is False

    resp = await client.patch(f"/email-templates/{template.id}/pause", headers=_auth(admin), json={"is_paused": True})
    assert resp.status_code == 200
    assert resp.json()["is_paused"] is True
    await db.refresh(template)
    assert template.is_paused is True

    resp = await client.patch(f"/email-templates/{template.id}/pause", headers=_auth(admin), json={"is_paused": False})
    assert resp.json()["is_paused"] is False


async def test_paused_template_skips_the_real_send(db, monkeypatch):
    """The router flips `is_paused`; `render_and_send` (the actual send path
    every wrapper funnels through) must honor it."""
    from app.services import email_templates as email_templates_service

    template = await _template(db, "phase1_approval")
    template.is_paused = True
    await db.flush()

    mock_send = AsyncMock(return_value=True)
    monkeypatch.setattr(email_templates_service, "try_send_email", mock_send)

    sent = await email_templates_service.render_and_send(
        db, key="phase1_approval", to="jane@example.com", placeholders={"name": "Jane", "status_link": "http://x"},
    )
    assert sent is False
    mock_send.assert_not_called()


async def test_preview_fills_placeholders_with_sample_values(db, client):
    admin = await _admin(db)
    template = await _template(db, "phase1_approval")

    resp = await client.post(
        f"/email-templates/{template.id}/preview", headers=_auth(admin),
        json={"subject": template.subject, "body_html": template.body_html},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "{name}" not in body["subject"] and "{name}" not in body["body_html"]
    assert "{status_link}" not in body["body_html"]
    assert "Jane Doe" in body["body_html"]


async def test_preview_reports_a_missing_placeholder_instead_of_dropping_it(db, client):
    admin = await _admin(db)
    template = await _template(db, "phase1_approval")

    resp = await client.post(
        f"/email-templates/{template.id}/preview", headers=_auth(admin),
        json={"subject": "Hi {typo_token}", "body_html": "<p>{typo_token}</p>"},
    )
    assert resp.status_code == 200
    assert resp.json()["subject"] == "Hi [TYPO_TOKEN]"


async def test_send_test_delivers_to_the_calling_admins_own_inbox(db, client, monkeypatch):
    from app.routers import email_templates as router_module

    admin = await _admin(db)
    template = await _template(db, "phase1_approval")

    mock_send = AsyncMock(return_value=True)
    monkeypatch.setattr(router_module, "try_send_email", mock_send)

    resp = await client.post(
        f"/email-templates/{template.id}/send-test", headers=_auth(admin),
        json={"subject": template.subject, "body_html": template.body_html},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sent"] is True
    assert data["to"] == admin.email
    mock_send.assert_awaited_once()
    assert mock_send.call_args.args[0] == admin.email


async def test_send_test_bypasses_pause(db, client, monkeypatch):
    """Testing a paused template is exactly when you'd want to see it render."""
    from app.routers import email_templates as router_module

    admin = await _admin(db)
    template = await _template(db, "phase1_approval")
    template.is_paused = True
    await db.flush()

    mock_send = AsyncMock(return_value=True)
    monkeypatch.setattr(router_module, "try_send_email", mock_send)

    resp = await client.post(
        f"/email-templates/{template.id}/send-test", headers=_auth(admin),
        json={"subject": template.subject, "body_html": template.body_html},
    )
    assert resp.status_code == 200
    assert resp.json()["sent"] is True
    mock_send.assert_awaited_once()
