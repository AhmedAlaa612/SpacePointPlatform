"""Missions domain (Phase 2 Stage 5) — standalone challenges, distinct from
`lms.courses` but embeddable inside one via `module_items.kind='mission'`
(P5-5).

Four tables, solo only this stage (MISSIONS_REPORT.md Ch.2/Ch.3,
PHASE2_EXECUTION_PLAN.md §4):
- `missions` — the authored challenge (template)
- `mission_variants` — difficulty levels of one mission, each with its own
  points and kind-specific `config`
- `mission_prerequisites` — a DAG edge, "mission_id requires requires_mission_id"
- `mission_attempts` — one run (template → instance), verifier-graded

Everything keys on `users`, same as the rest of `lms` — `MERGE_FK_REGISTRY`
is untouched.
"""

from app.models.missions.mission import (
    Mission,
    MissionAttempt,
    MissionPrerequisite,
    MissionVariant,
)
from app.models.missions.team import MissionTeam, MissionTeamMember

__all__ = [
    "Mission",
    "MissionAttempt",
    "MissionPrerequisite",
    "MissionVariant",
    "MissionTeam",
    "MissionTeamMember",
]
