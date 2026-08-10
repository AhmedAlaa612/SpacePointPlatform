"""Missions domain (Phase 2 Stages 5-6) — standalone challenges, distinct
from `lms.courses` but embeddable inside one via `module_items.kind='mission'`
(P5-5).

- `missions` — the authored challenge (template)
- `mission_variants` — difficulty levels of one mission, each with its own
  points and kind-specific `config`
- `mission_prerequisites` — a DAG edge, "mission_id requires requires_mission_id"
- `mission_attempts` — one run (template → instance), verifier-graded,
  `user_id` XOR `mission_team_id` (P6-2)
- `mission_teams` / `mission_team_members` — the current roster of a team
  attempting team-policy missions together (P6-1)
- `mission_attempt_members` — the frozen snapshot of who was on the team
  for one specific attempt (P6-2)

Everything keys on `users`, same as the rest of `lms` — `MERGE_FK_REGISTRY`
is untouched.
"""

from app.models.missions.mission import (
    Mission,
    MissionAttempt,
    MissionAttemptMember,
    MissionPrerequisite,
    MissionVariant,
)
from app.models.missions.team import MissionTeam, MissionTeamMember

__all__ = [
    "Mission",
    "MissionAttempt",
    "MissionAttemptMember",
    "MissionPrerequisite",
    "MissionVariant",
    "MissionTeam",
    "MissionTeamMember",
]
