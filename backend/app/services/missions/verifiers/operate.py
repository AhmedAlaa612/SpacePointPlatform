"""The `operate` mission kind (Operate v2, Stage 7C) — fly a real
spacecraft through a real orbit.

This module is orchestration only. The physics is
`services/missions/operate/spacecraft.py`, the orbit is `orbit.py`, the
teaching content is `anomalies.py`, and the grading is `evaluator.py`. What
lives here is the bridge between those pure functions and a
`MissionAttempt` row.

**The one piece of state that matters.** `mission_attempts.payload` stores
`events` — an append-only log of every command with the *sim time* it was
issued at — plus `crew` for a team attempt's optional seat assignments, and
`trace`/`report`, written once when the flight ends. Everything else
(telemetry, spacecraft state, faults, score) is recomputed by replaying
that log. Nothing derived is ever persisted while the flight is live, so
there is no way for what the student sees and what the grade says to
diverge.

**Sim time vs wall time.** A session is `orbits` laps of a ~95-minute
orbit, compressed so it runs in about fifteen real minutes. `sim_t` for
any moment is `(now - started_at) * time_compression`. Storing it on every
event is what makes the replay exact — and therefore what makes the
debrief trustworthy.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.missions.mission import MissionAttempt, MissionVariant
from app.services.missions.attempts import decide_attempt
from app.services.missions.operate import anomalies as lib
from app.services.missions.operate import debrief as debrief_mod
from app.services.missions.operate import design_link
from app.services.missions.operate.commands import command_reference, parse
from app.services.missions.operate.crew import ROLES, is_command_allowed, role_brief
from app.services.missions.operate.evaluator import MissionOutcome, evaluate, objective_spec
from app.services.missions.operate.orbit import OrbitModel, model_from_config, orbit_summary
from app.services.missions.operate.spacecraft import (
    SpacecraftParams,
    SpacecraftState,
    apply_command,
    project_state,
    schedule_injected_faults,
    simulate,
)
from app.services.missions.operate.telemetry import flight_rules

# How many points the debrief chart gets. Enough to show the shape of an
# eclipse cycle without shipping a few thousand rows in a JSONB column.
TRACE_POINTS = 220

DEFAULT_PASS_THRESHOLD = 65.0


# --------------------------------------------------------------------------
# Reading the attempt
# --------------------------------------------------------------------------

def attempt_events(attempt: MissionAttempt) -> list[dict]:
    return list((attempt.payload or {}).get("events", []))


def attempt_crew(attempt: MissionAttempt) -> dict[str, str]:
    return dict((attempt.payload or {}).get("crew", {}))


def commands_issued(attempt: MissionAttempt) -> list[str]:
    return [e.get("command", "") for e in attempt_events(attempt)]


def replay_commands(attempt: MissionAttempt) -> list[dict]:
    """The event log in the shape `simulate` wants."""
    return [
        {"sim_t": float(e.get("sim_t", 0.0)), "base": e.get("command", ""), "arg": e.get("arg", "")}
        for e in attempt_events(attempt)
    ]


def penalties_seen(attempt: MissionAttempt) -> list[str]:
    return [e["penalty"] for e in attempt_events(attempt) if e.get("penalty")]


def attempt_seed(attempt: MissionAttempt) -> int:
    """Per-attempt shuffle seed (D-b). Derived from the attempt id, so it
    is stable for the life of the attempt — a reload never re-rolls the
    flight — while a *retry* is a different attempt and therefore a
    different scenario at Engineer and above."""
    return attempt.id.int % 9973


def sim_time_now(attempt: MissionAttempt, orbit: OrbitModel) -> float:
    started = attempt.started_at or datetime.now(timezone.utc)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    real_elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return max(0.0, min(real_elapsed * orbit.time_compression, orbit.session_seconds))


# --------------------------------------------------------------------------
# Resolving the flight from the variant
# --------------------------------------------------------------------------

class FlightContext:
    """Everything a request needs to reason about one attempt's flight.
    Built fresh per request from the variant's config — no caching, because
    the whole model is cheap pure functions and a cache is a bug waiting
    for a variant edit."""

    def __init__(self, attempt: MissionAttempt, variant: MissionVariant):
        self.attempt = attempt
        self.variant = variant
        self.config: dict = variant.config or {}
        self.orbit = model_from_config(self.config)
        self.params = SpacecraftParams.from_config(self.config)
        self.injected = schedule_injected_faults(
            self.orbit,
            self.config,
            seed=attempt_seed(attempt),
            # A crewed attempt gets its external events compressed onto one
            # orbit so five officers have five things happening at once
            # (D-f) rather than four people watching one person work. The
            # variant only says whether that's allowed; whether it applies
            # depends on this attempt actually being a team attempt.
            concurrent=attempt.mission_team_id is not None
            and bool(self.config.get("crew_concurrency", True)),
        )
        self.pass_threshold = float(self.config.get("pass_threshold", DEFAULT_PASS_THRESHOLD))
        self.disclosure = str(self.config.get("handbook_disclosure", "full"))
        self.source_notes: list[str] = []

    async def resolve_spacecraft(self, db: AsyncSession) -> None:
        """Stage 7C-9 — if this variant flies the student's own design,
        swap the standard vehicle for theirs.

        The mapping is **snapshotted into the attempt** the first time it
        resolves. Editing the design afterwards then cannot change a flight
        that has already happened, which is the same discipline the design
        mission had to learn from Madar (F2: editing the component library
        retroactively re-graded finished work).

        Falls back silently to the standard vehicle when there's no passed
        design to read. A student who hasn't done the design mission should
        get a flyable spacecraft, not an error.
        """
        if self.config.get("spacecraft_source") != "design":
            return

        stored = (self.attempt.payload or {}).get("spacecraft_source")
        if stored is not None:
            overrides = {k: float(v) for k, v in (stored.get("params") or {}).items()}
            if overrides:
                self.params = SpacecraftParams(**{**self.params.__dict__, **overrides})
            self.source_notes = list(stored.get("notes") or [])
            return

        if self.attempt.status != "in_progress":
            return  # never mint a snapshot for a flight that's already graded

        design_attempt = await design_link.find_passed_design(
            db, user_id=self.attempt.user_id, team_id=self.attempt.mission_team_id,
        )
        if design_attempt is None:
            self.attempt.payload = {**(self.attempt.payload or {}), "spacecraft_source": {"params": {}, "notes": []}}
            await db.flush()
            await db.commit()
            return

        params, changes = await design_link.spacecraft_from_design(
            db, design_attempt=design_attempt, base=self.params,
        )
        notes = design_link.source_note(changes)
        self.params = params
        self.source_notes = notes
        self.attempt.payload = {
            **(self.attempt.payload or {}),
            "spacecraft_source": {
                "design_attempt_id": str(design_attempt.id),
                "params": {k: v["flown"] for k, v in changes.items()},
                "notes": notes,
            },
        }
        await db.flush()
        await db.commit()

    @property
    def sim_t(self) -> float:
        return sim_time_now(self.attempt, self.orbit)

    @property
    def expired(self) -> bool:
        return self.sim_t >= self.orbit.session_seconds

    def state_at(self, t: float) -> SpacecraftState:
        return project_state(
            orbit=self.orbit, params=self.params,
            commands=replay_commands(self.attempt), at_t=t, injected=self.injected,
        )

    def live_state(self) -> SpacecraftState:
        """The flight as of right now — or, once decided, as of the moment
        it ended, so a debrief doesn't keep flying a finished mission."""
        if self.attempt.status in ("passed", "failed"):
            return self.state_at(float((self.attempt.payload or {}).get("ended_sim_t", self.orbit.session_seconds)))
        return self.state_at(self.sim_t)

    def outcome_for(self, state: SpacecraftState) -> MissionOutcome:
        return evaluate(
            state=state, params=self.params, config=self.config,
            penalties_seen=penalties_seen(self.attempt), pass_threshold=self.pass_threshold,
            # How much of the session was actually flown. The live console
            # therefore shows a running score that starts near zero and
            # climbs — which is honest ("this is what you'd get if you
            # ended now") and quietly discourages bailing out early.
            completion=(state.t / self.orbit.session_seconds) if self.orbit.session_seconds else 1.0,
        )


async def flight_context(db: AsyncSession, attempt: MissionAttempt) -> FlightContext:
    variant = await db.get(MissionVariant, attempt.variant_id)
    if variant is None:
        raise HTTPException(500, detail="This mission's difficulty variant is missing")
    ctx = FlightContext(attempt, variant)
    await ctx.resolve_spacecraft(db)
    return ctx


# --------------------------------------------------------------------------
# Actions
# --------------------------------------------------------------------------

async def assign_crew_role(
    db: AsyncSession, *, attempt: MissionAttempt, role: str | None, user_id: uuid.UUID,
) -> dict[str, str]:
    """Sets `user_id` into `role`, or clears whatever role they currently
    hold if `role` is None. One seat per person — taking a new one vacates
    the old, the same intuition as a real crew reassignment."""
    if role is not None and role not in ROLES:
        raise HTTPException(400, detail=f"Unknown role '{role}'")

    crew = attempt_crew(attempt)
    crew = {r: uid for r, uid in crew.items() if uid != str(user_id)}
    if role is not None:
        crew[role] = str(user_id)

    attempt.payload = {**(attempt.payload or {}), "crew": crew}
    await db.flush()
    return crew


async def issue_command(
    db: AsyncSession, *, attempt: MissionAttempt, raw_command: str, issued_by: uuid.UUID,
    ctx: FlightContext,
) -> dict:
    """Apply one telecommand and append it to the log.

    The command is evaluated against the state produced by replaying every
    *previous* command up to this instant, which is by construction the
    same state a later replay will reconstruct. That is why the message the
    student sees now and the flight the debrief shows later can never
    disagree.

    Never decides pass/fail — that is `finish_operation`, a separate,
    explicit act. A flight session has an end point the operator chooses,
    the same as the design mission's "mark complete"; what differs is that
    ending it can genuinely fail.
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress' — the flight is over")

    if ctx.expired:
        raise HTTPException(409, detail="The flight window has closed — end the session to see your debrief")

    if attempt.mission_team_id is not None:
        if not is_command_allowed(command=raw_command, issuer_id=str(issued_by), crew=attempt_crew(attempt)):
            raise HTTPException(403, detail="That subsystem's officer holds this command — ask them, or take a free seat")

    base, arg = parse(raw_command)
    sim_t = ctx.sim_t
    state = ctx.state_at(sim_t)
    result = apply_command(state, ctx.params, base=base, arg=arg)

    events = attempt_events(attempt)
    event = {
        "seq": len(events) + 1,
        "command": base,
        "arg": arg,
        "sim_t": round(sim_t, 1),
        "issued_by": str(issued_by),
        "success": result.accepted,
        "message": result.message,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if result.penalty:
        event["penalty"] = result.penalty
    events.append(event)
    attempt.payload = {**(attempt.payload or {}), "events": events}
    await db.flush()
    return event


async def finish_operation(
    db: AsyncSession, *, attempt: MissionAttempt, ctx: FlightContext,
) -> tuple[MissionAttempt, MissionOutcome]:
    """End the flight, grade it, and freeze the debrief.

    The trace is sampled and written here — the only derived data this kind
    ever persists. It exists so a debrief opened next week doesn't depend
    on re-running a simulation whose variant config may have been edited
    since, which is the same "don't retroactively change graded work"
    discipline the design mission learned from Madar (F2/F4).
    """
    if attempt.status != "in_progress":
        raise HTTPException(409, detail=f"Attempt is '{attempt.status}', not 'in_progress'")

    ended_at = ctx.sim_t
    result = simulate(
        orbit=ctx.orbit, params=ctx.params, commands=replay_commands(attempt),
        until_t=ended_at, injected=ctx.injected, trace_points=TRACE_POINTS,
    )
    outcome = ctx.outcome_for(result.state)
    report = debrief_mod.flight_report(
        state=result.state, params=ctx.params, outcome=outcome,
        orbit=ctx.orbit, events=attempt_events(attempt),
    )

    attempt.payload = {
        **(attempt.payload or {}),
        "ended_sim_t": round(ended_at, 1),
        "trace": result.trace,
        "report": report,
    }
    await db.flush()

    decided = await decide_attempt(db, attempt=attempt, passed=outcome.passed, score=outcome.score)
    return decided, outcome


# --------------------------------------------------------------------------
# Static content — briefing and handbook
# --------------------------------------------------------------------------

def briefing(variant: MissionVariant, *, mission_title: str, mission_summary: str | None) -> dict:
    """Everything a student should read before they fly (plan §5.1).

    Deliberately available *before* an attempt row exists, so opening the
    briefing never burns a retry and a student can read the flight rules as
    many times as they like.
    """
    config = variant.config or {}
    orbit = model_from_config(config)
    params = SpacecraftParams.from_config(config)
    spec = objective_spec(config, params)

    return {
        "mission_title": mission_title,
        "mission_summary": mission_summary,
        "variant_id": str(variant.id),
        "variant_label": variant.label,
        "points": variant.points,
        "pass_threshold": float(config.get("pass_threshold", DEFAULT_PASS_THRESHOLD)),
        "orbit": orbit_summary(orbit),
        "spacecraft": {
            "battery_capacity_wh": params.battery_capacity_wh,
            "initial_soc_pct": round(params.initial_soc * 100, 0),
            "solar_array_w": params.solar_array_w,
            "bus_idle_w": params.bus_idle_w,
            "payload_active_w": params.payload_active_w,
            "transmitter_w": params.transmitter_w,
            "storage_capacity_mb": params.storage_capacity_mb,
            "science_take_mb": params.science_take_mb,
            "downlink_mbps": params.downlink_mbps,
            "wheel_max_rpm": params.wheel_max_rpm,
        },
        "objectives": [
            {"key": "science_takes", "label": "Collect science",
             "detail": f"Capture {spec['science_takes']} science takes with the instrument."},
            {"key": "downlink", "label": "Get it to the ground",
             "detail": f"Downlink at least {spec['downlink_mb']:.0f} MB during your ground station passes."},
            {"key": "soc_floor", "label": "Keep the battery healthy",
             "detail": f"Never let state of charge fall below {spec['soc_floor'] * 100:.0f}%."},
            {"key": "no_safe_mode", "label": "Never lose the spacecraft",
             "detail": "Do not let it drop into autonomous safe mode."},
        ],
        "flight_rules": flight_rules(),
        "commands": command_reference(),
        "handbook": lib.handbook(disclosure=str(config.get("handbook_disclosure", "full"))),
        "crew_roles": role_brief(),
        "assumptions": ASSUMPTIONS,
    }


# Stated on screen rather than buried, per D-c. A teaching model that
# doesn't say what it simplified teaches students to trust models they
# shouldn't — which is the criticism MISSIONS_REPORT.md R4 made of Madar's
# link budget reporting "Good Link" as though it were authoritative.
ASSUMPTIONS = [
    "Circular orbit at a fixed altitude — no atmospheric drag decay and no orbital manoeuvres.",
    "A fixed eclipse fraction rather than a beta-angle model that varies through the year.",
    "One ground station, with a pass at the same point in every orbit. A real mission's passes "
    "cluster and then leave long gaps.",
    "Station elevation follows a smooth half-sine across the pass; real passes are asymmetric.",
    "Power is modelled as an energy balance. There is no battery temperature effect, no charge "
    "efficiency curve and no depth-of-discharge lifetime penalty.",
    "Attitude is a single momentum and pointing-error figure, not full rigid-body dynamics.",
    "Anomalies are deterministic per attempt. Two students on the same variant and the same "
    "attempt see the same flight, which is what keeps grading fair.",
]
