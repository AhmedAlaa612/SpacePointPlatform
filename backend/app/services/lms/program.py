"""LMS Program resolution, assignment, and progress (2026-08-21) — the
checklist-driven redesign. `resolve_cohort_program` is the one place that
reads both `lms_program_cohort_overrides` and `lms_programs` and applies
the override, same role `resolve_cohort_curriculum` used to play; nothing
else should query `lms_program_items` directly to figure out what a
specific cohort's students see.

Items are first materialized at assignment time (`assign_lms_program`),
but a later edit to a program's or cohort's checklist is not silently
invisible to students already assigned to it — every item-adding endpoint
calls `sync_assignment_items`/`sync_program_assignments`/
`sync_cohort_assignments` (2026-08-27) afterward, which backfills a
missing progress row (with the same course-enroll/mission-assign side
effects `assign_lms_program` runs) for anything the cohort's checklist
currently resolves to that an assignment doesn't have yet. This was a
deliberate v1 gap ("no production data yet to migrate") until a live
competition hit it — ops added a checklist step mid-run and already-
assigned students never saw it. Forking a cohort override
(`fork_cohort_override`) repoints existing progress onto the fork's new
item-id copies for the same reason, rather than orphaning it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.certificate import Certificate
from app.models.lms.cohort_quiz import CohortQuizAttempt, CohortQuizTemplate
from app.models.lms.course import Course
from app.models.lms.program import (
    LmsProgram, LmsProgramAssignment, LmsProgramCohortOverride, LmsProgramItem, LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.missions.design import Design
from app.models.missions.mission import Mission, MissionAttempt, MissionVariant
from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.team import Team, TeamMember
from app.models.user import User
from app.models.videos import Video
from app.schemas.lms_admin import LmsProgramItemIn, LmsProgramItemOut
from app.services import storage
from app.services.lms import cohort_quiz as cohort_quiz_service
from app.services.lms.enrollment import enroll
from app.services.lms.progress import course_completion
from app.services.missions import assign_mission_run
from app.services.missions.design import service as design_service
from app.services.video_service import get_video_for_owner

# Same bucket routers/lms/admin.py's module-attachment upload already uses —
# a `pdf` program item is just another hosted-PDF-behind-a-checklist-item,
# no reason for a second bucket.
PROGRAM_ITEM_PDF_BUCKET = "lms-attachments"

AUTO_TRACKED_TYPES = {"course", "mission_run", "quiz"}

# Roadmap board (2026-09) — the vocabulary a `mission_run` item's
# `mission_step_key` can name. Eight of these mirror
# `services/lms/admin_progress.py::DESIGN_STEP_LABELS` exactly (the real
# Madar design phases); `setup` and `report` aren't in that vocabulary —
# they're wizard tabs with no gate/selection row of their own, so their
# completion is inferred (see `_mission_run_item_done`) rather than read
# off `dashboard.steps`.
MISSION_STEP_KEYS: frozenset[str] = frozenset({
    "setup", "components", "conops", "power_budget",
    "mass_budget", "data_budget", "link_budget", "cost_budget", "report",
})

GUIDELINE_KINDS: frozenset[str] = frozenset({"pdf", "link", "video"})


def _apply_guideline_video(out: LmsProgramItemOut, video: Video | None) -> None:
    """A `video`-kind guideline's real source of truth, once uploaded/set
    through the standardized service: a YouTube/Vimeo embed resolves
    straight into `guideline_url` (no different from a plain pasted link —
    nothing signed/private about a public embed URL); an uploaded file
    instead flags `guideline_video_uploaded` and leaves `guideline_url`
    unset, same no-baked-in-signed-url posture `has_pdf` follows."""
    if video is None:
        return
    if video.provider in ("youtube", "vimeo"):
        out.guideline_url = video.embed_url
    elif video.provider == "upload":
        out.guideline_video_uploaded = True


async def item_out(db: AsyncSession, item: LmsProgramItem) -> LmsProgramItemOut:
    """Serializes one item, filling `mission_kind` off a fresh `Mission`
    lookup for a `mission_run` item — see the schema's own docstring for
    why the Missions tab needs this (design-only Steps/Gates)."""
    out = LmsProgramItemOut.model_validate(item)
    out.has_pdf = item.pdf_path is not None
    if item.mission_id is not None:
        mission = await db.get(Mission, item.mission_id)
        out.mission_kind = mission.kind if mission is not None else None
    if item.cohort_quiz_template_id is not None:
        # Active questions only — matches what `cohort_quiz.start_attempt`
        # will actually draw, so this badge never overstates a quiz that's
        # had questions retired out from under it. Reuses the same counter
        # `cohort_quiz_admin.py`'s template views call, rather than a second
        # copy of the join+filter that could drift out of sync with it.
        out.cohort_quiz_question_count = await cohort_quiz_service.question_count_for_template(
            db, item.cohort_quiz_template_id,
        )
    if item.guideline_kind == "video":
        _apply_guideline_video(out, await get_video_for_owner(
            db, owner_type="program_item_guideline", owner_id=item.id,
        ))
    return out


async def items_out(db: AsyncSession, items: list[LmsProgramItem]) -> list[LmsProgramItemOut]:
    """Batch form of `item_out` — one query for every distinct mission_id
    in the list instead of N+1."""
    mission_ids = {i.mission_id for i in items if i.mission_id is not None}
    kinds: dict[uuid.UUID, str] = {}
    if mission_ids:
        rows = (await db.execute(select(Mission.id, Mission.kind).where(Mission.id.in_(mission_ids)))).all()
        kinds = dict(rows)
    quiz_template_ids = {i.cohort_quiz_template_id for i in items if i.cohort_quiz_template_id is not None}
    quiz_counts = await cohort_quiz_service.question_counts_for_templates(db, list(quiz_template_ids))
    video_item_ids = [i.id for i in items if i.guideline_kind == "video"]
    videos_by_owner: dict[uuid.UUID, Video] = {}
    if video_item_ids:
        video_rows = (await db.execute(
            select(Video).where(Video.owner_type == "program_item_guideline", Video.owner_id.in_(video_item_ids))
        )).scalars().all()
        videos_by_owner = {v.owner_id: v for v in video_rows}
    out = []
    for item in items:
        o = LmsProgramItemOut.model_validate(item)
        o.has_pdf = item.pdf_path is not None
        if item.mission_id is not None:
            o.mission_kind = kinds.get(item.mission_id)
        if item.cohort_quiz_template_id is not None:
            o.cohort_quiz_question_count = quiz_counts.get(item.cohort_quiz_template_id, 0)
        _apply_guideline_video(o, videos_by_owner.get(item.id))
        out.append(o)
    return out


# ── Checklist item CRUD helpers — shared by `routers/lms/admin.py` (full
# authoring, program or cohort-override scope) and `routers/lms/instructor.py`
# (cohort-override scope only, item_type further restricted to mission_run
# by the caller — see that router's own item-type check). ──────────────────

def validate_item_payload(body: LmsProgramItemIn) -> None:
    required = {
        "course": body.course_id is not None,
        "mission_run": body.mission_id is not None,
        "external_link": bool(body.external_url),
        "submission": bool(body.external_url) or bool(body.submission_prompt),
        # No required field at creation — the file itself is attached
        # afterward via a separate multipart upload (routers/lms/admin.py),
        # same two-step shape a module `attachment` item already follows.
        "pdf": True,
        "manual": True,
        # Every field is optional — an admin can leave date/location/link
        # blank and just have a titled placeholder, same posture as manual.
        "session": True,
        "quiz": body.cohort_quiz_template_id is not None,
    }
    if not required[body.item_type]:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"A '{body.item_type}' item is missing its required field",
        )
    # Competition domain (2026-08-24) — team scope is for the link-only
    # deliverables a team submits once together. Learning content
    # (course/mission_run/pdf) stays individual on purpose: each
    # teammate's own course progress and Design mission attempt are
    # genuinely personal, not something one submission speaks for.
    # `session` also stays individual — it's an informational/self-check
    # step, not a deliverable, so there's nothing for a team to share.
    if body.scope == "team" and body.item_type not in ("submission", "external_link", "manual"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"A '{body.item_type}' item can't be team-scoped — only submission, external_link, or manual items can be",
        )
    if body.deadline_at is not None and body.item_type != "submission":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Only a submission item can have a deadline",
        )
    # Roadmap board (2026-09) ─────────────────────────────────────────
    if body.mission_step_key is not None:
        if body.item_type != "mission_run":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="Only a mission_run item can target a mission phase",
            )
        if body.mission_step_key not in MISSION_STEP_KEYS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown mission phase '{body.mission_step_key}'")
    if body.guideline_kind is not None:
        if body.guideline_kind not in GUIDELINE_KINDS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown guideline kind '{body.guideline_kind}'")
        # A 'video' guideline may be left with no URL on purpose — the Week 1
        # platform-tutorial slot, recorded and filled in later (see
        # docs/HANDOFF_LMS.md §11). 'pdf' never needs a URL — it reuses this
        # item's own pdf_path/upload. Only 'link' has nothing else to fall
        # back on.
        if body.guideline_kind == "link" and not body.guideline_url:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A link guideline needs a URL")


def guard_locked_submission_scope(item: LmsProgramItem, body: LmsProgramItemIn) -> None:
    """A submission item's `scope` (individual vs. team) is locked at
    creation — flipping it later silently orphans whatever's already been
    submitted, since individual and team progress live in two entirely
    separate tables keyed differently (`LmsProgramItemProgress` by
    assignment, `LmsProgramTeamItemProgress` by team) with no migration
    between them (2026-08-29 incident: a submission made before the flip
    just stops being read anywhere, including the judge's team-detail
    view — see `checklist_item_write_target`'s own docstring). Delete and
    re-add the item instead of changing this once it might have anything
    submitted against it."""
    if item.item_type == "submission" and body.scope != item.scope:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A submission item's scope (individual vs. team) can't be changed after it's created — "
                   "delete and re-add it instead, so nothing already submitted gets silently orphaned.",
        )


async def validate_item_refs(db: AsyncSession, body: LmsProgramItemIn, *, require_active_quiz: bool = True) -> None:
    """`require_active_quiz` gates the retired-template check — True for
    creating a new item (never let ops pick an already-retired template),
    False for editing an existing one (an item that already points at a
    template retired *after* assignment must stay editable for its other
    fields — retiring a template stops new checklist items from picking
    it, it doesn't freeze whatever already has it)."""
    if body.course_id is not None and await db.get(Course, body.course_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")
    if body.cohort_quiz_template_id is not None:
        template = await db.get(CohortQuizTemplate, body.cohort_quiz_template_id)
        if template is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz template not found")
        if require_active_quiz and not template.is_active:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This quiz template has been retired")
    if body.mission_id is not None:
        mission = await db.get(Mission, body.mission_id)
        if mission is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Mission not found")
        if body.mission_step_key is not None and mission.kind != "design":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, detail="A mission phase can only be targeted on a design mission",
            )


async def check_item_conflicts(
    db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, body: LmsProgramItemIn,
    exclude_item_id: uuid.UUID | None = None,
) -> None:
    """Clean 409s for the two DB-level unique constraints
    (`uq_lms_program_items_owner_position`/`_owner_course`) rather than
    letting them surface as a raw IntegrityError."""
    if body.position is not None:
        q = select(LmsProgramItem.id).where(
            LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id,
            LmsProgramItem.position == body.position,
        )
        if exclude_item_id is not None:
            q = q.where(LmsProgramItem.id != exclude_item_id)
        if await db.scalar(q):
            raise HTTPException(status.HTTP_409_CONFLICT, detail=f"Position {body.position} is already taken")
    if body.course_id is not None:
        q = select(LmsProgramItem.id).where(
            LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id,
            LmsProgramItem.course_id == body.course_id,
        )
        if exclude_item_id is not None:
            q = q.where(LmsProgramItem.id != exclude_item_id)
        if await db.scalar(q):
            raise HTTPException(status.HTTP_409_CONFLICT, detail="This course is already on the checklist")


async def next_position(db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID) -> int:
    max_pos = await db.scalar(
        select(func.max(LmsProgramItem.position)).where(
            LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id,
        )
    )
    return (max_pos or 0) + 1


async def reorder_program_items(
    db: AsyncSession, *, owner_type: str, owner_id: uuid.UUID, item_ids: list[uuid.UUID],
) -> list[LmsProgramItem] | None:
    """Drag-and-drop reorder — same `ModuleReorderIn`/`reorder_modules`
    idiom: caller must send every item id for this owner exactly once, and
    positions are rewritten in one transaction via a negative-offset pass
    first, since `uq_lms_program_items_owner_position` isn't deferrable and
    a direct swap can collide mid-transaction. Returns None if `item_ids`
    doesn't match this owner's actual item set exactly."""
    items = (await db.execute(
        select(LmsProgramItem).where(LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id)
    )).scalars().all()
    by_id = {i.id: i for i in items}
    if set(item_ids) != set(by_id) or len(item_ids) != len(by_id):
        return None
    for offset, item_id in enumerate(item_ids, start=1):
        by_id[item_id].position = -offset
    await db.flush()
    for position, item_id in enumerate(item_ids, start=1):
        by_id[item_id].position = position
    await db.commit()
    return (await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == owner_type, LmsProgramItem.owner_id == owner_id)
        .order_by(LmsProgramItem.position)
    )).scalars().all()


async def resolve_cohort_program(
    db: AsyncSession, cohort_id: uuid.UUID,
) -> tuple[LmsProgram, list[LmsProgramItem]] | None:
    """The winning `(LmsProgram, items)` pair for this cohort — a cohort
    override with any item rows wins outright over its program's own
    checklist, never merged (the `CohortCurriculum` idiom). Returns None
    when the cohort has no checklist at all (no override, and its program
    has none either) — not every cohort needs one."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None

    override = await db.scalar(
        select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == cohort_id)
    )
    if override is not None:
        items = (await db.execute(
            select(LmsProgramItem)
            .where(LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id)
            .order_by(LmsProgramItem.position)
        )).scalars().all()
        if items:
            program = await db.get(LmsProgram, override.lms_program_id)
            return (program, list(items)) if program else None

    program = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == cohort.program_id))
    if program is None:
        return None
    items = (await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == program.id)
        .order_by(LmsProgramItem.position)
    )).scalars().all()
    return program, list(items)


async def effective_cohort_program_items(
    db: AsyncSession, cohort_id: uuid.UUID,
) -> tuple[LmsProgram, list[LmsProgramItem], bool] | None:
    """`resolve_cohort_program`, plus whether what's being shown is the
    program's own template rather than a real per-cohort override yet
    (`is_inherited`) — the authoring UI's "don't start me from scratch"
    ask (operator, 2026-08-22): a cohort with no override, or an override
    with zero items, should still show and let you edit the program's
    current checklist, exactly as `resolve_cohort_program` already
    resolves it for a real student. The actual fork only happens on a
    write — see `fork_cohort_override` below."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None
    override = await db.scalar(
        select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == cohort_id)
    )
    if override is not None:
        items = (await db.execute(
            select(LmsProgramItem)
            .where(LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id)
            .order_by(LmsProgramItem.position)
        )).scalars().all()
        if items:
            program = await db.get(LmsProgram, override.lms_program_id)
            return (program, list(items), False) if program else None

    program = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == cohort.program_id))
    if program is None:
        return None
    items = (await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == program.id)
        .order_by(LmsProgramItem.position)
    )).scalars().all()
    return program, list(items), True


async def team_submission_items(db: AsyncSession, *, team_id: uuid.UUID) -> list[dict]:
    """Every team-scoped item on the team's cohort checklist, plus that
    team's own progress row for it — the judge team-detail view's "what did
    they actually submit" panel, read straight off the same shared checklist
    a teammate's Learn page edits (`checklist_item_write_target`), not a
    judging-only copy of it. Carries `updated_at`/`updated_by_name` too
    (operator ask, 2026-08-24: a judge needs to see "submitted at [time] by
    [student]", not just the bare link), same fields
    `get_student_checklist` already surfaces for the team's own view."""
    team = await db.get(Team, team_id)
    if team is None or team.cohort_id is None:
        return []
    resolved = await effective_cohort_program_items(db, team.cohort_id)
    if resolved is None:
        return []
    _, items, _ = resolved
    team_items = [i for i in items if i.scope == "team"]
    if not team_items:
        return []
    progress_by_item = {
        p.item_id: p for p in (await db.execute(
            select(LmsProgramTeamItemProgress).where(
                LmsProgramTeamItemProgress.item_id.in_([i.id for i in team_items]),
                LmsProgramTeamItemProgress.team_id == team_id,
            )
        )).scalars().all()
    }
    updater_ids = {p.updated_by_user_id for p in progress_by_item.values() if p.updated_by_user_id}
    updater_names: dict[uuid.UUID, str] = {}
    if updater_ids:
        updater_names = dict((await db.execute(
            select(User.id, User.full_name).where(User.id.in_(updater_ids))
        )).all())

    out = []
    for item in team_items:
        progress = progress_by_item.get(item.id)
        out.append({
            "item_id": item.id, "title": item.title, "item_type": item.item_type,
            "status": progress.status if progress else "pending",
            "submitted_url": progress.submitted_url if progress else None,
            "updated_at": progress.updated_at if progress else None,
            "updated_by_name": updater_names.get(progress.updated_by_user_id) if progress and progress.updated_by_user_id else None,
        })
    return out


async def fork_cohort_override(
    db: AsyncSession, *, cohort_id: uuid.UUID,
) -> tuple[LmsProgramCohortOverride, dict[uuid.UUID, uuid.UUID]] | None:
    """Get-or-create the cohort's override row, copying every one of the
    program's current items into it the first time (i.e. whenever the
    override doesn't exist yet, or exists with zero items) so editing an
    "inherited" item never means starting from an empty checklist. Returns
    `None` when the cohort's program has no checklist to fork from at all
    (the existing 400 case `add_cohort_override_item` already raised).

    The returned dict maps each ORIGINAL program item's id to its new
    cohort_override copy's id — empty when no fork happened this call
    (the override already had its own items). A caller translating an
    incoming `item_id` that came from a not-yet-forked "inherited" list
    only needs this mapping on the one call that actually triggers the
    fork; every subsequent edit is against the override's own real item
    ids once the frontend refetches."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        return None
    override = await db.scalar(
        select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == cohort_id)
    )
    if override is not None:
        existing_count = await db.scalar(
            select(LmsProgramItem.id)
            .where(LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == override.id)
            .limit(1)
        )
        if existing_count is not None:
            return override, {}
        program = await db.get(LmsProgram, override.lms_program_id)
    else:
        program = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == cohort.program_id))
        if program is None:
            return None
        override = LmsProgramCohortOverride(id=uuid.uuid4(), cohort_id=cohort_id, lms_program_id=program.id)
        db.add(override)
        await db.flush()

    program_items = (await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == program.id)
        .order_by(LmsProgramItem.position)
    )).scalars().all()

    id_map: dict[uuid.UUID, uuid.UUID] = {}
    for item in program_items:
        copy_id = uuid.uuid4()
        # A real duplicate, not a shared reference — the program's own item
        # and the cohort's fork must be independently deletable/replaceable
        # afterward, so each gets its own storage object at its own id
        # rather than both pointing at the program item's path.
        copy_pdf_path = None
        if item.pdf_path:
            data = await storage.download_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
            filename = item.pdf_path.rsplit("/", 1)[-1]
            copy_pdf_path = await storage.upload_to_path(
                PROGRAM_ITEM_PDF_BUCKET, f"program-items/{copy_id}/{filename}", data, "application/pdf",
            )
        copy = LmsProgramItem(
            id=copy_id, owner_type="cohort_override", owner_id=override.id, position=item.position,
            item_type=item.item_type, title=item.title, description=item.description,
            optional=item.optional, requires_confirmation=item.requires_confirmation, scope=item.scope,
            course_id=item.course_id, mission_id=item.mission_id, variant_id=item.variant_id,
            external_url=item.external_url, submission_prompt=item.submission_prompt,
            pdf_path=copy_pdf_path, deadline_at=item.deadline_at,
            session_date=item.session_date, session_starts_at=item.session_starts_at,
            session_location=item.session_location, session_meeting_url=item.session_meeting_url,
            cohort_quiz_template_id=item.cohort_quiz_template_id,
        )
        db.add(copy)
        id_map[item.id] = copy.id
    await db.flush()
    # Every already-assigned student's progress row still points at the
    # original program item ids — repoint them to this cohort's new
    # copies in place (same row, same status/submitted_url) so the fork
    # is invisible to them, rather than leaving their existing progress
    # orphaned under an id nothing resolves to any more.
    await _repoint_cohort_progress(db, cohort_id=cohort_id, id_map=id_map)
    return override, id_map


async def _repoint_cohort_progress(
    db: AsyncSession, *, cohort_id: uuid.UUID, id_map: dict[uuid.UUID, uuid.UUID],
) -> None:
    if not id_map:
        return
    old_ids = list(id_map.keys())
    assignment_ids = (await db.execute(
        select(LmsProgramAssignment.id).where(LmsProgramAssignment.cohort_id == cohort_id)
    )).scalars().all()
    if assignment_ids:
        rows = (await db.execute(
            select(LmsProgramItemProgress).where(
                LmsProgramItemProgress.assignment_id.in_(assignment_ids),
                LmsProgramItemProgress.item_id.in_(old_ids),
            )
        )).scalars().all()
        for row in rows:
            row.item_id = id_map[row.item_id]
    team_rows = (await db.execute(
        select(LmsProgramTeamItemProgress)
        .join(Team, Team.id == LmsProgramTeamItemProgress.team_id)
        .where(LmsProgramTeamItemProgress.item_id.in_(old_ids), Team.cohort_id == cohort_id)
    )).scalars().all()
    for row in team_rows:
        row.item_id = id_map[row.item_id]
    await db.flush()


async def resolve_cohort_program_course_ids(db: AsyncSession, cohort_id: uuid.UUID) -> list[uuid.UUID]:
    """Drop-in replacement for the old `resolve_cohort_curriculum` — just
    the `course`-type items' course ids, in position order. Callers that
    only ever cared about "what courses does this cohort teach"
    (progress grids, the public catalog, session progress) keep working
    unchanged; they don't need to become checklist-aware."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return []
    _, items = resolved
    return [item.course_id for item in items if item.item_type == "course" and item.course_id]


async def resolve_course_titles_by_cohort(
    db: AsyncSession, cohort_ids: list[uuid.UUID],
) -> dict[uuid.UUID, list[str]]:
    """Batched drop-in for the public catalog's old `ProgramCurriculum`
    join (`routers/sessions/public.py`) — course titles per cohort, in
    position order, override-aware. One resolver call per cohort (the
    catalog's cohort count is small and this is a cheap read-only
    endpoint already, unlike a hot path), then a single batched title
    lookup for the union of course ids."""
    course_ids_by_cohort = {cohort_id: await resolve_cohort_program_course_ids(db, cohort_id) for cohort_id in cohort_ids}
    all_course_ids = {cid for ids in course_ids_by_cohort.values() for cid in ids}
    if not all_course_ids:
        return {cohort_id: [] for cohort_id in cohort_ids}
    titles = dict((await db.execute(
        select(Course.id, Course.title).where(Course.id.in_(all_course_ids))
    )).all())
    return {
        cohort_id: [titles[cid] for cid in ids if cid in titles]
        for cohort_id, ids in course_ids_by_cohort.items()
    }


async def assign_lms_program(
    db: AsyncSession, *, user_id: uuid.UUID, cohort_id: uuid.UUID, registration_id: uuid.UUID | None = None,
) -> LmsProgramAssignment | None:
    """The per-registration path — called once, at registration time, by
    `sync_registration_lms`, exactly where `enroll_in_cohort_curriculum`
    used to be called. Idempotent on `(user_id, cohort_id)`. Enrolls every
    `course` item immediately and assigns every `mission_run` item's
    attempt immediately (same "enroll everything up front" behavior the
    old curriculum table had) — sequential position only governs the
    checklist's own display/certificate gate, never actual access."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return None
    program, items = resolved
    if not items:
        return None

    existing = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user_id, LmsProgramAssignment.cohort_id == cohort_id,
        )
    )
    if existing is not None:
        return existing

    cohort = await db.get(Cohort, cohort_id)
    assignment = LmsProgramAssignment(
        id=uuid.uuid4(), user_id=user_id, lms_program_id=program.id,
        cohort_id=cohort_id, registration_id=registration_id,
    )
    db.add(assignment)
    await db.flush()

    for item in items:
        progress = LmsProgramItemProgress(id=uuid.uuid4(), assignment_id=assignment.id, item_id=item.id)
        if item.item_type == "course" and item.course_id:
            await enroll(
                db, user_id=user_id, course_id=item.course_id, source="registration",
                program_id=cohort.program_id if cohort else None, registration_id=registration_id,
            )
        elif item.item_type == "mission_run" and item.mission_id:
            attempt = await assign_mission_run(
                db, mission_id=item.mission_id, user_id=user_id, cohort_id=cohort_id, variant_id=item.variant_id,
            )
            progress.mission_attempt_id = attempt.id
        db.add(progress)

    await db.flush()
    return assignment


async def sync_assignment_items(db: AsyncSession, *, assignment: LmsProgramAssignment) -> int:
    """Backfill — creates a progress row for any item the assignment's
    cohort currently resolves to (via `resolve_cohort_program`, so it
    automatically respects whichever override wins) that this assignment
    was never materialized against. The module docstring's "deliberate
    v1 gap" (adding a checklist item after students are already assigned
    never reached them) stops being a gap once callers that add items
    run this afterward — a no-op once every current item already has a
    row, so it's safe to call any time, not just right after an add."""
    if assignment.cohort_id is None:
        return 0
    resolved = await resolve_cohort_program(db, assignment.cohort_id)
    if resolved is None:
        return 0
    _program, items = resolved
    existing_item_ids = set((await db.execute(
        select(LmsProgramItemProgress.item_id).where(LmsProgramItemProgress.assignment_id == assignment.id)
    )).scalars().all())
    missing = [item for item in items if item.id not in existing_item_ids]
    if not missing:
        return 0
    cohort = await db.get(Cohort, assignment.cohort_id)
    for item in missing:
        progress = LmsProgramItemProgress(id=uuid.uuid4(), assignment_id=assignment.id, item_id=item.id)
        if item.item_type == "course" and item.course_id:
            await enroll(
                db, user_id=assignment.user_id, course_id=item.course_id, source="registration",
                program_id=cohort.program_id if cohort else None, registration_id=assignment.registration_id,
            )
        elif item.item_type == "mission_run" and item.mission_id:
            attempt = await assign_mission_run(
                db, mission_id=item.mission_id, user_id=assignment.user_id,
                cohort_id=assignment.cohort_id, variant_id=item.variant_id,
            )
            progress.mission_attempt_id = attempt.id
        db.add(progress)
    await db.flush()
    return len(missing)


async def sync_program_assignments(db: AsyncSession, *, lms_program_id: uuid.UUID) -> int:
    """Backfill every existing assignment against this program — call
    after adding an item on the program's own checklist. Safe to call
    broadly: a cohort whose own override currently wins just no-ops."""
    assignments = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.lms_program_id == lms_program_id)
    )).scalars().all()
    total = 0
    for assignment in assignments:
        total += await sync_assignment_items(db, assignment=assignment)
    return total


async def sync_cohort_assignments(db: AsyncSession, *, cohort_id: uuid.UUID) -> int:
    """Backfill every existing assignment in this one cohort — call after
    adding an item on a cohort's own override.

    Also creates a missing assignment outright for anyone already on a
    team in this cohort but never assigned at all — the gap
    `advance_teams` leaves behind when it ran before this cohort had any
    checklist to assign (`assign_lms_program` silently no-ops with
    nothing to resolve, and nothing ever retries it once a checklist
    exists): a team advances fine, but the advanced student never gets a
    checklist until this runs."""
    team_ids = (await db.execute(select(Team.id).where(Team.cohort_id == cohort_id))).scalars().all()
    if team_ids:
        member_user_ids = set((await db.execute(
            select(TeamMember.user_id).where(TeamMember.team_id.in_(team_ids))
        )).scalars().all())
        already_assigned = set((await db.execute(
            select(LmsProgramAssignment.user_id).where(LmsProgramAssignment.cohort_id == cohort_id)
        )).scalars().all())
        for user_id in member_user_ids - already_assigned:
            user = await db.get(User, user_id)
            registration_id = None
            if user is not None and user.contact_id is not None:
                registration_id = await db.scalar(
                    select(Registration.id).where(
                        Registration.contact_id == user.contact_id, Registration.cohort_id == cohort_id,
                        Registration.status != "cancelled",
                    )
                )
            await assign_lms_program(db, user_id=user_id, cohort_id=cohort_id, registration_id=registration_id)

    assignments = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.cohort_id == cohort_id)
    )).scalars().all()
    total = 0
    for assignment in assignments:
        total += await sync_assignment_items(db, assignment=assignment)
    return total


async def _course_item_done(db: AsyncSession, *, user_id: uuid.UUID, course_id: uuid.UUID) -> bool:
    completion = await course_completion(db, user_id=user_id, course_id=course_id)
    modules = completion["modules"]
    return bool(modules) and all(m["completed"] for m in modules)


async def _design_dashboard_for_attempt(
    db: AsyncSession, *, mission_attempt_id: uuid.UUID, cache: dict[uuid.UUID, dict | None],
) -> dict | None:
    """Cached per attempt (not per checklist item) — several Madar phase
    tiles share one `mission_attempt_id` (see `start_attempt`'s
    single-flight resume), and the handoff spec is explicit: read the
    design state once per attempt per checklist load, not once per item.
    `None` means there's no design (or no attempt) to read from —
    callers treat that as "not done" rather than erroring, same posture
    the old whole-mission check took for a dangling attempt id."""
    if mission_attempt_id in cache:
        return cache[mission_attempt_id]
    attempt = await db.get(MissionAttempt, mission_attempt_id)
    design = (
        await db.scalar(select(Design).where(Design.attempt_id == mission_attempt_id))
        if attempt is not None else None
    )
    if attempt is None or design is None:
        cache[mission_attempt_id] = None
        return None
    variant = await db.get(MissionVariant, attempt.variant_id) if attempt.variant_id else None
    dash = await design_service.compute_dashboard(
        db, design=design, variant_config=(variant.config or {}) if variant else {}, attempt=attempt,
    )
    # 'setup' isn't a DESIGN_STEP_LABELS key (no gate/selection row of its
    # own — it's the wizard's free-text/guided-prompt tab), so its
    # completion isn't in `dash["steps"]`. Piggyback it on the same cached
    # lookup rather than a second query: SetupTab only ever writes
    # `design_objective` once the guided prompts are actually saved
    # (DesignMissionPage.tsx's SetupTab), so "has one" is a real signal,
    # unlike `design_name` which always starts pre-filled ("My CubeSat").
    dash["_setup_done"] = design.design_objective is not None
    # Self-check (2026-09) — the step keys the student has explicitly
    # confirmed via POST .../steps/{step_key}/confirm (routers/missions/
    # design.py), piggybacked here for the same reason `_setup_done` is:
    # one query per attempt, not one per checklist item.
    dash["_confirmed_steps"] = set(design.confirmed_steps or [])
    cache[mission_attempt_id] = dash
    return dash


async def _mission_run_item_done(
    db: AsyncSession, *, mission_attempt_id: uuid.UUID | None, mission_step_key: str | None,
    dashboard_cache: dict[uuid.UUID, dict | None],
) -> bool:
    if mission_attempt_id is None:
        return False
    if mission_step_key is None:
        # Whole-mission item — unchanged behaviour: done means passed.
        attempt = await db.get(MissionAttempt, mission_attempt_id)
        return attempt is not None and attempt.status == "passed"

    dash = await _design_dashboard_for_attempt(db, mission_attempt_id=mission_attempt_id, cache=dashboard_cache)
    if dash is None:
        return False
    if mission_step_key == "report":
        # Stays purely validity-driven — no self-check of its own, matching
        # DesignMissionPage.tsx's exclusion of the Report tab from the
        # Complete-button flow (it's a summary of the other steps, not a
        # step a student "finishes" on its own terms).
        return dash["all_valid"]
    # Every other step — 'setup' included — now needs BOTH its own
    # requirements met AND the student's explicit self-check confirmation.
    # `is_valid` alone used to be enough, so a tile flipped to done the
    # instant the bare-minimum requirement was met (e.g. one component
    # added) — see confirm_design_step's docstring for the full story.
    if mission_step_key == "setup":
        ready = dash["_setup_done"]
    else:
        step = dash["steps"].get(mission_step_key)
        ready = bool(step and step["has_data"] and step["is_valid"])
    return ready and mission_step_key in dash["_confirmed_steps"]


async def _cohort_quiz_item_done(db: AsyncSession, *, program_item_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """A quiz item is "done" once submitted — this is framed as a
    diagnostic, not a pass/fail gate, so score never factors in here (see
    `app/models/lms/cohort_quiz.py`'s own note on that)."""
    return bool(await db.scalar(
        select(CohortQuizAttempt.id).where(
            CohortQuizAttempt.program_item_id == program_item_id,
            CohortQuizAttempt.user_id == user_id,
            CohortQuizAttempt.status == "submitted",
        )
    ))


async def refresh_item_progress(
    db: AsyncSession, *, progress: LmsProgramItemProgress, item: LmsProgramItem, user_id: uuid.UUID,
    dashboard_cache: dict[uuid.UUID, dict | None] | None = None,
) -> str:
    """For `course`/`mission_run` items, recompute `status` from the real
    Enrollment/MissionAttempt state and persist it if it changed — never
    trust a stored 'done' alone, the same instinct
    `compute_dashboard`'s `all_valid` follows for Design missions. Manual/
    external/submission/article items are untouched here; their status is
    written directly by the self-check/confirm actions. Returns the
    resulting status.

    `dashboard_cache`, when passed, is shared across every item in one
    checklist read (`get_student_checklist`/`_assignment_summary`/etc.) so
    several Madar phase items pointing at the same attempt only compute
    the design dashboard once — pass a fresh dict per call, not None, from
    any caller that loops over more than one item."""
    if item.item_type not in AUTO_TRACKED_TYPES:
        return progress.status

    if item.item_type == "course":
        done = await _course_item_done(db, user_id=user_id, course_id=item.course_id) if item.course_id else False
    elif item.item_type == "mission_run":
        done = await _mission_run_item_done(
            db, mission_attempt_id=progress.mission_attempt_id, mission_step_key=item.mission_step_key,
            dashboard_cache=dashboard_cache if dashboard_cache is not None else {},
        )
    else:  # "quiz"
        done = await _cohort_quiz_item_done(db, program_item_id=item.id, user_id=user_id)

    if done and progress.status != "done":
        progress.status = "done"
        progress.completed_at = datetime.now(timezone.utc)
    elif not done and progress.status == "done":
        # A course/attempt can un-complete (e.g. a mission gets reset) —
        # reflect that rather than leaving a stale "done".
        progress.status = "pending"
        progress.completed_at = None
    return progress.status


def compute_lock_states(
    items: list[LmsProgramItem], statuses: dict[uuid.UUID, str],
) -> dict[uuid.UUID, bool]:
    """Roadmap board gating. An item is locked iff `item.gated` **and**
    some *earlier* (by position) non-optional item on the same checklist
    isn't `done` yet — `awaiting_confirmation` doesn't count as done, so a
    submission pending review does not unlock the next tile (the spec's
    "done when accepted, not when uploaded" rule). Optional items never
    block anything and are never themselves locked by this rule (they can
    still be individually `gated`, but nothing about being optional stops
    them being reachable). `statuses` is keyed by item id — callers pass
    whatever's already been resolved (post `refresh_item_progress`), so
    this function does no I/O of its own."""
    ordered = sorted(items, key=lambda i: i.position)
    locked: dict[uuid.UUID, bool] = {}
    blocked_by_earlier = False
    for item in ordered:
        locked[item.id] = bool(item.gated) and blocked_by_earlier
        if not item.optional and statuses.get(item.id) != "done":
            blocked_by_earlier = True
    return locked


async def certificate_gate_satisfied(db: AsyncSession, *, cohort_id: uuid.UUID, user_id: uuid.UUID | None) -> bool:
    """Whether this student's checklist (if any) is done enough to let the
    cohort's `student_completion` certificate issue. True when: the
    cohort has no checklist at all, its checklist doesn't require one
    (`certificate_required=False`), or every non-optional item is done.
    False when a checklist requires it and the student has no LMS
    account/assignment at all — an unassigned student's checklist is, by
    definition, not done. Only `complete_cohort`'s automatic path should
    call this; `issue_certificate_override` is the deliberate ops
    bypass and must not."""
    resolved = await resolve_cohort_program(db, cohort_id)
    if resolved is None:
        return True
    program, items = resolved
    if not program.certificate_required:
        return True
    required_items = [item for item in items if not item.optional]
    if not required_items:
        return True
    if user_id is None:
        return False

    assignment = await db.scalar(
        select(LmsProgramAssignment).where(
            LmsProgramAssignment.user_id == user_id, LmsProgramAssignment.cohort_id == cohort_id,
        )
    )
    if assignment is None:
        return False

    progress_rows = {
        p.item_id: p for p in (await db.execute(
            select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment.id)
        )).scalars().all()
    }
    dashboard_cache: dict[uuid.UUID, dict | None] = {}
    for item in required_items:
        progress = progress_rows.get(item.id)
        if progress is None:
            return False
        status = await refresh_item_progress(db, progress=progress, item=item, user_id=user_id, dashboard_cache=dashboard_cache)
        if status != "done":
            return False
    return True


async def _certificate_earned(db: AsyncSession, registration_id: uuid.UUID | None) -> bool:
    if registration_id is None:
        return False
    return await db.scalar(select(Certificate.id).where(Certificate.registration_id == registration_id)) is not None


async def _assignment_items_and_progress(
    db: AsyncSession, assignment_id: uuid.UUID,
) -> list[tuple[LmsProgramItem, LmsProgramItemProgress]]:
    """The assignment's own materialized item set, resolved via its
    progress rows rather than re-resolving `resolve_cohort_program` on
    every read — `sync_assignment_items` (see module docstring) is what
    keeps those progress rows caught up with a later checklist edit,
    not this function re-deriving them live."""
    progress_rows = (await db.execute(
        select(LmsProgramItemProgress).where(LmsProgramItemProgress.assignment_id == assignment_id)
    )).scalars().all()
    if not progress_rows:
        return []
    item_ids = [p.item_id for p in progress_rows]
    items_by_id = {
        i.id: i for i in (await db.execute(select(LmsProgramItem).where(LmsProgramItem.id.in_(item_ids)))).scalars().all()
    }
    pairs = [(items_by_id[p.item_id], p) for p in progress_rows if p.item_id in items_by_id]
    pairs.sort(key=lambda pair: pair[0].position)
    return pairs


async def team_for_cohort_member(db: AsyncSession, *, cohort_id: uuid.UUID | None, user_id: uuid.UUID) -> Team | None:
    """The caller's `Team` within this cohort, or None if they're not on
    one — a solo/no-cohort assignment (`cohort_id` None) never has a team.
    One row expected in practice (a student holds at most one team per
    cohort); `.first()` rather than erroring keeps this a lookup, not an
    invariant check that has no business living here."""
    if cohort_id is None:
        return None
    return await db.scalar(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id, Team.cohort_id == cohort_id)
    )


def _effective_status(
    item: LmsProgramItem, progress: LmsProgramItemProgress,
    team_progress_by_item: dict[uuid.UUID, LmsProgramTeamItemProgress],
) -> str:
    """The status that's actually true for this item — the shared team row
    for a team-scoped item, the individual row otherwise. Doesn't refresh
    course/mission_run status against live Enrollment/MissionAttempt state
    (see `refresh_item_progress`); callers that need that still call it
    themselves, this is only for callers (the roster's pending-confirmations
    filter) that just need to know if the stored status is
    `awaiting_confirmation`, which auto-tracked items never set anyway."""
    team_progress = team_progress_by_item.get(item.id) if item.scope == "team" else None
    return team_progress.status if team_progress is not None else progress.status


async def _team_progress_by_item(
    db: AsyncSession, *, pairs: list[tuple[LmsProgramItem, LmsProgramItemProgress]],
    cohort_id: uuid.UUID | None, user_id: uuid.UUID,
) -> dict[uuid.UUID, LmsProgramTeamItemProgress]:
    """Every team-scoped item's shared progress row for this cohort
    member's team, keyed by item_id — the one lookup any reader of an
    assignment's items needs before trusting an item's status/submitted_url:
    a team-scoped item's real state never lives on the individual row."""
    team = await team_for_cohort_member(db, cohort_id=cohort_id, user_id=user_id)
    team_item_ids = [item.id for item, _ in pairs if item.scope == "team"]
    if team is None or not team_item_ids:
        return {}
    rows = (await db.execute(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.team_id == team.id,
            LmsProgramTeamItemProgress.item_id.in_(team_item_ids),
        )
    )).scalars().all()
    return {r.item_id: r for r in rows}


async def _get_or_create_team_progress(
    db: AsyncSession, *, item_id: uuid.UUID, team_id: uuid.UUID,
) -> LmsProgramTeamItemProgress:
    row = await db.scalar(
        select(LmsProgramTeamItemProgress).where(
            LmsProgramTeamItemProgress.item_id == item_id, LmsProgramTeamItemProgress.team_id == team_id,
        )
    )
    if row is None:
        row = LmsProgramTeamItemProgress(id=uuid.uuid4(), item_id=item_id, team_id=team_id)
        db.add(row)
        await db.flush()
    return row


async def checklist_item_write_target(
    db: AsyncSession, *, assignment: LmsProgramAssignment, item: LmsProgramItem,
    individual: LmsProgramItemProgress, user_id: uuid.UUID,
) -> LmsProgramItemProgress | LmsProgramTeamItemProgress:
    """Where a checklist item's mutable state (status/submitted_url/
    completed_at/confirmed_by_user_id) actually lives. `individual` items
    write straight to their own `LmsProgramItemProgress` row — `individual`
    passed in, unchanged, same as before this function existed. `team`
    items write to the shared `LmsProgramTeamItemProgress` row for the
    caller's Team in this assignment's cohort, created on first write, so
    every teammate's edit lands on the same row — `individual`'s own row
    still exists (materialized at assignment time, see module docstring)
    but its state is never read or written once an item is team-scoped."""
    if item.scope != "team":
        return individual
    team = await team_for_cohort_member(db, cohort_id=assignment.cohort_id, user_id=user_id)
    if team is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You're not on a team for this cohort")
    return await _get_or_create_team_progress(db, item_id=item.id, team_id=team.id)


async def checklist_item_locked(db: AsyncSession, *, assignment: LmsProgramAssignment, item: LmsProgramItem) -> bool:
    """Server-side twin of the board's own "not-powered → no-op" rule —
    what `complete_program_item`/`submit_program_item` 409 on, so a
    locked tile can't be completed by calling the API directly even
    though the client already hides/disables it. Recomputes this whole
    assignment's lock state (a handful of items, workshop-scale tool —
    same "just re-fetch" posture DesignMissionPage's own re-fetch-per-save
    takes) rather than trusting anything the client sent."""
    pairs = await _assignment_items_and_progress(db, assignment.id)
    team_progress_by_item = await _team_progress_by_item(
        db, pairs=pairs, cohort_id=assignment.cohort_id, user_id=assignment.user_id,
    )
    dashboard_cache: dict[uuid.UUID, dict | None] = {}
    statuses: dict[uuid.UUID, str] = {}
    for row_item, progress in pairs:
        team_progress = team_progress_by_item.get(row_item.id) if row_item.scope == "team" else None
        statuses[row_item.id] = (
            team_progress.status if team_progress is not None
            else await refresh_item_progress(
                db, progress=progress, item=row_item, user_id=assignment.user_id, dashboard_cache=dashboard_cache,
            )
        )
    locked = compute_lock_states([row_item for row_item, _ in pairs], statuses)
    return locked.get(item.id, False)


async def get_student_checklist(db: AsyncSession, *, assignment_id: uuid.UUID, user_id: uuid.UUID) -> dict | None:
    """None means either the assignment doesn't exist or belongs to a
    different student — the router turns both into a plain 404, never
    leaking which."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None or assignment.user_id != user_id:
        return None
    program = await db.get(LmsProgram, assignment.lms_program_id)
    if program is None:
        return None
    cohort = await db.get(Cohort, assignment.cohort_id) if assignment.cohort_id else None

    pairs = await _assignment_items_and_progress(db, assignment_id)
    mission_ids = {item.mission_id for item, _ in pairs if item.mission_id}
    mission_kinds = dict((await db.execute(
        select(Mission.id, Mission.kind).where(Mission.id.in_(mission_ids))
    )).all()) if mission_ids else {}
    video_item_ids = [item.id for item, _ in pairs if item.guideline_kind == "video"]
    guideline_videos: dict[uuid.UUID, Video] = {}
    if video_item_ids:
        video_rows = (await db.execute(
            select(Video).where(Video.owner_type == "program_item_guideline", Video.owner_id.in_(video_item_ids))
        )).scalars().all()
        guideline_videos = {v.owner_id: v for v in video_rows}

    # Team-scoped items read their state from the shared team row instead
    # of the individual one materialized above — one lookup for the
    # caller's team, one batched query for every team-scoped item's
    # progress row, one for the names of whoever last touched each.
    team = await team_for_cohort_member(db, cohort_id=assignment.cohort_id, user_id=user_id)
    team_item_ids = [item.id for item, _ in pairs if item.scope == "team"]
    team_progress_by_item: dict[uuid.UUID, LmsProgramTeamItemProgress] = {}
    updater_names: dict[uuid.UUID, str] = {}
    if team is not None and team_item_ids:
        rows = (await db.execute(
            select(LmsProgramTeamItemProgress).where(
                LmsProgramTeamItemProgress.team_id == team.id,
                LmsProgramTeamItemProgress.item_id.in_(team_item_ids),
            )
        )).scalars().all()
        team_progress_by_item = {r.item_id: r for r in rows}
        updater_ids = {r.updated_by_user_id for r in rows if r.updated_by_user_id}
        if updater_ids:
            updater_names = dict((await db.execute(
                select(User.id, User.full_name).where(User.id.in_(updater_ids))
            )).all())

    # Individual-row updates have one possible author — the student
    # themselves — so a single lookup covers every such item below,
    # unlike the per-item `updater_names` batch the team rows needed.
    student = await db.get(User, user_id)
    student_name = student.full_name if student else None

    # One design-dashboard read per attempt for this whole checklist load,
    # not per item — several Madar phase tiles can share one
    # mission_attempt_id (see refresh_item_progress's own docstring).
    dashboard_cache: dict[uuid.UUID, dict | None] = {}
    statuses: dict[uuid.UUID, str] = {}
    rows: list[dict] = []
    for item, progress in pairs:
        team_progress = team_progress_by_item.get(item.id) if item.scope == "team" else None
        status = (
            team_progress.status if team_progress is not None
            else (await refresh_item_progress(db, progress=progress, item=item, user_id=user_id, dashboard_cache=dashboard_cache))
        )
        statuses[item.id] = status
        submitted_url = team_progress.submitted_url if team_progress is not None else progress.submitted_url
        updated_at = team_progress.updated_at if team_progress is not None else progress.updated_at
        updated_by_name = (
            updater_names.get(team_progress.updated_by_user_id)
            if team_progress is not None and team_progress.updated_by_user_id
            else (student_name if team_progress is None and progress.updated_at else None)
        )
        guideline_video = guideline_videos.get(item.id)
        guideline_url = item.guideline_url
        guideline_video_uploaded = False
        if guideline_video is not None:
            if guideline_video.provider in ("youtube", "vimeo"):
                guideline_url = guideline_video.embed_url
            elif guideline_video.provider == "upload":
                guideline_video_uploaded = True
        rows.append({
            "id": item.id, "position": item.position, "item_type": item.item_type,
            "title": item.title, "description": item.description,
            "optional": item.optional, "requires_confirmation": item.requires_confirmation,
            "status": status, "course_id": item.course_id,
            "mission_attempt_id": progress.mission_attempt_id,
            "mission_id": item.mission_id, "mission_kind": mission_kinds.get(item.mission_id),
            "external_url": item.external_url, "submission_prompt": item.submission_prompt,
            "has_pdf": item.pdf_path is not None,
            "submitted_url": submitted_url,
            "deadline_at": item.deadline_at,
            "session_date": item.session_date, "session_starts_at": item.session_starts_at,
            "session_location": item.session_location, "session_meeting_url": item.session_meeting_url,
            "scope": item.scope,
            "updated_by_name": updated_by_name,
            "updated_at": updated_at,
            "mission_step_key": item.mission_step_key, "gated": item.gated,
            "guideline_kind": item.guideline_kind, "guideline_url": guideline_url,
            "guideline_video_uploaded": guideline_video_uploaded,
            "checkpoint_label": item.checkpoint_label,
        })

    locked_by_item = compute_lock_states([item for item, _ in pairs], statuses)
    items_out = [{**row, "locked": locked_by_item.get(row["id"], False)} for row in rows]

    return {
        "assignment_id": assignment.id, "lms_program_id": program.id, "name": program.name,
        "description": program.description,
        "image_url": await storage.resolve_url(program.image_bucket, program.image_path),
        "cohort_id": assignment.cohort_id,
        "cohort_name": cohort.name if cohort else None,
        # Only meaningful once any item is team-scoped — resolved from the
        # same `team` lookup above rather than a second query. A student
        # with no team yet (or a program with no team-scoped items at all)
        # gets None, same as cohort_name for a program with no cohort.
        "team_name": team.name if team is not None else None,
        "certificate_required": program.certificate_required,
        "certificate_earned": await _certificate_earned(db, assignment.registration_id),
        "items": items_out,
    }


async def _assignment_summary(db: AsyncSession, assignment: LmsProgramAssignment) -> dict | None:
    program = await db.get(LmsProgram, assignment.lms_program_id)
    if program is None:
        return None
    cohort = await db.get(Cohort, assignment.cohort_id) if assignment.cohort_id else None

    pairs = await _assignment_items_and_progress(db, assignment.id)
    team_progress_by_item = await _team_progress_by_item(
        db, pairs=pairs, cohort_id=assignment.cohort_id, user_id=assignment.user_id,
    )

    done = 0
    required_total = 0
    next_item_title: str | None = None
    dashboard_cache: dict[uuid.UUID, dict | None] = {}
    for item, progress in pairs:
        if item.optional:
            continue
        required_total += 1
        team_progress = team_progress_by_item.get(item.id) if item.scope == "team" else None
        status = (
            team_progress.status if team_progress is not None
            else await refresh_item_progress(db, progress=progress, item=item, user_id=assignment.user_id, dashboard_cache=dashboard_cache)
        )
        if status == "done":
            done += 1
        elif next_item_title is None:
            next_item_title = item.title

    return {
        "assignment_id": assignment.id, "lms_program_id": program.id, "name": program.name,
        "cohort_id": assignment.cohort_id, "cohort_name": cohort.name if cohort else None,
        "items_total": required_total, "items_done": done,
        "pct": round(100 * done / required_total) if required_total else 100,
        "next_item_title": next_item_title,
        "certificate_required": program.certificate_required,
        "certificate_earned": await _certificate_earned(db, assignment.registration_id),
    }


async def list_student_assignments(db: AsyncSession, *, user_id: uuid.UUID) -> list[dict]:
    assignments = (await db.execute(
        select(LmsProgramAssignment)
        .where(LmsProgramAssignment.user_id == user_id)
        .order_by(LmsProgramAssignment.assigned_at.desc())
    )).scalars().all()
    out = []
    for assignment in assignments:
        summary = await _assignment_summary(db, assignment)
        if summary is not None:
            out.append(summary)
    return out


async def cohort_program_roster(
    db: AsyncSession, *, cohort_id: uuid.UUID, restrict_to_cohort_ids: set[uuid.UUID] | None = None,
) -> list[dict]:
    """Instructor/ops view — every student assigned this cohort's LMS
    Program checklist, each with the same progress summary shape as the
    student's own `/lms/programs` list. `restrict_to_cohort_ids` is an
    instructor's own scope (see `program_roster` below) — `None` (the
    default) is unrestricted, matching every other caller of this
    function today (the cohort_id is already the scope)."""
    if restrict_to_cohort_ids is not None and cohort_id not in restrict_to_cohort_ids:
        return []
    assignments = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.cohort_id == cohort_id)
    )).scalars().all()
    out = []
    for assignment in assignments:
        summary = await _assignment_summary(db, assignment)
        if summary is None:
            continue
        user = await db.get(User, assignment.user_id)
        pairs = await _assignment_items_and_progress(db, assignment.id)
        team_progress_by_item = await _team_progress_by_item(
            db, pairs=pairs, cohort_id=assignment.cohort_id, user_id=assignment.user_id,
        )
        pending = [
            {
                "item_id": item.id, "title": item.title,
                "submitted_url": (
                    team_progress_by_item[item.id].submitted_url if item.id in team_progress_by_item
                    else progress.submitted_url
                ),
            }
            for item, progress in pairs
            if _effective_status(item, progress, team_progress_by_item) == "awaiting_confirmation"
        ]
        out.append({
            **summary, "user_id": assignment.user_id, "student_name": user.full_name if user else "?",
            "pending_confirmations": pending,
        })
    return out


async def program_roster(
    db: AsyncSession, *, lms_program_id: uuid.UUID, restrict_to_cohort_ids: set[uuid.UUID] | None = None,
) -> list[dict]:
    """Program-wide sibling of `cohort_program_roster` — every student
    assigned this program's checklist, across every cohort using it (an
    override-scoped assignment still points `lms_program_id` at the
    parent program — see `assign_lms_program` — so this single filter
    already covers both). `restrict_to_cohort_ids`, when given, is an
    instructor's own reachable-cohort set (`instructor_cohort_ids()`) —
    the router computes it, this function just applies it, same split of
    responsibility `require_cohort_access` already uses elsewhere."""
    assignments = (await db.execute(
        select(LmsProgramAssignment).where(LmsProgramAssignment.lms_program_id == lms_program_id)
    )).scalars().all()
    out = []
    for assignment in assignments:
        if restrict_to_cohort_ids is not None and assignment.cohort_id not in restrict_to_cohort_ids:
            continue
        summary = await _assignment_summary(db, assignment)
        if summary is None:
            continue
        user = await db.get(User, assignment.user_id)
        pairs = await _assignment_items_and_progress(db, assignment.id)
        team_progress_by_item = await _team_progress_by_item(
            db, pairs=pairs, cohort_id=assignment.cohort_id, user_id=assignment.user_id,
        )
        pending = [
            {
                "item_id": item.id, "title": item.title,
                "submitted_url": (
                    team_progress_by_item[item.id].submitted_url if item.id in team_progress_by_item
                    else progress.submitted_url
                ),
            }
            for item, progress in pairs
            if _effective_status(item, progress, team_progress_by_item) == "awaiting_confirmation"
        ]
        out.append({
            **summary, "user_id": assignment.user_id, "student_name": user.full_name if user else "?",
            "pending_confirmations": pending,
        })
    return out


async def assignment_item_detail(db: AsyncSession, *, assignment_id: uuid.UUID) -> list[dict] | None:
    """Every item on one student's assignment, not just the ones awaiting
    confirmation — the roster's `pending_confirmations` only ever shows a
    fraction of the checklist; this is the "detailed submissions" drill-in
    (operator ask, 2026-08-22): what a `submission`-item actually links to,
    which `mission_run` item's attempt to open, everything in one call.
    `None` means the assignment doesn't exist — the router turns that into
    a 404 the same way `get_student_checklist` does.

    A `scope="team"` item's real state lives on the shared
    `LmsProgramTeamItemProgress` row, not this student's own individual
    row (that row is never written once an item is team-scoped) — same
    team-lookup `get_student_checklist` does, needed here too so ops sees
    the same status the student's own checklist shows instead of a
    permanently-"pending" individual row."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    if assignment is None:
        return None
    pairs = await _assignment_items_and_progress(db, assignment_id)
    team_progress_by_item = await _team_progress_by_item(
        db, pairs=pairs, cohort_id=assignment.cohort_id, user_id=assignment.user_id,
    )

    out = []
    dashboard_cache: dict[uuid.UUID, dict | None] = {}
    for item, progress in pairs:
        team_progress = team_progress_by_item.get(item.id) if item.scope == "team" else None
        if team_progress is not None:
            status = team_progress.status
            submitted_url = team_progress.submitted_url
            completed_at = team_progress.completed_at
            confirmed_by_user_id = team_progress.confirmed_by_user_id
        else:
            status = await refresh_item_progress(db, progress=progress, item=item, user_id=assignment.user_id, dashboard_cache=dashboard_cache)
            submitted_url = progress.submitted_url
            completed_at = progress.completed_at
            confirmed_by_user_id = progress.confirmed_by_user_id
        out.append({
            "item_id": item.id, "title": item.title, "item_type": item.item_type,
            "status": status, "submitted_url": submitted_url,
            "completed_at": completed_at, "mission_attempt_id": progress.mission_attempt_id,
            "confirmed_by_user_id": confirmed_by_user_id,
        })
    return out


async def confirm_program_item(
    db: AsyncSession, *, assignment_id: uuid.UUID, item_id: uuid.UUID, confirmed_by_user_id: uuid.UUID,
) -> LmsProgramItemProgress | LmsProgramTeamItemProgress | None:
    """Ops/instructor sign-off for a `requires_confirmation` item —
    the other half of the self-check flow (services/lms/program.py's
    `refresh_item_progress` never touches these, they're only ever
    written here or by the student's own self-check). A `scope="team"`
    item signs off the shared `LmsProgramTeamItemProgress` row for the
    assignment's own student's team — same row `checklist_item_write_target`
    resolves for a student's own submit/complete — not the never-written
    individual row; the confirming ops/instructor user has no team of
    their own to resolve here."""
    assignment = await db.get(LmsProgramAssignment, assignment_id)
    item = await db.get(LmsProgramItem, item_id)
    if assignment is None or item is None:
        return None
    if item.scope == "team":
        team = await team_for_cohort_member(db, cohort_id=assignment.cohort_id, user_id=assignment.user_id)
        if team is None:
            return None
        target: LmsProgramItemProgress | LmsProgramTeamItemProgress = await _get_or_create_team_progress(
            db, item_id=item.id, team_id=team.id,
        )
    else:
        row = await db.scalar(
            select(LmsProgramItemProgress).where(
                LmsProgramItemProgress.assignment_id == assignment_id, LmsProgramItemProgress.item_id == item_id,
            )
        )
        if row is None:
            return None
        target = row
    target.status = "done"
    target.completed_at = datetime.now(timezone.utc)
    target.confirmed_by_user_id = confirmed_by_user_id
    await db.flush()
    return target
