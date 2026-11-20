"""Tests for Case Studies Page Header & Partners (admin + public endpoints)."""

import uuid

import pytest
from sqlalchemy import delete, text

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.website_case_studies_header import WebsiteCaseStudiesHeader


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


@pytest.mark.asyncio
async def test_public_header_returns_defaults_when_row_missing(db, client):
    await db.execute(delete(WebsiteCaseStudiesHeader))
    await db.flush()

    resp = await client.get("/public/website/case-studies-header")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["stats"]) == 4
    assert body["stats"][0] == {"value": "1,000+", "label": "Students Trained"}
    assert len(body["partners"]) == 4
    assert body["partners"][0]["name"] == "Higher Colleges of Technology"


@pytest.mark.asyncio
async def test_admin_get_seeds_defaults_even_if_table_dropped(db, client):
    admin = await _make_user(db, ["admin"])
    await db.execute(text("DROP TABLE IF EXISTS website_case_studies_header"))
    await db.flush()

    resp = await client.get("/admin/website/case-studies-header", headers=_headers(admin))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["stats"]) == 4
    assert body["stats"][0] == {"value": "1,000+", "label": "Students Trained"}
    assert len(body["partners"]) == 4
    assert body["partners"][0]["name"] == "Higher Colleges of Technology"


@pytest.mark.asyncio
async def test_admin_put_updates_header_and_public_reflects_it(db, client):
    admin = await _make_user(db, ["admin"])
    await db.execute(delete(WebsiteCaseStudiesHeader))
    await db.flush()

    payload = {
        "stats": [
            {"value": "4000+", "label": "Students Trained"},
            {"value": "20+", "label": "Institutions"},
        ],
        "partners": [
            {
                "name": "UAE Space Agency",
                "logo_url": "/assets/img/Case studies/Logos/UAE Space Agency white.png",
                "website_url": "https://space.gov.ae",
            }
        ],
    }
    put_resp = await client.put(
        "/admin/website/case-studies-header",
        json=payload,
        headers=_headers(admin),
    )
    assert put_resp.status_code == 200, put_resp.text
    put_body = put_resp.json()
    assert put_body["stats"] == payload["stats"]
    assert put_body["partners"] == payload["partners"]

    pub_resp = await client.get("/public/website/case-studies-header")
    assert pub_resp.status_code == 200, pub_resp.text
    pub_body = pub_resp.json()
    assert pub_body["stats"] == payload["stats"]
    assert pub_body["partners"] == payload["partners"]
