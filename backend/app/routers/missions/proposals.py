"""Intern mission proposal pipeline (7B-6, D7/D8) — `/missions/proposals/*`.

D7's flow: intern submits (repo link or zip + description) here; staff
reviews via `/queue` + `/{id}/review` (`require_lms_content`, same
population that reviews submission-kind attempts); staff integrates the
mission by hand through the existing `/missions/admin` authoring surface,
then optionally calls `/{id}/link-mission` for traceability. Nothing here
creates a `Mission` row automatically — see `models/missions/proposal.py`.

Registered before `student_router` in `routers/missions/__init__.py`:
`/missions/proposals` is a static path that would otherwise be swallowed by
`/missions/{mission_id}` (same routing-order lesson as `/teams`/`/graph`).
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_intern, require_lms_content
from app.db.session import get_db
from app.models.missions.mission import Mission
from app.models.missions.proposal import MissionProposal
from app.models.user import User
from app.schemas.missions_proposals import (
    MissionProposalCreateIn,
    MissionProposalLinkIn,
    MissionProposalOut,
    MissionProposalReviewIn,
)
from app.services import storage
from app.services.missions.proposals import review_proposal, submit_proposal

router = APIRouter(prefix="/missions/proposals", tags=["missions-proposals"])

ZIP_BUCKET = "mission-proposals"
MAX_ZIP_BYTES = 50 * 1024 * 1024  # 50MB — a small mission prototype, not a full asset pipeline


async def _proposal_out(db: AsyncSession, proposal: MissionProposal) -> MissionProposalOut:
    submitter = await db.get(User, proposal.submitted_by)
    return MissionProposalOut(
        id=proposal.id, title=proposal.title, description=proposal.description, repo_url=proposal.repo_url,
        zip_url=await storage.resolve_url(proposal.zip_bucket, proposal.zip_path),
        submitted_by=proposal.submitted_by,
        submitted_by_name=submitter.full_name if submitter else "(deleted user)",
        status=proposal.status, reviewed_by=proposal.reviewed_by, review_notes=proposal.review_notes,
        mission_id=proposal.mission_id, created_at=proposal.created_at, decided_at=proposal.decided_at,
    )


async def _own_proposal(db: AsyncSession, proposal_id: uuid.UUID, user: User) -> MissionProposal:
    proposal = await db.get(MissionProposal, proposal_id)
    if proposal is None or proposal.submitted_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    return proposal


# ── intern-facing ────────────────────────────────────────────────────────

@router.get("/mine", response_model=list[MissionProposalOut])
async def my_proposals(db: AsyncSession = Depends(get_db), current: User = Depends(require_intern)):
    rows = (await db.execute(
        select(MissionProposal)
        .where(MissionProposal.submitted_by == current.id)
        .order_by(MissionProposal.created_at.desc())
    )).scalars().all()
    return [await _proposal_out(db, p) for p in rows]


@router.post("", response_model=MissionProposalOut, status_code=status.HTTP_201_CREATED)
async def create_proposal(
    body: MissionProposalCreateIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_intern),
):
    proposal = await submit_proposal(
        db, submitted_by=current.id, title=body.title, description=body.description, repo_url=body.repo_url,
    )
    await db.commit()
    await db.refresh(proposal)
    return await _proposal_out(db, proposal)


@router.post("/{proposal_id}/zip", response_model=MissionProposalOut)
async def upload_proposal_zip(
    proposal_id: uuid.UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_intern),
):
    proposal = await _own_proposal(db, proposal_id, current)
    if proposal.status != "submitted":
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Can't replace the artifact once review has started")
    if file.content_type not in ("application/zip", "application/x-zip-compressed"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Only .zip files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Empty upload")
    if len(data) > MAX_ZIP_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Zip exceeds the 50MB limit")

    filename = Path(file.filename or "proposal.zip").name
    path = f"{proposal_id}/{filename}"
    await storage.upload_to_path(ZIP_BUCKET, path, data, "application/zip")

    proposal.zip_bucket = ZIP_BUCKET
    proposal.zip_path = path
    await db.commit()
    await db.refresh(proposal)
    return await _proposal_out(db, proposal)


# ── staff review ─────────────────────────────────────────────────────────

@router.get("/queue", response_model=list[MissionProposalOut])
async def review_queue(db: AsyncSession = Depends(get_db), _: User = Depends(require_lms_content)):
    rows = (await db.execute(
        select(MissionProposal)
        .where(MissionProposal.status.in_(("submitted", "in_review")))
        .order_by(MissionProposal.created_at)
    )).scalars().all()
    return [await _proposal_out(db, p) for p in rows]


@router.post("/{proposal_id}/review", response_model=MissionProposalOut)
async def review(
    proposal_id: uuid.UUID,
    body: MissionProposalReviewIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(require_lms_content),
):
    proposal = await db.get(MissionProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    reviewed = await review_proposal(
        db, proposal=proposal, reviewer_id=current.id, review_status=body.status, review_notes=body.review_notes,
    )
    await db.commit()
    await db.refresh(reviewed)
    return await _proposal_out(db, reviewed)


@router.post("/{proposal_id}/link-mission", response_model=MissionProposalOut)
async def link_mission(
    proposal_id: uuid.UUID,
    body: MissionProposalLinkIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Purely a traceability pointer, set once staff has actually built the
    real `Mission` through the existing admin authoring surface — nothing
    reads `mission_id` to gate anything (see the model docstring)."""
    proposal = await db.get(MissionProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    mission = await db.get(Mission, body.mission_id)
    if mission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
    proposal.mission_id = mission.id
    await db.commit()
    await db.refresh(proposal)
    return await _proposal_out(db, proposal)
