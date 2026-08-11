"""Intern mission proposal pipeline (7B-6, D7/D8) — submission and review.
`models/missions/proposal.py` has the full design note.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.proposal import MissionProposal

_REVIEW_STATUSES = ("in_review", "approved", "rejected")


async def submit_proposal(
    db: AsyncSession, *, submitted_by: uuid.UUID, title: str, description: str, repo_url: str | None,
) -> MissionProposal:
    """A repo link is optional here — an intern who's about to upload a zip
    instead submits with `repo_url=None` and follows up with
    `POST /missions/proposals/{id}/zip`. `review_proposal` is what actually
    enforces "there has to be something to review" before a decision."""
    proposal = MissionProposal(
        id=uuid.uuid4(), title=title, description=description, repo_url=repo_url or None,
        submitted_by=submitted_by,
    )
    db.add(proposal)
    await db.flush()
    return proposal


async def review_proposal(
    db: AsyncSession, *, proposal: MissionProposal, reviewer_id: uuid.UUID,
    review_status: str, review_notes: str | None,
) -> MissionProposal:
    if review_status not in _REVIEW_STATUSES:
        raise HTTPException(400, detail=f"Unknown review status '{review_status}'")
    if not proposal.repo_url and not proposal.zip_path:
        raise HTTPException(400, detail="This proposal has no repo link or zip to review yet")
    proposal.status = review_status
    proposal.reviewed_by = reviewer_id
    proposal.review_notes = review_notes
    if review_status in ("approved", "rejected"):
        proposal.decided_at = datetime.now(timezone.utc)
    return proposal
