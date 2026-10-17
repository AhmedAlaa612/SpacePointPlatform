"""Competition judging schemas (2026-08-24) — rubric authoring, blind
per-judge scoring, the leaderboard, and judge-roster management. See
`services/competitions/judging.py` and `services/competitions/judges.py`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from app.schemas.lms import LmsSubmissionLink
from app.schemas.lms_admin import StudentSummaryOut
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
    is_observer: bool = False
    join_code: str | None = None
    roster_team_id: str | None = None


class CompetitionTeamCreateIn(BaseModel):
    name: str
    is_observer: bool = False


class TeamCheckpointStateOut(BaseModel):
    """One checkpoint gate's lock state for one team — backs the ops Teams
    tab's gate badges + per-gate unlock button. `status` is the team's own
    shared row (`done` = locked, anything else = open); a team with no row
    yet reads `pending`."""
    item_id: UUID
    title: str
    position: int
    status: str


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


class CompetitionRubricSubCriterionIn(BaseModel):
    key: str
    label: str
    max_points: int


class CompetitionRubricCriterionIn(BaseModel):
    key: str
    label: str
    max_points: int
    scored_by: Literal["judge", "operations"] = "judge"
    sub_criteria: list[CompetitionRubricSubCriterionIn] = []


class CompetitionRubricSubCriterionOut(BaseModel):
    key: str
    label: str
    max_points: int
    position: int


class CompetitionRubricCriterionOut(BaseModel):
    key: str
    label: str
    max_points: int
    position: int
    scored_by: str = "judge"
    sub_criteria: list[CompetitionRubricSubCriterionOut] = []


class CompetitionRubricIn(BaseModel):
    name: str
    criteria: list[CompetitionRubricCriterionIn]


class CompetitionRubricOut(BaseModel):
    id: UUID
    program_id: UUID
    cohort_id: UUID | None = None
    name: str
    criteria: list[CompetitionRubricCriterionOut]


class CompetitionScoreIn(BaseModel):
    criterion_scores: dict[str, float]
    criterion_comments: dict[str, str] = {}
    bonus_points: float = 0.0
    timing_adjustment: float = 0.0
    notes: str | None = None
    # False (default): an autosaved draft — stored, but doesn't count as
    # "scored" anywhere. True: the judge's own deliberate submit click.
    submitted: bool = False


class CompetitionScoreOut(BaseModel):
    id: UUID
    team_id: UUID
    judge_user_id: UUID
    criterion_scores: dict[str, float]
    criterion_comments: dict[str, str] = {}
    bonus_points: float = 0.0
    timing_adjustment: float = 0.0
    total_points: float
    notes: str | None = None
    submitted_at: datetime | None = None
    submitted: bool = False


class CompetitionJudgeScoreOut(BaseModel):
    judge_user_id: UUID
    judge_name: str = "Judge"
    total_points: float = 0.0


class CompetitionLeaderboardRowOut(BaseModel):
    rank: int
    team_id: UUID
    team_name: str
    score: float | None = None
    score_percent: float | None = None
    qualification: str | None = None
    judges_scored: int
    status: str  # scored|unscored
    judge_scores: list[CompetitionJudgeScoreOut] = []
    # Inferred by name-match against a later-created sibling cohort under
    # the same program — see leaderboard()'s own docstring. None = not
    # advanced (yet), otherwise the sibling cohort name(s) it advanced to.
    advanced_to: str | None = None
    # Timing & Submission Window fields:
    timing_adjustment: float | None = 0.0
    timing_badge: str | None = None
    timing_tier_name: str | None = None
    is_timing_override: bool = False
    timing_override_notes: str | None = None
    final_locked_at: datetime | None = None
    first_locked_at: datetime | None = None
    raw_judge_score: float | None = None
    ops_score: float | None = None
    ops_max_points: float | None = None
    ops_criterion_scores: dict[str, float] = {}
    ops_criterion_notes: str | None = None
    is_observer: bool = False


class CompetitionVisibilitySettings(BaseModel):
    show_score: bool = True
    show_rank: bool = True
    show_breakdown: bool = True
    show_ops_criteria: bool = True
    show_ops_comments: bool = True
    show_judge_comments: bool = True


class CompetitionPublishIn(BaseModel):
    visibility_settings: CompetitionVisibilitySettings = CompetitionVisibilitySettings()


class StudentCriterionScoreBreakdown(BaseModel):
    key: str
    label: str
    max_points: int
    average_points: float | None = None
    subs: list[CriterionSubScoreItem] = []


class StudentJudgeCriteriaComment(BaseModel):
    criterion: str
    comment: str


class CompetitionStudentResultOut(BaseModel):
    team_id: UUID
    team_name: str
    status: str  # scored | unscored | pending_publication
    locked: bool = False
    locked_at: datetime | None = None
    published: bool = False
    qualification: str | None = None
    timing_adjustment: float | None = None
    timing_badge: str | None = None

    # Visibility-gated fields (null if disabled or unpublished)
    final_score: float | None = None
    score_percent: float | None = None
    raw_judge_score: float | None = None
    rank: int | None = None
    total_teams: int | None = None

    criteria_breakdown: list[StudentCriterionScoreBreakdown] | None = None
    ops_score: float | None = None
    ops_max_points: float | None = None
    ops_breakdown: list[CriterionScoreItem] | None = None

    ops_comments: str | None = None
    judge_comments: list[str] | None = None
    judge_criteria_comments: list[StudentJudgeCriteriaComment] | None = None

    visibility_settings: CompetitionVisibilitySettings | None = None


class SubmissionWindowItem(BaseModel):
    id: str
    name: str
    cutoff_at: str  # ISO string
    points: float = 0.0
    badge: str | None = None
    color: str | None = "green"
    description: str | None = None
    is_deadline: bool = False


class CohortSubmissionWindowsUpdate(BaseModel):
    windows: list[SubmissionWindowItem]


class TeamTimingAdjustmentUpdate(BaseModel):
    override_points: float | None = None
    notes: str | None = None


class CriterionSubScoreItem(BaseModel):
    key: str
    label: str
    max_points: int
    awarded_points: float | None = None


class CriterionScoreItem(BaseModel):
    key: str
    label: str
    max_points: int
    awarded_points: float | None = None
    comment: str | None = None
    subs: list[CriterionSubScoreItem] = []


class JudgeEvaluationDetailOut(BaseModel):
    judge_user_id: UUID
    judge_name: str
    judge_email: str
    submitted_at: datetime | None = None
    total_points: float
    bonus_points: float = 0.0
    timing_adjustment: float = 0.0
    notes: str | None = None
    criteria: list[CriterionScoreItem] = []


class TeamScoreBreakdownOut(BaseModel):
    team_id: UUID
    team_name: str
    cohort_id: UUID
    status: str
    qualification: str | None = None
    final_score: float | None = None
    score_percent: float | None = None
    raw_judge_score: float | None = None
    timing_adjustment: float | None = None
    timing_badge: str | None = None
    is_timing_override: bool = False
    timing_override_notes: str | None = None
    final_locked_at: datetime | None = None
    first_locked_at: datetime | None = None
    judges: list[JudgeEvaluationDetailOut] = []
    ops_score: float | None = None
    ops_max_points: float | None = None
    ops_criterion_scores: dict[str, float] = {}
    ops_criterion_notes: str | None = None
    ops_breakdown: list[CriterionScoreItem] = []


class OpsScoreIn(BaseModel):
    criterion_scores: dict[str, float] = {}
    notes: str | None = None


class OpsScoreOut(BaseModel):
    team_id: UUID
    ops_criterion_scores: dict[str, float]
    ops_criterion_notes: str | None = None
    ops_scored_at: datetime | None = None
    ops_scored_by_name: str | None = None


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
    visibility_settings: CompetitionVisibilitySettings = CompetitionVisibilitySettings()


class CompetitionSubmissionItemOut(BaseModel):
    item_id: UUID
    title: str
    item_type: str
    status: str
    submitted_url: str | None = None
    # 2026-09-16 — see LmsProgramItem.submission_field_type's own comment.
    submission_field_type: Literal["text", "link"] = "link"
    submitted_text: str | None = None
    # 2026-09-14 — set (alongside submitted_url mirroring the first link)
    # only for a submission_multi_link item; the judge/ops team-detail view
    # renders these grouped under the one submission instead of a bare link.
    submission_multi_link: bool = False
    submitted_links: list[LmsSubmissionLink] | None = None
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
    # True once the team has hit "Final Submit" (Team.final_locked_at is
    # set) — same any-judge, not just-this-judge, visibility as a locked
    # checklist genuinely is.
    locked: bool = False
    locked_at: datetime | None = None
    roster_team_id: str | None = None
    member_count: int = 0
    items_done: int = 0
    items_total: int = 0
    pct: int = 0


class CompetitionTeamDetailOut(BaseModel):
    team: TeamOut
    submissions: list[CompetitionSubmissionItemOut]
    # Defaults to [] so a cohort running only individual missions (every
    # cohort today, until team-scoped mission_run items are authored) never
    # notices this field exists.
    mission_runs: list[CompetitionMissionRunOut] = []
    rubric: CompetitionRubricOut | None = None
    own_score: CompetitionScoreOut | None = None
    locked: bool = False
    locked_at: datetime | None = None
    # Operations-graded scores for context — read-only on the judge surface
    # (leaf `parent.sub` keys plus recomputed parent keys, same shape as the
    # operations endpoint stores). Judges never see who scored what, only
    # the numbers, and they can't edit them.
    ops_criterion_scores: dict[str, float] = {}
    ops_max_points: float | None = None


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
    batch_id: UUID | None = None
    status: str | None = None
    progress: dict[str, int] | None = None
    error: str | None = None


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
    gender: str | None = None
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
    gender: str | None = None
    nationality: str | None = None
    school: str | None = None


class CompetitionImportConfirmIn(BaseModel):
    rows: list[CompetitionImportConfirmRowIn]

    # Batch-level, applied to every row — same default-on convention as the
    # single member-add path and the rest of the app's registration flows.
    send_ticket_email: bool = True
    send_welcome_email: bool = True
    async_mode: bool = False


class CompetitionAssignableStudentOut(StudentSummaryOut):
    """The Assign tab's own search result (2026-09-14, `registered`/
    `lms_access` added 2026-09-15) — the same student row `/lms/admin/
    students` returns, plus this cohort's own state: `team_id` (the roster
    grouping code) and `team_name` when this student is already on a team
    in *this* cohort (both None otherwise), whether they have a
    Registration here at all (`registered` — the tab's search is
    platform-wide by default, so this distinguishes an actual competition
    registrant from someone who merely matched the name/email search), and
    whether they already have this cohort's LMS program checklist
    (`lms_access`, via `LmsProgramAssignment`, regardless of how they got
    it — invite-code grant, desk registration, or the Assign flow itself).
    Drives the `registered_only`/`team_status`/`lms_status` filters
    server-side, same idea as the original `unassigned_only` filter.

    Assign rebuild (2026-10): `card_number`/`card_id` for the Card ID
    column + sortable ID, `roles` so the Staff toggle can show/filter the
    account's actual roles. `lms_access` is kept for back-compat but the
    tab's "In program" state reads `registered` — registration and LMS
    assignment are created interchangeably by every assign path."""
    team_id: str | None = None
    team_name: str | None = None
    team_uuid: UUID | None = None
    registered: bool = False
    lms_access: bool = False
    is_observer: bool = False
    card_number: int | None = None
    card_id: str | None = None
    roles: list[str] = []


class CompetitionAssignableStudentsPage(BaseModel):
    """Paginated wrapper for the Assign tab search (2026-10 rebuild) —
    the tab lists the whole platform's accounts, so an uncapped list is
    no longer viable. `items` carries the page's rows, `total` the full
    match count for the pagination controls."""
    items: list[CompetitionAssignableStudentOut] = []
    total: int = 0
    page: int = 1
    page_size: int = 25


class CompetitionRegisterUsersIn(BaseModel):
    """Add-to-program without a team (2026-10 rebuild) — registers each
    account into the cohort (find-or-create Registration +
    LmsProgramAssignment, auto-creating a Contact when the account has
    none) and leaves them teamless (`no_team` backlog). Staff accounts
    assigned this way get the `observer` role appended + a
    `mode="observer"` assignment."""
    user_ids: list[UUID] = []
    send_welcome_email: bool = True
    send_ticket_email: bool = True


class CompetitionAssignStudentRowIn(BaseModel):
    """One row of the Assign tab's bulk submit — a student already found via
    `/lms/admin/students` search, plus the Team ID ops typed in for them
    (same editable-per-row feel as the Roster import table). `team_name` is
    left in for parity with the CSV path's per-row rename fallback, but the
    Assign tab itself never shows a name field — team naming stays the
    student's own deadline-gated step (see `registration_import.py`'s
    module docstring); ops assigning a bad name here is not a supported UI
    path, just not actively blocked by this schema either."""
    user_id: UUID
    team_id: str
    team_name: str | None = None


class CompetitionAssignStudentsIn(BaseModel):
    rows: list[CompetitionAssignStudentRowIn]

    # Same default-on convention as the Roster import batch toggles — see
    # that schema's own comment. `send_welcome_email` only matters for a row
    # that turns out to need a *new* student account (see
    # sync_registration_lms's own docstring) — every row here already has
    # one from self-signup, so in practice this only ever gates the "you're
    # registered for X" notice sync_registration_lms sends either way.
    send_ticket_email: bool = True
    send_welcome_email: bool = True


class CompetitionAssignStudentRowOut(BaseModel):
    row_number: int
    user_id: UUID | None = None
    team_id: str | None = None
    team_name: str | None = None
    disposition: str  # created|matched|error — same vocabulary as CompetitionImportRowOut
    reason: str | None = None


class CompetitionAssignStudentsOut(BaseModel):
    summary: dict[str, int]
    rows: list[CompetitionAssignStudentRowOut]


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


# ── Team analytics (2026-09-16) ─────────────────────────────────────────
# The Analysis tab's one payload — see `services/competitions/analytics.py`
# for where each number comes from, and in particular why `mission_run`
# items are reported in `missions` rather than as `items` bars.

class CompetitionAnalyticsItemOut(BaseModel):
    """One checklist item's completion rate. `denominator` names what
    `total` counts — teams for a team-scoped item, students holding this
    cohort's assignment for an individual one — so the frontend never has
    to infer it from `scope`."""
    item_id: UUID
    title: str
    item_type: str
    scope: Literal["team", "individual"]
    position: int
    optional: bool
    deadline_at: datetime | None = None
    denominator: Literal["teams", "students"]
    total: int
    done: int
    awaiting: int
    pending: int
    pct: int


class CompetitionAnalyticsMissionOut(BaseModel):
    mission_id: UUID
    title: str
    scope: Literal["team", "individual"]
    total: int
    passed: int
    in_progress: int
    not_started: int


class CompetitionAnalyticsDeliverableOut(BaseModel):
    """One team-scoped deliverable's state for one team —
    every one of them (required and optional), not just the missing ones, so a done item can show
    what was actually submitted instead of ops having to click through to
    the checklist for it."""
    item_id: UUID
    title: str
    status: str
    optional: bool = False
    submitted_url: str | None = None
    submitted_text: str | None = None
    submitted_links: list[LmsSubmissionLink] | None = None


class CompetitionAnalyticsTeamMemberOut(BaseModel):
    name: str
    last_login_at: datetime | None = None


class CompetitionTeamQuizSubmissionOut(BaseModel):
    user_id: UUID
    student_name: str
    assignment_id: UUID | None = None
    item_id: UUID
    quiz_title: str
    status: str
    score: int | None = None
    total: int | None = None
    submitted_at: datetime | None = None


class CompetitionAnalyticsTeamOut(BaseModel):
    """One team's progress against the cohort's *required* team-scoped
    deliverables. `deliverables` covers every one of them — done ones
    carry their submitted content, the rest are ops's outstanding work
    (awaiting_confirmation included, since confirming it is exactly that)."""
    team_id: UUID
    team_name: str
    roster_team_id: str | None = None
    is_observer: bool = False
    member_count: int
    members: list[CompetitionAnalyticsTeamMemberOut] = []
    never_logged_in: int
    items_total: int
    items_done: int
    awaiting: int
    pct: int
    deliverables: list[CompetitionAnalyticsDeliverableOut] = []
    # Team-scoped Design mission runs on this team's checklist, if any —
    # cheap (MissionAttempt.status only, no design-dashboard cascade, see
    # the module docstring in services/competitions/analytics.py). Empty
    # for any cohort with no team-scoped mission_run item, which is most
    # of them today.
    mission_runs: list[CompetitionMissionRunOut] = []
    quiz_submissions: list[CompetitionTeamQuizSubmissionOut] = []
    last_activity_at: datetime | None = None
    stalled: bool
    # True once the team has hit "Final Submit" (Team.final_locked_at is
    # set) — read straight off the already-loaded Team row, no new query.
    locked: bool = False
    locked_at: datetime | None = None
    locked_by_name: str | None = None
    locked_by_email: str | None = None
    locked_by_id: UUID | None = None


class CompetitionAnalyticsActivityOut(BaseModel):
    date: date
    updates: int


class CompetitionAnalyticsTotalsOut(BaseModel):
    teams: int
    students_on_teams: int
    avg_team_size: float
    empty_teams: int
    registered_students: int
    students_without_team: int
    assigned_students: int
    never_logged_in: int
    deliverables_per_team: int
    deliverables_done: int
    deliverables_awaiting: int
    teams_complete: int
    teams_not_started: int
    teams_stalled: int
    avg_team_pct: int


class CompetitionAnalyticsOut(BaseModel):
    cohort_id: UUID
    cohort_name: str
    totals: CompetitionAnalyticsTotalsOut
    items: list[CompetitionAnalyticsItemOut] = []
    missions: list[CompetitionAnalyticsMissionOut] = []
    teams: list[CompetitionAnalyticsTeamOut] = []
    activity: list[CompetitionAnalyticsActivityOut] = []
    stalled_after_days: int


# ── Certificates (2026-09) ───────────────────────────────────────────────────

class CompetitionCertificateRecipientOut(BaseModel):
    registration_id: UUID
    user_id: UUID | None = None
    contact_id: UUID
    student_name: str
    email: str | None = None
    team_id: UUID | None = None
    team_name: str | None = None
    submissions_done: int
    submissions_total: int
    required_submissions_total: int
    # Required vs optional split — optionals are bonus only and never drive
    # eligibility. Defaults keep older cached payloads valid.
    required_submissions_done: int = 0
    optional_submissions_done: int = 0
    optional_submissions_total: int = 0
    team_locked: bool = False
    meets_locked_only: bool = False
    meets_participation: bool = False
    meets_at_least_one: bool
    meets_all_completed: bool
    certificate_type_earned: str | None = None
    certificate_issued: bool
    certificate_id: UUID | None = None
    certificate_generated_at: datetime | None = None


class CompetitionCertificateRecipientsSummaryOut(BaseModel):
    program_name: str | None = None
    cohort_name: str | None = None
    dates: str | None = None
    total_registered: int
    submission_items_total: int
    required_submissions_total: int
    locked_only_count: int = 0
    participation_count: int = 0
    at_least_one_count: int
    all_completed_count: int
    recipients: list[CompetitionCertificateRecipientOut]
    templates: list[dict] | None = None
    default_template_id: str | None = None


class CompetitionCertificateSendIn(BaseModel):
    filter: Literal["locked_only", "participation", "at_least_one", "all_completed", "custom", "all"] = "at_least_one"
    registration_ids: list[UUID] | None = None
    theme: str = "dark"
    template_id: str | None = None
    skip_already_issued: bool = True
    custom_email_subject: str | None = None
    custom_email_body: str | None = None
    save_email_to_template: bool = False
    # Bulk override (2026-09-30) — issue every targeted recipient as this
    # type regardless of what the system computed for them. None = per
    # recipient earned type, as before.
    force_certificate_type: Literal["completion", "participation"] | None = None


class CompetitionCertificateDownloadIn(BaseModel):
    filter: Literal["locked_only", "participation", "at_least_one", "all_completed", "all"] = "at_least_one"
    theme: str = "dark"
    template_id: str | None = None
    registration_ids: list[UUID] | None = None
    force_certificate_type: Literal["completion", "participation"] | None = None


class CompetitionCertificateTestEmailIn(BaseModel):
    """Send a test certificate email to a specific address with the current config."""
    to_email: str
    recipient_name: str | None = None  # Name shown on the certificate PDF; defaults to "Test Recipient"
    theme: str = "dark"
    template_id: str | None = None
    certificate_type: Literal["completion", "participation"] = "completion"
    custom_email_subject: str | None = None
    custom_email_body: str | None = None


class CompetitionCertificateSendResultOut(BaseModel):
    status: str = "queued"
    sent_count: int = 0
    skipped_count: int = 0
    total_targeted: int = 0
    recipient_names: list[str] = []
    errors: list[str] = []

