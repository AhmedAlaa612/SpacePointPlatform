"""The debrief (Operate v2, Stage 7C-8) — where the learning actually
lands.

A score on its own teaches nothing. What teaches is seeing the moment the
battery started falling, noticing it was four minutes before you did
anything, and reading what the correct response would have been. That is
the whole reason the simulator is a deterministic replay: reconstructing
the flight is the same function that ran it, so the debrief can never show
a student something different from what they lived through.

This is also where SatKit's orphaned `reports` table finally has a
purpose. It modelled a per-team mission report (title, content,
`presentation_url`) that its frontend never used and the Stage 7B port
never carried over. The auto-generated flight report below is that object,
built from data rather than typed by hand — and a *written* post-flight
report can now be a separate `submission`-kind mission chained off this
one through the 7B-2 prerequisite DAG, which keeps the operations lesson
and the communication lesson properly separate.
"""

from __future__ import annotations

from app.services.missions.operate import anomalies as lib
from app.services.missions.operate.evaluator import MissionOutcome
from app.services.missions.operate.orbit import (
    OrbitModel,
    eclipse_windows,
    pass_windows,
    saa_windows,
)
from app.services.missions.operate.spacecraft import SpacecraftParams, SpacecraftState


def timeline(orbit: OrbitModel) -> dict:
    """The orbit plan as bands the debrief chart shades. This is SatKit's
    six-step 'Team Progress' timeline made real — its version was six
    hardcoded literals ('Data collection · In progress · 34% complete');
    this one is derived from the orbit model, so it describes the flight
    that actually happened."""
    return {
        "session_seconds": round(orbit.session_seconds, 1),
        "period_seconds": round(orbit.period_seconds, 1),
        "orbits": orbit.orbits,
        "passes": pass_windows(orbit),
        "eclipses": eclipse_windows(orbit),
        "saa": saa_windows(orbit),
    }


def command_markers(events: list[dict]) -> list[dict]:
    """Every command the student issued, pinned to the flight clock so it
    can be overlaid on the telemetry trace. Seeing your own actions against
    the curve is the point — 'I did nothing for six minutes' is a lesson
    that no number delivers."""
    return [
        {
            "t": round(float(e.get("sim_t", 0.0)), 1),
            "command": e.get("command", ""),
            "success": bool(e.get("success", False)),
            "issued_by": e.get("issued_by"),
        }
        for e in events
    ]


def anomaly_windows(outcome: MissionOutcome, session_seconds: float) -> list[dict]:
    """Each fault as a shaded span, with the teaching note attached.

    Disclosure is always full here regardless of the variant's in-flight
    setting (`anomalies.handbook`) — once the flight is over, withholding
    the explanation from a student who just lost a pass to it serves
    nobody.
    """
    out = []
    for a in outcome.anomalies:
        out.append({
            "key": a.key,
            "title": a.title,
            "subsystem": a.subsystem,
            "origin": a.origin,
            "start_t": a.raised_t,
            "end_t": a.cleared_t if a.cleared_t is not None else round(session_seconds, 1),
            "outcome": a.outcome,
            "cleared_by": a.cleared_by,
            "response_seconds": a.response_seconds,
            "response_window_s": a.response_window_s,
            "teaching": lib.teaching_for(a.key),
        })
    return out


def flight_report(
    *,
    state: SpacecraftState,
    params: SpacecraftParams,
    outcome: MissionOutcome,
    orbit: OrbitModel,
    events: list[dict],
) -> dict:
    """The structured post-flight record. Deliberately a dict rather than
    prose so the frontend can render it, a manager can aggregate it, and a
    future export can turn it into the written report SatKit's `reports`
    table was reaching for."""
    resolved = [a for a in outcome.anomalies if a.outcome == "resolved"]
    late = [a for a in outcome.anomalies if a.outcome == "late"]
    missed = [a for a in outcome.anomalies if a.outcome == "unresolved"]

    return {
        "summary": {
            "orbits_flown": orbit.orbits,
            "session_minutes": round(orbit.session_seconds / 60.0, 1),
            "commands_issued": len(events),
            "science_takes": state.science_takes,
            "science_dropped": state.science_dropped,
            "downlinked_mb": round(state.downlinked_mb, 1),
            "downlink_minutes": round(state.downlink_seconds / 60.0, 1),
            "min_soc_pct": round(state.min_soc_seen * 100, 1),
            "final_soc_pct": round(state.battery_soc * 100, 1),
            "max_payload_temp_c": round(state.max_payload_temp_c, 1),
            "safe_mode_entries": state.safe_mode_entries,
            "obc_upsets": state.obc_upsets,
            "final_mode": state.mode,
        },
        "anomaly_tally": {
            "total": len(outcome.anomalies),
            "resolved": len(resolved),
            "late": len(late),
            "unresolved": len(missed),
        },
        # One plain-language line per thing that went well or badly. This
        # is what a student reads first, so it has to say something true
        # and specific rather than congratulate them.
        "notes": _notes(state, outcome, params),
    }


def _notes(state: SpacecraftState, outcome: MissionOutcome, params: SpacecraftParams) -> list[dict]:
    notes: list[dict] = []

    dl = next((o for o in outcome.objectives if o.key == "downlink"), None)
    if dl is not None and dl.met:
        notes.append({"tone": "good", "text": f"You got {state.downlinked_mb:.0f} MB to the ground — objective met."})
    elif dl is not None and state.downlinked_mb == 0:
        notes.append({"tone": "bad", "text":
            "Nothing was downlinked at all. Science only counts once it is on the ground, and the "
            "spacecraft can only talk during a pass."})
    elif dl is not None:
        notes.append({"tone": "bad", "text":
            f"Only {state.downlinked_mb:.0f} of {dl.target:.0f} MB made it down. Start the downlink at "
            f"AOS rather than partway through the pass."})

    if state.safe_mode_entries:
        notes.append({"tone": "bad", "text":
            "The spacecraft safed itself on undervoltage. Everything after that point was recovery "
            "rather than mission — watch the eclipse countdown and shed the payload before you enter "
            "shadow, not after."})
    elif state.min_soc_seen < 0.5:
        notes.append({"tone": "warn", "text":
            f"Battery got down to {state.min_soc_seen * 100:.0f}%. That worked, but there was not much "
            f"margin left if anything else had gone wrong."})
    else:
        notes.append({"tone": "good", "text":
            f"Power stayed healthy all flight — lowest charge {state.min_soc_seen * 100:.0f}%."})

    if state.wheel_rpm >= params.wheel_max_rpm:
        notes.append({"tone": "bad", "text":
            "The reaction wheel saturated and you lost attitude control. Once pointing goes, the "
            "antenna stops looking at the ground station and every remaining pass is wasted."})

    if state.science_dropped:
        notes.append({"tone": "bad", "text":
            f"{state.science_dropped} science take(s) were dropped because mass memory was full. "
            f"Downlink before collecting more."})

    if state.max_payload_temp_c >= params.payload_temp_limit_c:
        notes.append({"tone": "warn", "text":
            f"The instrument reached {state.max_payload_temp_c:.0f} C. Duty-cycle it: power it for the "
            f"collection you need, then put it in standby."})

    for penalty in outcome.penalties:
        notes.append({"tone": "warn", "text": f"{penalty.label}. {penalty.note}"})

    if not any(n["tone"] == "bad" for n in notes) and outcome.passed:
        notes.append({"tone": "good", "text":
            "Clean flight. Every fault was caught and the objectives were met — that is what a good "
            "shift at a console looks like."})

    return notes
