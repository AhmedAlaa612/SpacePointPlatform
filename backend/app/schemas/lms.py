"""LMS student-facing schemas (LM1-3).

The content models are the *second* enforcement of the §2 answer-leakage
guarantee. Every model is `extra="forbid"`, so a payload that retains
`is_correct` or `explanation` fails response validation instead of silently
passing — the leak the service-layer `student_view` already strips is caught
again at the response boundary (plan: "Pydantic response models on the student
routes enforce it a second time").
"""

from datetime import date, datetime, time
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.curriculum import PrerequisiteItemOut


class ContentText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str


class QuizOptionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class QuizQuestionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str
    options: list[QuizOptionOut]


class ContentQuiz(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pass_threshold: int
    questions: list[QuizQuestionOut]


class FlashcardCardOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str
    definition: str


class ContentFlashcards(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    cards: list[FlashcardCardOut]


class ContentVideo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcode_status: str | None = None
    duration_seconds: int | None = None
    # The Video row's own id — needed by the player to call the generic
    # /videos/{video_id}/token|playlist|segment|key surface (routers/video.py),
    # which is keyed by video_id, not item_id. None only when no Video row
    # exists yet for this item (never uploaded), same case transcode_status
    # is already None for.
    video_id: str | None = None


class ContentAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filename: str | None = None
    size_bytes: int | None = None


class ContentMission(BaseModel):
    """P5-5 — a mission embedded in a course module. `mission_title`/
    `mission_kind`/`points`/`attempt_status` are enriched by the router
    (mirrors ContentVideo's transcode_status — not stored in `content`
    itself, looked up fresh per request)."""
    model_config = ConfigDict(extra="forbid")
    mission_id: UUID
    variant_id: UUID | None = None
    mission_title: str | None = None
    mission_kind: str | None = None
    points: int | None = None
    attempt_status: str | None = None


ModuleContent = Union[ContentQuiz, ContentText, ContentFlashcards, ContentVideo, ContentAttachment, ContentMission]


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────

class CheckpointNoteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body: str


class CheckpointQuizOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_type: Literal["mcq", "multiselect", "open"]
    prompt: str
    # None for open questions — nothing to choose from.
    options: list[QuizOptionOut] | None = None


CheckpointContent = Union[CheckpointNoteOut, CheckpointQuizOut]


class VideoCheckpointOut(BaseModel):
    id: UUID
    start_seconds: float
    end_seconds: float | None = None
    kind: Literal["note", "quiz"]
    content: CheckpointContent


class CheckpointAnswerIn(BaseModel):
    # int (mcq), list[int] (multiselect), or str (open) — validated against
    # the checkpoint's actual question_type server-side, same "don't trust
    # the client's own shape" posture as QuizAnswersIn.
    answer: int | list[int] | str


class CheckpointAnswerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # None for open questions (not graded) or if the student skipped.
    correct: bool | None = None
    explanation: str | None = None


# ── catalog / course outline (login-only) ───────────────────────────────────

class CourseCatalogOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str
    image_url: str | None = None
    level: str | None = None
    track: str | None = None
    access_mode: str = "open"  # P1-7 — open|invite|paid
    enrolled: bool = False  # this caller's own active, unexpired enrollment
    locked: bool = False  # 7B-2 — unmet prerequisites; independent of access_mode


# ── my-courses dashboard (student, LMS redesign 2026-08-06) ────────────────

class DashboardStatsOut(BaseModel):
    in_progress: int
    total_enrolled: int
    modules_done: int


class ResumePointerOut(BaseModel):
    course_id: UUID
    course_title: str
    module_id: UUID
    module_title: str
    next_item_id: UUID | None = None
    mandatory_completed: int
    mandatory_total: int


class DashboardCourseOut(BaseModel):
    course_id: UUID
    title: str
    kind: str
    status: str  # not_started | in_progress | completed
    modules_done: int
    modules_total: int
    pct: int


class MyCoursesOut(BaseModel):
    stats: DashboardStatsOut
    resume: ResumePointerOut | None = None
    courses: list[DashboardCourseOut]


class ActivityItemOut(BaseModel):
    item_id: UUID
    item_title: str | None = None
    item_kind: str
    course_id: UUID
    course_title: str
    completed_at: datetime | None = None


class ModuleLockOut(BaseModel):
    module_id: UUID
    title: str | None = None
    position: int
    locked: bool
    mandatory_total: int
    mandatory_completed: int
    total_items: int = 0


class CourseDetailOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    kind: str
    enrolled: bool
    completed: bool
    modules: list[ModuleLockOut]
    image_url: str | None = None
    outcomes: list[str] = []
    level: str | None = None
    track: str | None = None
    instructor_name: str | None = None
    instructor_title: str | None = None
    instructor_photo_url: str | None = None
    access_mode: str = "open"  # P1-7 — open|invite|paid, drives the CTA
    locked: bool = False  # 7B-2 — unmet prerequisites; independent of access_mode
    prerequisites: list[PrerequisiteItemOut] = []
    # Stage S — integer minor units, matching Stripe's unit_amount. NULL
    # unless access_mode == "paid".
    price_cents: int | None = None
    currency: str = "usd"


# ── enrollment ──────────────────────────────────────────────────────────────

class EnrollIn(BaseModel):
    course_id: UUID


class EnrollmentOut(BaseModel):
    id: UUID
    course_id: UUID
    source: str
    status: str
    created_at: datetime | None = None
    expires_at: datetime | None = None  # P1-3 — NULL means perpetual


# ── checkout (Stage S, Stripe) ───────────────────────────────────────────────

class CheckoutSessionOut(BaseModel):
    checkout_url: str


class CheckoutFulfillOut(BaseModel):
    status: str  # pending | paid | refunded | disputed | failed
    course_id: UUID | None = None
    learning_path_id: UUID | None = None


# ── module read (enrolled student only) ─────────────────────────────────────

class ModuleItemOut(BaseModel):
    id: UUID
    kind: Literal["video", "text", "quiz", "flashcards", "attachment", "mission"]
    title: str | None = None
    position: int
    content: ModuleContent
    # this student's own per-item state, so the player can render progress
    status: str | None = None


class ModuleOut(BaseModel):
    id: UUID
    course_id: UUID
    title: str
    position: int
    items: list[ModuleItemOut]


# ── progress + quiz submission ──────────────────────────────────────────────

class ProgressIn(BaseModel):
    action: Literal["video-watched", "text-viewed", "quiz-attempt", "flashcards-skipped", "attachment-viewed"]


class ProgressOut(BaseModel):
    status: str
    quiz_attempts: int
    best_score: float | None = None
    completed_at: datetime | None = None


class QuizAnswersIn(BaseModel):
    answers: list[int]


class QuizAnswerCheckIn(BaseModel):
    question_index: int
    answer: int


class QuizAnswerCheckOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correct: bool
    explanation: str | None = None
    correct_text: str | None = None


class AttachmentUrlOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    filename: str | None = None


class QuizReviewItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str | None = None
    selected: int
    correct: bool
    explanation: str | None = None
    correct_text: str | None = None


class QuizReviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float
    passed: bool
    pass_threshold: int
    attempts: int
    best_score: float | None = None
    questions: list[QuizReviewItemOut]


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

class LearningPathCatalogOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    image_url: str | None = None
    course_count: int
    mission_count: int
    total_duration_seconds: int
    pct: int
    # 2026-08-12 — "am I on this path", so the landing page can split
    # "your paths" from "explore". True iff the caller has an active
    # enrollment in at least one of the path's courses; `pct` alone can't
    # answer it (a freshly-started path is 0% but is still yours), which is
    # the same distinction `CourseCatalogOut.enrolled` already draws.
    enrolled: bool = False
    access_mode: str = "open"  # mirrors CourseCatalogOut.access_mode — open|invite|paid
    # Bundle pricing (2026-08-21) — null price_cents means not purchasable,
    # same convention as Course. `fully_owned` is true iff the caller already
    # has an active enrollment in every step's course, i.e. there's nothing
    # left for a bundle purchase to grant.
    price_cents: int | None = None
    currency: str = "usd"
    fully_owned: bool = False


class MyCertificateOut(BaseModel):
    """One earned LMS certificate (2026-08-13). `url` is signed at query
    time from bucket/file_path, the resolve_url pattern — never stored."""
    id: UUID
    type: str  # lms_course_completion | lms_path_completion
    title: str  # the course or learning path it was earned for
    course_id: UUID | None = None
    learning_path_id: UUID | None = None
    issued_at: datetime | None = None
    url: str | None = None


class LearningPathStepOut(BaseModel):
    position: int
    course_id: UUID
    title: str
    kind: str
    state: Literal["done", "current", "mission", "locked"]
    pct: int
    modules_done: int
    modules_total: int


class LearningPathDetailOut(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    image_url: str | None = None
    pct: int
    course_count: int
    mission_count: int
    total_duration_seconds: int
    steps: list[LearningPathStepOut]
    access_mode: str = "open"
    # True iff the caller already holds an active enrollment in at least one
    # step course — lets the client tell a genuine self-enrol ("Start path")
    # from an already-granted invite/paid path ("Continue"), which must
    # navigate straight to the next step instead of re-POSTing to `/start`.
    enrolled: bool = False
    price_cents: int | None = None
    currency: str = "usd"
    fully_owned: bool = False


# ── leaderboard (P2-4) — not wired into any student-facing page yet, D6 is
# still an open operator decision (PHASE2_EXECUTION_PLAN.md §2) ────────────

class LeaderboardEntryOut(BaseModel):
    rank: int
    user_id: UUID
    display_name: str
    points: int


# ── my-programs (P4-3) — the cohort view a student cannot currently see ────

class MyProgramCourseOut(BaseModel):
    course_id: UUID
    title: str
    enrolled: bool
    progress_pct: int


class MyProgramOut(BaseModel):
    registration_id: UUID
    cohort_id: UUID
    program_name: str
    cohort_name: str
    starts_on: date | None = None
    ends_on: date | None = None
    location_name: str | None = None
    location_address: str | None = None
    instructor_name: str | None = None
    attended_sessions: int
    total_sessions: int
    courses: list[MyProgramCourseOut] = []
    missions: list = []  # Stage 5 fills this in; empty, not omitted, until then


# ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────

LmsProgramItemStatus = Literal["pending", "done", "awaiting_confirmation"]


class LmsSubmissionLink(BaseModel):
    """One entry in a multi-field submission (2026-09-14, ops's own toggle —
    see LmsProgramItem.submission_multi_link; field_type added 2026-09-16).
    `label` is free text (e.g. "Member 1 link", "Team link"), optional so a
    stray extra entry doesn't need one. Exactly one of `url`/`text` is ever
    populated, matching the field's own `field_type` — a link isn't
    validated as a real URL beyond non-empty (same posture the single-link
    `submitted_url`/`LmsProgramItemSubmitIn.url` has always had), and text
    is free-form paragraph content, not a link. Both optional at the schema
    level (routers/lms/student.py::submit_program_item enforces "at least
    one of them, matching this label's configured type" — the schema can't
    know which type a given label is on its own)."""
    label: str | None = Field(default=None, max_length=80)
    url: str | None = Field(default=None, max_length=512)
    text: str | None = Field(default=None, max_length=4000)


class LmsSubmissionLinkLabel(BaseModel):
    """One entry in ops's own fixed field set for a `submission_multi_link`
    item (2026-09-14, "link" originally; text fields added 2026-09-16) —
    see `LmsProgramItem.submission_link_labels`'s own comment. `required`
    is ops's per-field checkbox: a required field blocks submission until
    it has an answer, an optional one doesn't. `field_type` decides whether
    the student sees a single-line link input or a multi-line text area —
    defaults to "link" so every field authored before this existed keeps
    behaving exactly as it did."""
    label: str = Field(min_length=1, max_length=80)
    required: bool = False
    field_type: Literal["text", "link"] = "link"


class LmsProgramChecklistItemOut(BaseModel):
    id: UUID
    position: int
    item_type: str
    title: str
    description: str | None = None
    optional: bool
    requires_confirmation: bool
    status: LmsProgramItemStatus
    # Resolved link, whatever the item type: a course id, a mission
    # attempt id (the ops-assigned run itself, never the mission catalog
    # entry), or the stored external_url — the frontend picks which by
    # `item_type`, same shape the Poster tab already established.
    course_id: UUID | None = None
    mission_attempt_id: UUID | None = None
    # mission_id/mission_kind: which route a mission_run item's "Continue"
    # link needs — design/operate attempts have their own attempt-keyed
    # page, every other kind is viewed inline on the mission's own page.
    mission_id: UUID | None = None
    mission_kind: str | None = None
    external_url: str | None = None
    submission_prompt: str | None = None
    # True once a `pdf` item has a file uploaded — the student calls the
    # separate resolve-url endpoint to actually view it (never baked in
    # here), same posture as the Curriculum Library's list payload.
    has_pdf: bool = False
    # What the student themself submitted back, for a `submission` item.
    submitted_url: str | None = None
    # 2026-09-16 — the single-field submission's own type, and its answer
    # when that type is "text". Only meaningful when submission_multi_link
    # is False; defaults to "link" so every item authored before this
    # existed (the only kind there was) reads exactly as it did — a link
    # paste-back into submitted_url above.
    submission_field_type: Literal["text", "link"] = "link"
    submitted_text: str | None = None
    # 2026-09-14 — see LmsProgramItem.submission_multi_link's own comment.
    # `submitted_links` is only ever populated when `submission_multi_link`
    # is true; `submitted_url` above still mirrors its first link either way.
    submission_multi_link: bool = False
    submitted_links: list[LmsSubmissionLink] | None = None
    # 2026-09-14 — ops's own fixed label set for this item, in the order
    # ops entered them; None when the item is either not multi-link or is
    # an older multi-link item authored before this existed (that one
    # still takes free-text, student-entered labels — see submit_program_item).
    submission_link_labels: list[LmsSubmissionLinkLabel] | None = None
    # submission-only cutoff — students can no longer submit/replace once
    # past; already-submitted content and its confirmation are unaffected.
    deadline_at: datetime | None = None
    # session-only fields — always self-contained, never a live link to a
    # real Sessions-domain row (see LmsProgramItem.session_date's comment).
    session_date: date | None = None
    session_starts_at: time | None = None
    session_location: str | None = None
    session_meeting_url: str | None = None
    # Competition domain (2026-08-24) — individual (default) means
    # submitted_url/status above are this student's own, same as always.
    # team means they're the whole Team's shared fact: any member wrote
    # them, and updated_by_name/updated_at say who last did, since there's
    # no single "you" for a team row.
    scope: str = "individual"
    updated_by_name: str | None = None
    updated_at: datetime | None = None
    # ── Roadmap board (2026-09) ─────────────────────────────────────────
    # Which single Madar design phase a `mission_run` tile targets — NULL
    # means the whole mission (see LmsProgramItem.mission_step_key).
    mission_step_key: str | None = None
    gated: bool = False
    guideline_kind: str | None = None
    # A YouTube/Vimeo `video` guideline resolves straight into guideline_url
    # above (no different from a plain link — nothing signed/private about
    # a public embed URL). An *uploaded* `video` guideline instead flips
    # this flag and leaves guideline_url unset — the student calls the
    # separate resolve-url endpoint to actually view it, never baked in
    # here, same posture as `has_pdf`/the Curriculum Library's list payload.
    guideline_url: str | None = None
    guideline_video_uploaded: bool = False
    checkpoint_label: str | None = None
    poster_template_url: str | None = None
    # Derived, never stored — see compute_lock_states. True iff `gated`
    # and some earlier non-optional item on this checklist isn't done yet.
    locked: bool = False


class LmsProgramAssignmentSummaryOut(BaseModel):
    assignment_id: UUID
    lms_program_id: UUID
    name: str
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    items_total: int
    items_done: int
    pct: int
    next_item_title: str | None = None
    certificate_required: bool
    certificate_earned: bool


class LmsProgramChecklistOut(BaseModel):
    assignment_id: UUID
    lms_program_id: UUID
    name: str
    description: str | None = None
    image_url: str | None = None
    poster_template_url: str | None = None
    cohort_id: UUID | None = None
    cohort_name: str | None = None
    # Competition domain — the student's own team in this cohort, if any
    # (resolved once for the whole checklist, not per item). None when
    # they have no team yet or the program has no team-scoped items.
    team_name: str | None = None
    # None means the team's checklist is still editable — set once any
    # teammate has hit "Final Submit" (routers/lms/student.py::
    # final_submit_program). Same None-for-no-team/no-team-items posture
    # as team_name above.
    team_final_locked_at: datetime | None = None
    team_final_locked_by_name: str | None = None
    certificate_required: bool
    certificate_earned: bool
    items: list[LmsProgramChecklistItemOut]


class LmsProgramTeamNameIn(BaseModel):
    """A `team_setup` item's one action — see routers/lms/student.py's
    `set_team_name`. Trimmed and length-capped to `learner_teams.name`'s
    own column width (models/team.py)."""
    name: str = Field(min_length=1, max_length=100)


class LmsProgramItemSubmitIn(BaseModel):
    # Single-link items (the default) send `url`; a single *text*-type item
    # (2026-09-16, item.submission_field_type == "text") sends `text`
    # instead; a `submission_multi_link` item sends `links` instead of
    # either — routers/lms/student.py::submit_program_item picks which is
    # required off the item's own fields rather than here, so the 400 reads
    # as "submit a link"/"submit an answer"/"this item needs N fields"
    # instead of a bare 422.
    url: str | None = None
    text: str | None = Field(default=None, max_length=4000)
    links: list[LmsSubmissionLink] | None = None