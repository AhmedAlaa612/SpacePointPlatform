"""Missions domain (Phase 2 Stages 5-6) — standalone challenges, distinct
from `lms.courses` but embeddable inside one via `module_items.kind='mission'`
(P5-5).

- `missions` — the authored challenge (template)
- `mission_variants` — difficulty levels of one mission, each with its own
  points and kind-specific `config`
- prerequisites live in `models/curriculum.py::Prerequisite` since 7B-2 —
  unified with courses, no longer a mission-only table here
- `mission_attempts` — one run (template → instance), verifier-graded,
  `user_id` XOR `mission_team_id` (P6-2)
- `mission_teams` / `mission_team_members` — the current roster of a team
  attempting team-policy missions together (P6-1)
- `mission_attempt_members` — the frozen snapshot of who was on the team
  for one specific attempt (P6-2)

Everything keys on `users`, same as the rest of `lms` — `MERGE_FK_REGISTRY`
is untouched.
"""

from app.models.missions.design import (
    Design,
    DesignComponent,
    DesignComponentLibrary,
    DesignComponentModeState,
    DesignCostBudgetEntry,
    DesignDataBudgetEntry,
    DesignLinkBudgetEntry,
    DesignMassBudgetEntry,
    DesignMode,
    DesignPowerBudgetEntry,
)
from app.models.missions.assignment import MissionAssignment
from app.models.missions.manager import MissionManager
from app.models.missions.mission import (
    Mission,
    MissionAttempt,
    MissionAttemptMember,
    MissionVariant,
)
from app.models.missions.proposal import MissionProposal
from app.models.missions.team import MissionTeam, MissionTeamMember

__all__ = [
    "Mission",
    "MissionAttempt",
    "MissionAttemptMember",
    "MissionVariant",
    "MissionProposal",
    "MissionManager",
    "MissionAssignment",
    "MissionTeam",
    "MissionTeamMember",
    "Design",
    "DesignComponent",
    "DesignComponentLibrary",
    "DesignComponentModeState",
    "DesignCostBudgetEntry",
    "DesignDataBudgetEntry",
    "DesignLinkBudgetEntry",
    "DesignMassBudgetEntry",
    "DesignMode",
    "DesignPowerBudgetEntry",
]
