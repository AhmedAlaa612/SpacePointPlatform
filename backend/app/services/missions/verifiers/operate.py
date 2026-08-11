"""The `operate` mission kind (Phase 2B, Stage 7B-3/7B-5) — fly the
satellite you designed, ported from SatKit's prototype. Unlike `design`
(open-ended, never fails, just isn't ready yet) this kind is a bounded,
reactive session much closer to `quiz`: the student issues telecommands
while scripted anomalies fire, and `finish_operation` is a real pass/fail
decision, not a "check again later" gate.

`mission_attempts.payload` is the only state this kind stores:
`events` is an ordered, append-only log of every command issued (who,
when, what it returned); `crew` (Stage 7B-5) is `{role: user_id}` for a
team attempt's optional role assignments. Telemetry
(`operate/telemetry.py`) and the anomaly/score state
(`operate/evaluator.py`) are never stored, both are pure functions
computed on read from `attempt.started_at` and the event log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.missions.attempts import decide_attempt
from app.services.missions.operate.commands import process_command
from app.services.missions.operate.crew import ROLES, is_command_allowed
from app.services.missions.operate.evaluator import OperationResult, evaluate_operation


def attempt_events(attempt: MissionAttempt) -> list[dict]:
    return list((attempt.payload or {}).get("events", []))


def commands_issued(attempt: MissionAttempt) -> list[str]:
    return [e["command"] for e in attempt_events(attempt)]


def attempt_crew(attempt: MissionAttempt) -> dict[str, str]:
    return dict((attempt.payload or {}).get("crew", {}))


async def assign_crew_role(
    db: AsyncSession, *, attempt: MissionAttempt, role: str | None, user_id: uuid.UUID,
) -> dict[str, str]:
    """Sets `user_id` into `role`, or clears whatever role `user_id`
    currently holds if `role` is None. A team member can only ever hold
    one role at a time — taking a new one vacates the old one, same
    intuition as a real crew reassignment."""
    if role is not None and role not in ROLES:
        raise HTTPException(400, detail=f"Unknown role '{role}'")

    crew = attempt_crew(attempt)
    crew = {r: uid for r, uid in crew.items() if uid != str(user_id)}  # vacate any role this user held
    if role is not None:
        crew[role] = str(user_id)

    attempt.payload = {**(attempt.payload or {}), "crew": crew}
    await db.flush()
    return crew


async def issue_command(
    db: AsyncSession, *, attempt: MissionAttempt, raw_command: str, issued_by: uuid.UUID,
) -> dict:
    """Appends one event to the log and returns it. Never decides
    pass/fail on its own — that's `finish_operation`, a separate,
    explicit action, mirroring the design mission's "mark complete"
    rather than quiz's "grades itself on submit" (a flight session has a
    clear end point the student chooses, same as design; what differs
    from design is that ending it can genuinely fail, same as quiz).

    Team attempts are crew-gated (Stage 7B-5): a filled role restricts
    that role's commands to whoever holds it; an unfilled role never
    blocks anyone. Solo attempts have no crew at all, so gating is
    always a no-op for them.
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress' — session is over")

    if attempt.mission_team_id is not None:
        crew = attempt_crew(attempt)
        if not is_command_allowed(command=raw_command, issuer_id=str(issued_by), crew=crew):
            raise HTTPException(403, detail="That subsystem's officer hasn't authorized you for this command")

    result = process_command(raw_command)
    events = attempt_events(attempt)
    event = {
        "seq": len(events) + 1,
        "command": raw_command.strip().split(" ")[0].upper() if raw_command.strip() else "",
        "issued_by": str(issued_by),
        "success": result.success,
        "message": result.message,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    events.append(event)
    attempt.payload = {**(attempt.payload or {}), "events": events}
    await db.flush()
    return event


async def finish_operation(db: AsyncSession, *, attempt: MissionAttempt) -> tuple[MissionAttempt, OperationResult]:
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress'")

    variant = await db.get(MissionVariant, attempt.variant_id)
    config = variant.config or {}
    result = evaluate_operation(
        commands_issued=commands_issued(attempt),
        anomaly_script=config.get("anomalies", []),
        pass_threshold=config.get("pass_threshold", 70),
    )
    decided = await decide_attempt(db, attempt=attempt, passed=result.passed, score=result.score)
    return decided, result
