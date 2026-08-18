"""Operate mission routes (Operate v2, Stage 7C) — `/missions/operate/*`.
Registered before `/missions/{mission_id}` in `routers/missions/__init__.py`
for the same static-before-dynamic reason as `/missions/design`,
`/missions/admin`, `/missions/graph` and `/missions/teams`.

Authorization reuses `routers/missions/student.py::_own_attempt` — the solo
student, or any member of a team attempt's frozen roster. Same posture as
the design mission: nothing here is operate-specific about *who* may act on
an attempt. Crew role gating happens one level down, at command-issue time,
and is a coordination aid rather than an access control (see `crew.py`).

The briefing route is the exception: it takes a `mission_id`, not an
attempt, because a student reads it *before* committing to a flight.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember, MissionVariant
from app.models.user import User
from app.routers.missions.student import _own_attempt
from app.schemas.missions_operate import (
    AnomalyStateOut,
    AssignCrewRoleIn,
    BriefingOut,
    CommandEventOut,
    CrewMemberOut,
    DebriefOut,
    FinishOperationOut,
    HandbookOut,
    IssueCommandIn,
    IssueCommandOut,
    ObjectiveOut,
    OperateStateOut,
    OrbitPhaseOut,
    SpacecraftLogOut,
    SubsystemCardOut,
)
from app.services.missions.operate import anomalies as lib
from app.services.missions.operate import debrief as debrief_mod
from app.services.missions.operate.commands import command_reference
from app.services.missions.operate.crew import role_brief
from app.services.missions.operate.orbit import orbit_summary
from app.services.missions.operate.telemetry import (
    compute_telemetry,
    flight_rules,
    subsystem_detail,
)
from app.services.missions.verifiers.operate import (
    ASSUMPTIONS,
    FlightContext,
    assign_crew_role,
    attempt_crew,
    attempt_events,
    briefing,
    finish_operation,
    flight_context,
    issue_command,
)

router = APIRouter(prefix="/missions/operate", tags=["missions-operate"])


async def _own_operate_attempt(db: AsyncSession, attempt_id: uuid.UUID, user: User) -> MissionAttempt:
    attempt = await _own_attempt(db, attempt_id, user)
    mission = await db.get(Mission, attempt.mission_id)
    if mission is None or mission.kind != "operate":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")
    return attempt


async def _state_out(db: AsyncSession, attempt: MissionAttempt, ctx: FlightContext) -> OperateStateOut:
    """The whole console in one payload. Everything below is recomputed
    from the event log — nothing derived is read from the database."""
    mission = await db.get(Mission, attempt.mission_id)
    state = ctx.live_state()
    outcome = ctx.outcome_for(state)
    phase = state.phase

    crew = attempt_crew(attempt)
    roster: list[CrewMemberOut] = []
    is_team = attempt.team_id is not None
    if is_team:
        member_ids = (await db.execute(
            select(MissionAttemptMember.user_id).where(MissionAttemptMember.attempt_id == attempt.id)
        )).scalars().all()
        role_by_user = {uid: role for role, uid in crew.items()}
        for uid in member_ids:
            member = await db.get(User, uid)
            roster.append(CrewMemberOut(
                user_id=uid, name=member.full_name if member else "Unknown", role=role_by_user.get(str(uid)),
            ))

    return OperateStateOut(
        attempt_id=attempt.id,
        mission_id=mission.id,
        variant_id=ctx.variant.id,
        variant_label=ctx.variant.label,
        attempt_status=attempt.status,
        sim_t=round(state.t, 1),
        session_seconds=round(ctx.orbit.session_seconds, 1),
        time_compression=ctx.orbit.time_compression,
        expired=ctx.expired,
        phase=OrbitPhaseOut(
            orbit_number=phase.orbit_number,
            orbit_fraction=round(phase.orbit_fraction, 4),
            label=phase.label,
            sunlit=phase.sunlit,
            in_pass=phase.in_pass,
            in_saa=phase.in_saa,
            elevation_deg=phase.elevation_deg,
            seconds_to_next_aos=round(phase.seconds_to_next_aos, 1),
            seconds_to_los=round(phase.seconds_to_los, 1),
            seconds_to_eclipse=round(phase.seconds_to_eclipse, 1),
            seconds_to_sunrise=round(phase.seconds_to_sunrise, 1),
        ),
        orbit=orbit_summary(ctx.orbit),
        telemetry=compute_telemetry(state, ctx.params),
        subsystems=[SubsystemCardOut(**card) for card in subsystem_detail(state, ctx.params)],
        events=[CommandEventOut(**e) for e in attempt_events(attempt)],
        spacecraft_log=[SpacecraftLogOut(**entry) for entry in state.log],
        anomalies=[
            AnomalyStateOut(
                key=a.key, title=a.title, subsystem=a.subsystem, origin=a.origin,
                raised_t=a.raised_t, cleared_t=a.cleared_t, outcome=a.outcome,
            )
            for a in outcome.anomalies
        ],
        objectives=[
            ObjectiveOut(
                key=o.key, label=o.label, detail=o.detail, target=o.target,
                actual=o.actual, fraction=round(o.fraction, 3), met=o.met,
            )
            for o in outcome.objectives
        ],
        score=outcome.score,
        objectives_score=outcome.objectives_score,
        performance_score=outcome.performance_score,
        penalty_points=outcome.penalty_points,
        pass_threshold=ctx.pass_threshold,
        is_team=is_team,
        crew=crew,
        roster=roster,
        spacecraft_source=ctx.source_notes,
    )


@router.get("/briefing/{mission_id}", response_model=BriefingOut)
async def get_briefing(
    mission_id: uuid.UUID, variant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Pre-flight briefing (Stage 7C-7). No attempt is created — a student
    can read this as often as they like without spending a retry, which is
    the whole point of splitting it out from the console."""
    mission = await db.get(Mission, mission_id)
    if mission is None or mission.kind != "operate":
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")

    if variant_id is not None:
        variant = await db.get(MissionVariant, variant_id)
        if variant is None or variant.mission_id != mission.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variant not found")
    else:
        variant = (await db.execute(
            select(MissionVariant).where(MissionVariant.mission_id == mission.id)
            .order_by(MissionVariant.position)
        )).scalars().first()
        if variant is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="This mission has no difficulty variants")

    return BriefingOut(
        mission_id=mission.id,
        **briefing(variant, mission_title=mission.title, mission_summary=mission.summary),
    )


@router.get("/attempts/{attempt_id}", response_model=OperateStateOut)
async def get_operate_state(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    ctx = await flight_context(db, attempt)
    return await _state_out(db, attempt, ctx)


@router.get("/attempts/{attempt_id}/handbook", response_model=HandbookOut)
async def get_handbook(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """The Ops Handbook (Stage 7C-7, D-d) — the anomaly library rendered as
    flight rules, available *during* flight at every difficulty. Real
    flight teams work from a rules document; treating that as cheating
    would teach the wrong lesson. What difficulty controls is how much of
    the response is written down, via `config.handbook_disclosure`."""
    attempt = await _own_operate_attempt(db, attempt_id, current)
    ctx = await flight_context(db, attempt)
    return HandbookOut(
        disclosure=ctx.disclosure,
        entries=lib.handbook(disclosure=ctx.disclosure),
        commands=command_reference(),
        flight_rules=flight_rules(),
        crew_roles=role_brief(),
        assumptions=ASSUMPTIONS,
    )


@router.post("/attempts/{attempt_id}/crew", response_model=OperateStateOut)
async def set_crew_role(
    attempt_id: uuid.UUID, body: AssignCrewRoleIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """Any team member may take or vacate their own seat — same
    low-ceremony self-service as the rest of this platform's team
    formation. Solo attempts have nothing to assign."""
    attempt = await _own_operate_attempt(db, attempt_id, current)
    if attempt.team_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Crew roles only apply to team attempts")
    ctx = await flight_context(db, attempt)
    await assign_crew_role(db, attempt=attempt, role=body.role, user_id=current.id)
    await db.commit()
    return await _state_out(db, attempt, ctx)


@router.post("/attempts/{attempt_id}/command", response_model=IssueCommandOut)
async def send_command(
    attempt_id: uuid.UUID, body: IssueCommandIn,
    db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    ctx = await flight_context(db, attempt)
    event = await issue_command(db, attempt=attempt, raw_command=body.command, issued_by=current.id, ctx=ctx)
    await db.commit()
    state = await _state_out(db, attempt, ctx)
    return IssueCommandOut(event=CommandEventOut(**event), state=state)


@router.post("/attempts/{attempt_id}/finish", response_model=FinishOperationOut)
async def finish(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    attempt = await _own_operate_attempt(db, attempt_id, current)
    ctx = await flight_context(db, attempt)
    decided, outcome = await finish_operation(db, attempt=attempt, ctx=ctx)
    await db.commit()
    state = await _state_out(db, decided, ctx)
    return FinishOperationOut(passed=outcome.passed, score=outcome.score, state=state)


@router.get("/attempts/{attempt_id}/debrief", response_model=DebriefOut)
async def get_debrief(
    attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    """The replay (Stage 7C-8). Served from the trace frozen at finish
    time, not re-simulated — a debrief opened next week must show the
    flight that was actually graded, even if the variant has been edited
    since (same discipline the design mission learned from Madar's F2)."""
    attempt = await _own_operate_attempt(db, attempt_id, current)
    if attempt.status not in ("passed", "failed"):
        raise HTTPException(status.HTTP_409_CONFLICT, detail="This flight hasn't ended yet")

    ctx = await flight_context(db, attempt)
    payload = attempt.payload or {}
    state = ctx.live_state()
    outcome = ctx.outcome_for(state)
    events = attempt_events(attempt)

    return DebriefOut(
        attempt_id=attempt.id,
        mission_id=attempt.mission_id,
        variant_label=ctx.variant.label,
        attempt_status=attempt.status,
        passed=attempt.status == "passed",
        score=float(attempt.score or 0),
        pass_threshold=ctx.pass_threshold,
        objectives_score=outcome.objectives_score,
        performance_score=outcome.performance_score,
        penalty_points=outcome.penalty_points,
        objectives=[
            ObjectiveOut(
                key=o.key, label=o.label, detail=o.detail, target=o.target,
                actual=o.actual, fraction=round(o.fraction, 3), met=o.met,
            )
            for o in outcome.objectives
        ],
        penalties=[
            {"key": p.key, "label": p.label, "note": p.note, "count": p.count, "points": p.points}
            for p in outcome.penalties
        ],
        timeline=debrief_mod.timeline(ctx.orbit),
        trace=list(payload.get("trace", [])),
        command_markers=debrief_mod.command_markers(events),
        anomaly_windows=debrief_mod.anomaly_windows(outcome, ctx.orbit.session_seconds),
        report=dict(payload.get("report", {})),
        events=[CommandEventOut(**e) for e in events],
        spacecraft_log=[SpacecraftLogOut(**entry) for entry in state.log],
    )
