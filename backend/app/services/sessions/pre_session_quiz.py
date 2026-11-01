from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.pre_session_quiz import (
    PreSessionQuizAssignment,
    PreSessionQuizAttempt,
    PreSessionQuizDatasheet,
    PreSessionQuizPhaseTrial,
    PreSessionQuizPreset,
    PreSessionQuizQuestion,
)
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.sessions.pre_session_quiz import (
    PhaseTrialSubmitIn,
    PreSessionQuizAnswerIn,
    PreSessionQuizDatasheetIn,
    PreSessionQuizDatasheetUpdateIn,
    PreSessionQuizPresetIn,
    PreSessionQuizQuestionIn,
    PreSessionQuizReviewQuestionIn,
    PreSessionQuizSubmitIn,
)


# ── Question Bank CRUD ──────────────────────────────────────────────────────

async def list_questions(
    db: AsyncSession, *, topic: str | None = None, active_only: bool = True
) -> list[PreSessionQuizQuestion]:
    q = select(PreSessionQuizQuestion)
    if active_only:
        q = q.where(PreSessionQuizQuestion.is_active.is_(True))
    if topic:
        q = q.where(PreSessionQuizQuestion.topic == topic)
    q = q.order_by(PreSessionQuizQuestion.created_at.asc())
    return list((await db.execute(q)).scalars().all())


async def create_question(
    db: AsyncSession, body: PreSessionQuizQuestionIn, user: User
) -> PreSessionQuizQuestion:
    row = PreSessionQuizQuestion(
        topic=body.topic.strip() or "General",
        question_type=body.question_type,
        title=body.title.strip(),
        prompt=body.prompt.strip(),
        image_url=body.image_url,
        options=[o.model_dump() for o in body.options],
        table_config=body.table_config.model_dump() if body.table_config else None,
        allow_other=body.allow_other,
        is_other_correct=body.is_other_correct,
        explanation=body.explanation,
        explanation_image_url=body.explanation_image_url,
        explanation_table=body.explanation_table.model_dump() if body.explanation_table else None,
        is_active=body.is_active,
        created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_question(
    db: AsyncSession, question_id: UUID, body: PreSessionQuizQuestionIn
) -> PreSessionQuizQuestion:
    row = await db.get(PreSessionQuizQuestion, question_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    row.topic = body.topic.strip() or "General"
    row.question_type = body.question_type
    row.title = body.title.strip()
    row.prompt = body.prompt.strip()
    row.image_url = body.image_url
    row.options = [o.model_dump() for o in body.options]
    row.table_config = body.table_config.model_dump() if body.table_config else None
    row.allow_other = body.allow_other
    row.is_other_correct = body.is_other_correct
    row.explanation = body.explanation
    row.explanation_image_url = body.explanation_image_url
    row.explanation_table = body.explanation_table.model_dump() if body.explanation_table else None
    row.is_active = body.is_active
    await db.commit()
    await db.refresh(row)
    return row


async def delete_question(db: AsyncSession, question_id: UUID) -> None:
    row = await db.get(PreSessionQuizQuestion, question_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found")
    await db.delete(row)
    await db.commit()


# ── Datasheet Library CRUD ──────────────────────────────────────────────────

async def list_datasheets(
    db: AsyncSession,
    *,
    subsystem: str | None = None,
    doc_type: str | None = None,
    search: str | None = None,
    active_only: bool = True,
) -> list[PreSessionQuizDatasheet]:
    q = select(PreSessionQuizDatasheet)
    if active_only:
        q = q.where(PreSessionQuizDatasheet.is_active.is_(True))
    if subsystem and subsystem != "all":
        q = q.where(PreSessionQuizDatasheet.subsystem_tag == subsystem)
    if doc_type and doc_type != "all":
        q = q.where(PreSessionQuizDatasheet.doc_type == doc_type)
    if search and search.strip():
        term = f"%{search.strip().lower()}%"
        q = q.where(
            func.lower(PreSessionQuizDatasheet.title).like(term)
            | func.lower(PreSessionQuizDatasheet.description).like(term)
        )
    q = q.order_by(PreSessionQuizDatasheet.created_at.desc())
    return list((await db.execute(q)).scalars().all())


async def get_datasheet(db: AsyncSession, datasheet_id: UUID) -> PreSessionQuizDatasheet:
    ds = await db.get(PreSessionQuizDatasheet, datasheet_id)
    if not ds:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Datasheet not found")
    return ds


async def create_datasheet(
    db: AsyncSession, body: PreSessionQuizDatasheetIn, user: User
) -> PreSessionQuizDatasheet:
    row = PreSessionQuizDatasheet(
        title=body.title.strip(),
        url=body.url.strip(),
        doc_type=body.doc_type,
        subsystem_tag=body.subsystem_tag.strip() if body.subsystem_tag else None,
        description=body.description.strip() if body.description else None,
        image_url=body.image_url.strip() if body.image_url else None,
        page_count=body.page_count,
        is_active=body.is_active,
        created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_datasheet(
    db: AsyncSession, datasheet_id: UUID, body: PreSessionQuizDatasheetUpdateIn
) -> PreSessionQuizDatasheet:
    ds = await get_datasheet(db, datasheet_id)
    if body.title is not None:
        ds.title = body.title.strip()
    if body.url is not None:
        ds.url = body.url.strip()
    if body.doc_type is not None:
        ds.doc_type = body.doc_type
    if body.subsystem_tag is not None:
        ds.subsystem_tag = body.subsystem_tag.strip() if body.subsystem_tag else None
    if body.description is not None:
        ds.description = body.description.strip() if body.description else None
    if body.image_url is not None:
        ds.image_url = body.image_url.strip() if body.image_url else None
    if body.page_count is not None:
        ds.page_count = body.page_count
    if body.is_active is not None:
        ds.is_active = body.is_active
    await db.commit()
    await db.refresh(ds)
    return ds


async def delete_datasheet(db: AsyncSession, datasheet_id: UUID) -> None:
    ds = await get_datasheet(db, datasheet_id)
    ds.is_active = False
    await db.commit()


# ── Presets / Templates CRUD ────────────────────────────────────────────────

async def _hydrate_presets(
    db: AsyncSession, presets: list[PreSessionQuizPreset]
) -> list[dict]:
    all_q_ids: set[UUID] = set()
    for p in presets:
        for qid in p.question_ids or []:
            try:
                all_q_ids.add(UUID(str(qid)))
            except (ValueError, TypeError):
                pass
        for phase in p.phases or []:
            for qid in phase.get("question_ids") or []:
                try:
                    all_q_ids.add(UUID(str(qid)))
                except (ValueError, TypeError):
                    pass

    questions_by_id: dict[str, PreSessionQuizQuestion] = {}
    if all_q_ids:
        q_rows = (
            await db.execute(
                select(PreSessionQuizQuestion).where(PreSessionQuizQuestion.id.in_(list(all_q_ids)))
            )
        ).scalars().all()
        questions_by_id = {str(q.id): q for q in q_rows}

    out = []
    for p in presets:
        ordered_questions = []
        for qid in p.question_ids or []:
            q_obj = questions_by_id.get(str(qid))
            if q_obj:
                ordered_questions.append(q_obj)
        out.append({
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "question_ids": [str(qid) for qid in (p.question_ids or []) if str(qid) in questions_by_id],
            "reference_attachments": list(p.reference_attachments or []),
            "phases": list(p.phases or []),
            "questions": ordered_questions,
            "is_active": p.is_active,
            "created_at": p.created_at,
        })
    return out


async def list_presets(db: AsyncSession, *, active_only: bool = True) -> list[dict]:
    q = select(PreSessionQuizPreset)
    if active_only:
        q = q.where(PreSessionQuizPreset.is_active.is_(True))
    q = q.order_by(PreSessionQuizPreset.created_at.asc())
    rows = list((await db.execute(q)).scalars().all())
    return await _hydrate_presets(db, rows)


async def get_preset_hydrated(db: AsyncSession, preset_id: UUID) -> dict | None:
    p = await db.get(PreSessionQuizPreset, preset_id)
    if p is None:
        return None
    hydrated = await _hydrate_presets(db, [p])
    return hydrated[0] if hydrated else None


async def create_preset(
    db: AsyncSession, body: PreSessionQuizPresetIn, user: User
) -> dict:
    # If question_ids not provided, aggregate from phases
    question_ids = list(body.question_ids or [])
    if not question_ids and body.phases:
        seen = set()
        for ph in body.phases:
            for qid in ph.question_ids:
                if qid not in seen:
                    seen.add(qid)
                    question_ids.append(qid)

    row = PreSessionQuizPreset(
        name=body.name.strip(),
        description=body.description,
        question_ids=question_ids,
        reference_attachments=[a.model_dump() for a in (body.reference_attachments or [])],
        phases=[ph.model_dump() for ph in (body.phases or [])],
        is_active=body.is_active,
        created_by=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    hydrated = await _hydrate_presets(db, [row])
    return hydrated[0]


async def update_preset(
    db: AsyncSession, preset_id: UUID, body: PreSessionQuizPresetIn
) -> dict:
    row = await db.get(PreSessionQuizPreset, preset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Preset not found")
    row.name = body.name.strip()
    row.description = body.description

    question_ids = list(body.question_ids or [])
    if not question_ids and body.phases:
        seen = set()
        for ph in body.phases:
            for qid in ph.question_ids:
                if qid not in seen:
                    seen.add(qid)
                    question_ids.append(qid)

    row.question_ids = question_ids
    row.reference_attachments = [a.model_dump() for a in (body.reference_attachments or [])]
    row.phases = [ph.model_dump() for ph in (body.phases or [])]
    row.is_active = body.is_active
    await db.commit()
    await db.refresh(row)
    hydrated = await _hydrate_presets(db, [row])
    return hydrated[0]


async def delete_preset(db: AsyncSession, preset_id: UUID) -> None:
    row = await db.get(PreSessionQuizPreset, preset_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Preset not found")
    await db.delete(row)
    await db.commit()


# ── Assignment & Inheritance (Program -> Cohort -> Session) ─────────────────

async def get_assignment_for_scope(
    db: AsyncSession, scope: str, owner_id: UUID
) -> dict:
    """Resolve the active pre-session quiz assignment for a program, cohort, or session."""
    if scope == "programs":
        program = await db.get(Program, owner_id)
        if not program:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
        assign = (
            await db.execute(
                select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.program_id == owner_id)
            )
        ).scalars().first()
        if assign and assign.preset_id:
            preset = await db.get(PreSessionQuizPreset, assign.preset_id)
            if preset:
                return {
                    "level": "program",
                    "preset_id": preset.id,
                    "preset_name": preset.name,
                    "inherited": False,
                }
        return {"level": "none", "preset_id": None, "preset_name": None, "inherited": False}

    if scope == "cohorts":
        cohort = await db.get(Cohort, owner_id)
        if not cohort:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
        c_assign = (
            await db.execute(
                select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id == owner_id)
            )
        ).scalars().first()
        if c_assign is not None:
            if c_assign.preset_id is None:
                return {"level": "cohort", "preset_id": None, "preset_name": None, "inherited": False}
            preset = await db.get(PreSessionQuizPreset, c_assign.preset_id)
            if preset:
                return {
                    "level": "cohort",
                    "preset_id": preset.id,
                    "preset_name": preset.name,
                    "inherited": False,
                }
        # Fallback to program
        if cohort.program_id:
            p_assign = (
                await db.execute(
                    select(PreSessionQuizAssignment).where(
                        PreSessionQuizAssignment.program_id == cohort.program_id
                    )
                )
            ).scalars().first()
            if p_assign and p_assign.preset_id:
                preset = await db.get(PreSessionQuizPreset, p_assign.preset_id)
                if preset:
                    return {
                        "level": "program",
                        "preset_id": preset.id,
                        "preset_name": preset.name,
                        "inherited": True,
                    }
        return {"level": "none", "preset_id": None, "preset_name": None, "inherited": False}

    if scope == "sessions":
        session = await db.get(Session, owner_id)
        if not session:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
        s_assign = (
            await db.execute(
                select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id == owner_id)
            )
        ).scalars().first()
        if s_assign is not None:
            if s_assign.preset_id is None:
                return {"level": "session", "preset_id": None, "preset_name": None, "inherited": False}
            preset = await db.get(PreSessionQuizPreset, s_assign.preset_id)
            if preset:
                return {
                    "level": "session",
                    "preset_id": preset.id,
                    "preset_name": preset.name,
                    "inherited": False,
                }
        # Fallback to cohort
        if session.cohort_id:
            res = await get_assignment_for_scope(db, "cohorts", session.cohort_id)
            if res["preset_id"] is not None:
                res["inherited"] = True
            return res
        return {"level": "none", "preset_id": None, "preset_name": None, "inherited": False}

    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid scope")


async def set_assignment_for_scope(
    db: AsyncSession, scope: str, owner_id: UUID, preset_id: UUID | None, *, clear_override: bool = False
) -> dict:
    if scope == "programs":
        col = PreSessionQuizAssignment.program_id
        kwargs = {"program_id": owner_id}
    elif scope == "cohorts":
        col = PreSessionQuizAssignment.cohort_id
        kwargs = {"cohort_id": owner_id}
    elif scope == "sessions":
        col = PreSessionQuizAssignment.session_id
        kwargs = {"session_id": owner_id}
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid scope")

    existing = (await db.execute(select(PreSessionQuizAssignment).where(col == owner_id))).scalars().first()

    if clear_override or (scope == "programs" and preset_id is None):
        if existing:
            await db.delete(existing)
            await db.commit()
        return await get_assignment_for_scope(db, scope, owner_id)

    if preset_id is not None:
        preset = await db.get(PreSessionQuizPreset, preset_id)
        if preset is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Preset not found")

    if existing:
        existing.preset_id = preset_id
    else:
        db.add(PreSessionQuizAssignment(**kwargs, preset_id=preset_id))

    await db.commit()
    return await get_assignment_for_scope(db, scope, owner_id)


# ── Pipeline Attempt Serialization & Helpers ────────────────────────────────

async def _serialize_attempt(db: AsyncSession, attempt: PreSessionQuizAttempt, user_name: str | None = None) -> dict:
    now = datetime.now(timezone.utc)
    cooldown_rem = None
    if attempt.locked_until and attempt.locked_until > now:
        cooldown_rem = max(0, int((attempt.locked_until - now).total_seconds()))

    if user_name is None:
        u = await db.get(User, attempt.user_id)
        user_name = (u.full_name or u.email) if u else "Instructor"

    return {
        "id": attempt.id,
        "cohort_id": attempt.cohort_id,
        "session_id": attempt.session_id,
        "preset_id": attempt.preset_id,
        "user_id": attempt.user_id,
        "user_name": user_name,
        "status": attempt.status,
        "current_phase_index": attempt.current_phase_index,
        "phase_started_at": attempt.phase_started_at,
        "locked_until": attempt.locked_until,
        "cooldown_seconds_remaining": cooldown_rem,
        "started_at": attempt.started_at,
        "submitted_at": attempt.submitted_at,
        "total_duration_seconds": attempt.total_duration_seconds,
        "answers": list(attempt.answers or []),
        "phase_states": dict(attempt.phase_states or {}),
        "auto_score": attempt.auto_score,
        "final_score": attempt.final_score,
        "total_questions": attempt.total_questions,
        "pending_review_count": attempt.pending_review_count,
    }


def _serialize_trial(trial: PreSessionQuizPhaseTrial) -> dict:
    now = datetime.now(timezone.utc)
    cooldown_rem = None
    if trial.cooldown_until and trial.cooldown_until > now:
        cooldown_rem = max(0, int((trial.cooldown_until - now).total_seconds()))

    return {
        "id": trial.id,
        "attempt_id": trial.attempt_id,
        "phase_id": trial.phase_id,
        "phase_index": trial.phase_index,
        "phase_type": trial.phase_type,
        "trial_number": trial.trial_number,
        "started_at": trial.started_at,
        "submitted_at": trial.submitted_at,
        "duration_seconds": trial.duration_seconds,
        "score": trial.score,
        "total": trial.total,
        "score_pct": trial.score_pct,
        "pass_percentage_required": trial.pass_percentage_required,
        "passed": trial.passed,
        "cooldown_until": trial.cooldown_until,
        "cooldown_seconds_remaining": cooldown_rem,
        "payload": dict(trial.payload or {}),
    }


def _sanitize_trial_for_instructor(trial_data: dict, phase_cfg: dict) -> dict:
    """Conditionally strips expected answers/explanations if phase trial failed."""
    if trial_data.get("passed"):
        return trial_data

    payload = dict(trial_data.get("payload") or {})
    show_correct = bool(phase_cfg.get("show_correct_on_fail", False))
    show_explanation = bool(phase_cfg.get("show_explanation_on_fail", False))

    if trial_data.get("phase_type") == "subsystem_matching":
        results = dict(payload.get("results") or {})
        sanitized_results = {}
        for ds_id, res in results.items():
            r = dict(res)
            if not show_correct:
                r.pop("expected_bucket_id", None)
                r.pop("is_correct", None)
            if not show_explanation:
                r.pop("explanation", None)
            sanitized_results[ds_id] = r
        payload["results"] = sanitized_results

    elif trial_data.get("phase_type") == "quiz":
        answers = list(payload.get("answers") or [])
        sanitized_answers = []
        for a in answers:
            ans = dict(a)
            if not show_correct:
                ans.pop("expected_cells", None)
                ans.pop("expected_option_index", None)
            if not show_explanation:
                ans.pop("explanation", None)
                ans.pop("explanation_table", None)
            sanitized_answers = sanitized_answers + [ans]
        payload["answers"] = sanitized_answers

    trial_data["payload"] = payload
    return trial_data


# ── Cohort Pre-Quiz State Machine & Status Endpoints ────────────────────────

async def get_cohort_pre_quiz_status(
    db: AsyncSession, cohort_id: UUID, user: User
) -> dict:
    assign_info = await get_assignment_for_scope(db, "cohorts", cohort_id)
    preset_id = assign_info.get("preset_id")
    if not preset_id:
        return {
            "has_quiz": False,
            "assignment_level": "none",
            "preset": None,
            "my_attempt": None,
            "trials": [],
            "all_attempts": [],
        }

    preset_hydrated = await get_preset_hydrated(db, preset_id)
    if not preset_hydrated:
        return {
            "has_quiz": False,
            "assignment_level": assign_info.get("level", "none"),
            "preset": None,
            "my_attempt": None,
            "trials": [],
            "all_attempts": [],
        }

    attempt_row = (
        await db.execute(
            select(PreSessionQuizAttempt).where(
                PreSessionQuizAttempt.cohort_id == cohort_id,
                PreSessionQuizAttempt.user_id == user.id,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    # Check if cooldown lock expired naturally
    if attempt_row and attempt_row.status == "cooldown_locked" and attempt_row.locked_until and now >= attempt_row.locked_until:
        attempt_row.status = "in_progress"
        attempt_row.locked_until = None
        attempt_row.phase_started_at = now
        await db.commit()
        await db.refresh(attempt_row)

    trials_data = []
    if attempt_row:
        trial_rows = (
            await db.execute(
                select(PreSessionQuizPhaseTrial)
                .where(PreSessionQuizPhaseTrial.attempt_id == attempt_row.id)
                .order_by(PreSessionQuizPhaseTrial.submitted_at.asc())
            )
        ).scalars().all()

        phases_by_id = {ph.get("id"): ph for ph in (preset_hydrated.get("phases") or [])}
        for tr in trial_rows:
            tr_dict = _serialize_trial(tr)
            ph_cfg = phases_by_id.get(tr.phase_id, {})
            trials_data.append(_sanitize_trial_for_instructor(tr_dict, ph_cfg))

    my_attempt = await _serialize_attempt(db, attempt_row, user.full_name or user.email) if attempt_row else None

    is_ops = any(r in user.role_values for r in ("operations", "admin", "facilitator"))
    all_attempts = []
    if is_ops:
        rows = (
            await db.execute(
                select(PreSessionQuizAttempt)
                .where(PreSessionQuizAttempt.cohort_id == cohort_id)
                .order_by(PreSessionQuizAttempt.started_at.desc())
            )
        ).scalars().all()
        user_ids = [r.user_id for r in rows]
        user_names = {}
        if user_ids:
            u_rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
            user_names = {u.id: u.full_name or u.email for u in u_rows}
        for r in rows:
            all_attempts.append(await _serialize_attempt(db, r, user_names.get(r.user_id, "Instructor")))

        attempt_ids = [r.id for r in rows]
        if attempt_ids:
            all_trial_rows = (
                await db.execute(
                    select(PreSessionQuizPhaseTrial)
                    .where(PreSessionQuizPhaseTrial.attempt_id.in_(attempt_ids))
                    .order_by(PreSessionQuizPhaseTrial.submitted_at.asc())
                )
            ).scalars().all()
            trials_data = [_serialize_trial(tr) for tr in all_trial_rows]

    return {
        "has_quiz": True,
        "assignment_level": assign_info.get("level", "cohort"),
        "preset": preset_hydrated,
        "my_attempt": my_attempt,
        "trials": trials_data,
        "all_attempts": all_attempts,
    }


async def get_session_pre_quiz_status(
    db: AsyncSession, session_id: UUID, user: User
) -> dict:
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    res = await get_cohort_pre_quiz_status(db, session.cohort_id, user)
    # Check if session has a specific assignment override
    s_assign = (
        await db.execute(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id == session_id)
        )
    ).scalars().first()
    if s_assign and s_assign.preset_id is None:
        res["has_quiz"] = False
    return res


# ── Phase Start & Server-Side Cooldown Enforcement ──────────────────────────

async def start_cohort_phase(
    db: AsyncSession, cohort_id: UUID, phase_id: str, user: User
) -> dict:
    assign_info = await get_assignment_for_scope(db, "cohorts", cohort_id)
    preset_id = assign_info.get("preset_id")
    if not preset_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No pre-session quiz assigned to this cohort")

    preset_hydrated = await get_preset_hydrated(db, preset_id)
    if not preset_hydrated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz preset not found")

    phases: list[dict[str, Any]] = preset_hydrated.get("phases") or []
    target_idx = next((i for i, p in enumerate(phases) if p.get("id") == phase_id), None)
    if target_idx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Phase not found in preset")

    # Race-safe get or create attempt
    attempt = (
        await db.execute(
            select(PreSessionQuizAttempt).where(
                PreSessionQuizAttempt.cohort_id == cohort_id,
                PreSessionQuizAttempt.user_id == user.id,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    if attempt is None:
        attempt = PreSessionQuizAttempt(
            cohort_id=cohort_id,
            preset_id=preset_id,
            user_id=user.id,
            status="in_progress",
            current_phase_index=0,
            phase_started_at=now,
            started_at=now,
            total_questions=len(preset_hydrated.get("questions") or []),
        )
        db.add(attempt)
        await db.commit()
        await db.refresh(attempt)

    # Instructors cannot jump ahead to locked phases
    if target_idx > attempt.current_phase_index:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cannot access locked phase")

    # Server-Side Cooldown Enforcement
    if attempt.locked_until and now < attempt.locked_until:
        remaining = int((attempt.locked_until - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": f"Phase is locked for review. Try again in {remaining} seconds.",
                "locked_until": attempt.locked_until.isoformat(),
                "remaining_seconds": remaining,
            },
        )

    # Cooldown passed or phase reopened
    if attempt.status != "completed":
        attempt.status = "in_progress"
    attempt.locked_until = None
    attempt.phase_started_at = now
    await db.commit()
    await db.refresh(attempt)

    return await _serialize_attempt(db, attempt, user.full_name or user.email)


# ── Phase Submission, Grading & Masking ──────────────────────────────────────

async def submit_cohort_phase(
    db: AsyncSession, cohort_id: UUID, phase_id: str, user: User, body: PhaseTrialSubmitIn
) -> dict:
    assign_info = await get_assignment_for_scope(db, "cohorts", cohort_id)
    preset_id = assign_info.get("preset_id")
    if not preset_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No pre-session quiz assigned to this cohort")

    preset_hydrated = await get_preset_hydrated(db, preset_id)
    if not preset_hydrated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz preset not found")

    phases: list[dict[str, Any]] = preset_hydrated.get("phases") or []
    target_idx = next((i for i, p in enumerate(phases) if p.get("id") == phase_id), None)
    if target_idx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Phase not found in preset")
    phase = phases[target_idx]

    attempt = (
        await db.execute(
            select(PreSessionQuizAttempt).where(
                PreSessionQuizAttempt.cohort_id == cohort_id,
                PreSessionQuizAttempt.user_id == user.id,
            )
        )
    ).scalars().first()
    if attempt is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Phase has not been started yet")

    now = datetime.now(timezone.utc)
    # Check cooldown lock
    if attempt.locked_until and now < attempt.locked_until:
        remaining = int((attempt.locked_until - now).total_seconds())
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "message": f"Phase is currently locked. Try again in {remaining} seconds.",
                "locked_until": attempt.locked_until.isoformat(),
                "remaining_seconds": remaining,
            },
        )

    # Duration calculation
    phase_started = attempt.phase_started_at or attempt.started_at or now
    wall_sec = max(1, int((now - phase_started).total_seconds()))
    duration_seconds = min(wall_sec, body.client_duration_seconds) if body.client_duration_seconds > 0 else wall_sec

    # Grading per phase_type
    phase_type = phase.get("phase_type")
    pass_pct_req = phase.get("pass_percentage", 100)
    cooldown_sec = phase.get("cooldown_seconds", 0)

    score = 0
    total = 0
    score_pct = 100
    passed = False
    trial_payload: dict[str, Any] = {}

    if phase_type == "explore_datasheets":
        score = 1
        total = 1
        score_pct = 100
        passed = True
        trial_payload = {"acknowledged": True}

    elif phase_type == "subsystem_matching":
        matching_cfg = phase.get("matching_config") or {}
        items = matching_cfg.get("items") or []
        placements = body.matching_placements or {}
        results = {}
        correct_count = 0

        for it in items:
            ds_id = it.get("datasheet_id")
            exp_bucket = it.get("correct_bucket_id")
            actual_bucket = placements.get(ds_id)
            is_corr = (actual_bucket == exp_bucket)
            if is_corr:
                correct_count += 1
            results[ds_id] = {
                "is_correct": is_corr,
                "expected_bucket_id": exp_bucket,
                "actual_bucket_id": actual_bucket,
                "explanation": it.get("explanation"),
            }

        score = correct_count
        total = len(items)
        score_pct = round((score / total) * 100) if total else 100
        passed = (score_pct >= pass_pct_req)
        trial_payload = {
            "placements": placements,
            "results": results,
        }

    elif phase_type == "quiz":
        phase_q_ids = [UUID(str(qid)) for qid in (phase.get("question_ids") or [])]
        phase_questions: list[PreSessionQuizQuestion] = []
        if phase_q_ids:
            q_rows = (
                await db.execute(
                    select(PreSessionQuizQuestion).where(PreSessionQuizQuestion.id.in_(phase_q_ids))
                )
            ).scalars().all()
            q_map = {q.id: q for q in q_rows}
            phase_questions = [q_map[qid] for qid in phase_q_ids if qid in q_map]

        answers_by_qid = {str(a.question_id): a.model_dump() for a in body.answers}
        graded_answers = []
        pending_count = 0

        for q in phase_questions:
            qid_str = str(q.id)
            ans_in = answers_by_qid.get(qid_str, {})
            chose_other = bool(ans_in.get("chose_other"))
            other_text = (ans_in.get("other_text") or "").strip()
            written_text = (ans_in.get("written_text") or "").strip()

            q_status = "incorrect"
            needs_ops = False

            # Case A: Tricky Discrepancy Question where "Other" is expected
            if q.is_other_correct:
                if chose_other and bool(other_text):
                    q_status = "correct"
                    needs_ops = True
                else:
                    q_status = "incorrect"

            # Case B: Standard Question where Instructor Chose "Other"
            elif chose_other:
                if bool(other_text):
                    q_status = "pending_review"
                    pending_count += 1
                else:
                    q_status = "incorrect"

            # Case C: Open-Ended Written Question
            elif q.question_type == "written":
                if bool(written_text):
                    q_status = "pending_review"
                    pending_count += 1
                else:
                    q_status = "incorrect"

            # Case D: Pinout Table Widget
            elif q.question_type == "pinout_table":
                table_cfg = q.table_config or {}
                rows = table_cfg.get("rows") or []
                selected_cells = ans_in.get("selected_cells") or []
                has_any_selection = any(
                    isinstance(r, list) and len(r) > 0 for r in selected_cells
                )
                if not rows or not has_any_selection:
                    q_status = "incorrect"
                else:
                    is_ok = True
                    has_expected = False
                    for r_idx, row in enumerate(rows):
                        cells = row.get("cells") or []
                        expected = {c_idx for c_idx, cell in enumerate(cells) if cell.get("is_correct")}
                        if expected:
                            has_expected = True
                        actual = set(selected_cells[r_idx]) if r_idx < len(selected_cells) and isinstance(selected_cells[r_idx], list) else set()
                        if expected != actual:
                            is_ok = False
                            break
                    q_status = "correct" if (is_ok and has_expected) else "incorrect"

            # Case E: Standard MCQ
            else:
                options = q.options or []
                sel_idx = ans_in.get("selected_option_index")
                if sel_idx is not None and isinstance(sel_idx, int) and 0 <= sel_idx < len(options) and options[sel_idx].get("is_correct"):
                    q_status = "correct"
                else:
                    q_status = "incorrect"

            # Credit toward phase gate (written questions with text credit toward gate progression)
            if q_status == "correct" or (q.question_type == "written" and bool(written_text)):
                score += 1

            graded_answers.append({
                "question_id": qid_str,
                "selected_option_index": ans_in.get("selected_option_index"),
                "selected_cells": ans_in.get("selected_cells"),
                "chose_other": chose_other,
                "other_text": other_text or None,
                "written_text": written_text or None,
                "status": q_status,
                "needs_ops_inspection": needs_ops,
                "reviewed_by": None,
                "reviewed_at": None,
                "review_comment": None,
            })

        total = len(phase_questions)
        score_pct = round((score / total) * 100) if total else 100
        passed = (score_pct >= pass_pct_req)
        trial_payload = {"answers": graded_answers}

    # Count prior trials for trial_number
    prev_trials_count = (
        await db.execute(
            select(func.count()).select_from(PreSessionQuizPhaseTrial).where(
                PreSessionQuizPhaseTrial.attempt_id == attempt.id,
                PreSessionQuizPhaseTrial.phase_id == phase_id,
            )
        )
    ).scalar() or 0
    trial_number = prev_trials_count + 1

    cooldown_until = None
    if not passed and cooldown_sec > 0:
        cooldown_until = now + timedelta(seconds=cooldown_sec)
        if attempt.status != "completed":
            attempt.status = "cooldown_locked"
            attempt.locked_until = cooldown_until
    elif passed:
        attempt.locked_until = None
        if attempt.status != "completed":
            if target_idx + 1 < len(phases):
                attempt.current_phase_index = max(attempt.current_phase_index, target_idx + 1)
                attempt.phase_started_at = now
                attempt.status = "in_progress"
            else:
                attempt.current_phase_index = len(phases)
                attempt.status = "completed"
                attempt.submitted_at = now
        else:
            attempt.current_phase_index = max(attempt.current_phase_index, len(phases))

    trial = PreSessionQuizPhaseTrial(
        attempt_id=attempt.id,
        phase_id=phase_id,
        phase_index=target_idx,
        phase_type=phase_type,
        trial_number=trial_number,
        started_at=phase_started,
        submitted_at=now,
        duration_seconds=duration_seconds,
        score=score,
        total=total,
        score_pct=score_pct,
        pass_percentage_required=pass_pct_req,
        passed=passed,
        cooldown_until=cooldown_until,
        payload=trial_payload,
    )
    db.add(trial)

    # Rollup metrics on attempt
    attempt.total_duration_seconds = (attempt.total_duration_seconds or 0) + duration_seconds
    phase_states = dict(attempt.phase_states or {})
    phase_states[phase_id] = {
        "passed": passed,
        "score_pct": score_pct,
        "trial_number": trial_number,
        "duration_seconds": duration_seconds,
        "last_trial_id": str(trial.id),
    }
    attempt.phase_states = phase_states

    if phase_type == "quiz":
        # Merge updated answers into attempt.answers
        ans_map = {a["question_id"]: a for a in (attempt.answers or [])}
        for ga in trial_payload.get("answers", []):
            ans_map[ga["question_id"]] = ga
        attempt.answers = list(ans_map.values())
        attempt.auto_score = sum(1 for a in attempt.answers if a.get("status") == "correct")
        attempt.final_score = attempt.auto_score
        attempt.pending_review_count = sum(1 for a in attempt.answers if a.get("status") == "pending_review")

    await db.commit()
    await db.refresh(trial)
    await db.refresh(attempt)

    trial_dict = _serialize_trial(trial)
    sanitized_trial = _sanitize_trial_for_instructor(trial_dict, phase)
    return {
        "trial": sanitized_trial,
        "attempt": await _serialize_attempt(db, attempt, user.full_name or user.email),
    }


# ── Ops Review & Escape Hatch Endpoints ─────────────────────────────────────

async def review_attempt_question(
    db: AsyncSession, attempt_id: UUID, body: PreSessionQuizReviewQuestionIn, reviewer: User
) -> dict:
    attempt = await db.get(PreSessionQuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    target_qid = str(body.question_id)
    updated_answers = []
    found = False
    now_iso = datetime.now(timezone.utc).isoformat()

    for ans in attempt.answers or []:
        ans_copy = dict(ans)
        if str(ans_copy.get("question_id")) == target_qid:
            found = True
            ans_copy["status"] = "correct" if body.is_correct else "incorrect"
            ans_copy["reviewed_by"] = reviewer.full_name or reviewer.email
            ans_copy["reviewed_at"] = now_iso
            ans_copy["review_comment"] = (body.review_comment or "").strip() or None
        updated_answers.append(ans_copy)

    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Question not found in this attempt")

    final_score = sum(1 for a in updated_answers if a.get("status") == "correct")
    pending_count = sum(1 for a in updated_answers if a.get("status") == "pending_review")

    attempt.answers = updated_answers
    attempt.final_score = final_score
    attempt.pending_review_count = pending_count

    await db.commit()
    await db.refresh(attempt)
    return await _serialize_attempt(db, attempt)


async def unlock_cooldown(db: AsyncSession, attempt_id: UUID, user: User) -> dict:
    attempt = await db.get(PreSessionQuizAttempt, attempt_id)
    if attempt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    attempt.locked_until = None
    if attempt.status != "completed":
        attempt.status = "in_progress"
    attempt.phase_started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(attempt)
    return await _serialize_attempt(db, attempt)


# Legacy flat submit compatibility wrapper
async def submit_session_pre_quiz(
    db: AsyncSession, session_id: UUID, user: User, body: PreSessionQuizSubmitIn
) -> dict:
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")
    status_data = await get_session_pre_quiz_status(db, session_id, user)
    preset = status_data.get("preset")
    if not preset:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No pre-session quiz is assigned to this session")

    # Delegate to the active phase or first quiz phase
    phases = preset.get("phases") or []
    quiz_phase = next((p for p in phases if p.get("phase_type") == "quiz"), None)
    phase_id = quiz_phase.get("id") if quiz_phase else "phase-quiz"

    res = await submit_cohort_phase(
        db, session.cohort_id, phase_id, user, PhaseTrialSubmitIn(answers=body.answers)
    )
    return res["attempt"]
