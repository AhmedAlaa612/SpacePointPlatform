"""GET /admin/users.

Reported from production (2026-08-28): a bare 500 the moment the list had any
row with a malformed `email` — `UserOut.model_validate(user)` re-validated
`email` as `EmailStr` on the way *out*, so one bad row (a bulk-import
artifact, `email='456'`) took down the whole list for every admin, not just
that one row. Output schemas reflect what's stored; they don't gatekeep it —
`EmailStr` stays on `UserCreate`/`UserUpdate`, which is where it actually
stops a bad value from being written in the first place.
"""

import uuid

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(), full_name="Admin", email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"), roles=["admin"], status="active",
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
async def test_a_row_with_a_malformed_email_does_not_500_the_whole_list(db, client, admin_headers, admin_user):
    """The exact production shape: one user whose email isn't a real address
    (here written straight to the column, bypassing UserCreate/UserUpdate's
    EmailStr check — exactly how a bulk-import artifact would land) must not
    break the list for every other row alongside it."""
    bad = User(
        id=uuid.uuid4(), full_name="Bulk Import Artifact", email="456",
        password_hash=get_password_hash("x"), roles=["student"], status="active",
    )
    db.add(bad)
    await db.flush()

    resp = await client.get("/admin/users", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    by_id = {row["id"]: row for row in resp.json()}
    assert by_id[str(bad.id)]["email"] == "456"
    assert by_id[str(admin_user.id)]["email"] == admin_user.email
