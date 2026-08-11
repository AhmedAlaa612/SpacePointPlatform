"""Shared rule for collapsing a student's multiple attempts at one mission
into the one that matters: the passed attempt if any exists, else the most
recent by `attempt_no`. Used by the cohort-scoped admin progress grid
(7B-1, `services/lms/admin_progress.py`) and the mission-manager's
mission-wide stats view (7B-7, `services/missions/stats.py`) — same rule,
two different scopes to collect attempts from.
"""

from __future__ import annotations

from app.models.missions.mission import MissionAttempt

STATUS_RANK = {"abandoned": 0, "failed": 1, "in_progress": 2, "submitted": 3, "passed": 4}


def best_attempt(attempts: list[MissionAttempt]) -> MissionAttempt | None:
    best: MissionAttempt | None = None
    for attempt in attempts:
        if best is None or (STATUS_RANK[attempt.status], attempt.attempt_no) > (
            STATUS_RANK[best.status], best.attempt_no
        ):
            best = attempt
    return best
