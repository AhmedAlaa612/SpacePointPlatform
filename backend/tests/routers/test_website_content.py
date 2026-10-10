"""Step 4 — FAQs, Media Coverage & Monthly Newsletters.

Public GET /public/faqs, /public/media, /public/newsletters are
unauthenticated and hide inactive rows; POST
/public/newsletter/subscribe deduplicates by email. Admin CRUD plus the
leads list require the admin role.
"""

import uuid

import pytest
from sqlalchemy import delete, func, select

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_faq import WebsiteFaq
from app.models.website_media import MediaClipping
from app.models.website_newsletter import Newsletter, WebsiteLead


async def _ensure_tables(db):
    conn = await db.connection()
    for table in (
        WebsiteFaq.__table__,
        MediaClipping.__table__,
        Newsletter.__table__,
        WebsiteLead.__table__,
    ):
        await conn.run_sync(lambda c, t=table: t.create(c, checkfirst=True))


async def _clear(db):
    for model in (WebsiteFaq, MediaClipping, Newsletter, WebsiteLead):
        await db.execute(delete(model))
    await db.flush()


async def _make_user(db, roles):
    user = User(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("pass"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id, user.roles)}"}


# ── FAQs ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_faq_public_and_admin_crud(db, client):
    await _ensure_tables(db)
    await _clear(db)
    admin = await _make_user(db, ["admin"])

    # Public starts empty
    assert (await client.get("/public/faqs")).json() == []

    # Unauthenticated admin access is rejected
    assert (await client.get("/admin/website/faqs")).status_code in (401, 403)
    assert (
        await client.post("/admin/website/faqs", json={"question": "Q?", "answer": "A."})
    ).status_code in (401, 403)

    # Create (category defaults to General)
    resp = await client.post(
        "/admin/website/faqs",
        json={"question": "What is SpacePoint?", "answer": "Space education."},
        headers=_headers(admin),
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["category"] == "General"
    assert created["is_active"] is True

    # Public sees it, ordered
    public = (await client.get("/public/faqs")).json()
    assert [f["question"] for f in public] == ["What is SpacePoint?"]

    # Update
    resp = await client.put(
        f"/admin/website/faqs/{created['id']}",
        json={"category": "Programs", "is_active": False},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["category"] == "Programs"

    # Inactive is hidden from public but listed for admin
    assert (await client.get("/public/faqs")).json() == []
    assert len((await client.get("/admin/website/faqs", headers=_headers(admin))).json()) == 1

    # Unknown id → 404, not 500
    assert (
        await client.put(
            f"/admin/website/faqs/{uuid.uuid4()}", json={"question": "X"}, headers=_headers(admin)
        )
    ).status_code == 404

    # Delete
    assert (
        await client.delete(f"/admin/website/faqs/{created['id']}", headers=_headers(admin))
    ).status_code == 204
    assert (await client.get("/admin/website/faqs", headers=_headers(admin))).json() == []


# ── Media ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_media_public_and_admin_crud_with_arabic(db, client):
    await _ensure_tables(db)
    await _clear(db)
    admin = await _make_user(db, ["admin"])
    student = await _make_user(db, ["student"])

    assert (await client.get("/admin/website/media", headers=_headers(student))).status_code == 403

    for payload in [
        {
            "publisher_name": "Gulf News",
            "article_title": "Satellite kits for schools",
            "article_url": "https://gulfnews.com/x",
            "published_date": "2025-11-15",
            "display_order": 1,
        },
        {
            "publisher_name": "WAM",
            "article_title": "National space talent initiative",
            "article_url": "https://wam.ae/x",
            "published_date": "2025-10-20",
            "is_arabic": True,
            "snippet": "Arabic snippet",
            "display_order": 2,
        },
    ]:
        resp = await client.post("/admin/website/media", json=payload, headers=_headers(admin))
        assert resp.status_code == 201, resp.text

    public = (await client.get("/public/media")).json()
    assert len(public) == 2
    arabic = next(c for c in public if c["publisher_name"] == "WAM")
    assert arabic["is_arabic"] is True
    assert arabic["snippet"] == "Arabic snippet"
    assert [c["display_order"] for c in public] == [1, 2]

    # Delete one; public reflects immediately
    victim = next(c for c in public if c["publisher_name"] == "Gulf News")
    assert (
        await client.delete(f"/admin/website/media/{victim['id']}", headers=_headers(admin))
    ).status_code == 204
    assert len((await client.get("/public/media")).json()) == 1


# ── Newsletters & leads ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_newsletter_crud_and_subscribe_dedup(db, client):
    await _ensure_tables(db)
    await _clear(db)
    admin = await _make_user(db, ["admin"])

    assert (await client.get("/public/newsletters")).json() == []
    assert (await client.get("/admin/website/newsletters")).status_code in (401, 403)

    resp = await client.post(
        "/admin/website/newsletters",
        json={"title": "October Issue", "issue_date": "2025-10-01", "file_url": "/docs/oct.pdf"},
        headers=_headers(admin),
    )
    assert resp.status_code == 201, resp.text
    issue = resp.json()

    public = (await client.get("/public/newsletters")).json()
    assert [n["title"] for n in public] == ["October Issue"]

    # Subscribe (no auth) — twice with different casing deduplicates
    first = await client.post("/public/newsletter/subscribe", json={"email": "Reader@Example.com"})
    assert first.status_code == 200, first.text
    second = await client.post("/public/newsletter/subscribe", json={"email": "reader@example.com"})
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]

    count = (
        await db.execute(
            select(func.count())
            .select_from(WebsiteLead)
            .where(WebsiteLead.lead_type == "newsletter")
        )
    ).scalar()
    assert count == 1

    # Invalid email is rejected
    assert (await client.post("/public/newsletter/subscribe", json={"email": "not-an-email"})).status_code == 422

    # Leads list (admin) with type filter
    leads = (
        await client.get("/admin/website/leads", params={"type": "newsletter"}, headers=_headers(admin))
    ).json()
    assert [lead["email"] for lead in leads] == ["reader@example.com"]
    assert (
        await client.get("/admin/website/leads", params={"type": "workshop"}, headers=_headers(admin))
    ).json() == []
    assert (await client.get("/admin/website/leads")).status_code in (401, 403)

    # Delete the issue; public archive reflects immediately
    assert (
        await client.delete(f"/admin/website/newsletters/{issue['id']}", headers=_headers(admin))
    ).status_code == 204
    assert (await client.get("/public/newsletters")).json() == []
