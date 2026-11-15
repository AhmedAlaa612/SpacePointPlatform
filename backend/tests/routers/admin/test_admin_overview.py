"""Tests for GET /admin/overview and /auth/me missing_profile_fields."""

import json
import uuid

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.services.settings import set_portal_setting


async def _make_user(
    db, *, roles: list[str], phone: str | None = "+971501234567", country: str | None = "AE"
) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"u-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("x"),
        roles=roles,
        status="active",
        phone=phone,
        country=country,
    )
    db.add(user)
    await db.flush()
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


@pytest.mark.asyncio
async def test_admin_overview_requires_admin_role(db, client):
    non_admin = await _make_user(db, roles=["student"])
    await db.flush()

    resp = await client.get("/admin/overview", headers=_headers(non_admin))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_overview_returns_valid_schema(db, client):
    admin = await _make_user(db, roles=["admin"])
    await db.flush()

    resp = await client.get("/admin/overview", headers=_headers(admin))
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert set(data.keys()) == {
        "pending_requests",
        "onboarding",
        "payments",
        "actions",
        "business",
    }
    assert set(data["pending_requests"].keys()) == {"applications", "role_requests", "documents"}
    assert set(data["onboarding"].keys()) == {
        "pending",
        "to_be_reviewed",
        "phase1_in_progress",
        "phase2_in_progress",
        "phase3_in_progress",
        "phase2_or_3_in_progress",
    }
    assert set(data["payments"].keys()) == {"pending", "published", "signed"}
    assert isinstance(data["actions"], list)
    assert data["business"]["total_users"] >= 1


@pytest.mark.asyncio
async def test_auth_me_includes_missing_profile_fields(db, client):
    await set_portal_setting(
        db,
        "apply_field_config_student",
        json.dumps({
            "has_custom_override": True,
            "fields": [
                {"key": "phone", "enabled": True, "required": True},
                {"key": "city", "enabled": True, "required": True},
            ],
            "hidden_question_ids": [],
        }),
    )

    student = await _make_user(db, roles=["student"], phone=None, country="AE")
    admin = await _make_user(db, roles=["admin"], phone=None, country=None)
    await db.flush()

    me_student = await client.get("/auth/me", headers=_headers(student))
    assert me_student.status_code == 200, me_student.text
    missing = me_student.json()["missing_profile_fields"]
    assert isinstance(missing, list)
    assert "phone" in missing
    assert "city" in missing

    me_admin = await client.get("/auth/me", headers=_headers(admin))
    assert me_admin.status_code == 200, me_admin.text
    assert me_admin.json()["missing_profile_fields"] == []
