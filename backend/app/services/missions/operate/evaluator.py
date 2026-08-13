"""Scoring (Operate v2, Stage 7C-4) — mission objectives first, flight
performance second.

**What this replaces and why.** v1 scored "percent of *triggered* anomalies
resolved", where anomalies triggered on a command counter. Two consequences
followed, both verified against the shipped code:

* Ending the session without typing anything triggered nothing, so
  `triggered_count == 0`, so the empty-case fallback returned 100.0 and
  the attempt **passed with full points on the hardest variant**.
* Typing the fix commands twice in a row scored 100% without reading a
  single telemetry channel.

Neither is patched here. Both are *structurally* impossible now, because
the score is anchored to what the mission was for. Do nothing and you
collect no science, downlink nothing, and the battery dies — the
objectives simply aren't met. No minimum-engagement guard is needed, and
that is the difference between a rule and a design.

    score = 60% objectives + 40% flight performance - penalties

Objectives carry partial credit, because getting two of the three science
takes down is genuinely better than getting none. Anomaly response is the
flight-performance half. Penalties are small, always itemised, and always
explained in the debrief — the point is to teach, not to punish.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.missions.operate import anomalies as lib
from app.services.missions.operate.spacecraft import SpacecraftParams, SpacecraftState

OBJECTIVES_WEIGHT = 0.60
PERFORMANCE_WEIGHT = 0.40

# Deducted from the final 0-100 score. Deliberately gentle: a student who
# meets the objectives despite a couple of mistakes should still pass, and
# the debrief line explaining what it cost is worth more than the points.
PENALTIES: dict[str, dict] = {
    "needless_reboot": {
        "points": 5.0,
        "label": "Rebooted the OBC with no fault latched",
        "note": "A cold reboot costs 120 seconds of flight time. It is the right call for a "
                "latched-up processor and the wrong one for anything else.",
    },
    "downlink_out_of_pass": {
        "points": 2.0,
        "label": "Commanded a downlink with no station in view",
        "note": "Check the next-AOS countdown before reaching for the transmitter. The "
                "spacecraft can only talk to the ground for about eight minutes an orbit.",
    },
    "premature_safe_exit": {
        "points": 3.0,
        "label": "Tried to leave safe mode before the battery had recovered",
        "note": "Safe mode is a symptom of a power problem. Fix the power, then exit.",
    },
    "data_loss": {
        "points": 4.0,
        "label": "Science take dropped — mass memory was full",
        "note": "Collection is cheap and downlink is scarce. Plan collection around the "
                "pass schedule, not the other way round.",
    },
}


@dataclass
class ObjectiveResult:
    key: str
    label: str
    detail: str
    target: float
    actual: float
    weight: float
    fraction: float  # 0..1 achieved
    met: bool


@dataclass
class AnomalyResult:
    key: str
    title: str
    subsystem: str
    origin: str
    raised_t: float
    cleared_t: float | None
    cleared_by: str | None
    response_seconds: float | None
    response_window_s: float
    outcome: str  # resolved | late | unresolved
    weight: float
    credit: float  # 0..1


@dataclass
class PenaltyResult:
    key: str
    label: str
    note: str
    count: int
    points: float


@dataclass
class MissionOutcome:
    objectives: list[ObjectiveResult] = field(default_factory=list)
    objectives_score: float = 0.0
    anomalies: list[AnomalyResult] = field(default_factory=list)
    performance_score: float = 0.0
    penalties: list[PenaltyResult] = field(default_factory=list)
    penalty_points: float = 0.0
    score: float = 0.0
    passed: bool = False
    pass_threshold: float = 65.0


CREDIT = {"resolved": 1.0, "late": 0.5, "unresolved": 0.0}


def objective_spec(config: dict, params: SpacecraftParams) -> dict:
    """Variant-authored targets, with defaults that suit the standard
    3-orbit Engineer flight: three takes captured and all three on the
    ground, which is roughly one clean pass of downlinking."""
    raw = (config or {}).get("objectives", {}) or {}
    takes = int(raw.get("science_takes", 3))
    return {
        "science_takes": takes,
        "downlink_mb": float(raw.get("downlink_mb", takes * params.science_take_mb)),
        "soc_floor": float(raw.get("soc_floor", 0.40)),
        "allow_safe_mode": bool(raw.get("allow_safe_mode", False)),
    }


def evaluate(
    *,
    state: SpacecraftState,
    params: SpacecraftParams,
    config: dict,
    penalties_seen: list[str],
    pass_threshold: float = 65.0,
    completion: float = 1.0,
) -> MissionOutcome:
    """Grade a flight. Pure — same state in, same score out, which is what
    lets the live console show a running score that the final decision can
    never contradict.

    `completion` is how much of the session was actually flown (0..1), and
    it gates the two *protective* objectives and the no-faults case. The
    reasoning is not a patch on the exploit but the honest reading of what
    those measure: **"I never let the battery drop below 40%" is not a
    claim you can make about a flight you didn't fly.** Ending at T+0 with
    a full battery and a clean fault log demonstrates nothing, so it earns
    nothing. Ending halfway earns half — you did keep it alive that long.

    Without this, the collect-and-downlink objectives were the only ones an
    instant finish couldn't satisfy, and on a low threshold the remaining
    free credit was enough to pass. That was the last surviving shape of
    the v1 bug.
    """
    completion = max(0.0, min(1.0, completion))
    spec = objective_spec(config, params)
    outcome = MissionOutcome(pass_threshold=pass_threshold)

    # --- objectives ------------------------------------------------------
    takes_target = max(1, spec["science_takes"])
    takes_fraction = min(1.0, state.science_takes / takes_target)
    outcome.objectives.append(ObjectiveResult(
        key="science_takes",
        label="Collect science",
        detail=f"{state.science_takes} of {takes_target} takes captured",
        target=takes_target, actual=state.science_takes, weight=0.25,
        fraction=takes_fraction, met=state.science_takes >= takes_target,
    ))

    dl_target = max(1.0, spec["downlink_mb"])
    dl_fraction = min(1.0, state.downlinked_mb / dl_target)
    outcome.objectives.append(ObjectiveResult(
        key="downlink",
        label="Get it to the ground",
        detail=f"{state.downlinked_mb:.0f} of {dl_target:.0f} MB downlinked",
        target=dl_target, actual=round(state.downlinked_mb, 1), weight=0.40,
        fraction=dl_fraction, met=state.downlinked_mb >= dl_target,
    ))

    # The two protective objectives are scaled by how much of the flight
    # actually happened — see the `completion` note in the docstring.
    floor = spec["soc_floor"]
    soc_met = state.min_soc_seen >= floor
    outcome.objectives.append(ObjectiveResult(
        key="soc_floor",
        label="Keep the battery healthy",
        detail=f"lowest charge {state.min_soc_seen * 100:.0f}% (floor {floor * 100:.0f}%)"
               + ("" if completion >= 0.999 else f", {completion * 100:.0f}% of the flight flown"),
        target=floor * 100, actual=round(state.min_soc_seen * 100, 1), weight=0.20,
        fraction=(1.0 if soc_met else max(0.0, state.min_soc_seen / floor)) * completion,
        met=soc_met and completion >= 0.999,
    ))

    safe_met = spec["allow_safe_mode"] or state.safe_mode_entries == 0
    outcome.objectives.append(ObjectiveResult(
        key="no_safe_mode",
        label="Never lose the spacecraft",
        detail="stayed in nominal operations" if state.safe_mode_entries == 0
               else f"entered safe mode {state.safe_mode_entries}x",
        target=0, actual=state.safe_mode_entries, weight=0.15,
        fraction=(1.0 if safe_met else 0.0) * completion,
        met=safe_met and completion >= 0.999,
    ))

    total_weight = sum(o.weight for o in outcome.objectives)
    outcome.objectives_score = round(
        sum(o.fraction * o.weight for o in outcome.objectives) / total_weight * 100, 2,
    )

    # --- anomaly response ------------------------------------------------
    for fault in state.faults:
        spec_a = lib.BY_KEY.get(fault.key)
        outcome.anomalies.append(AnomalyResult(
            key=fault.key,
            title=lib.title_for(fault.key),
            subsystem=lib.subsystem_for(fault.key),
            origin=spec_a.origin if spec_a else "emergent",
            raised_t=round(fault.raised_t, 1),
            cleared_t=round(fault.cleared_t, 1) if fault.cleared_t is not None else None,
            cleared_by=fault.cleared_by,
            response_seconds=round(fault.response_seconds, 1) if fault.response_seconds is not None else None,
            response_window_s=fault.response_window_s,
            outcome=fault.outcome,
            weight=lib.weight_for(fault.key),
            credit=CREDIT[fault.outcome],
        ))

    if outcome.anomalies:
        wsum = sum(a.weight for a in outcome.anomalies)
        outcome.performance_score = round(
            sum(a.credit * a.weight for a in outcome.anomalies) / wsum * 100, 2,
        )
    else:
        # No fault ever raised means the student flew cleanly enough that
        # nothing emergent fired and no injected one had landed yet. There
        # is nothing to grade — but only a flight that actually ran can
        # claim that, so it is scaled by completion for the same reason the
        # protective objectives are.
        outcome.performance_score = round(100.0 * completion, 2)

    # --- penalties -------------------------------------------------------
    counted: dict[str, int] = {}
    for key in penalties_seen:
        if key in PENALTIES:
            counted[key] = counted.get(key, 0) + 1
    for key, count in counted.items():
        meta = PENALTIES[key]
        points = meta["points"] * count
        outcome.penalties.append(PenaltyResult(
            key=key, label=meta["label"], note=meta["note"], count=count, points=round(points, 1),
        ))
    outcome.penalty_points = round(sum(p.points for p in outcome.penalties), 1)

    raw = (
        outcome.objectives_score * OBJECTIVES_WEIGHT
        + outcome.performance_score * PERFORMANCE_WEIGHT
        - outcome.penalty_points
    )
    outcome.score = round(max(0.0, min(100.0, raw)), 2)
    outcome.passed = outcome.score >= pass_threshold
    return outcome
