"""Spine identity services (V2 R1-3, extended in R1-5).

Matching is deterministic, on email and phone only — see MASTER_EXECUTION_PLAN.md
§2.5. Name is not an input anywhere in this file: no normalization, no fuzzy
comparison, no equivalence table, no similarity hint. `contacts.full_name`
exists purely for a human to read and to search by (`GET /contacts?q=`, a
plain text search — see P2-3); nothing here reads it.

Two amendments landed here before any code existed (2026-07-22, see V2
§DISCOVERIES): the original spec let phone+name-similarity auto-merge with no
human involved — rejected outright, twice, first down to "email-only
auto-merge, name as a hint" and then further to "name plays no role at all."
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal, Optional
from uuid import UUID, uuid4

import phonenumbers
from phonenumbers import NumberParseException
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.identity_alias import IdentityAlias
from app.models.spine.merge_review import MergeReview
from app.models.spine.organization import Organization
from app.models.spine.touchpoint import Touchpoint
from app.models.user import User
from app.services.countries import COUNTRY_NAMES
from app.services.spine.role_history import record_role_diff

# Only these user roles carry a matching contact_roles value; every other
# role (admin, leader, applicant, facilitator, operations) maps to "other" —
# spec: MASTER_EXECUTION_PLAN.md P2-4. Canonical location as of 2026-07-24
# (moved from scripts/backfill_user_contacts.py, which re-exports this name
# for its existing tests/imports — see that file).
_ROLE_MAP = {
    "instructor": "instructor",
    "ambassador": "ambassador",
    "teacher": "teacher",
    "intern": "intern",
}

# (table_name, column_name) for every FK to contacts.id that a merge must repoint.
# merge_reviews.candidate_a/candidate_b are deliberately excluded: they're the
# audit trail of merge decisions themselves, not live references to redirect.
MERGE_FK_REGISTRY: list[tuple[str, str]] = [
    ("contact_relationships", "contact_id"),
    ("contact_relationships", "related_contact_id"),
    ("organizations", "primary_contact_id"),
    ("consent_records", "contact_id"),
    ("consent_records", "guardian_contact_id"),
    ("touchpoints", "contact_id"),
    ("identity_aliases", "contact_id"),
    ("registrations", "contact_id"),
    ("registrations", "payer_contact_id"),
    ("users", "contact_id"),
    ("contact_role_events", "contact_id"),
]

# Scalar contact fields eligible for copy-if-winner-is-NULL during a merge.
# Excludes the PK, array fields (unioned separately, see merge_contacts), and
# fields that are NOT NULL with a default (never NULL, so the rule never fires).
_MERGEABLE_SCALAR_FIELDS = [
    "primary_phone_e164", "whatsapp_e164", "email",
    "country", "city", "owner_user_id",
    "organization_id", "notes",
]

ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize_phone(raw: str | None, default_region: str = "AE") -> str | None:
    """E.164 phone, or None if it can't be parsed as a valid number."""
    if not raw or not raw.strip():
        return None
    cleaned = raw.translate(ARABIC_INDIC_DIGITS).strip()
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_email(email: str | None) -> str | None:
    """Lowercase, whitespace-stripped email — the exact-match key for auto-merge."""
    if not email or not email.strip():
        return None
    return email.strip().lower()


def _alias_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _find_contact_by_alias(db: AsyncSession, alias_type: str, value: str) -> Optional[UUID]:
    result = await db.execute(
        select(IdentityAlias.contact_id).where(
            IdentityAlias.alias_type == alias_type,
            IdentityAlias.alias_value_hash == _alias_hash(value),
        )
    )
    return result.scalars().first()


async def find_candidates(
    db: AsyncSession, phone: str | None, email: str | None
) -> dict[Literal["email", "phone"], UUID]:
    """Contacts sharing a normalized email or phone via `identity_aliases`.
    Name is never inspected — this is the entire candidate search."""
    candidates: dict[Literal["email", "phone"], UUID] = {}
    norm_email = normalize_email(email)
    if norm_email:
        contact_id = await _find_contact_by_alias(db, "email", norm_email)
        if contact_id:
            candidates["email"] = contact_id
    norm_phone = normalize_phone(phone)
    if norm_phone:
        contact_id = await _find_contact_by_alias(db, "phone", norm_phone)
        if contact_id:
            candidates["phone"] = contact_id
    return candidates


@dataclass
class IdentityEvaluation:
    outcome: Literal["EXACT_MERGE", "REVIEW", "NEW"]
    contact_id: Optional[UUID] = None
    matched_via: Optional[Literal["email", "phone"]] = None


async def evaluate(db: AsyncSession, phone: str | None, email: str | None) -> IdentityEvaluation:
    """Decide whether an incoming (phone, email) belongs to an existing contact.

    EXACT_MERGE: normalized email matches — attach directly, no human involved.
    REVIEW: a phone match with no email match — always queued for a human;
        never auto-merged, never auto-resolved as a household link.
    NEW: no candidates at all.

    Name is not a parameter. There is no HOUSEHOLD_PROMPT outcome — guardian/
    household links are only ever created from explicit registration-form
    fields, never inferred here.
    """
    candidates = await find_candidates(db, phone, email)
    if "email" in candidates:
        return IdentityEvaluation("EXACT_MERGE", candidates["email"], "email")
    if "phone" in candidates:
        return IdentityEvaluation("REVIEW", candidates["phone"], "phone")
    return IdentityEvaluation("NEW")


async def ensure_alias(db: AsyncSession, contact_id: UUID, alias_type: Literal["email", "phone"], value: str) -> None:
    """Idempotent — if this (type, value) is already recorded (for this
    contact or, in principle, another one), do nothing rather than fight the
    unique constraint. Never reassigns an existing alias's owner; that's
    merge_contacts' job, deliberately, with a human or an exact-email match
    behind it."""
    existing = await _find_contact_by_alias(db, alias_type, value)
    if existing is not None:
        return
    db.add(IdentityAlias(
        id=uuid4(), contact_id=contact_id, alias_type=alias_type,
        alias_value_hash=_alias_hash(value), alias_value_plain=value,
        matched_by="deterministic_exact",
    ))
    await db.flush()


async def resolve_or_create_organization(
    db: AsyncSession, name: str, org_type: str = "school",
) -> Organization:
    """Find-or-create an Organization by name (2026-07-24, CEO request to
    capture a student's school) — deterministic exact match, case- and
    whitespace-insensitive, never fuzzy. Organizations have no phone/email
    to key on the way contacts do, so name is the only viable identifier
    here; this is not a reversal of the "name plays no role in matching"
    policy above, which is specifically about not silently merging two
    different PEOPLE — a school genuinely only has a name.
    """
    normalized = name.strip()
    existing = (await db.execute(
        select(Organization).where(func.lower(Organization.name_latin) == normalized.lower())
    )).scalars().first()
    if existing is not None:
        return existing

    org = Organization(id=uuid4(), name_latin=normalized, org_type=org_type)
    db.add(org)
    await db.flush()
    return org


async def resolve_or_create_contact(
    db: AsyncSession,
    *,
    full_name: str,
    phone: str | None = None,
    email: str | None = None,
    contact_roles: list[str] | None = None,
    country: str | None = None,
    city: str | None = None,
    lifecycle_stage: str = "lead",
    role_event_source: str = "registration",
    date_of_birth: date | None = None,
    grade: str | None = None,
    organization_name: str | None = None,
) -> tuple[Contact, IdentityEvaluation]:
    """Find-or-create a contact from raw submitted fields — the orchestration
    every intake path (R1-5's public form, R2-2's bulk importer) needs on top
    of the bare evaluate()/merge_contacts() primitives above. This is the ONLY
    place that writes identity_aliases from an intake flow (evaluate() only
    ever reads them) — skip calling this and every later submission with the
    same phone/email comes back NEW forever, never finding the contact it
    should.

    On REVIEW (a phone match, no email match), creates the new contact anyway
    and queues a merge_reviews row — the public flow never blocks on
    ambiguity; a human resolves it later. On EXACT_MERGE, attaches to the
    existing contact and records any phone/email from this submission that
    wasn't on file yet (so the next lookup finds it too) — no role-history
    event, since an EXACT_MERGE never touches `contact_roles` on the matched
    contact (a separate, pre-existing gap: re-registering under a new role
    with an already-known email doesn't add that role today).

    `role_event_source` tags the resulting ContactRoleEvent rows (see
    services/spine/role_history.py) so a contact's role timeline can tell a
    public-form signup apart from a desk registration or a bulk import.

    `date_of_birth`/`grade`/`organization_name` (2026-07-24, CEO request) are
    purely informational — no age/minor enforcement is derived from them
    anywhere. `organization_name` resolves (or creates) an Organization via
    resolve_or_create_organization and sets it on the contact.
    """
    evaluation = await evaluate(db, phone, email)

    if evaluation.outcome == "EXACT_MERGE":
        contact = await db.get(Contact, evaluation.contact_id)
        norm_phone = normalize_phone(phone)
        if norm_phone:
            await ensure_alias(db, contact.id, "phone", norm_phone)
        norm_email = normalize_email(email)
        if norm_email:
            await ensure_alias(db, contact.id, "email", norm_email)
        # Gap-fill only — never overwrite what the contact already has,
        # matching merge_contacts' existing gap-fill convention for scalar
        # fields elsewhere in this module.
        if contact.date_of_birth is None and date_of_birth is not None:
            contact.date_of_birth = date_of_birth
        if contact.grade is None and grade is not None:
            contact.grade = grade
        if contact.organization_id is None and organization_name:
            org = await resolve_or_create_organization(db, organization_name)
            contact.organization_id = org.id
        return contact, evaluation

    organization_id = None
    if organization_name:
        org = await resolve_or_create_organization(db, organization_name)
        organization_id = org.id

    contact = Contact(
        id=uuid4(),
        full_name=full_name,
        contact_roles=contact_roles or [],
        secondary_phones=[],
        primary_phone_e164=normalize_phone(phone),
        email=normalize_email(email),
        preferred_language="ar",
        country=country,
        city=city,
        lifecycle_stage=lifecycle_stage,
        date_of_birth=date_of_birth,
        grade=grade,
        organization_id=organization_id,
    )
    db.add(contact)
    await db.flush()
    await record_role_diff(db, contact.id, [], contact.contact_roles, source=role_event_source)

    norm_phone = normalize_phone(phone)
    if norm_phone:
        await ensure_alias(db, contact.id, "phone", norm_phone)
    norm_email = normalize_email(email)
    if norm_email:
        await ensure_alias(db, contact.id, "email", norm_email)

    if evaluation.outcome == "REVIEW":
        db.add(MergeReview(
            id=uuid4(),
            candidate_a=contact.id,
            candidate_b=evaluation.contact_id,
            reason="phone_match",
            status="pending",
            detail={"matched_via": evaluation.matched_via},
        ))
        await db.flush()

    return contact, evaluation


async def ensure_guardian_relationship(db: AsyncSession, *, student_id: UUID, guardian_id: UUID) -> None:
    """Idempotent — writes the `guardian_of` `ContactRelationship` row if one
    doesn't already exist. Promoted 2026-08-08 from
    `routers/sessions/public.py` (public registration) so LMS student
    signup can create the same relationship without duplicating the check."""
    result = await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian_id,
            ContactRelationship.related_contact_id == student_id,
            ContactRelationship.relation == "guardian_of",
        )
    )
    if result.scalars().first() is not None:
        return
    db.add(ContactRelationship(
        id=uuid4(), contact_id=guardian_id, related_contact_id=student_id, relation="guardian_of",
    ))
    await db.flush()


async def merge_contacts(
    db: AsyncSession, winner_id: UUID, loser_id: UUID, actor_user_id: UUID | None
) -> None:
    """Consolidate loser into winner. Only ever called from an EXACT_MERGE
    (email) auto-match, or a human resolving a `merge_reviews` row — never
    from a name-similarity signal, because there isn't one (see §2.5).

    Part of the caller's transaction — does not commit. `actor_user_id` isn't
    stored by this function itself (no DB column exists for it on Contact or
    Touchpoint); the caller records it on `merge_reviews.resolved_by` when
    resolving a human-reviewed merge.
    """
    if winner_id == loser_id:
        raise ValueError("cannot merge a contact into itself")

    winner = await db.get(Contact, winner_id)
    loser = await db.get(Contact, loser_id)
    if winner is None or loser is None:
        raise ValueError("winner and loser must both be existing contacts")

    # Repoint every registered FK, row by row. Some tables (contact_relationships,
    # registrations) have unique constraints that already include the FK column
    # alongside another column, so a blind bulk UPDATE can collide with a row
    # the winner already has. Handle every registry entry the same defensive
    # way: try the repoint in a SAVEPOINT; on conflict, the winner already has
    # an equivalent row, so drop the loser's duplicate instead of erroring.
    for table_name, column_name in MERGE_FK_REGISTRY:
        table = Base.metadata.tables[table_name]
        col = table.c[column_name]
        pk_col = table.c["id"]
        values = {column_name: winner_id}
        if table_name == "identity_aliases":
            # These rows are moving because of a manual merge, not their
            # original creation reason — record that.
            values["matched_by"] = "manual_merge"

        result = await db.execute(select(pk_col).where(col == loser_id))
        row_ids = [row[0] for row in result.all()]

        if table_name == "users" and column_name == "contact_id":
            # D1: contact_id is UNIQUE now (Phase 2 Stage 1). Every other
            # registry entry below treats a repoint conflict as "the winner
            # already has an equivalent row, so drop the loser's duplicate" —
            # correct for a duplicate *row*, never for a duplicate *account*.
            # Falling through to that generic handling here would silently
            # delete a real login. Route to a human instead; leave both
            # accounts exactly as they are until someone decides what
            # "reconciles the two accounts" means for this pair (whose
            # enrollments/progress/login survives) — that's a product
            # decision this merge, and this migration, deliberately don't
            # make automatically.
            if row_ids:
                winner_has_account = bool(
                    (await db.execute(select(pk_col).where(col == winner_id).limit(1))).first()
                )
                if winner_has_account:
                    db.add(MergeReview(
                        id=uuid4(), candidate_a=winner_id, candidate_b=loser_id,
                        reason="dual_lms_accounts", status="pending",
                        detail={
                            "note": "both contacts hold a linked user account; the contact merge "
                                    "went ahead but left both accounts untouched — resolve manually",
                        },
                    ))
                    await db.flush()
                else:
                    await db.execute(update(table).where(col == loser_id).values(**values))
            continue

        for row_id in row_ids:
            try:
                async with db.begin_nested():
                    await db.execute(update(table).where(pk_col == row_id).values(**values))
            except IntegrityError:
                async with db.begin_nested():
                    await db.execute(delete(table).where(pk_col == row_id))

    # Fill winner's gaps from loser; never overwrite something winner already has.
    for field in _MERGEABLE_SCALAR_FIELDS:
        if getattr(winner, field) is None:
            setattr(winner, field, getattr(loser, field))
    # Union array fields rather than silently dropping loser's values.
    winner.contact_roles = sorted(set(winner.contact_roles or []) | set(loser.contact_roles or []))
    winner.secondary_phones = sorted(set(winner.secondary_phones or []) | set(loser.secondary_phones or []))

    loser.merged_into_id = winner_id

    db.add(Touchpoint(
        contact_id=winner_id,
        channel="system",
        touchpoint_type="other",
        occurred_at=datetime.now(timezone.utc),
        raw_platform_id=f"merge:{loser_id}",
    ))

    await db.flush()
    # No separate role-history event for the contact_roles union above: the
    # loser's own ContactRoleEvent rows were just repointed to winner_id by
    # the MERGE_FK_REGISTRY loop, so whatever history the loser already had
    # (with its real, original dates) now simply reads as part of winner's
    # timeline — recording a second "gained via merge" event today would be
    # a misleading duplicate for roles the loser has held for a long time.


def contact_roles_for_user(user: User) -> list[str]:
    """Map a user's raw `users.roles` onto the coarser `contact_roles`
    vocabulary — canonical location as of 2026-07-24 (moved here from
    scripts/backfill_user_contacts.py, which re-exports this name so its
    existing tests/imports keep working)."""
    mapped = {_ROLE_MAP.get(role, "other") for role in user.role_values}
    return sorted(mapped) if mapped else ["other"]


async def ensure_user_contact(db: AsyncSession, user: User, *, source: str = "backfill_initial") -> Contact:
    """Return the contact already linked to this user, creating one (a plain
    create, no evaluate()/matching — see scripts/backfill_user_contacts.py's
    module docstring for why) if this user has never been linked before.

    Used both by the periodic backfill script (unattended, `source`
    defaults to "backfill_initial") and, as of 2026-07-24, by the live
    role-edit path in services/user.py (`source="user_role_edit"`) so a
    staff account gets its first role-history event the moment an admin
    assigns it a role, not just whenever the script next runs.
    """
    if user.contact_id:
        existing = await db.get(Contact, user.contact_id)
        if existing is not None:
            return existing

    contact = Contact(
        id=uuid4(),
        full_name=user.full_name,
        contact_roles=contact_roles_for_user(user),
        primary_phone_e164=normalize_phone(user.phone),
        email=normalize_email(user.email),
        preferred_language="ar",
        # `user.country` is an ISO code (2026-08-08 country-code migration);
        # `Contact.country` stays free text on its own, older convention
        # (never migrated) — resolve to a name so this gap-fill doesn't leak
        # a raw code into a field every other write to it treats as a
        # human-typed display string.
        country=COUNTRY_NAMES.get(user.country, user.country) if user.country else None,
        owner_user_id=None,
    )
    db.add(contact)
    await db.flush()
    # Raw user role strings here (applicant/instructor/...), not
    # contact.contact_roles' collapsed bucket — kept consistent with how
    # services/user.py::update_user records later edits on this same contact,
    # so a person's timeline doesn't switch vocabulary mid-story.
    await record_role_diff(db, contact.id, [], user.role_values, source=source)

    norm_phone = normalize_phone(user.phone)
    if norm_phone:
        await ensure_alias(db, contact.id, "phone", norm_phone)
    norm_email = normalize_email(user.email)
    if norm_email:
        await ensure_alias(db, contact.id, "email", norm_email)

    user.contact_id = contact.id
    await db.flush()
    return contact
