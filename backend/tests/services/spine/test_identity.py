"""Mandatory tests for V2 R1-3 (see MASTER_EXECUTION_PLAN.md P2-2).

Every test here exists to prove the amended policy in §2.5: matching is
email + phone only, name plays no role whatsoever — not fuzzy, not a hint.
"""

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select

from app.models.spine.consent import ConsentRecord
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.contact_role_event import ContactRoleEvent
from app.models.spine.identity_alias import IdentityAlias
from app.models.spine.merge_review import MergeReview
from app.models.spine.organization import Organization
from app.models.spine.touchpoint import Touchpoint
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.user import User
from app.services.spine.identity import (
    MERGE_FK_REGISTRY,
    _alias_hash,
    evaluate,
    merge_contacts,
    normalize_email,
    normalize_phone,
    resolve_or_create_contact,
    resolve_or_create_organization,
)


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


async def _add_alias(db, contact_id, alias_type, value, matched_by="deterministic_exact"):
    alias = IdentityAlias(
        id=uuid.uuid4(),
        contact_id=contact_id,
        alias_type=alias_type,
        alias_value_hash=_alias_hash(value),
        alias_value_plain=value,
        matched_by=matched_by,
    )
    db.add(alias)
    await db.flush()
    return alias


# ── normalize_phone / normalize_email ──────────────────────────────────────

def test_normalize_phone_valid_uae_number():
    assert normalize_phone("050 123 4567", default_region="AE") == "+971501234567"


def test_normalize_phone_arabic_indic_digits():
    assert normalize_phone("٠٥٠١٢٣٤٥٦٧", default_region="AE") == "+971501234567"


def test_normalize_phone_garbage_returns_none():
    assert normalize_phone("not a phone number") is None
    assert normalize_phone(None) is None
    assert normalize_phone("") is None


def test_normalize_email_lowercases_and_strips():
    assert normalize_email("  Test@Example.COM  ") == "test@example.com"
    assert normalize_email(None) is None
    assert normalize_email("") is None


# ── evaluate: the core policy ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_phone_only_never_returns_exact_merge(db):
    """A phone match alone — no email match — must always be REVIEW, never
    EXACT_MERGE. This is the frozen rule from §2.5: only email auto-merges."""
    existing = _new_contact(full_name="Ahmed Khalil")
    db.add(existing)
    await db.flush()
    await _add_alias(db, existing.id, "phone", "+971501234567")

    result = await evaluate(db, phone="050 123 4567", email=None)

    assert result.outcome == "REVIEW"
    assert result.contact_id == existing.id
    assert result.matched_via == "phone"


@pytest.mark.asyncio
async def test_exact_email_match_returns_exact_merge(db):
    """An exact email match auto-merges — the only automatic outcome. This
    works purely on email; evaluate() takes no name parameter at all, so
    there is no name for it to be swayed by, matching or otherwise."""
    existing = _new_contact(full_name="Completely Different Name")
    db.add(existing)
    await db.flush()
    await _add_alias(db, existing.id, "email", "student@example.com")

    result = await evaluate(db, phone=None, email="Student@Example.com")

    assert result.outcome == "EXACT_MERGE"
    assert result.contact_id == existing.id
    assert result.matched_via == "email"


@pytest.mark.asyncio
async def test_duplicate_names_never_produce_a_candidate_without_phone_or_email_match(db):
    """Two existing contacts share an identical name. Neither their phone nor
    email match the incoming submission. Result must be NEW — proving name
    similarity/equality is never inspected as a fallback signal."""
    contact_a = _new_contact(full_name="Mohamed Ali")
    contact_b = _new_contact(full_name="Mohamed Ali")  # identical name, different person
    db.add_all([contact_a, contact_b])
    await db.flush()
    await _add_alias(db, contact_a.id, "phone", "+971501111111")
    await _add_alias(db, contact_b.id, "email", "mohamed.ali@example.com")

    result = await evaluate(db, phone="+971509999999", email="someone.else@example.com")

    assert result.outcome == "NEW"
    assert result.contact_id is None


@pytest.mark.asyncio
async def test_no_candidates_returns_new(db):
    result = await evaluate(db, phone="+971501234567", email="nobody@example.com")
    assert result.outcome == "NEW"
    assert result.contact_id is None


# ── merge_contacts: FK repointing across the whole registry ────────────────

async def _make_cohort(db) -> Cohort:
    program = Program(
        id=uuid.uuid4(), code=f"TEST-{uuid.uuid4().hex[:8]}", name="Test Program",
        program_type="workshop", pricing_model="free", active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Test Cohort")
    db.add(cohort)
    await db.flush()
    return cohort


async def _seed_registry_row(db, table_name: str, column_name: str, loser_id):
    """Create one row in `table_name` with `column_name` pointing at loser_id,
    filling every other required column with valid minimal data. Returns the
    new row's own id."""
    filler = _new_contact()
    db.add(filler)
    await db.flush()

    if table_name == "contact_relationships":
        kwargs = dict(id=uuid.uuid4(), relation="guardian_of")
        kwargs["contact_id"] = loser_id if column_name == "contact_id" else filler.id
        kwargs["related_contact_id"] = loser_id if column_name == "related_contact_id" else filler.id
        row = ContactRelationship(**kwargs)
    elif table_name == "organizations":
        row = Organization(id=uuid.uuid4(), name_latin="Test Org", org_type="school", primary_contact_id=loser_id)
    elif table_name == "consent_records":
        kwargs = dict(id=uuid.uuid4(), consent_type="email_marketing", status="granted", source="test", contact_id=filler.id)
        kwargs[column_name] = loser_id
        row = ConsentRecord(**kwargs)
    elif table_name == "touchpoints":
        row = Touchpoint(
            id=uuid.uuid4(), contact_id=loser_id, channel="system",
            touchpoint_type="other", occurred_at=datetime.now(timezone.utc),
        )
    elif table_name == "identity_aliases":
        row = IdentityAlias(
            id=uuid.uuid4(), contact_id=loser_id, alias_type="lp_cookie",
            alias_value_hash=uuid.uuid4().hex, matched_by="import",
        )
    elif table_name == "registrations":
        cohort = await _make_cohort(db)
        kwargs = dict(
            id=uuid.uuid4(), cohort_id=cohort.id, payment_status="waived", status="registered",
            is_repeat=False, ticket_token=f"tok-{uuid.uuid4().hex}", registered_via="form",
            contact_id=filler.id,
        )
        kwargs[column_name] = loser_id
        row = Registration(**kwargs)
    elif table_name == "users":
        row = User(
            id=uuid.uuid4(), full_name="Test Staff User", email=f"{uuid.uuid4().hex}@example.com",
            password_hash="x", roles=[], contact_id=loser_id,
        )
    elif table_name == "contact_role_events":
        row = ContactRoleEvent(
            id=uuid.uuid4(), contact_id=loser_id, role="student", action="added",
            source="registration", occurred_at=datetime.now(timezone.utc),
        )
    else:
        raise AssertionError(f"no test fixture wired for registry table {table_name!r}")

    db.add(row)
    await db.flush()
    return row.id


@pytest.mark.asyncio
async def test_merge_contacts_repoints_every_registered_fk(db):
    for table_name, column_name in MERGE_FK_REGISTRY:
        winner = _new_contact(full_name="Winner")
        loser = _new_contact(full_name="Loser")
        db.add_all([winner, loser])
        await db.flush()

        row_id = await _seed_registry_row(db, table_name, column_name, loser.id)

        await merge_contacts(db, winner_id=winner.id, loser_id=loser.id, actor_user_id=None)

        table = Contact.metadata.tables[table_name]
        result = await db.execute(
            select(table.c[column_name]).where(table.c["id"] == row_id)
        )
        repointed_value = result.scalar_one_or_none()

        assert repointed_value == winner.id, (
            f"{table_name}.{column_name} was not repointed to the winner after merge "
            f"(row may have been dropped as a duplicate instead — got {repointed_value!r})"
        )


@pytest.mark.asyncio
async def test_merge_contacts_fills_winner_gaps_and_unions_arrays(db):
    winner = _new_contact(full_name="Winner", contact_roles=["student"], city=None)
    loser = _new_contact(full_name="Loser", contact_roles=["alumnus"], city="Dubai")
    db.add_all([winner, loser])
    await db.flush()

    await merge_contacts(db, winner_id=winner.id, loser_id=loser.id, actor_user_id=None)

    assert winner.city == "Dubai"  # winner's NULL filled from loser
    assert set(winner.contact_roles) == {"student", "alumnus"}  # arrays unioned, not dropped
    assert loser.merged_into_id == winner.id  # soft-retired, never deleted


@pytest.mark.asyncio
async def test_merge_contacts_drops_duplicate_relationship_instead_of_erroring(db):
    """Winner and loser both already have the identical relationship to a
    third contact (e.g. both were independently recorded as guardian_of the
    same child before anyone noticed they're the same person). Repointing the
    loser's row verbatim would collide with winner's existing row and violate
    uq_contact_relationship — merge_contacts must catch that and drop the
    loser's duplicate instead of raising."""
    winner = _new_contact(full_name="Winner")
    loser = _new_contact(full_name="Loser")
    child = _new_contact(full_name="Child")
    db.add_all([winner, loser, child])
    await db.flush()

    db.add(ContactRelationship(id=uuid.uuid4(), contact_id=winner.id, related_contact_id=child.id, relation="guardian_of"))
    db.add(ContactRelationship(id=uuid.uuid4(), contact_id=loser.id, related_contact_id=child.id, relation="guardian_of"))
    await db.flush()

    await merge_contacts(db, winner_id=winner.id, loser_id=loser.id, actor_user_id=None)  # must not raise

    result = await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.related_contact_id == child.id, ContactRelationship.relation == "guardian_of"
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].contact_id == winner.id


@pytest.mark.asyncio
async def test_merge_contacts_writes_a_touchpoint_on_the_winner(db):
    winner = _new_contact()
    loser = _new_contact()
    db.add_all([winner, loser])
    await db.flush()

    await merge_contacts(db, winner_id=winner.id, loser_id=loser.id, actor_user_id=None)

    result = await db.execute(
        select(Touchpoint).where(Touchpoint.contact_id == winner.id, Touchpoint.channel == "system")
    )
    touchpoint = result.scalars().first()
    assert touchpoint is not None
    assert touchpoint.touchpoint_type == "other"
    assert str(loser.id) in touchpoint.raw_platform_id


@pytest.mark.asyncio
async def test_merge_contacts_routes_dual_accounts_to_merge_review_instead_of_deleting(db):
    """D1 (Phase 2 Stage 1): once UNIQUE(users.contact_id) exists, a blind
    repoint-or-delete (the generic registry-loop fallback every other table
    uses) would silently delete a real account the moment both contacts
    being merged already have one. Must route to a human via merge_reviews
    instead, and leave both accounts exactly as they were."""
    winner = _new_contact(full_name="Winner")
    loser = _new_contact(full_name="Loser")
    db.add_all([winner, loser])
    await db.flush()

    winner_user = User(
        id=uuid.uuid4(), full_name="Winner Account", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["student"], contact_id=winner.id, status="active",
    )
    loser_user = User(
        id=uuid.uuid4(), full_name="Loser Account", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["student"], contact_id=loser.id, status="active",
    )
    db.add_all([winner_user, loser_user])
    await db.flush()

    await merge_contacts(db, winner_id=winner.id, loser_id=loser.id, actor_user_id=None)  # must not raise

    # Neither account was touched.
    await db.refresh(winner_user)
    await db.refresh(loser_user)
    assert winner_user.contact_id == winner.id
    assert loser_user.contact_id == loser.id  # not deleted, not repointed

    # The contact-level merge still went ahead (D1 doesn't block that).
    assert loser.merged_into_id == winner.id

    review = (await db.execute(
        select(MergeReview).where(
            MergeReview.candidate_a == winner.id, MergeReview.candidate_b == loser.id,
            MergeReview.reason == "dual_lms_accounts",
        )
    )).scalars().first()
    assert review is not None
    assert review.status == "pending"


# ── resolve_or_create_organization / DOB+grade+org on resolve_or_create_contact
# (2026-07-24, CEO request: "add birthdate to students, also the organization
# and grade") ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_or_create_organization_creates_new(db):
    org = await resolve_or_create_organization(db, "Brand New School")
    assert org.name_latin == "Brand New School"
    assert org.org_type == "school"


@pytest.mark.asyncio
async def test_resolve_or_create_organization_matches_existing_case_insensitive(db):
    first = await resolve_or_create_organization(db, "Existing Academy")
    second = await resolve_or_create_organization(db, "  existing academy  ")
    assert second.id == first.id

    count = await db.scalar(
        select(func.count()).select_from(Organization).where(Organization.name_latin == "Existing Academy")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_resolve_or_create_contact_sets_dob_grade_and_organization_on_create(db):
    contact, evaluation = await resolve_or_create_contact(
        db, full_name="New Student", phone="0501112233", email="new.student@example.com",
        contact_roles=["student"], date_of_birth=date(2013, 3, 1), grade="Grade 6",
        organization_name="Riverside School",
    )
    assert evaluation.outcome == "NEW"
    assert contact.date_of_birth == date(2013, 3, 1)
    assert contact.grade == "Grade 6"

    org = await db.get(Organization, contact.organization_id)
    assert org.name_latin == "Riverside School"


@pytest.mark.asyncio
async def test_resolve_or_create_contact_gap_fills_dob_grade_org_on_exact_merge(db):
    """An EXACT_MERGE (matched by email) must fill in DOB/grade/organization
    if the existing contact doesn't have them yet — but never overwrite
    values it already has."""
    existing = _new_contact(full_name="Returning Student", grade="Grade 4")
    db.add(existing)
    await db.flush()
    await _add_alias(db, existing.id, "email", "returning.student@example.com")

    contact, evaluation = await resolve_or_create_contact(
        db, full_name="Returning Student", email="returning.student@example.com",
        date_of_birth=date(2014, 6, 15), grade="Grade 5", organization_name="New School",
    )
    assert evaluation.outcome == "EXACT_MERGE"
    assert contact.id == existing.id
    assert contact.date_of_birth == date(2014, 6, 15)  # filled, was None
    assert contact.grade == "Grade 4"  # NOT overwritten — already had a value
    org = await db.get(Organization, contact.organization_id)
    assert org.name_latin == "New School"
