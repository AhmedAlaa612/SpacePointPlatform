"""Public registration endpoint (V2 R1-5) — no auth, rate-limited, honeypot-
guarded. Mounted at /public/register/{cohort_key} — this codebase has no
/api prefix anywhere (VERIFY against main.py: every router mounts at root),
unlike the literal path in MASTER_EXECUTION_PLAN_V2.md; followed the real
convention instead, matching the existing /public/* pattern in
routers/ambassadors/public.py.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from arq.connections import ArqRedis

from app.db.session import get_db
from app.core.rate_limit import enforce_rate_limit
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import ContactRelationship
from app.schemas.sessions.catalog import CatalogCohortOut
from app.schemas.sessions.public_registration import PublicRegistrationRequest
from app.services.spine.identity import resolve_or_create_contact
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES, register
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/public", tags=["public-registration"])


@router.get("/catalog", response_model=list[CatalogCohortOut])
async def public_catalog(db: AsyncSession = Depends(get_db)):
    """Open, public cohorts a marketing site can list and link a
    registration form at (V2 R3-1). No auth, no rate limit — read-only and
    cheap; the abuse-prone endpoint is the POST above, not this GET."""
    rows = (await db.execute(
        select(Cohort, Program)
        .join(Program, Program.id == Cohort.program_id)
        .where(Cohort.status == "registration_open", Cohort.visibility == "public")
        .order_by(Cohort.starts_on.asc().nullslast())
    )).all()

    cohort_ids = [cohort.id for cohort, _ in rows]
    active_counts: dict[uuid.UUID, int] = {}
    if cohort_ids:
        count_rows = (await db.execute(
            select(Registration.cohort_id, func.count())
            .where(
                Registration.cohort_id.in_(cohort_ids),
                Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            )
            .group_by(Registration.cohort_id)
        )).all()
        active_counts = dict(count_rows)

    items: list[CatalogCohortOut] = []
    for cohort, program in rows:
        spots_left = None
        is_limited = False
        if cohort.capacity is not None:
            spots_left = max(cohort.capacity - active_counts.get(cohort.id, 0), 0)
            is_limited = cohort.capacity > 0 and (spots_left / cohort.capacity) < 0.10

        if program.pricing_model == "free":
            price_display = "Free"
        elif program.price is not None:
            price_display = f"AED {program.price}"
        else:
            price_display = "Paid"

        items.append(CatalogCohortOut(
            cohort_id=cohort.id,
            program_name=program.name,
            program_type=program.program_type,
            description=program.description,
            starts_on=cohort.starts_on,
            ends_on=cohort.ends_on,
            location=cohort.location,
            price_display=price_display,
            spots_left=spots_left,
            is_limited=is_limited,
            registration_endpoint=f"/public/register/{cohort.id}",
        ))

    return items


@router.post("/register/{cohort_key}", status_code=status.HTTP_201_CREATED)
async def public_register(
    cohort_key: uuid.UUID,
    body: PublicRegistrationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    # Rate-limit before the honeypot check, so a flood of bot-filled requests
    # still gets throttled even though they'll be dropped either way.
    enforce_rate_limit(request)

    if body.website:
        # Honeypot tripped — a human never sees this field. Return the same
        # success shape as a real registration so a bot can't distinguish a
        # drop from a real acceptance; just don't do anything.
        return {"message": "You're registered! Check your email for your ticket."}

    cohort = await db.get(Cohort, cohort_key)
    if cohort is None or cohort.status != "registration_open" or cohort.visibility != "public":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Registration is not open for this cohort")

    student, _ = await resolve_or_create_contact(
        db,
        full_name=body.student_name,
        phone=body.phone,
        email=body.email,
        contact_roles=["student"],
        city=body.city,
        date_of_birth=body.date_of_birth,
        grade=body.grade,
        organization_name=body.organization_name,
    )

    payer_contact_id = None
    if body.parent_name and body.parent_phone:
        guardian, _ = await resolve_or_create_contact(
            db,
            full_name=body.parent_name,
            phone=body.parent_phone,
            email=body.parent_email,
            contact_roles=["parent_guardian"],
        )
        payer_contact_id = guardian.id
        await _ensure_guardian_relationship(db, student_id=student.id, guardian_id=guardian.id)

    registration = await register(
        db,
        contact_id=student.id,
        cohort_id=cohort.id,
        payer_contact_id=payer_contact_id,
        registered_via="form",
        session_ids=body.session_ids,
    )

    await db.commit()

    # Ticket email now runs on the ARQ queue (V2 R2-1), not synchronously in
    # this request (that was R1-4's explicitly-flagged W1 interim). A failed
    # or slow send — or Redis being unreachable at all (safe_enqueue) — must
    # never hold up or undo a successful registration.
    await safe_enqueue(arq_redis, "send_ticket_email", str(registration.id))

    return {
        "message": "You're registered! Check your email for your ticket.",
        "email": _mask_email(body.email),
    }


async def _ensure_guardian_relationship(db: AsyncSession, *, student_id: uuid.UUID, guardian_id: uuid.UUID) -> None:
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
        id=uuid.uuid4(), contact_id=guardian_id, related_contact_id=student_id, relation="guardian_of",
    ))
    await db.flush()


def _mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    if len(name) <= 2:
        masked = name[:1] + "***"
    else:
        masked = name[:2] + "***"
    return f"{masked}@{domain}"
