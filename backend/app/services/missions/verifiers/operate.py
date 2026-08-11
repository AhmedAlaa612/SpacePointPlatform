"""The `operate` mission kind (Phase 2B, Stage 7B-3) — fly the satellite you
designed, ported from SatKit's prototype. Unlike `design` (open-ended,
never fails, just isn't ready yet) this kind is a bounded, reactive
session much closer to `quiz`: the student issues telecommands while
scripted anomalies fire, and `finish_operation` is a real pass/fail
decision, not a "check again later" gate.

`mission_attempts.payload["events"]` is the only state this kind stores —
an ordered, append-only log of every command issued (who, when, what it
returned). Telemetry (`operate/telemetry.py`) and the anomaly/score state
(`operate/evaluator.py`) are never stored, both are pure functions
computed on read from `attempt.started_at` and this event log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.missions.attempts import decide_attempt
from app.services.missions.operate.commands import process_command
from app.services.missions.operate.evaluator import OperationResult, evaluate_operation


def attempt_events(attempt: MissionAttempt) -> list[dict]:
    return list((attempt.payload or {}).get("events", []))


def commands_issued(attempt: MissionAttempt) -> list[str]:
    return [e["command"] for e in attempt_events(attempt)]


async def issue_command(
    db: AsyncSession, *, attempt: MissionAttempt, raw_command: str, issued_by: uuid.UUID,
) -> dict:
    """Appends one event to the log and returns it. Never decides
    pass/fail on its own — that's `finish_operation`, a separate,
    explicit action, mirroring the design mission's "mark complete"
    rather than quiz's "grades itself on submit" (a flight session has a
    clear end point the student chooses, same as design; what differs
    from design is that ending it can genuinely fail, same as quiz).
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress' — session is over")

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
