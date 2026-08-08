"""Applying with the new structured city (2026-08-08).

The apply form (intern / ambassador / teacher / facilitator) now offers a
country-gated city picker that posts `city_id`. The endpoint validates it
against `cities` and the admin list resolves the city name. Redis-free —
nothing here enqueues.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.inventory.city import City
from app.models.user import User


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Admin",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["admin"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin_user.id, ['admin'])}"}


@pytest_asyncio.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_apply_submits_with_a_city_and_admin_list_resolves_its_name(db, client, admin_headers):
    city = City(id=uuid.uuid4(), name=f"Apply Dubai {uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.commit()

    email = f"apply-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post("/apply/intern", data={
        "full_name": "Aya Hassan",
        "email": email,
        "password": "secret123",
        "country": "AE",
        "city_id": str(city.id),
    })
    assert resp.status_code == 201, resp.text

    listed = await client.get("/admin/applications", params={"role": "intern"}, headers=admin_headers)
    assert listed.status_code == 200, listed.text
    match = next(a for a in listed.json() if a["email"] == email)
    assert match["country"] == "AE"
    assert match["city"] == city.name


@pytest.mark.asyncio
async def test_apply_rejects_an_unknown_city(db, client):
    resp = await client.post("/apply/ambassador", data={
        "full_name": "Omar Ali",
        "email": f"apply-{uuid.uuid4().hex[:8]}@example.com",
        "password": "secret123",
        "city_id": str(uuid.uuid4()),
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_apply_ignores_a_garbage_city_id(db, client):
    resp = await client.post("/apply/intern", data={
        "full_name": "Omar Ali",
        "email": f"apply-{uuid.uuid4().hex[:8]}@example.com",
        "password": "secret123",
        "city_id": "not-a-uuid",
    })
    assert resp.status_code == 400
