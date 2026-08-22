"""LMS authoring schemas (LM1-5) — the `/lms/admin/*` input/output shapes.

Deliberately separate from `schemas/lms.py`: that file is the answer-leakage
choke point (every model there is `extra="forbid"` and strips `is_correct`/
`explanation`). These models are the *author's* view — they carry the
answers on purpose, because the author is the one writing them. Never import
these into a student-facing route.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModuleItemKind = Literal["video", "text", "quiz", "flashcards", "attachment", "mission"]


class InstructorOptionOut(BaseModel):
    """One row for the course-authoring instructor picker (LMS redesign,
    2026-08-06) — deliberately minimal, not the full User shape."""
    id: UUID
    full_name: str
    photo_url: str | None = None


class StaffOptionOut(BaseModel):
    """One row for the named-individual assignment picker (2026-08-12) —
    any staff account (every role except `student`), searchable by name so
    ops/facilitators can grant a course/mission to a specific person rather
    than only via the role-wide bulk grant."""
    id: UUID
    full_name: str
    email: str
    roles: list[str]


# ── student invite codes (2026-08-13) ───────────────────────────────────────

class InviteCodeOut(BaseModel):
    id: UUID
    code: str
    label: str | None = None
    is_active: bool
    max_uses: int
    used_count: int
    expires_at: datetime | None = None
    created_at: datetime | None = None
    # Convenience for the ops list — how many accounts actually signed up on
    # this code, counted from users.invitation_code_used rather than trusting
    # `used_count`, which only ever increments and can drift if an account is
    # later deleted.
    signups: int = 0


class InviteCodeCreate(BaseModel):
    code: str
    label: str | None = None
    max_uses: int = 30
    is_active: bool = True
    expires_at: datetime | None = None


class InviteCodeUpdate(BaseModel):
    code: str | None = None
    label: str | None = None
    max_uses: int | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


# ── invite-code course/path grants (2026-08-21) ─────────────────────────────

class InviteCodeGrantCreate(BaseModel):
    course_id: UUID | None = None
    learning_path_id: UUID | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "InviteCodeGrantCreate":
        if (self.course_id is None) == (self.learning_path_id is None):
            raise ValueError("Provide exactly one of course_id or learning_path_id")
        return self


class InviteCodeGrantOut(BaseModel):
    id: UUID
    product_type: Literal["course", "learning_path"]
    course_id: UUID | None = None
    course_title: str | None = None
    learning_path_id: UUID | None = None
    learning_path_title: str | None = None
    created_at: datetime | None = None


class InviteCodeGrantCreateOut(BaseModel):
    grant: InviteCodeGrantOut
    accounts_enrolled: int


# ── student management (2026-08-12) ─────────────────────────────────────────

class StudentSummaryOut(BaseModel):
    """One row for the student search/list.

    Was "deliberately minimal" on the theory that the profile page carries
    the rest — but a list you have to click through row by row to identify
    anyone isn't a roster. School, grade, join date and status are what let
    an operator scan a camp's intake, so they belong on the row.
    """
    id: UUID
    full_name: str
    nickname: str | None = None
    email: str
    # The code this account signed up with, and its batch label if it was an
    # ops-issued one (2026-08-13). None for students who predate the gate.
    invite_code: str | None = None
    invite_label: str | None = None
    # From the linked spine Contact — absent for accounts without one.
    school_name: str | None = None
    grade: str | None = None
    status: str | None = None
    created_at: datetime | None = None


class StudentProgramOut(BaseModel):
    """A subset of `my_programs`'s per-registration shape — only what the
    profile page shows; `my_programs` itself is reused as-is rather than
    duplicated (it already composes cohort/program/registration correctly
    for a given user, staff viewing a student is the same query shape as a
    student viewing themself)."""
    registration_id: UUID
    cohort_id: UUID
    program_name: str
    cohort_name: str
    starts_on: date | None = None
    ends_on: date | None = None


class StudentProfileOut(BaseModel):
    id: UUID
    full_name: str
    nickname: str | None = None
    # The account's default game avatar (an AVATAR_PRESETS key) — editable
    # here because a student could previously only change it from inside a
    # game lobby, which left staff no way to correct one.
    avatar: str | None = None
    email: str
    programs: list[StudentProgramOut]


# ── authored content shapes (mirrors LMS_EXECUTION_PLAN.md §2, answers included) ──

class AdminContentText(BaseModel):
    body: str


class AdminQuizOptionIn(BaseModel):
    text: str
    is_correct: bool = False


class AdminQuizQuestionIn(BaseModel):
    prompt: str
    explanation: str | None = None
    options: list[AdminQuizOptionIn] = Field(min_length=2)

    @model_validator(mode="after")
    def _validate_correct_option(self) -> "AdminQuizQuestionIn":
        # submit_quiz/check_quiz_answer take one answer index per question
        # (services/lms/quiz.py) — multi-answer isn't a supported shape, and
        # zero correct answers is a question no student can ever pass (B3).
        correct_count = sum(1 for o in self.options if o.is_correct)
        if correct_count != 1:
            raise ValueError(
                f"quiz questions need exactly one correct option, got {correct_count}"
            )
        return self


class AdminContentQuiz(BaseModel):
    pass_threshold: int = Field(ge=0, le=100, default=0)
    questions: list[AdminQuizQuestionIn] = Field(min_length=1)


class AdminFlashcardIn(BaseModel):
    term: str
    definition: str


class AdminContentFlashcards(BaseModel):
    title: str | None = None
    cards: list[AdminFlashcardIn] = Field(min_length=1)


class AdminContentVideo(BaseModel):
    """Empty on purpose — video state lives in `module_videos` (LM1-6)."""
    model_config = ConfigDict(extra="forbid")


class AdminContentAttachment(BaseModel):
    """Empty on purpose, same reasoning as AdminContentVideo — a PDF is
    binary, so it can't ride the JSON create/update body. The upload
    endpoint (POST .../items/{id}/attachment) writes bucket/path/filename/
    size_bytes into `content` directly once the file is actually on disk,
    same two-step "create the item, then upload the file" shape video
    uses (2026-08-09). No separate table needed like module_videos — a PDF
    has no async processing step, so there's nothing to track a state
    machine for; the file reference alone is the whole story."""
    model_config = ConfigDict(extra="forbid")


class AdminContentMission(BaseModel):
    """P5-5 — embeds a standalone mission inside a course module. `variant_id`
    pinned means every student sees that one difficulty; omitted means the
    student picks, same as attempting it standalone. No FK-existence check
    here (this validator has no db access, same shallow-validation posture
    every other kind's model already has) — an unknown mission_id just 404s
    when the student actually opens the item."""
    model_config = ConfigDict(extra="forbid")
    mission_id: UUID
    variant_id: UUID | None = None


AdminModuleContent = Union[
    AdminContentQuiz, AdminContentFlashcards, AdminContentText, AdminContentVideo, AdminContentAttachment,
    AdminContentMission,
]


# ── video checkpoints (timeline notes + mid-video quizzes, 2026-08-07) ───────
# Belong to the video item they're authored on, not a sibling module item —
# see the video_checkpoints migration docstring for why the old
# mid_video_at_seconds indirection was replaced.

CheckpointKind = Literal["note", "quiz"]
CheckpointQuestionType = Literal["mcq", "multiselect", "open"]


class AdminCheckpointNoteContent(BaseModel):
    body: str


class AdminCheckpointQuizContent(BaseModel):
    question_type: CheckpointQuestionType
    prompt: str
    explanation: str | None = None
    # Required for mcq/multiselect (answer choices), omitted for open.
    options: list[AdminQuizOptionIn] | None = None

    @model_validator(mode="after")
    def _validate_options(self) -> "AdminCheckpointQuizContent":
        if self.question_type == "open":
            if self.options:
                raise ValueError("open questions don't take options")
            return self
        if not self.options or len(self.options) < 2:
            raise ValueError(f"{self.question_type} questions need at least 2 options")
        correct_count = sum(1 for o in self.options if o.is_correct)
        if self.question_type == "mcq" and correct_count != 1:
            raise ValueError("mcq questions need exactly one correct option")
        if self.question_type == "multiselect" and correct_count < 1:
            raise ValueError("multiselect questions need at least one correct option")
        return self


class VideoCheckpointCreate(BaseModel):
    start_seconds: int = Field(ge=0)
    # Required for notes (a banner has a window); ignored for quizzes (a
    # quiz is a single moment) — enforced in the router, not here, since it
    # depends on `kind`.
    end_seconds: int | None = Field(default=None, ge=0)
    kind: CheckpointKind
    content: dict = Field(default_factory=dict)


class VideoCheckpointUpdate(BaseModel):
    start_seconds: int | None = Field(default=None, ge=0)
    end_seconds: int | None = Field(default=None, ge=0)
    content: dict | None = None


class VideoCheckpointAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    item_id: UUID
    start_seconds: int
    end_seconds: int | None
    kind: str
    content: dict


# ── courses ──────────────────────────────────────────────────────────────────

CourseLevel = Literal["beginner", "intermediate", "advanced"]
# P1-2 — open: any logged-in student self-enrols. invite: lists with a lock,
# only an admin grant (P1-5) enrols. paid: self-enrol starts a checkout
# (Stage S, not built yet — POST /lms/enroll 402s in the meantime).
CourseAccessMode = Literal["open", "invite", "paid"]


class CourseCreate(BaseModel):
    title: str
    description: str | None = None
    kind: Literal["course", "mission"] = "course"
    outcomes: list[str] = Field(default_factory=list)
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None
    access_mode: CourseAccessMode = "open"
    access_days: int | None = Field(default=None, ge=1)  # NULL = perpetual
    # Stage S (Stripe Checkout) — integer minor units, matching Stripe's
    # unit_amount. Only meaningful when access_mode == "paid"; the checkout
    # endpoint is what actually enforces "paid must have a positive price".
    price_cents: int | None = Field(default=None, ge=1)
    currency: str = "usd"


class CourseUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    kind: Literal["course", "mission"] | None = None
    outcomes: list[str] | None = None
    level: CourseLevel | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_title: str | None = None
    access_mode: CourseAccessMode | None = None
    access_days: int | None = Field(default=None, ge=1)
    price_cents: int | None = Field(default=None, ge=1)
    currency: str | None = None


class CourseAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    kind: str
    is_published: bool
    created_by: UUID
    created_at: datetime | None
    image_url: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    level: str | None = None
    track: str | None = None
    instructor_id: UUID | None = None
    instructor_name: str | None = None
    instructor_title: str | None = None
    access_mode: str = "open"
    access_days: int | None = None
    price_cents: int | None = None
    currency: str = "usd"


# ── modules ──────────────────────────────────────────────────────────────────

class ModuleCreate(BaseModel):
    title: str
    position: int | None = None


class ModuleUpdate(BaseModel):
    title: str | None = None
    position: int | None = None


class ModuleAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    course_id: UUID
    title: str
    position: int


class ModuleReorderIn(BaseModel):
    """Full ordered id list, not a single move — same shape works for
    drag-and-drop or up/down buttons, and lets the backend rewrite positions
    in one transaction instead of racing the unique constraint two requests
    at a time."""
    module_ids: list[UUID]


# ── items ────────────────────────────────────────────────────────────────────

class ItemCreate(BaseModel):
    kind: ModuleItemKind
    title: str | None = None
    is_required: bool = True
    position: int | None = None
    content: dict = Field(default_factory=dict)


class ItemUpdate(BaseModel):
    title: str | None = None
    is_required: bool | None = None
    position: int | None = None
    content: dict | None = None


class ItemAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    module_id: UUID
    kind: str
    title: str | None
    is_required: bool
    position: int
    content: dict


class ItemReorderIn(BaseModel):
    item_ids: list[UUID]


# ── LMS Program checklist (2026-08-21 redesign) ─────────────────────────────

LmsProgramItemType = Literal["course", "mission_run", "external_link", "submission", "article", "manual"]


class LmsProgramItemIn(BaseModel):
    item_type: LmsProgramItemType
    title: str
    description: str | None = None
    optional: bool = False
    requires_confirmation: bool = False
    course_id: UUID | None = None
    mission_id: UUID | None = None
    variant_id: UUID | None = None
    external_url: str | None = None
    submission_prompt: str | None = None
    position: int | None = None


class LmsProgramItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    position: int
    item_type: LmsProgramItemType
    title: str
    description: str | None
    optional: bool
    requires_confirmation: bool
    course_id: UUID | None
    mission_id: UUID | None
    variant_id: UUID | None
    external_url: str | None
    submission_prompt: str | None


class LmsProgramCreate(BaseModel):
    program_id: UUID | None = None
    name: str
    description: str | None = None
    certificate_required: bool = True


class LmsProgramUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    certificate_required: bool | None = None


class LmsProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    program_id: UUID | None
    name: str
    description: str | None
    certificate_required: bool
    items: list[LmsProgramItemOut] = []


class LmsProgramCohortEffectiveOut(BaseModel):
    """What a cohort's checklist actually resolves to right now — its own
    override once one has real items, else its program's own checklist
    shown as the editable starting point (`is_inherited=True`; operator
    ask, 2026-08-22: don't make ops start from scratch). No `id` when
    inherited — there's no override row yet, the first edit creates one
    (`fork_cohort_override`)."""
    cohort_id: UUID
    lms_program_id: UUID
    is_inherited: bool
    items: list[LmsProgramItemOut] = []


# ── learning paths (self-paced ordered course sequences, 2026-08-08) ───────

class LearningPathCreate(BaseModel):
    title: str
    description: str | None = None
    # Bundle pricing (2026-08-21) — mirrors Course; null = not purchasable as
    # a bundle, existing free `/start` self-enrol is unaffected either way.
    price_cents: int | None = Field(default=None, ge=1)
    currency: str = "usd"


class LearningPathUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    is_published: bool | None = None
    price_cents: int | None = Field(default=None, ge=1)
    currency: str | None = None


class LearningPathAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str
    description: str | None
    is_published: bool
    created_by: UUID
    created_at: datetime | None
    image_url: str | None = None
    price_cents: int | None = None
    currency: str = "usd"


class LearningPathStepIn(BaseModel):
    course_id: UUID
    position: int | None = None


class LearningPathStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    learning_path_id: UUID
    course_id: UUID
    position: int


# ── enrollment admin (P1-5) ──────────────────────────────────────────────────

class EnrollmentAdminOut(BaseModel):
    id: UUID
    user_id: UUID
    student_name: str
    student_email: str
    course_id: UUID
    # Only populated where the host page doesn't already know the course
    # (the per-student view, 2026-08-12) — the per-course roster leaves this
    # None rather than pay for a lookup the caller doesn't need.
    course_title: str | None = None
    source: str
    status: str
    granted_by: UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime | None = None


class EnrollmentGrantIn(BaseModel):
    user_id: UUID


class BulkGrantIn(BaseModel):
    """Exactly one of cohort_id (every student with an active registration in
    that cohort) or role (every user holding that role — D2, staff can take
    LMS courses too) — a one-shot iteration, never a live membership rule
    (§3: "do not build a groups/audiences table")."""
    cohort_id: UUID | None = None
    role: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "BulkGrantIn":
        if (self.cohort_id is None) == (self.role is None):
            raise ValueError("give exactly one of cohort_id or role")
        return self


class BulkGrantOut(BaseModel):
    granted: int
    already_enrolled: int
    # Only meaningful for cohort mode — a registered contact with no linked
    # LMS account. Bulk-grant doesn't create accounts; that's
    # ops_integration.sync_registration_lms's job, a separate concern.
    skipped_no_account: int = 0
