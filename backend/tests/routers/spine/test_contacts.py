"""Tests for the spine contacts admin + organizations endpoints (V2 R2-4).

Covers: search by name/phone/email, role filter, contact detail with
relationships (both directions), creating a relationship (and rejecting a
duplicate cleanly), and the operations-role guard.
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
from app.models.spine.organization import Organization
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


async def _make_user(db, roles: list[UserRole], **overrides) -> User:
    defaults = dict(
        id=uuid.uuid4(),
        full_name="Test User",
        email=f"{uuid.uuid4().hex}@example.com",
        password_hash=get_password_hash("password123"),
        roles=roles,
        status="active",
    )
    defaults.update(overrides)
    user = User(**defaults)
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
    """A role with neither operations nor admin — every spine route must 403 it."""
    return await _make_user(db, [UserRole.intern])


# ── search ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_by_name(db, client, ops_user):
    c1 = _new_contact(full_name="Ahmed Khalil Al Mansoori", email="ahmed.km@example.com")
    c2 = _new_contact(full_name="Sara Othman", email="sara.o@example.com")
    db.add_all([c1, c2])
    await db.flush()

    resp = await client.get("/spine/contacts", params={"q": "Khalil"}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = [item["full_name"] for item in body["items"]]
    assert "Ahmed Khalil Al Mansoori" in names
    assert "Sara Othman" not in names


@pytest.mark.asyncio
async def test_search_by_phone(db, client, ops_user):
    c1 = _new_contact(full_name="Phone Match", primary_phone_e164="+971509998877")
    db.add(c1)
    await db.flush()

    resp = await client.get("/spine/contacts", params={"q": "9998877"}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert str(c1.id) in ids


@pytest.mark.asyncio
async def test_search_by_email(db, client, ops_user):
    c1 = _new_contact(full_name="Email Match", email="unique.email.tag@example.com")
    db.add(c1)
    await db.flush()

    resp = await client.get(
        "/spine/contacts", params={"q": "unique.email.tag"}, headers=_auth_headers(ops_user)
    )
    assert resp.status_code == 200, resp.text
    ids = [item["id"] for item in resp.json()["items"]]
    assert str(c1.id) in ids


@pytest.mark.asyncio
async def test_role_filter(db, client, ops_user):
    tag = uuid.uuid4().hex[:8]
    instructor = _new_contact(full_name=f"Instructor {tag}", contact_roles=["instructor"])
    student = _new_contact(full_name=f"Student {tag}", contact_roles=["student"])
    db.add_all([instructor, student])
    await db.flush()

    resp = await client.get("/spine/contacts", params={"role": "instructor", "q": tag}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(instructor.id) in ids
    assert str(student.id) not in ids


@pytest.mark.asyncio
async def test_city_filter(db, client, ops_user):
    tag = uuid.uuid4().hex[:8]
    dubai = _new_contact(full_name=f"Dubai {tag}", city="Dubai")
    cairo = _new_contact(full_name=f"Cairo {tag}", city="Cairo")
    db.add_all([dubai, cairo])
    await db.flush()

    resp = await client.get("/spine/contacts", params={"city": "Dubai", "q": tag}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(dubai.id) in ids
    assert str(cairo.id) not in ids


@pytest.mark.asyncio
async def test_cohort_and_program_filters(db, client, ops_user):
    """P3-2: the student-management view is this endpoint plus cohort_id/
    program_id — no second, students-only list endpoint."""
    from app.models.sessions.cohort import Cohort
    from app.models.sessions.program import Program
    from app.models.sessions.registration import Registration

    tag = uuid.uuid4().hex[:8]
    program = Program(
        id=uuid.uuid4(), code=f"P-{tag}", name="Filter Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(
        id=uuid.uuid4(), program_id=program.id, name="Filter Cohort",
        status="registration_open", visibility="public",
    )
    db.add(cohort)
    await db.flush()

    in_cohort = _new_contact(full_name=f"In Cohort {tag}")
    not_in_cohort = _new_contact(full_name=f"Not In Cohort {tag}")
    db.add_all([in_cohort, not_in_cohort])
    await db.flush()
    db.add(Registration(
        id=uuid.uuid4(), contact_id=in_cohort.id, cohort_id=cohort.id, status="registered",
        ticket_token=uuid.uuid4().hex, registered_via="desk", payment_status="waived",
    ))
    await db.flush()

    by_cohort = await client.get(
        "/spine/contacts", params={"cohort_id": str(cohort.id)}, headers=_auth_headers(ops_user),
    )
    assert by_cohort.status_code == 200, by_cohort.text
    cohort_ids = {item["id"] for item in by_cohort.json()["items"]}
    assert str(in_cohort.id) in cohort_ids
    assert str(not_in_cohort.id) not in cohort_ids

    by_program = await client.get(
        "/spine/contacts", params={"program_id": str(program.id)}, headers=_auth_headers(ops_user),
    )
    assert by_program.status_code == 200, by_program.text
    program_ids = {item["id"] for item in by_program.json()["items"]}
    assert str(in_cohort.id) in program_ids
    assert str(not_in_cohort.id) not in program_ids


@pytest.mark.asyncio
async def test_merged_contacts_excluded_from_search(db, client, ops_user):
    tag = uuid.uuid4().hex[:8]
    winner = _new_contact(full_name=f"Winner {tag}")
    loser = _new_contact(full_name=f"Loser {tag}", merged_into_id=None)
    db.add_all([winner, loser])
    await db.flush()
    loser.merged_into_id = winner.id
    await db.flush()

    resp = await client.get("/spine/contacts", params={"q": tag}, headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    ids = {item["id"] for item in resp.json()["items"]}
    assert str(winner.id) in ids
    assert str(loser.id) not in ids


# ── detail + relationships ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_contact_detail_with_relationships_both_directions(db, client, ops_user):
    guardian = _new_contact(full_name="Guardian Person", contact_roles=["parent_guardian"])
    child = _new_contact(full_name="Child Person", contact_roles=["student"])
    db.add_all([guardian, child])
    await db.flush()
    db.add(ContactRelationship(
        id=uuid.uuid4(), contact_id=guardian.id, related_contact_id=child.id, relation="guardian_of",
    ))
    await db.flush()

    # From the guardian's side — outgoing.
    resp = await client.get(f"/spine/contacts/{guardian.id}", headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["relationships"]) == 1
    rel = body["relationships"][0]
    assert rel["direction"] == "outgoing"
    assert rel["relation"] == "guardian_of"
    assert rel["other_contact"]["id"] == str(child.id)

    # From the child's side — incoming.
    resp2 = await client.get(f"/spine/contacts/{child.id}", headers=_auth_headers(ops_user))
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()
    assert len(body2["relationships"]) == 1
    rel2 = body2["relationships"][0]
    assert rel2["direction"] == "incoming"
    assert rel2["other_contact"]["id"] == str(guardian.id)


@pytest.mark.asyncio
async def test_contact_detail_includes_organization_name(db, client, ops_user):
    org = Organization(id=uuid.uuid4(), name_latin="Test School", org_type="school")
    db.add(org)
    await db.flush()
    contact = _new_contact(full_name="Org Linked Contact", organization_id=org.id)
    db.add(contact)
    await db.flush()

    resp = await client.get(f"/spine/contacts/{contact.id}", headers=_auth_headers(ops_user))
    assert resp.status_code == 200, resp.text
    assert resp.json()["organization_name"] == "Test School"


@pytest.mark.asyncio
async def test_contact_detail_404(db, client, ops_user):
    resp = await client.get(f"/spine/contacts/{uuid.uuid4()}", headers=_auth_headers(ops_user))
    assert resp.status_code == 404


# ── update ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_contact_editable_fields(db, client, ops_user):
    contact = _new_contact(full_name="Before Update", city="Abu Dhabi")
    db.add(contact)
    await db.flush()

    resp = await client.patch(
        f"/spine/contacts/{contact.id}",
        json={"city": "Dubai", "lifecycle_stage": "customer", "notes": "updated via test"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["city"] == "Dubai"
    assert body["lifecycle_stage"] == "customer"
    assert body["notes"] == "updated via test"

    await db.refresh(contact)
    assert contact.city == "Dubai"


@pytest.mark.asyncio
async def test_update_contact_date_of_birth_and_grade(db, client, ops_user):
    """2026-07-24, CEO request — purely informational, no enforcement."""
    contact = _new_contact(full_name="School Kid")
    db.add(contact)
    await db.flush()

    resp = await client.patch(
        f"/spine/contacts/{contact.id}",
        json={"date_of_birth": "2013-09-01", "grade": "Grade 7"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["date_of_birth"] == "2013-09-01"
    assert body["grade"] == "Grade 7"

    await db.refresh(contact)
    assert str(contact.date_of_birth) == "2013-09-01"
    assert contact.grade == "Grade 7"


@pytest.mark.asyncio
async def test_update_contact_organization_name_resolves_organization(db, client, ops_user):
    """Regression test — the School/Organization field in the admin Edit
    Student modal was bound to local state but never sent in the update
    payload, and even if it had been, ContactUpdate had no field for it."""
    contact = _new_contact(full_name="School Kid Two")
    db.add(contact)
    await db.flush()

    resp = await client.patch(
        f"/spine/contacts/{contact.id}",
        json={"organization_name": "American School of Dubai"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["organization_name"] == "American School of Dubai"

    await db.refresh(contact)
    assert contact.organization_id is not None
    org = await db.get(Organization, contact.organization_id)
    assert org.name_latin == "American School of Dubai"


@pytest.mark.asyncio
async def test_update_contact_blank_organization_name_does_not_clear(db, client, ops_user):
    contact = _new_contact(full_name="Already Has School")
    db.add(contact)
    await db.flush()

    await client.patch(
        f"/spine/contacts/{contact.id}", json={"organization_name": "Existing School"},
        headers=_auth_headers(ops_user),
    )
    await db.refresh(contact)
    existing_org_id = contact.organization_id
    assert existing_org_id is not None

    resp = await client.patch(
        f"/spine/contacts/{contact.id}", json={"city": "Sharjah"}, headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text
    await db.refresh(contact)
    assert contact.organization_id == existing_org_id


# ── role history (2026-07-24) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_contact_roles_records_history(db, client, ops_user):
    contact = _new_contact(full_name="Role History Contact", contact_roles=["student"])
    db.add(contact)
    await db.flush()

    resp = await client.patch(
        f"/spine/contacts/{contact.id}",
        json={"contact_roles": ["instructor", "alumnus"]},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text

    history_resp = await client.get(f"/spine/contacts/{contact.id}/role-history", headers=_auth_headers(ops_user))
    assert history_resp.status_code == 200, history_resp.text
    events = history_resp.json()

    added = {e["role"] for e in events if e["action"] == "added"}
    removed = {e["role"] for e in events if e["action"] == "removed"}
    assert added == {"instructor", "alumnus"}
    assert removed == {"student"}
    assert all(e["source"] == "contact_edit" for e in events)
    assert all(e["changed_by_user_id"] == str(ops_user.id) for e in events)


@pytest.mark.asyncio
async def test_update_contact_without_role_change_writes_no_history(db, client, ops_user):
    contact = _new_contact(full_name="No Role Change", contact_roles=["student"])
    db.add(contact)
    await db.flush()

    resp = await client.patch(
        f"/spine/contacts/{contact.id}", json={"city": "Dubai"}, headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 200, resp.text

    history_resp = await client.get(f"/spine/contacts/{contact.id}/role-history", headers=_auth_headers(ops_user))
    assert history_resp.json() == []


@pytest.mark.asyncio
async def test_role_history_404_for_missing_contact(db, client, ops_user):
    resp = await client.get(f"/spine/contacts/{uuid.uuid4()}/role-history", headers=_auth_headers(ops_user))
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_role_history_requires_operations_role(db, client, outsider_user):
    contact = _new_contact(full_name="Guarded History")
    db.add(contact)
    await db.flush()

    resp = await client.get(f"/spine/contacts/{contact.id}/role-history", headers=_auth_headers(outsider_user))
    assert resp.status_code == 403


# ── relationships endpoint ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_relationship_and_reject_duplicate(db, client, ops_user):
    a = _new_contact(full_name="Relationship A")
    b = _new_contact(full_name="Relationship B")
    db.add_all([a, b])
    await db.flush()

    resp = await client.post(
        f"/spine/contacts/{a.id}/relationships",
        json={"related_contact_id": str(b.id), "relation": "guardian_of"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["other_contact"]["id"] == str(b.id)

    existing = (await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == a.id, ContactRelationship.related_contact_id == b.id
        )
    )).scalars().first()
    assert existing is not None

    dup = await client.post(
        f"/spine/contacts/{a.id}/relationships",
        json={"related_contact_id": str(b.id), "relation": "guardian_of"},
        headers=_auth_headers(ops_user),
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_create_relationship_self_rejected(db, client, ops_user):
    a = _new_contact(full_name="Self Relationship")
    db.add(a)
    await db.flush()

    resp = await client.post(
        f"/spine/contacts/{a.id}/relationships",
        json={"related_contact_id": str(a.id), "relation": "sibling_of"},
        headers=_auth_headers(ops_user),
    )
    assert resp.status_code == 400


# ── organizations ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_organization_crud(db, client, ops_user):
    create_resp = await client.post(
        "/spine/organizations",
        json={"name_latin": "New Org", "org_type": "sponsor", "country": "UAE"},
        headers=_auth_headers(ops_user),
    )
    assert create_resp.status_code == 201, create_resp.text
    org_id = create_resp.json()["id"]

    get_resp = await client.get(f"/spine/organizations/{org_id}", headers=_auth_headers(ops_user))
    assert get_resp.status_code == 200
    assert get_resp.json()["name_latin"] == "New Org"

    patch_resp = await client.patch(
        f"/spine/organizations/{org_id}", json={"city": "Sharjah"}, headers=_auth_headers(ops_user)
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["city"] == "Sharjah"

    list_resp = await client.get("/spine/organizations", headers=_auth_headers(ops_user))
    assert list_resp.status_code == 200
    assert any(o["id"] == org_id for o in list_resp.json())


# ── role guard ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_outsider_role_forbidden_everywhere(db, client, outsider_user):
    contact = _new_contact(full_name="Guard Test")
    db.add(contact)
    await db.flush()

    assert (await client.get("/spine/contacts", headers=_auth_headers(outsider_user))).status_code == 403
    assert (await client.get(f"/spine/contacts/{contact.id}", headers=_auth_headers(outsider_user))).status_code == 403
    assert (await client.patch(
        f"/spine/contacts/{contact.id}", json={"city": "X"}, headers=_auth_headers(outsider_user)
    )).status_code == 403
    assert (await client.get("/spine/organizations", headers=_auth_headers(outsider_user))).status_code == 403


@pytest.mark.asyncio
async def test_no_token_unauthorized(client):
    resp = await client.get("/spine/contacts")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_can_access_operations_routes(db, client, admin_user):
    """RequireRole always lets admin through, even for the operations-gated routes."""
    resp = await client.get("/spine/contacts", headers=_auth_headers(admin_user))
    assert resp.status_code == 200
