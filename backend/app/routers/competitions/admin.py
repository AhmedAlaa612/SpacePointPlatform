"""Ops authoring/oversight surface for competition judging (2026-08-24) —
`/competitions/admin/*`. Gated by `require_lms_content` (operations,
facilitator, admin), same role that authors `/lms/admin` checklists — a
competition's rubric and judge roster are program/cohort configuration,
not a separate permission concept.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_lms_content
from app.db.session import get_db
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.schemas.competitions import (
    CompetitionAdvanceResultOut, CompetitionAdvanceTeamsIn, CompetitionImportResultOut, CompetitionImportRowOut,
    CompetitionJudgeInviteIn, CompetitionJudgeOut, CompetitionJudgeProgressOut, CompetitionLeaderboardRowOut,
    CompetitionPublicationOut, CompetitionRubricIn, CompetitionRubricOut,
)
from app.services.competitions import judges as judges_service
from app.services.competitions import judging as judging_service
from app.services.competitions import progression as progression_service
from app.services.competitions import registration_import as import_service

router = APIRouter(
    prefix="/competitions/admin", tags=["competitions-admin"],
    dependencies=[Depends(require_lms_content)],
)


def _rubric_out(rubric, criteria) -> CompetitionRubricOut:
    return CompetitionRubricOut(
        id=rubric.id, program_id=rubric.program_id, name=rubric.name,
        criteria=[
            {"key": c.key, "label": c.label, "max_points": c.max_points, "position": c.position}
            for c in criteria
        ],
    )


async def _get_cohort_or_404(db: AsyncSession, cohort_id: uuid.UUID) -> Cohort:
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return cohort


# ── Rubric ───────────────────────────────────────────────────────────────

@router.get("/programs/{program_id}/rubric", response_model=CompetitionRubricOut)
async def get_program_rubric(program_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await judging_service.get_rubric(db, program_id=program_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No rubric configured for this program yet")
    return _rubric_out(*result)


@router.put("/programs/{program_id}/rubric", response_model=CompetitionRubricOut)
async def put_program_rubric(program_id: uuid.UUID, body: CompetitionRubricIn, db: AsyncSession = Depends(get_db)):
    if await db.get(Program, program_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    rubric, criteria = await judging_service.upsert_rubric(
        db, program_id=program_id, name=body.name,
        criteria=[c.model_dump() for c in body.criteria],
    )
    await db.commit()
    return _rubric_out(rubric, criteria)


# ── Judges ───────────────────────────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/judges", response_model=list[CompetitionJudgeProgressOut])
async def get_cohort_judges(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rows = await judging_service.list_judges_with_progress(db, cohort_id=cohort_id)
    return [CompetitionJudgeProgressOut(**row) for row in rows]


@router.post("/cohorts/{cohort_id}/judges", response_model=CompetitionJudgeOut, status_code=status.HTTP_201_CREATED)
async def post_cohort_judge(cohort_id: uuid.UUID, body: CompetitionJudgeInviteIn, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    user = await judges_service.invite_judge(db, cohort_id=cohort_id, name=body.name, email=body.email)
    await db.commit()
    return CompetitionJudgeOut(user_id=user.id, full_name=user.full_name, email=user.email)


@router.delete("/cohorts/{cohort_id}/judges/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_judge(cohort_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    removed = await judges_service.revoke_judge(db, cohort_id=cohort_id, user_id=user_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This judge isn't assigned to this cohort")
    await db.commit()


# ── Registration import, progression ────────────────────────────────────

@router.post("/cohorts/{cohort_id}/registration-import", response_model=CompetitionImportResultOut)
async def post_cohort_registration_import(
    cohort_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
):
    await _get_cohort_or_404(db, cohort_id)
    file_bytes = await file.read()
    rows = import_service.parse_registration_sheet(file_bytes)
    results = await import_service.import_registrations(db, cohort_id=cohort_id, rows=rows)
    await db.commit()
    return CompetitionImportResultOut(
        summary=import_service.summarize(results),
        rows=[CompetitionImportRowOut(**r) for r in import_service.results_as_dicts(results)],
    )


@router.post("/cohorts/{cohort_id}/advance-teams", response_model=list[CompetitionAdvanceResultOut])
async def post_cohort_advance_teams(cohort_id: uuid.UUID, body: CompetitionAdvanceTeamsIn, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    results = await progression_service.advance_teams(
        db, team_ids=body.team_ids, from_cohort_id=cohort_id, to_cohort_id=body.to_cohort_id,
    )
    await db.commit()
    return [CompetitionAdvanceResultOut(**r) for r in progression_service.results_as_dicts(results)]


# ── Leaderboard, publish, export ────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/leaderboard", response_model=list[CompetitionLeaderboardRowOut])
async def get_cohort_leaderboard(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rows = await judging_service.leaderboard(db, cohort_id=cohort_id)
    return [CompetitionLeaderboardRowOut(**row) for row in rows]


@router.get("/cohorts/{cohort_id}/export-top20", response_model=list[CompetitionLeaderboardRowOut])
async def get_cohort_export_top20(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rows = await judging_service.export_top(db, cohort_id=cohort_id, limit=20)
    return [CompetitionLeaderboardRowOut(**row) for row in rows]


@router.post("/cohorts/{cohort_id}/publish", response_model=CompetitionPublicationOut)
async def post_cohort_publish(
    cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _get_cohort_or_404(db, cohort_id)
    row = await judging_service.publish(db, cohort_id=cohort_id, actor_user_id=current.id)
    await db.commit()
    return CompetitionPublicationOut(published=True, published_at=row.published_at)


@router.post("/cohorts/{cohort_id}/unpublish", status_code=status.HTTP_204_NO_CONTENT)
async def post_cohort_unpublish(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    unpublished = await judging_service.unpublish(db, cohort_id=cohort_id)
    if not unpublished:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort's results aren't published")
    await db.commit()
