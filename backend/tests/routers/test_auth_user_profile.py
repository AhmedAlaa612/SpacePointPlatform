"""GET /auth/users/{id} and GET /auth/me.

Reported from production (2026-08-29): the profile modal 500'd — bare "user
not found" from the frontend's error fallback — for any account with a
malformed `email` (a bulk-import artifact, e.g. `email='456'`). This is a
second, independent occurrence of the 2026-08-28 admin-list incident: a
*separate* `UserOut` class lives in `app.schemas.auth` (used only by
`app/routers/auth.py`), distinct from `app.schemas.user.UserOut` fixed
then — same re-validate-on-read bug, in a class the first fix never
touched.
"""

import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest.mark.asyncio
async def test_getting_a_users_own_profile_with_a_malformed_email_does_not_500(db, client):
    bad = User(
        id=uuid.uuid4(), full_name="Bulk Import Artifact", email="456",
        password_hash=get_password_hash("x"), roles=["student"], status="active",
    )
    db.add(bad)
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(bad.id, ['student'])}"}

    resp = await client.get("/auth/me", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "456"


@pytest.mark.asyncio
async def test_viewing_another_users_profile_with_a_malformed_email_does_not_500(db, client):
    viewer = User(
        id=uuid.uuid4(), full_name="Viewer", email=f"viewer-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"), roles=["operations"], status="active",
    )
    bad = User(
        id=uuid.uuid4(), full_name="Bulk Import Artifact", email="456",
        password_hash=get_password_hash("x"), roles=["student"], status="active",
    )
    db.add_all([viewer, bad])
    await db.flush()
    headers = {"Authorization": f"Bearer {create_access_token(viewer.id, ['operations'])}"}

    resp = await client.get(f"/auth/users/{bad.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] == "456"
