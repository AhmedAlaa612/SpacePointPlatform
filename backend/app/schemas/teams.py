"""Domain-agnostic team schemas (2026-08-17) — generalized out of
`schemas/missions.py`'s `MissionTeamOut`/`MissionTeamCreateIn`. Imported
back into mission-specific schemas wherever a team is embedded (e.g.
`MissionDetailOut.my_teams`); Competition will import from here too.
"""

from uuid import UUID

from pydantic import BaseModel


class TeamOut(BaseModel):
    id: UUID
    name: str
    cohort_id: UUID | None = None
    member_ids: list[UUID] = []
    member_names: list[str] = []


class TeamCreateIn(BaseModel):
    name: str
    member_ids: list[UUID] = []
