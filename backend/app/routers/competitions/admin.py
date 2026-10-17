"""Ops authoring/oversight surface for competition judging (2026-08-24) —
`/competitions/admin/*`. Gated by `require_lms_content` (operations,
facilitator, admin), same role that authors `/lms/admin` checklists — a
competition's rubric and judge roster are program/cohort configuration,
not a separate permission concept.
"""

import logging
import uuid
from typing import Literal

from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.dependencies import get_current_active_user, require_lms_content
from app.db.session import get_db
from app.workers.settings import get_arq_redis, safe_enqueue
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.user import User
from app.models.team import Team
from app.schemas.competitions import (
    CompetitionAdvanceResultOut, CompetitionAdvanceTeamsIn, CompetitionAnalyticsOut,
    CompetitionAssignableStudentOut, CompetitionAssignableStudentsPage,
    CompetitionAssignStudentRowOut, CompetitionAssignStudentsIn, CompetitionAssignStudentsOut,
    CompetitionRegisterUsersIn,
    CompetitionCertificateRecipientOut, CompetitionCertificateRecipientsSummaryOut,
    CompetitionCertificateSendIn, CompetitionCertificateSendResultOut,
    CompetitionCertificateDownloadIn, CompetitionCertificateTestEmailIn,
    CompetitionImportConfirmIn,
    CompetitionImportPreviewOut, CompetitionImportPreviewRowOut, CompetitionImportResultOut,
    CompetitionImportRowOut, CompetitionJudgeInviteIn, CompetitionJudgeOut, CompetitionJudgeProgressOut,
    CompetitionLeaderboardRowOut, CompetitionPublicationOut, CompetitionPublishIn, CompetitionVisibilitySettings,
    CompetitionRubricIn, CompetitionRubricOut,
    CompetitionTeamCreateIn, CompetitionTeamMemberIn, CompetitionTeamOut, CompetitionTeamRenameIn,
    CohortSubmissionWindowsUpdate, TeamCheckpointStateOut, TeamTimingAdjustmentUpdate, TeamScoreBreakdownOut,
    OpsScoreIn, OpsScoreOut,
)
from app.services.competitions import analytics as analytics_service
from app.services.competitions import certificates as certificates_service
from app.services.competitions import export as export_service
from app.services.competitions import judges as judges_service
from app.services.competitions import judging as judging_service
from app.services.competitions import progression as progression_service
from app.services.competitions import registration_import as import_service
from app.services.competitions import team_management as team_service
from app.services.lms import students as student_search_service
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(
    prefix="/competitions/admin", tags=["competitions-admin"],
    dependencies=[Depends(require_lms_content)],
)


def _rubric_out(rubric, criteria) -> CompetitionRubricOut:
    return CompetitionRubricOut(
        id=rubric.id, program_id=rubric.program_id, cohort_id=rubric.cohort_id, name=rubric.name,
        criteria=[
            {
                "key": c.key, "label": c.label, "max_points": c.max_points, "position": c.position,
                "scored_by": getattr(c, "scored_by", "judge") or "judge",
                "sub_criteria": [
                    {
                        "key": s["key"], "label": s["label"],
                        "max_points": int(s["max_points"]), "position": s.get("position", i),
                    }
                    for i, s in enumerate(getattr(c, "sub_criteria", None) or [])
                ],
            }
            for c in criteria
        ],
    )


async def _get_cohort_or_404(db: AsyncSession, cohort_id: uuid.UUID) -> Cohort:
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return cohort


# ── Rubric ───────────────────────────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/rubric", response_model=CompetitionRubricOut)
async def get_cohort_rubric(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    result = await judging_service.get_rubric(db, cohort_id=cohort_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No rubric configured for this cohort yet")
    return _rubric_out(*result)


@router.put("/cohorts/{cohort_id}/rubric", response_model=CompetitionRubricOut)
async def put_cohort_rubric(cohort_id: uuid.UUID, body: CompetitionRubricIn, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rubric, criteria = await judging_service.upsert_rubric(
        db, cohort_id=cohort_id, name=body.name,
        criteria=[c.model_dump() for c in body.criteria],
    )
    await db.commit()
    return _rubric_out(rubric, criteria)


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
    user = await judges_service.invite_judge(
        db, cohort_id=cohort_id, name=body.name, email=body.email, send_email=body.send_email,
    )
    await db.commit()
    return CompetitionJudgeOut(user_id=user.id, full_name=user.full_name, email=user.email)


@router.delete("/cohorts/{cohort_id}/judges/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort_judge(cohort_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    removed = await judges_service.revoke_judge(db, cohort_id=cohort_id, user_id=user_id)
    if not removed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This judge isn't assigned to this cohort")
    await db.commit()


@router.post("/cohorts/{cohort_id}/judges/{user_id}/resend-onboarding-email")
async def resend_judge_onboarding_email(cohort_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    sent = await judges_service.resend_judge_onboarding_email(db, cohort_id=cohort_id, user_id=user_id)
    await db.commit()
    return {"sent": sent}


# ── Teams (manual management — 2026-08-26) ─────────────────────────────
# Complements Roster import: that's for the whole-sheet bulk case, this is
# for the one-off corrections after — a late signup, a team split, someone
# switching teams — without re-uploading a whole sheet over one row.

@router.get("/cohorts/{cohort_id}/teams", response_model=list[CompetitionTeamOut])
async def get_cohort_teams(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rows = await team_service.list_teams_with_members(db, cohort_id=cohort_id)
    return [CompetitionTeamOut(**row) for row in rows]


@router.post("/cohorts/{cohort_id}/teams", response_model=CompetitionTeamOut, status_code=status.HTTP_201_CREATED)
async def post_cohort_team(
    cohort_id: uuid.UUID, body: CompetitionTeamCreateIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    await _get_cohort_or_404(db, cohort_id)
    team = await team_service.create_empty_team(
        db, cohort_id=cohort_id, name=body.name, created_by=current.id, is_observer=body.is_observer,
    )
    await db.commit()
    await db.refresh(team)
    return CompetitionTeamOut(
        id=team.id, name=team.name, cohort_id=team.cohort_id, is_observer=team.is_observer,
        join_code=getattr(team, "join_code", None), roster_team_id=getattr(team, "roster_team_id", None),
    )


@router.patch("/teams/{team_id}", response_model=CompetitionTeamOut)
async def patch_team(team_id: uuid.UUID, body: CompetitionTeamRenameIn, db: AsyncSession = Depends(get_db)):
    await team_service.rename_team(db, team_id=team_id, name=body.name)
    await db.commit()
    rows = await team_service.list_teams_with_members(db, cohort_id=(await _team_cohort_id(db, team_id)))
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await team_service.delete_team(db, team_id=team_id)
    await db.commit()


@router.post("/teams/{team_id}/unlock", response_model=CompetitionTeamOut)
async def unlock_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Reopens a team's checklist after "Final Submit" — the only way that
    lock ever clears (see `Team.final_locked_at`'s own docstring). Already
    gated ops-only by this whole router's `require_lms_content` dependency
    — no separate check needed here."""
    await team_service.unlock_team_submission(db, team_id=team_id)
    await db.commit()
    rows = await team_service.list_teams_with_members(db, cohort_id=(await _team_cohort_id(db, team_id)))
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.get("/teams/{team_id}/checkpoints", response_model=list[TeamCheckpointStateOut])
async def get_team_checkpoints(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """This team's checkpoint gates with their lock states — backs the ops
    Teams tab's gate badges + per-gate unlock buttons. Same ops-only gating
    as everything else on this router."""
    return await team_service.team_checkpoint_states(db, team_id=team_id)


@router.post("/teams/{team_id}/unlock-checkpoint/{checkpoint_item_id}", response_model=CompetitionTeamOut)
async def unlock_team_checkpoint(
    team_id: uuid.UUID, checkpoint_item_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    """Reopens one checkpoint gate for a team and cascades down: every
    checkpoint at or after it on the team's checklist resets too, plus
    the team's final lock — so the team can re-work and re-lock forward
    again. Same ops-only gating as `unlock_team` above."""
    await team_service.unlock_team_checkpoint(db, team_id=team_id, checkpoint_item_id=checkpoint_item_id)
    await db.commit()
    rows = await team_service.list_teams_with_members(db, cohort_id=(await _team_cohort_id(db, team_id)))
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.post("/teams/{team_id}/observer-reset", response_model=CompetitionTeamOut)
async def observer_reset_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Reset an observer team's deliverables and judging scores, unlocking the team."""
    await team_service.reset_observer_team(db, team_id=team_id)
    await db.commit()
    cohort_id = await _team_cohort_id(db, team_id)
    rows = await team_service.list_teams_with_members(db, cohort_id=cohort_id)
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.post("/teams/{team_id}/regenerate-code", response_model=CompetitionTeamOut)
async def regenerate_team_code(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Ops regen of a team's student-shareable join code."""
    await team_service.regenerate_team_code(db, team_id=team_id)
    await db.commit()
    cohort_id = await _team_cohort_id(db, team_id)
    rows = await team_service.list_teams_with_members(db, cohort_id=cohort_id)
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.post("/teams/{team_id}/members", response_model=CompetitionTeamOut, status_code=status.HTTP_201_CREATED)
async def post_team_member(
    team_id: uuid.UUID, body: CompetitionTeamMemberIn, db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    registration_id: uuid.UUID | None = None
    if body.user_id is not None:
        await team_service.add_existing_member(db, team_id=team_id, user_id=body.user_id)
    elif body.full_name and body.email:
        _user, registration_id = await team_service.register_and_add_member(
            db, team_id=team_id, full_name=body.full_name, email=body.email,
            phone=body.phone, school=body.school, send_welcome_email=body.send_welcome_email,
        )
    else:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide either user_id, or full_name and email")
    await db.commit()
    if registration_id is not None and body.send_ticket_email:
        await safe_enqueue(arq_redis, "send_ticket_email", str(registration_id))
    cohort_id = await _team_cohort_id(db, team_id)
    rows = await team_service.list_teams_with_members(db, cohort_id=cohort_id)
    return next(CompetitionTeamOut(**r) for r in rows if r["id"] == team_id)


@router.delete("/teams/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_member(team_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await team_service.remove_member(db, team_id=team_id, user_id=user_id)
    await db.commit()


async def _team_cohort_id(db: AsyncSession, team_id: uuid.UUID) -> uuid.UUID:
    from app.models.team import Team
    team = await db.get(Team, team_id)
    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team.cohort_id


# ── Team analytics (2026-09-16) ─────────────────────────────────────────
# One payload for the Judging page's Analysis tab. Read-only and cohort
# -scoped, same as every other progress view here; deliberately team-first,
# since per-student checklist progress already has its own surface (the
# cohort's LMS > Progress tab).

@router.get("/cohorts/{cohort_id}/team-analytics", response_model=CompetitionAnalyticsOut)
async def get_cohort_team_analytics(
    cohort_id: uuid.UUID,
    mode: Literal["participant", "observer", "all"] = Query("participant"),
    db: AsyncSession = Depends(get_db),
):
    result = await analytics_service.cohort_team_analytics(db, cohort_id=cohort_id, mode=mode)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return CompetitionAnalyticsOut(**result)


# ── Registration import, progression ────────────────────────────────────

@router.post("/cohorts/{cohort_id}/registration-import/preview", response_model=CompetitionImportPreviewOut)
async def post_cohort_registration_import_preview(
    cohort_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
):
    """Parse the sheet and report every row's issues — writes nothing. Ops
    reviews and fixes flagged rows (a malformed email, most often) in the
    browser, then calls .../confirm with the corrected rows to actually
    import. Safe to call as many times as needed on the same or a re-picked
    file while ops is still fixing things."""
    await _get_cohort_or_404(db, cohort_id)
    file_bytes = await file.read()
    rows = await import_service.preview_registration_sheet_for_cohort(
        db, cohort_id=cohort_id, file_bytes=file_bytes, filename=file.filename,
    )
    return CompetitionImportPreviewOut(
        rows=[CompetitionImportPreviewRowOut(**r) for r in import_service.preview_rows_as_dicts(rows)],
    )


@router.post("/cohorts/{cohort_id}/registration-import/confirm", response_model=CompetitionImportResultOut)
async def post_cohort_registration_import_confirm(
    cohort_id: uuid.UUID, body: CompetitionImportConfirmIn, db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    """Actually commits. Re-checks required fields (team/member/email
    present) and refuses a row missing one of those — but a still-malformed
    email is only ever a warning, so a row ops leaves flagged (a bad email
    is fine to keep, fix later) still gets written.

    When `body.async_mode` is True (used by the Roster UI for large sheets),
    persists an `ImportBatch` row and enqueues
    `run_competition_registration_import_job` on ARQ so DB creation and
    throttled onboarding/ticket emails execute asynchronously in the worker
    while the UI polls `/registration-import/batches/{batch_id}`."""
    from app.models.sessions.import_batch import ImportBatch

    await _get_cohort_or_404(db, cohort_id)
    rows = [
        {"row_number": r.row_number, "raw": r.model_dump(exclude={"row_number"})}
        for r in body.rows
    ]
    if body.async_mode:
        initial_summary = {"total": len(rows), "created": 0, "matched": 0, "error": 0}
        batch = ImportBatch(
            id=uuid.uuid4(),
            uploaded_by=current.id,
            source="competition",
            cohort_id=cohort_id,
            filename="competition_roster",
            status="queued",
            counts={
                "rows_in": rows,
                "options": {
                    "send_ticket_email": body.send_ticket_email,
                    "send_welcome_email": body.send_welcome_email,
                },
                "progress": {"processed": 0, "total": len(rows)},
                "summary": initial_summary,
                "rows": [],
            },
        )
        db.add(batch)
        await db.commit()
        dispatch_status = await safe_enqueue(
            arq_redis, "run_competition_registration_import_job", str(batch.id),
        )
        return CompetitionImportResultOut(
            batch_id=batch.id,
            status="queued" if dispatch_status == "queued" else "running",
            progress={"processed": 0, "total": len(rows)},
            summary=initial_summary,
            rows=[],
        )

    results = await import_service.import_registrations(
        db, cohort_id=cohort_id, rows=rows, send_welcome_email=body.send_welcome_email,
    )
    await db.commit()
    if body.send_ticket_email:
        for r in results:
            if r.disposition == "created" and r.registration_id is not None:
                await safe_enqueue(arq_redis, "send_ticket_email", str(r.registration_id))
    return CompetitionImportResultOut(
        status="committed",
        summary=import_service.summarize(results),
        rows=[
            CompetitionImportRowOut(**{k: v for k, v in r.items() if k != "registration_id"})
            for r in import_service.results_as_dicts(results)
        ],
    )


@router.get("/cohorts/{cohort_id}/registration-import/batches/{batch_id}", response_model=CompetitionImportResultOut)
async def get_cohort_registration_import_batch_status(
    cohort_id: uuid.UUID, batch_id: uuid.UUID, db: AsyncSession = Depends(get_db),
):
    """Polls the status and results of an async ARQ competition roster import batch."""
    from app.models.sessions.import_batch import ImportBatch

    await _get_cohort_or_404(db, cohort_id)
    batch = await db.get(ImportBatch, batch_id)
    if batch is None or batch.cohort_id != cohort_id or batch.source != "competition":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Import batch not found")
    counts = batch.counts or {}
    return CompetitionImportResultOut(
        batch_id=batch.id,
        status=batch.status,
        progress=counts.get("progress"),
        error=counts.get("error"),
        summary=counts.get("summary", {"total": 0, "created": 0, "matched": 0, "error": 0}),
        rows=[CompetitionImportRowOut(**r) for r in counts.get("rows", [])],
    )


@router.get("/cohorts/{cohort_id}/assignable-students", response_model=CompetitionAssignableStudentsPage)
async def get_cohort_assignable_students(
    cohort_id: uuid.UUID, q: str | None = None, invite_code: str | None = None,
    registered_only: bool = False,
    team_status: Literal["all", "has_team", "no_team"] = "all",
    lms_status: Literal["all", "has_access", "no_access"] = "all",
    login_status: Literal["all", "never", "has_logged_in"] = "all",
    mode: Literal["all", "student", "observer", "staff"] = "student",
    role: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort: Literal["full_name", "card_number", "created_at", "email"] = "full_name",
    direction: Literal["asc", "desc"] = "asc",
    db: AsyncSession = Depends(get_db),
):
    """Backs the Assign tab's search + filters (2026-09-15: `registered_only`,
    `team_status`, `lms_status` replaced the original boolean
    `unassigned_only`; `login_status` added 2026-09-16; paginated +
    `staff` mode + `role` + sorting added 2026-10 rebuild). See
    `student_search_service.search_cohort_assignable_students` for what each
    does — `registered_only` switches the candidate set between "matches my
    search, anywhere on the platform" (the original behavior, for finding an
    unregistered invite-code signup to assign) and "actually registered in
    this cohort" (for viewing the roster itself); `team_status`/
    `login_status` filter either set further. The tab's "In program" state
    reads `registered`, not `lms_access` — registration and LMS assignment
    are created interchangeably by every assign path."""
    await _get_cohort_or_404(db, cohort_id)
    result = await student_search_service.search_cohort_assignable_students(
        db, cohort_id=cohort_id, q=q, invite_code=invite_code, registered_only=registered_only,
        team_status=team_status, lms_status=lms_status, login_status=login_status, mode=mode,
        role=role, page=page, page_size=page_size, sort=sort, direction=direction,
    )
    return CompetitionAssignableStudentsPage(**result)


@router.post("/cohorts/{cohort_id}/assign-students", response_model=CompetitionAssignStudentsOut)
async def post_cohort_assign_students(
    cohort_id: uuid.UUID, body: CompetitionAssignStudentsIn, db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    """Assign tab (2026-09-14): ops has already found these students via
    `/lms/admin/students` search (they self-registered with an invite code)
    and typed in a Team ID per row — this registers each one into `cohort`
    and adds them to that team, creating the team if it's new. See
    `registration_import.assign_existing_students`'s own docstring for why
    this exists alongside the CSV roster-import path rather than replacing
    it.

    Same `send_ticket_email` rule as the CSV confirm endpoint: only a row
    that actually created a new Registration (`disposition == "created"`)
    gets a ticket-email job — a row that just moved an already-registered
    student to a different team has nothing new to ticket."""
    await _get_cohort_or_404(db, cohort_id)
    rows = [
        {"row_number": i, "user_id": r.user_id, "team_id": r.team_id, "team_name": r.team_name}
        for i, r in enumerate(body.rows, start=1)
    ]
    results = await import_service.assign_existing_students(
        db, cohort_id=cohort_id, rows=rows, send_welcome_email=body.send_welcome_email,
    )
    await db.commit()
    if body.send_ticket_email:
        for r in results:
            if r.disposition == "created" and r.registration_id is not None:
                await safe_enqueue(arq_redis, "send_ticket_email", str(r.registration_id))
    return CompetitionAssignStudentsOut(
        summary=import_service.summarize_assign_results(results),
        rows=[
            CompetitionAssignStudentRowOut(**{k: v for k, v in r.items() if k != "registration_id"})
            for r in import_service.assign_results_as_dicts(results)
        ],
    )


@router.post("/cohorts/{cohort_id}/register-users", response_model=CompetitionAssignStudentsOut)
async def post_cohort_register_users(
    cohort_id: uuid.UUID, body: CompetitionRegisterUsersIn, db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    """Assign tab add-to-program (2026-10 rebuild): registers each account
    into `cohort` WITHOUT putting them on a team (the `no_team` backlog).
    Registration + LMS assignment are created interchangeably in one
    transaction; accounts without a Contact get one auto-created; staff
    (non-student) accounts get the `observer` role appended + a
    `mode="observer"` assignment. Idempotent per user: re-adding an
    already-registered account reports `matched`.

    Same ticket-email rule as assign-students: only a genuinely new
    Registration gets a job."""
    await _get_cohort_or_404(db, cohort_id)
    results = await import_service.register_existing_users(
        db, cohort_id=cohort_id,
        user_ids=[r for r in body.user_ids],
        send_welcome_email=body.send_welcome_email,
    )
    await db.commit()
    if body.send_ticket_email:
        for r in results:
            if r.disposition == "created" and r.registration_id is not None:
                await safe_enqueue(arq_redis, "send_ticket_email", str(r.registration_id))
    return CompetitionAssignStudentsOut(
        summary=import_service.summarize_assign_results(results),
        rows=[
            CompetitionAssignStudentRowOut(
                row_number=r.row_number, user_id=r.user_id, team_id=None,
                team_name=None, disposition=r.disposition, reason=r.reason,
            )
            for r in results
        ],
    )


@router.post("/cohorts/{cohort_id}/advance-teams", response_model=list[CompetitionAdvanceResultOut])
async def post_cohort_advance_teams(
    cohort_id: uuid.UUID, body: CompetitionAdvanceTeamsIn, db: AsyncSession = Depends(get_db),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    await _get_cohort_or_404(db, cohort_id)
    results = await progression_service.advance_teams(
        db, team_ids=body.team_ids, from_cohort_id=cohort_id, to_cohort_id=body.to_cohort_id,
        send_welcome_email=body.send_welcome_email,
    )
    await db.commit()
    # Same "only genuinely new registrations get a ticket job" rule the bulk
    # import confirm endpoint already follows — a member already registered
    # in the target cohort (idempotent re-run) most likely already has one.
    if body.send_ticket_email:
        for r in results:
            for registration_id in r.new_registration_ids:
                await safe_enqueue(arq_redis, "send_ticket_email", str(registration_id))
    return [
        CompetitionAdvanceResultOut(**{k: v for k, v in r.items() if k != "new_registration_ids"})
        for r in progression_service.results_as_dicts(results)
    ]


# ── Leaderboard, publish, export ────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/leaderboard", response_model=list[CompetitionLeaderboardRowOut])
async def get_cohort_leaderboard(
    cohort_id: uuid.UUID,
    mode: Literal["participant", "observer", "all"] = Query("participant"),
    db: AsyncSession = Depends(get_db),
):
    await _get_cohort_or_404(db, cohort_id)
    try:
        rows = await judging_service.leaderboard(db, cohort_id=cohort_id, mode=mode)
        return [CompetitionLeaderboardRowOut(**row) for row in rows]
    except Exception as exc:
        logger.exception("Failed to get leaderboard for cohort %s: %s", cohort_id, exc)
        raise


@router.get("/cohorts/{cohort_id}/export-top20", response_model=list[CompetitionLeaderboardRowOut])
async def get_cohort_export_top20(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    rows = await judging_service.export_top(db, cohort_id=cohort_id, limit=20)
    return [CompetitionLeaderboardRowOut(**row) for row in rows]


@router.get("/cohorts/{cohort_id}/export.xlsx")
async def export_cohort_results_workbook(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """A single spreadsheet for offline review: every team's rank/average/
    each judge's own score on one sheet, every team's link submissions
    (who sent it, when) on another. Same numbers as the Results tab and
    judge team-detail view, just handed over as a file."""
    cohort = await _get_cohort_or_404(db, cohort_id)
    content = await export_service.export_results_workbook(db, cohort_id=cohort_id)
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in cohort.name).strip() or cohort_id
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name} results.xlsx"'},
    )


@router.get("/cohorts/{cohort_id}/quiz-answers.xlsx")
async def export_cohort_quiz_answers_workbook(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Exports all quiz answers for the cohort, grouped by team and quiz,
    with an overview summary sheet and per-question answer breakdown sheet."""
    cohort = await _get_cohort_or_404(db, cohort_id)
    content = await export_service.export_quiz_answers_workbook(db, cohort_id=cohort_id)
    safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in cohort.name).strip() or cohort_id
    return Response(
        content=content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe_name} quiz answers.xlsx"'},
    )


@router.get("/cohorts/{cohort_id}/publication", response_model=CompetitionPublicationOut)
async def get_cohort_publication(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    row = await judging_service.get_publication(db, cohort_id=cohort_id)
    settings = row.visibility_settings if row and row.visibility_settings else {}
    return CompetitionPublicationOut(
        published=row is not None,
        published_at=row.published_at if row else None,
        visibility_settings=CompetitionVisibilitySettings(**settings),
    )


@router.post("/cohorts/{cohort_id}/publish", response_model=CompetitionPublicationOut)
async def post_cohort_publish(
    cohort_id: uuid.UUID,
    body: CompetitionPublishIn | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    await _get_cohort_or_404(db, cohort_id)
    settings = body.visibility_settings.model_dump() if body else None
    row = await judging_service.publish(db, cohort_id=cohort_id, actor_user_id=current.id, visibility_settings=settings)
    await db.commit()
    row_settings = row.visibility_settings if row and row.visibility_settings else {}
    return CompetitionPublicationOut(
        published=True,
        published_at=row.published_at,
        visibility_settings=CompetitionVisibilitySettings(**row_settings),
    )


@router.put("/cohorts/{cohort_id}/publication/settings", response_model=CompetitionPublicationOut)
async def put_cohort_publication_settings(
    cohort_id: uuid.UUID,
    body: CompetitionPublishIn,
    db: AsyncSession = Depends(get_db),
):
    await _get_cohort_or_404(db, cohort_id)
    row = await judging_service.update_publication_settings(
        db, cohort_id=cohort_id, visibility_settings=body.visibility_settings.model_dump()
    )
    await db.commit()
    row_settings = row.visibility_settings if row and row.visibility_settings else {}
    return CompetitionPublicationOut(
        published=True,
        published_at=row.published_at,
        visibility_settings=CompetitionVisibilitySettings(**row_settings),
    )


@router.post("/cohorts/{cohort_id}/unpublish", status_code=status.HTTP_204_NO_CONTENT)
async def post_cohort_unpublish(cohort_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    await _get_cohort_or_404(db, cohort_id)
    unpublished = await judging_service.unpublish(db, cohort_id=cohort_id)
    if not unpublished:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This cohort's results aren't published")
    await db.commit()


# ── Certificates (2026-09) ───────────────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/certificates/recipients", response_model=CompetitionCertificateRecipientsSummaryOut)
async def get_cohort_certificate_recipients(
    cohort_id: uuid.UUID,
    filter: Literal["locked_only", "participation", "at_least_one", "all_completed", "all"] = Query("all"),
    db: AsyncSession = Depends(get_db),
):
    await _get_cohort_or_404(db, cohort_id)
    result = await certificates_service.get_cohort_certificate_recipients(db, cohort_id=cohort_id, filter_type=filter)
    return CompetitionCertificateRecipientsSummaryOut(**result)


@router.post("/cohorts/{cohort_id}/certificates/send", response_model=CompetitionCertificateSendResultOut)
async def post_cohort_certificates_send(
    cohort_id: uuid.UUID,
    body: CompetitionCertificateSendIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    await _get_cohort_or_404(db, cohort_id)

    # Quickly resolve recipient count to report back to admin
    recip_summary = await certificates_service.get_cohort_certificate_recipients(
        db, cohort_id=cohort_id, filter_type=body.filter
    )
    target_ids: list[str] = []
    selected_set = {str(r) for r in body.registration_ids} if body.registration_ids else None
    for r in recip_summary.get("recipients", []):
        rid_str = str(r["registration_id"])
        if selected_set is not None and rid_str not in selected_set:
            continue
        if body.skip_already_issued and r.get("certificate_issued"):
            continue
        target_ids.append(rid_str)

    if not target_ids:
        return CompetitionCertificateSendResultOut(
            status="sent",
            sent_count=0,
            skipped_count=recip_summary.get("total_students", 0),
            total_targeted=0,
            recipient_names=[],
            errors=[],
        )

    # If requested to save email template, persist it immediately
    if body.save_email_to_template and body.template_id:
        try:
            tmpl_uuid = uuid.UUID(str(body.template_id))
            from app.models.competitions.certificates import ProgramCertificateTemplate
            tmpl = await db.get(ProgramCertificateTemplate, tmpl_uuid)
            if tmpl:
                if body.custom_email_subject is not None:
                    tmpl.email_subject = body.custom_email_subject.strip() or None
                if body.custom_email_body is not None:
                    tmpl.email_body = body.custom_email_body.strip() or None
                await db.commit()
        except Exception as exc:
            logger.warning("Could not persist email template synchronously: %s", exc)

    status_result = await safe_enqueue(
        arq_redis,
        "send_cohort_certificates_job",
        str(cohort_id),
        str(current.id),
        filter_type=body.filter,
        registration_ids=target_ids,
        theme=body.theme,
        template_id=body.template_id,
        skip_already_issued=body.skip_already_issued,
        custom_email_subject=body.custom_email_subject,
        custom_email_body=body.custom_email_body,
        save_email_to_template=False,
        force_certificate_type=body.force_certificate_type,
    )

    return CompetitionCertificateSendResultOut(
        status=status_result,
        sent_count=0,
        skipped_count=0,
        total_targeted=len(target_ids),
        recipient_names=[],
        errors=[],
    )


@router.get("/cohorts/{cohort_id}/certificates/download")
async def download_cohort_certificates(
    cohort_id: uuid.UUID,
    filter: Literal["locked_only", "participation", "at_least_one", "all_completed", "all"] = Query("at_least_one"),
    theme: str = Query("dark"),
    template_id: str | None = Query(None),
    registration_ids: list[uuid.UUID] | None = Query(None),
    force_certificate_type: Literal["completion", "participation"] | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Download merged certificate PDF for students matching the filter or selected registration IDs."""
    await _get_cohort_or_404(db, cohort_id)
    content, filename = await certificates_service.render_cohort_certificates_pdf(
        db,
        cohort_id=cohort_id,
        filter_type=filter,
        theme=theme,
        template_id=template_id,
        registration_ids=registration_ids,
        force_certificate_type=force_certificate_type,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cohorts/{cohort_id}/certificates/download")
async def download_cohort_certificates_post(
    cohort_id: uuid.UUID,
    body: CompetitionCertificateDownloadIn,
    db: AsyncSession = Depends(get_db),
):
    """Download merged certificate PDF for students matching the filter or selected registration IDs."""
    await _get_cohort_or_404(db, cohort_id)
    content, filename = await certificates_service.render_cohort_certificates_pdf(
        db,
        cohort_id=cohort_id,
        filter_type=body.filter,
        theme=body.theme,
        template_id=body.template_id,
        registration_ids=body.registration_ids,
        force_certificate_type=body.force_certificate_type,
    )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/cohorts/{cohort_id}/certificates/test-email")
async def post_cohort_certificates_test_email(
    cohort_id: uuid.UUID,
    body: CompetitionCertificateTestEmailIn,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_lms_content),
):
    """Send a test certificate email (with a sample PDF) to the given address.
    Uses the exact template/theme/subject/body config currently selected in the
    modal. Does NOT write any Certificate record or modify registrations.
    """
    await _get_cohort_or_404(db, cohort_id)
    result = await certificates_service.send_test_certificate_email(
        db,
        cohort_id=cohort_id,
        to_email=body.to_email,
        recipient_name=body.recipient_name,
        theme=body.theme,
        template_id=body.template_id,
        certificate_type=body.certificate_type,
        custom_email_subject=body.custom_email_subject,
        custom_email_body=body.custom_email_body,
    )
    return result


# ── Submission Windows & Timing Adjustments ─────────────────────────────

@router.get("/cohorts/{cohort_id}/submission-windows")
async def get_cohort_submission_windows(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve configured submission time windows for a cohort."""
    cohort = await _get_cohort_or_404(db, cohort_id)
    return cohort.submission_windows or []


@router.put("/cohorts/{cohort_id}/submission-windows")
async def update_cohort_submission_windows(
    cohort_id: uuid.UUID,
    body: CohortSubmissionWindowsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Save or update submission time windows for a cohort."""
    from sqlalchemy.orm.attributes import flag_modified
    cohort = await _get_cohort_or_404(db, cohort_id)
    cohort.submission_windows = [w.model_dump() for w in body.windows]
    flag_modified(cohort, "submission_windows")
    await db.commit()
    return cohort.submission_windows


@router.patch("/cohorts/{cohort_id}/teams/{team_id}/timing-adjustment", response_model=TeamScoreBreakdownOut)
async def update_team_timing_adjustment(
    cohort_id: uuid.UUID,
    team_id: uuid.UUID,
    body: TeamTimingAdjustmentUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Manual Ops override for a team's timing bonus/deduction points."""
    team = await db.get(Team, team_id)
    if team is None or team.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found in this cohort")
    team.timing_adjustment_override = body.override_points
    team.timing_adjustment_notes = body.notes
    await db.commit()
    breakdown = await judging_service.get_team_score_breakdown(db, cohort_id=cohort_id, team_id=team_id)
    return TeamScoreBreakdownOut(**breakdown)


# ── Score Breakdown & Comments Inspector ────────────────────────────────

@router.get("/cohorts/{cohort_id}/teams/{team_id}/score-breakdown", response_model=TeamScoreBreakdownOut)
async def get_team_score_breakdown(
    cohort_id: uuid.UUID,
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Returns the full evaluation breakdown per judge for inspection,
    including individual criteria scores, criterion comments, and judge notes."""
    breakdown = await judging_service.get_team_score_breakdown(db, cohort_id=cohort_id, team_id=team_id)
    return TeamScoreBreakdownOut(**breakdown)


# ── Operations Scoring ─────────────────────────────────────────────────

@router.put(
    "/cohorts/{cohort_id}/teams/{team_id}/ops-score",
    response_model=OpsScoreOut,
)
async def put_team_ops_score(
    cohort_id: uuid.UUID,
    team_id: uuid.UUID,
    body: OpsScoreIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Operations team — submit or update the operations-graded criterion
    scores for a team. These are stored directly on the team row and
    combined with the judge average on the leaderboard."""
    if await judging_service.is_published(db, cohort_id=cohort_id):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Results are published — scoring is closed for this stage")

    team = await db.get(Team, team_id)
    if team is None or team.cohort_id != cohort_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Team not found in this cohort")

    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    rubric_tuple = await judging_service.get_rubric(db, cohort_id=cohort.id)
    criteria = rubric_tuple[1] if rubric_tuple else []
    ops_criteria = {c.key: c for c in criteria if getattr(c, "scored_by", "judge") == "operations"}

    from datetime import datetime, timezone
    stored: dict[str, float] = dict(team.ops_criterion_scores or {})
    if body.criterion_scores:
        if not ops_criteria:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This rubric has no operations-graded criteria")

        leaf_spec: dict[str, tuple[str, str, int]] = {}  # leaf key -> (parent key, label, max)
        for c in ops_criteria.values():
            subs = getattr(c, "sub_criteria", None) or []
            if subs:
                for s in subs:
                    leaf_spec[f"{c.key}.{s['key']}"] = (c.key, s["label"], int(s["max_points"]))
            else:
                leaf_spec[c.key] = (c.key, c.label, c.max_points)
        for key in body.criterion_scores:
            if key not in leaf_spec:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{key}' is not an operations score — submit sub-criteria leaves (e.g. 'mission.clarity')",
                )
        touched_parents = {leaf_spec[k][0] for k in body.criterion_scores}
        for parent_key in touched_parents:
            c = ops_criteria[parent_key]
            subs = getattr(c, "sub_criteria", None) or []
            if subs:
                missing = [s["key"] for s in subs if f"{parent_key}.{s['key']}" not in body.criterion_scores]
                if missing:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"'{c.label}' needs all sub-scores ({', '.join(missing)} missing)",
                    )
        for key, pts in body.criterion_scores.items():
            _parent, label, max_pts = leaf_spec[key]
            if not (0 <= pts <= max_pts):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"'{label}' must be between 0 and {max_pts}",
                )

        stored = dict(body.criterion_scores)
        for parent_key in touched_parents:
            c = ops_criteria[parent_key]
            subs = getattr(c, "sub_criteria", None) or []
            if subs:
                stored[parent_key] = float(sum(body.criterion_scores[f"{parent_key}.{s['key']}"] for s in subs))

    team.ops_criterion_scores = stored
    team.ops_criterion_notes = body.notes
    team.ops_scored_by = current_user.id
    team.ops_scored_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(team)

    return OpsScoreOut(
        team_id=team.id,
        ops_criterion_scores=team.ops_criterion_scores or {},
        ops_criterion_notes=team.ops_criterion_notes,
        ops_scored_at=team.ops_scored_at,
        ops_scored_by_name=current_user.full_name or current_user.email,
    )
