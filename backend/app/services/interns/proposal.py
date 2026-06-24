from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from uuid import UUID
from datetime import datetime, timezone

from app.models.interns.proposal import Proposal
from app.models.interns.epic import Epic
from app.schemas.interns.proposal import ProposalCreate, ProposalReview
from app.services import notification as notification_service


def _proposal_options():
    return [selectinload(Proposal.proposer), selectinload(Proposal.reviewer)]


async def create_proposal(
    db: AsyncSession, epic_id: UUID, proposal_in: ProposalCreate, user_id: UUID
) -> Proposal:
    proposal = Proposal(
        epic_id=epic_id,
        proposed_by=user_id,
        title=proposal_in.title,
        description=proposal_in.description,
    )
    db.add(proposal)
    await db.commit()
    return await get_proposal_by_id(db, proposal.id)


async def get_proposals_by_team(db: AsyncSession, team_id: UUID):
    """All proposals for epics belonging to a team, newest first."""
    result = await db.execute(
        select(Proposal)
        .join(Epic, Proposal.epic_id == Epic.id)
        .where(Epic.team_id == team_id)
        .options(*_proposal_options())
        .order_by(Proposal.created_at.desc())
    )
    return result.scalars().all()


async def get_proposals_by_user(db: AsyncSession, user_id: UUID):
    """All proposals submitted by a specific user, newest first."""
    result = await db.execute(
        select(Proposal)
        .where(Proposal.proposed_by == user_id)
        .options(*_proposal_options())
        .order_by(Proposal.created_at.desc())
    )
    return result.scalars().all()


async def get_proposals_by_epic(db: AsyncSession, epic_id: UUID):
    result = await db.execute(
        select(Proposal).where(Proposal.epic_id == epic_id).options(*_proposal_options())
    )
    return result.scalars().all()


async def get_proposal_by_id(db: AsyncSession, proposal_id: UUID) -> Proposal:
    result = await db.execute(
        select(Proposal).where(Proposal.id == proposal_id).options(*_proposal_options())
    )
    proposal = result.scalars().first()
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return proposal


async def review_proposal(
    db: AsyncSession, proposal_id: UUID, review_in: ProposalReview, reviewer_id: UUID
) -> Proposal:
    if review_in.status not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Status must be accepted or rejected")
    proposal = await get_proposal_by_id(db, proposal_id)
    proposal.status = review_in.status
    proposal.reviewed_by = reviewer_id
    proposal.reviewed_at = datetime.now(timezone.utc)
    await db.commit()

    await notification_service.create_notification(
        db, proposal.proposed_by,
        f"Proposal {review_in.status}",
        f'Your proposal "{proposal.title}" was {review_in.status}.',
    )

    return await get_proposal_by_id(db, proposal_id)
