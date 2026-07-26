"""Merge-review resolution (V2 R2-4). Mounted at /spine — listing is open to
operations, but resolving a review is admin-only per this week's plan (only
admins resolve merges; operations can browse/search — see
app/core/dependencies.py's require_operations/require_admin).

Both candidates' summary info is shown so a human reads both records and
decides — no similarity score or algorithmic hint of any kind is computed or
returned here. Name plays no role in identity matching anywhere in this
system (see app/services/spine/identity.py's module docstring — a
hard-fought, deliberate design decision); this router doesn't add a
name-based shortcut for merge resolution either.

Note: this file deliberately does not import `fastapi.status` (unlike
routers/spine/contacts.py) because the list endpoint's own query parameter is
named `status` (matching the plan's `GET /spine/merge-reviews?status=pending`)
— HTTPException status codes are given as plain ints here instead, matching
the existing convention in routers/ambassadors/leads.py.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_admin, require_operations
from app.db.session import get_db
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.merge_review import MergeReview
from app.models.user import User
from app.schemas.spine.contacts import ContactBrief, MergeResolveRequest, MergeReviewOut
from app.services.spine.identity import merge_contacts

router = APIRouter(prefix="/spine", tags=["spine-merge-reviews"])


async def _to_review_out(db: AsyncSession, review: MergeReview) -> MergeReviewOut:
    a = await db.get(Contact, review.candidate_a)
    b = await db.get(Contact, review.candidate_b)
    return MergeReviewOut(
        id=review.id,
        reason=review.reason,
        status=review.status,
        detail=review.detail,
        created_at=review.created_at,
        resolved_by=review.resolved_by,
        resolved_at=review.resolved_at,
        candidate_a=ContactBrief.model_validate(a) if a else None,
        candidate_b=ContactBrief.model_validate(b) if b else None,
    )


@router.get("/merge-reviews", response_model=list[MergeReviewOut])
async def list_merge_reviews(
    status: str | None = "pending",
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_operations),
):
    stmt = select(MergeReview).order_by(MergeReview.created_at.asc())
    if status:
        stmt = stmt.where(MergeReview.status == status)
    reviews = (await db.execute(stmt)).scalars().all()

    # Batch-load every candidate contact once rather than per-row.
    contact_ids = {r.candidate_a for r in reviews} | {r.candidate_b for r in reviews}
    contacts: dict[uuid.UUID, Contact] = {}
    if contact_ids:
        rows = (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
        contacts = {c.id: c for c in rows}

    out = []
    for r in reviews:
        a = contacts.get(r.candidate_a)
        b = contacts.get(r.candidate_b)
        out.append(MergeReviewOut(
            id=r.id, reason=r.reason, status=r.status, detail=r.detail,
            created_at=r.created_at, resolved_by=r.resolved_by, resolved_at=r.resolved_at,
            candidate_a=ContactBrief.model_validate(a) if a else None,
            candidate_b=ContactBrief.model_validate(b) if b else None,
        ))
    return out


@router.post("/merge-reviews/{review_id}/resolve", response_model=MergeReviewOut)
async def resolve_merge_review(
    review_id: uuid.UUID,
    body: MergeResolveRequest,
    db: AsyncSession = Depends(get_db),
    # require_admin itself depends on get_current_active_user and returns the
    # same authenticated User — reused directly as the actor for
    # actor_user_id/resolved_by rather than depending on it a second time.
    current_user: User = Depends(require_admin),
):
    review = await db.get(MergeReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Merge review not found")
    if review.status != "pending":
        raise HTTPException(status_code=400, detail="This merge review has already been resolved")

    now = datetime.now(timezone.utc)

    if body.action == "merge":
        if body.winner_id not in (review.candidate_a, review.candidate_b):
            raise HTTPException(status_code=400, detail="winner_id must be one of the review's two candidates")
        loser_id = review.candidate_b if body.winner_id == review.candidate_a else review.candidate_a
        await merge_contacts(db, winner_id=body.winner_id, loser_id=loser_id, actor_user_id=current_user.id)
        review.status = "merged"
        review.resolved_by = current_user.id
        review.resolved_at = now
        await db.commit()

    elif body.action == "keep_separate":
        review.status = "kept_separate"
        review.resolved_by = current_user.id
        review.resolved_at = now
        await db.commit()

    elif body.action == "link_household":
        relation = (body.relation or "").strip()
        existing = (await db.execute(
            select(ContactRelationship).where(
                ContactRelationship.contact_id == review.candidate_a,
                ContactRelationship.related_contact_id == review.candidate_b,
                ContactRelationship.relation == relation,
            )
        )).scalars().first()
        if existing is None:
            db.add(ContactRelationship(
                id=uuid.uuid4(),
                contact_id=review.candidate_a,
                related_contact_id=review.candidate_b,
                relation=relation,
            ))
        review.status = "linked_household"
        review.resolved_by = current_user.id
        review.resolved_at = now
        await db.commit()

    await db.refresh(review)
    return await _to_review_out(db, review)
