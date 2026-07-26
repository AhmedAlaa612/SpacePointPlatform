"""Tests for the spine merge-review resolution endpoints (V2 R2-4).

Covers: listing pending reviews with both candidates inlined, resolving as
merge (verifying merge_contacts() actually ran — merged_into_id set and data
moved, not just a status flip), resolving as keep_separate, resolving as
link_household (verifying the ContactRelationship exists afterward), and the
admin-only guard on /resolve (operations gets 403; a role with neither gets
403 everywhere).
"""

import uuid

import httpx
import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.enums import UserRole
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.merge_review import MergeReview
from app.models.user import User
from app.routers.spine import router as spine_router

# main.py isn't touched by this change (see PLAN R2-4 — the router just needs
# `app.include_router(spine_router)` added there manually); mount it onto the
# shared `app` singleton here instead, once, so these tests exercise the real
# app/routing stack exactly like every other router's test suite does.
if not getattr(app, "_spine_router_mounted_for_tests", False):
    app.include_router(spine_router)
    app._spine_router_mounted_for_tests = True


@pytest.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def _make_user(db, roles: list[UserRole]) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("password123"),
        roles=roles,
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


def _auth_headers(user: User) -> dict:
    token = create_access_token(user.id, user.role_values)
    return {"Authorization": f"Bearer {token}"}


def _new_contact(**overrides) -> Contact:
    defaults = dict(
        id=uuid.uuid4(),
        full_name="Test Contact",
        contact_roles=["student"],
        secondary_phones=[],
        preferred_language="ar",
        lifecycle_stage="lead",
    )
    defaults.update(overrides)
    return Contact(**defaults)


@pytest.fixture
async def ops_user(db):
    return await _make_user(db, [UserRole.operations])


@pytest.fixture
async def admin_user(db):
    return await _make_user(db, [UserRole.admin])


@pytest.fixture
async def outsider_user(db):
    return await _make_user(db, [UserRole.intern])


async def _make_pending_review(db, *, phone="+971501112233") -> tuple[MergeReview, Contact, Contact]:
    """Two contacts sharing a phone (a phone match — never auto-merged, see
    services/spine/identity.py) plus the pending merge_reviews row a human
    must resolve, mirroring what resolve_or_create_contact would have queued."""
    a = _new_contact(full_name="Candidate A", primary_phone_e164=phone, email="a@example.com")
    b = _new_contact(full_name="Candidate B", primary_phone_e164=phone, contact_roles=["parent_guardian"])
    db.add_all([a, b])
    await db.flush()
    review = MergeReview(
        id=uuid.uuid4(),
        candidate_a=a.id,
        candidate_b=b.id,
        reason="phone_match",
        status="pending",
        detail={"matched_via": "phone"},
    )
    db.add(review)
    await db.flush()
    return review, a, b


# ── list ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_pending_merge_reviews_inlines_both_candidates(db, client, ops_user):
    review, a, b = await _make_pending_review(db)

    resp = await client.get("/spine/merge-reviews", params={"status": "pending"}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    match = next(r for r in rows if r["id"] == str(review.id))
    assert match["reason"] == "phone_match"
    assert match["status"] == "pending"
    candidate_ids = {match["candidate_a"]["id"], match["candidate_b"]["id"]}
    assert candidate_ids == {str(a.id), str(b.id)}
    # Plain fields only — no similarity score or algorithmic hint of any kind.
    assert "similarity" not in match["candidate_a"]
    assert "score" not in match


# ── resolve: merge ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_merge_actually_merges_via_merge_contacts(db, client, admin_user):
    review, a, b = await _make_pending_review(db)

    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "merge", "winner_id": str(a.id)},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "merged"
    assert body["resolved_by"] == str(admin_user.id)
    assert body["resolved_at"] is not None

    await db.refresh(b)
    await db.refresh(a)
    # loser's merged_into_id set...
    assert b.merged_into_id == a.id
    # ...and data actually moved: union of contact_roles (merge_contacts unions
    # array fields), not just the status flip a hand-rolled merge might do.
    assert "parent_guardian" in a.contact_roles
    assert "student" in a.contact_roles

    await db.refresh(review)
    assert review.status == "merged"
    assert review.resolved_by == admin_user.id


@pytest.mark.asyncio
async def test_resolve_merge_winner_must_be_a_candidate(db, client, admin_user):
    review, a, b = await _make_pending_review(db)
    other = _new_contact(full_name="Not a candidate")
    db.add(other)
    await db.flush()

    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "merge", "winner_id": str(other.id)},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_resolve_merge_requires_winner_id(db, client, admin_user):
    review, a, b = await _make_pending_review(db)
    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "merge"},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 422  # pydantic validation, not a 500


@pytest.mark.asyncio
async def test_resolve_already_resolved_review_rejected(db, client, admin_user):
    review, a, b = await _make_pending_review(db)
    first = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "keep_separate"},
        headers=_auth_headers(admin_user),
    )
    assert first.status_code == 200, first.text

    second = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "keep_separate"},
        headers=_auth_headers(admin_user),
    )
    assert second.status_code == 400


# ── resolve: keep_separate ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_keep_separate(db, client, admin_user):
    review, a, b = await _make_pending_review(db)

    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "keep_separate"},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "kept_separate"

    await db.refresh(a)
    await db.refresh(b)
    assert a.merged_into_id is None
    assert b.merged_into_id is None


# ── resolve: link_household ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_link_household_creates_relationship(db, client, admin_user):
    review, a, b = await _make_pending_review(db)

    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "link_household", "relation": "guardian_of"},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "linked_household"

    rel = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == a.id,
            ContactRelationship.related_contact_id == b.id,
            ContactRelationship.relation == "guardian_of",
        )
    )).scalars().first()
    assert rel is not None


@pytest.mark.asyncio
async def test_resolve_link_household_requires_relation(db, client, admin_user):
    review, a, b = await _make_pending_review(db)
    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "link_household"},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_resolve_link_household_no_duplicate_relationship_error(db, client, admin_user):
    review, a, b = await _make_pending_review(db)
    db.add(ContactRelationship(
        id=uuid.uuid4(), contact_id=a.id, related_contact_id=b.id, relation="guardian_of",
    ))
    await db.flush()

    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "link_household", "relation": "guardian_of"},
        headers=_auth_headers(admin_user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "linked_household"

    rows = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == a.id, ContactRelationship.related_contact_id == b.id
        )
    )).scalars().all()
    assert len(rows) == 1  # not duplicated


# ── role guard ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_operations_forbidden_on_resolve(db, client, ops_user):
    review, a, b = await _make_pending_review(db)
    resp = await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "keep_separate"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 403

    await db.refresh(review)
    assert review.status == "pending"  # nothing happened


@pytest.mark.asyncio
async def test_outsider_role_forbidden_everywhere(db, client, outsider_user):
    review, a, b = await _make_pending_review(db)
    assert (await client.get("/spine/merge-reviews", headers=_auth_headers(outsider_user))).status_code == 403
    assert (await client.post(
        f"/spine/merge-reviews/{review.id}/resolve",
        json={"action": "keep_separate"},
        headers=_auth_headers(outsider_user),
    )).status_code == 403


@pytest.mark.asyncio
async def test_admin_can_list_merge_reviews_too(db, client, admin_user):
    """RequireRole always lets admin through, even for the operations-gated list route."""
    await _make_pending_review(db)
    resp = await client.get("/spine/merge-reviews", headers=_auth_headers(admin_user))
    assert resp.status_code == 200
