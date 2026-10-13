"""Step 5 — Articles, Blog & Editorial Review Queue.

Full lifecycle: contributor creates a draft -> submits -> admin requests
changes -> contributor updates -> admin approves -> the article appears on
GET /public/articles/{slug} -> admin unpublishes -> 404 on public.
"""

import uuid

import pytest
from sqlalchemy import delete

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_article import WebsiteArticle

DRAFT = {
    "title": "My First Flight Computer",
    "summary": "Notes from building an OBC prototype.",
    "content_markdown": "## Intro\n\nHello **world**.\n\n<script>alert('xss')</script>",
    "category": "TECHNOLOGY",
}


async def _ensure_table(db):
    conn = await db.connection()
    await conn.run_sync(lambda c: WebsiteArticle.__table__.create(c, checkfirst=True))


async def _clear(db):
    await db.execute(delete(WebsiteArticle))
    await db.flush()


async def _make_user(db, roles):
    user = User(
        id=uuid.uuid4(),
        full_name="Test Contributor",
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


@pytest.mark.asyncio
async def test_article_full_lifecycle(db, client):
    await _ensure_table(db)
    await _clear(db)
    author = await _make_user(db, ["intern"])
    admin = await _make_user(db, ["admin"])

    # Unauthenticated contributor access is rejected
    assert (await client.get("/articles/me")).status_code in (401, 403)

    # 1. Contributor creates a draft — slug auto-generated, HTML sanitized
    resp = await client.post("/articles", json=DRAFT, headers=_headers(author))
    assert resp.status_code == 201, resp.text
    draft = resp.json()
    assert draft["status"] == "draft"
    assert draft["slug"] == "my-first-flight-computer"
    assert draft["author_display_name"] == "Test Contributor"
    assert "<strong>world</strong>" in draft["content_html"]
    assert "<script>" not in draft["content_html"]
    article_id = draft["id"]

    # Draft is invisible on public
    assert (await client.get(f"/public/articles/{draft['slug']}")).status_code == 404
    assert (await client.get("/public/articles")).json() == []

    # 2. Contributor submits
    resp = await client.post(f"/articles/{article_id}/submit", headers=_headers(author))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "submitted"

    # Submitted drafts are locked for the author...
    resp = await client.put(
        f"/articles/{article_id}", json={"title": "Sneaky Edit"}, headers=_headers(author)
    )
    assert resp.status_code == 400
    # ...but still invisible publicly
    assert (await client.get(f"/public/articles/{draft['slug']}")).status_code == 404

    # 3. Admin requests changes (feedback required)
    resp = await client.post(
        f"/admin/website/articles/{article_id}/review",
        json={"action": "request_changes"},
        headers=_headers(admin),
    )
    assert resp.status_code == 400
    resp = await client.post(
        f"/admin/website/articles/{article_id}/review",
        json={"action": "request_changes", "feedback": "Add a wiring diagram section."},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "changes_requested"
    assert resp.json()["reviewer_feedback"] == "Add a wiring diagram section."

    # 4. Contributor sees feedback and revises
    mine = (await client.get("/articles/me", headers=_headers(author))).json()
    assert mine[0]["reviewer_feedback"] == "Add a wiring diagram section."
    resp = await client.put(
        f"/articles/{article_id}",
        json={"content_markdown": "## Intro\n\nHello **world**.\n\n## Wiring\n\nDiagram added."},
        headers=_headers(author),
    )
    assert resp.status_code == 200, resp.text
    assert "Wiring" in resp.json()["content_html"]
    resp = await client.post(f"/articles/{article_id}/submit", headers=_headers(author))
    assert resp.json()["status"] == "submitted"

    # 5. Admin approves → live on public
    resp = await client.post(
        f"/admin/website/articles/{article_id}/review",
        json={"action": "approve"},
        headers=_headers(admin),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "published"

    public = await client.get(f"/public/articles/{draft['slug']}")
    assert public.status_code == 200, public.text
    assert public.json()["title"] == "My First Flight Computer"
    listing = (await client.get("/public/articles")).json()
    assert [a["slug"] for a in listing] == [draft["slug"]]

    # 6. Admin unpublishes → 404 on public again
    resp = await client.post(
        f"/admin/website/articles/{article_id}/unpublish", headers=_headers(admin)
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "draft"
    assert (await client.get(f"/public/articles/{draft['slug']}")).status_code == 404
    assert (await client.get("/public/articles")).json() == []


@pytest.mark.asyncio
async def test_article_guards(db, client):
    await _ensure_table(db)
    await _clear(db)
    author = await _make_user(db, ["intern"])
    other = await _make_user(db, ["instructor"])
    admin = await _make_user(db, ["admin"])

    # Another contributor cannot touch someone else's draft
    resp = await client.post("/articles", json=DRAFT, headers=_headers(author))
    article_id = resp.json()["id"]
    assert (
        await client.put(f"/articles/{article_id}", json={"title": "Hijack"}, headers=_headers(other))
    ).status_code == 403
    assert (
        await client.post(f"/articles/{article_id}/submit", headers=_headers(other))
    ).status_code == 403

    # Admin routes reject non-admins
    assert (
        await client.get("/admin/website/articles", headers=_headers(other))
    ).status_code == 403
    assert (
        await client.post(
            f"/admin/website/articles/{article_id}/review",
            json={"action": "approve"},
            headers=_headers(other),
        )
    ).status_code == 403

    # Slug uniqueness across authors
    resp = await client.post("/articles", json=DRAFT, headers=_headers(other))
    assert resp.status_code == 201, resp.text
    assert resp.json()["slug"] == "my-first-flight-computer-2"

    # Admin queue lists everything; delete removes it
    queue = (await client.get("/admin/website/articles", headers=_headers(admin))).json()
    assert len(queue) == 2

    # Operations role also has full access to the editorial queue and review
    ops = await _make_user(db, ["operations"])
    ops_queue = (await client.get("/admin/website/articles", headers=_headers(ops))).json()
    assert len(ops_queue) == 2
    assert (
        await client.post(
            f"/admin/website/articles/{article_id}/review",
            json={"action": "approve"},
            headers=_headers(ops),
        )
    ).status_code == 200

    assert (
        await client.delete(f"/admin/website/articles/{article_id}", headers=_headers(admin))
    ).status_code == 204
    assert (
        await client.delete(f"/admin/website/articles/{uuid.uuid4()}", headers=_headers(admin))
    ).status_code == 404
