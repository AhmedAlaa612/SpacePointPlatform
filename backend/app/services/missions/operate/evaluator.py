"""The anomaly evaluator — this is the mechanic SatKit never had at all.
The source's subsystem-health lights and its terminal were two disconnected
systems (status only ever changed via a manual admin toggle, never in
response to anything typed); this is new domain design, not a port.

Anomalies are a **deterministic script**, not true randomness — every
student on the same variant faces the same sequence, which keeps grading
fair and this function trivially testable. What still varies is whether
*this* student resolves each one in time.

Nothing here is stored — `evaluate_operation` is a pure function over the
ordered list of commands actually issued (`mission_attempts.payload
["events"]`) and the variant's scripted anomaly list
(`mission_variants.config["anomalies"]`), exactly like the design
mission's calculators never store a derived total either.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AnomalyState:
    index: int
    subsystem: str
    correct_command: str
    triggered: bool
    resolved: bool


@dataclass
class OperationResult:
    anomalies: list[AnomalyState]
    triggered_count: int
    resolved_count: int
    score: float
    passed: bool


def evaluate_operation(
    *, commands_issued: list[str], anomaly_script: list[dict], pass_threshold: float,
) -> OperationResult:
    """`anomaly_script[i]` is `{trigger_after_commands, subsystem,
    correct_command}`. An anomaly is *triggered* once at least
    `trigger_after_commands` commands have been issued in total; it's
    *resolved* if its `correct_command` appears anywhere in the commands
    issued from that point onward — a command issued *before* the anomaly
    triggers can't pre-resolve it, matching the intuition that you can't
    fix something before it breaks.

    Score is percent of *triggered* anomalies resolved — an anomaly that
    never triggered (session ended early) doesn't count against the
    student either way. No anomalies scripted at all is a trivial pass,
    same spirit as quiz's `pass_threshold == 0` rule.
    """
    total = len(commands_issued)
    states: list[AnomalyState] = []
    for i, a in enumerate(anomaly_script):
        trigger_at = a["trigger_after_commands"]
        triggered = total >= trigger_at
        resolved = triggered and a["correct_command"] in commands_issued[trigger_at:]
        states.append(AnomalyState(
            index=i, subsystem=a["subsystem"], correct_command=a["correct_command"],
            triggered=triggered, resolved=resolved,
        ))

    triggered_count = sum(1 for s in states if s.triggered)
    resolved_count = sum(1 for s in states if s.resolved)
    score = round((resolved_count / triggered_count) * 100, 2) if triggered_count > 0 else 100.0
    passed = score >= pass_threshold

    return OperationResult(
        anomalies=states, triggered_count=triggered_count, resolved_count=resolved_count,
        score=score, passed=passed,
    )
