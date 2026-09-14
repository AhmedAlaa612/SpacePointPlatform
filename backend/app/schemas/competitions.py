"""Competition judging schemas (2026-08-24) — rubric authoring, blind
per-judge scoring, the leaderboard, and judge-roster management. See
`services/competitions/judging.py` and `services/competitions/judges.py`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.teams import TeamOut


class CompetitionTeamOut(BaseModel):
    """Manual team management (2026-08-26) — like `TeamOut` but with
    emails, since the ops-facing Teams panel needs to show who's who
    without a second round trip per team."""
    id: UUID
    name: str
    cohort_id: UUID | None = None
    member_ids: list[UUID] = []
    member_names: list[str] = []
    member_emails: list[str] = []


class CompetitionTeamCreateIn(BaseModel):
    name: str


class CompetitionTeamRenameIn(BaseModel):
    name: str


class CompetitionTeamMemberIn(BaseModel):
    """Either `user_id` (an already-registered person) or `full_name` +
    `email` (find-or-create a brand-new one, the single-row equivalent of
    a Roster import row) — never both."""
    user_id: UUID | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    school: str | None = None

    # Only meaningful for the full_name+email (new person) path — user_id
    # just links an existing account, nothing to send. Both default True to
    # match every other registration path in the app (desk, public, general
    # bulk import) that sends both by default.
    send_ticket_email: bool = True
    send_welcome_email: bool = True


class CompetitionRubricCriterionIn(BaseModel):
    key: str
    label: str
    max_points: int


class CompetitionRubricCriterionOut(BaseModel):
    key: str
    label: str
    max_points: int
    position: int


class CompetitionRubricIn(BaseModel):
    name: str
    criteria: list[CompetitionRubricCriterionIn]


class CompetitionRubricOut(BaseModel):
    id: UUID
    program_id: UUID
    name: str
    criteria: list[CompetitionRubricCriterionOut]


class CompetitionScoreIn(BaseModel):
    criterion_scores: dict[str, int]
    bonus_points: int = 0
    # False (default): an autosaved draft — stored, but doesn't count as
    # "scored" anywhere. True: the judge's own deliberate submit click.
    submitted: bool = False


class CompetitionScoreOut(BaseModel):
    id: UUID
    team_id: UUID
    judge_user_id: UUID
    criterion_scores: dict[str, int]
    bonus_points: int
    total_points: int
    submitted_at: datetime | None = None
    submitted: bool = False


class CompetitionJudgeScoreOut(BaseModel):
    judge_user_id: UUID
    judge_name: str
    total_points: int


class CompetitionLeaderboardRowOut(BaseModel):
    rank: int
    team_id: UUID
    team_name: str
    score: float | None = None
    judges_scored: int
    status: str  # scored|unscored
    judge_scores: list[CompetitionJudgeScoreOut] = []
    # Inferred by name-match against a later-created sibling cohort under
    # the same program — see leaderboard()'s own docstring. None = not
    # advanced (yet), otherwise the sibling cohort name(s) it advanced to.
    advanced_to: str | None = None


class CompetitionJudgeOut(BaseModel):
    user_id: UUID
    full_name: str
    email: str


class CompetitionJudgeProgressOut(CompetitionJudgeOut):
    scored_count: int
    team_count: int
    onboarding_sent: bool


class CompetitionJudgeInviteIn(BaseModel):
    name: str
    email: str
    # "Send email" (2026-09-10) — same "the action always happens, the
    # notification is optional" toggle shape as send_welcome_email/
    # send_ticket_email elsewhere; the judge account/assignment is always
    # created either way.
    send_email: bool = True


class CompetitionPublicationOut(BaseModel):
    published: bool
    published_at: datetime | None = None


class CompetitionSubmissionItemOut(BaseModel):
    item_id: UUID
    title: str
    item_type: str
    status: str
    submitted_url: str | None = None
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class CompetitionMissionRunOut(BaseModel):
    """One team-scoped design mission run (Phase 3, 2026-09) — grouped by
    mission_id, since a run can be split into several checklist steps that
    all share one MissionAttempt. `attempt_id` is null until the team has
    one (e.g. not assigned to the checklist yet); `status` is
    `"not_started"` in that case, otherwise the attempt's own status
    (in_progress/submitted/passed/failed)."""
    mission_id: UUID
    title: str
    attempt_id: UUID | None = None
    status: str


class CompetitionJudgeCohortOut(BaseModel):
    id: UUID
    name: str
    program_name: str


class CompetitionJudgeTeamOut(TeamOut):
    """A team as seen on the judge's roster — `TeamOut` plus whether this
    judge (specifically, not any judge) has already scored it, so the judge
    UI can show a done/pending mark without a second round trip."""

    already_scored: bool = False


class CompetitionTeamDetailOut(BaseModel):
    team: TeamOut
    submissions: list[CompetitionSubmissionItemOut]
    # Defaults to [] so a cohort running only individual missions (every
    # cohort today, until team-scoped mission_run items are authored) never
    # notices this field exists.
    mission_runs: list[CompetitionMissionRunOut] = []
    rubric: CompetitionRubricOut | None = None
    own_score: CompetitionScoreOut | None = None


class CompetitionImportRowOut(BaseModel):
    row_number: int
    team_id: str | None = None
    team_name: str | None = None
    email: str | None = None
    disposition: str  # created|matched|error
    reason: str | None = None


class CompetitionImportResultOut(BaseModel):
    summary: dict[str, int]
    rows: list[CompetitionImportRowOut]


class CompetitionImportPreviewRowOut(BaseModel):
    """One parsed sheet row, before anything is written. `issues` is empty
    for a clean row; non-empty means ops needs to fix it (in the browser,
    via the confirm payload below) before it can be committed. `team_name`
    is optional (2026-09-14) — a blank one just means this team hasn't
    named itself yet, not a bad row; `team_id` (the sheet's own grouping
    key) is what's actually required."""
    row_number: int
    team_id: str | None = None
    team_name: str | None = None
    member_name: str | None = None
    email: str | None = None
    phone: str | None = None
    nationality: str | None = None
    school: str | None = None
    issues: list[str] = []


class CompetitionImportPreviewOut(BaseModel):
    rows: list[CompetitionImportPreviewRowOut]


class CompetitionImportConfirmRowIn(BaseModel):
    """The preview row, echoed back — possibly hand-edited (a fixed email,
    typically) — to actually commit. Same fields as the preview row, minus
    `issues`: the server re-validates on the way in rather than trusting
    whatever the client last saw."""
    row_number: int
    team_id: str | None = None
    team_name: str | None = None
    member_name: str | None = None
    email: str | None = None
    phone: str | None = None
    nationality: str | None = None
    school: str | None = None


class CompetitionImportConfirmIn(BaseModel):
    rows: list[CompetitionImportConfirmRowIn]

    # Batch-level, applied to every row — same default-on convention as the
    # single member-add path and the rest of the app's registration flows.
    send_ticket_email: bool = True
    send_welcome_email: bool = True


class CompetitionAdvanceTeamsIn(BaseModel):
    team_ids: list[UUID]
    to_cohort_id: UUID
    # "Send Ticket" (2026-09-10) — a promoted member's new-cohort ticket,
    # same toggle/mechanism as the desk and bulk-import registration flows.
    send_ticket_email: bool = True
    # "Send LMS onboarding mail" (2026-09-10) — independent of the ticket:
    # a promoted member may still never have set a password, so this isn't
    # covered by the (always-sent) congrats email alone.
    send_welcome_email: bool = True


class CompetitionAdvanceResultOut(BaseModel):
    team_id: UUID
    team_name: str
    to_team_id: UUID
    members_advanced: int
