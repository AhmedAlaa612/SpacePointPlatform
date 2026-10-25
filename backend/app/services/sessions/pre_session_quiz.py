from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.pre_session_quiz import (
    PreSessionQuizAssignment,
    PreSessionQuizAttempt,
    PreSessionQuizPreset,
    PreSessionQuizQuestion,
)
from app.models.sessions.program import Program
from app.models.sessions.session import Session
from app.models.user import User
from app.schemas.sessions.pre_session_quiz import (
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
    row = PreSessionQuizPreset(
        name=body.name.strip(),
        description=body.description,
        question_ids=list(body.question_ids or []),
        reference_attachments=[a.model_dump() for a in (body.reference_attachments or [])],
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
    row.question_ids = list(body.question_ids or [])
    row.reference_attachments = [a.model_dump() for a in (body.reference_attachments or [])]
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


# ── Attempt Grading, Submission & Ops Review ────────────────────────────────

def _grade_question(question: PreSessionQuizQuestion, ans_in: dict) -> str:
    """Return 'correct', 'incorrect', or 'pending_review'."""
    chose_other = bool(ans_in.get("chose_other"))
    other_text = (ans_in.get("other_text") or "").strip()

    # Any "Other" answer with explanation goes to Pending Review for Ops to judge
    if chose_other:
        if not other_text:
            return "incorrect"
        return "pending_review"

    # If the question was a tricky datasheet error where "Other" was the expected choice,
    # and the instructor did NOT select "Other", it's incorrect.
    if question.is_other_correct:
        return "incorrect"

    if question.question_type == "pinout_table":
        table_cfg = question.table_config or {}
        rows = table_cfg.get("rows") or []
        selected_cells = ans_in.get("selected_cells") or []
        if not rows:
            return "correct"
        for r_idx, row in enumerate(rows):
            cells = row.get("cells") or []
            expected = {c_idx for c_idx, cell in enumerate(cells) if cell.get("is_correct")}
            actual = set(selected_cells[r_idx]) if r_idx < len(selected_cells) and isinstance(selected_cells[r_idx], list) else set()
            if expected != actual:
                return "incorrect"
        return "correct"

    # Default: MCQ
    options = question.options or []
    sel_idx = ans_in.get("selected_option_index")
    if sel_idx is None or not isinstance(sel_idx, int) or sel_idx < 0 or sel_idx >= len(options):
        return "incorrect"
    return "correct" if options[sel_idx].get("is_correct") else "incorrect"


async def _serialize_attempt(db: AsyncSession, attempt: PreSessionQuizAttempt, user_name: str | None = None) -> dict:
    if user_name is None:
        u = await db.get(User, attempt.user_id)
        user_name = (u.full_name or u.email) if u else "Instructor"
    return {
        "id": attempt.id,
        "session_id": attempt.session_id,
        "preset_id": attempt.preset_id,
        "user_id": attempt.user_id,
        "user_name": user_name,
        "answers": list(attempt.answers or []),
        "auto_score": attempt.auto_score,
        "final_score": attempt.final_score,
        "total_questions": attempt.total_questions,
        "pending_review_count": attempt.pending_review_count,
        "submitted_at": attempt.submitted_at,
    }


async def get_session_pre_quiz_status(
    db: AsyncSession, session_id: UUID, user: User
) -> dict:
    assign_info = await get_assignment_for_scope(db, "sessions", session_id)
    preset_id = assign_info.get("preset_id")
    if not preset_id:
        return {
            "has_quiz": False,
            "preset": None,
            "my_attempt": None,
            "all_attempts": [],
        }

    preset_hydrated = await get_preset_hydrated(db, preset_id)
    if not preset_hydrated or not preset_hydrated.get("questions"):
        return {
            "has_quiz": False,
            "preset": None,
            "my_attempt": None,
            "all_attempts": [],
        }

    my_attempt_row = (
        await db.execute(
            select(PreSessionQuizAttempt).where(
                PreSessionQuizAttempt.session_id == session_id,
                PreSessionQuizAttempt.user_id == user.id,
            )
        )
    ).scalars().first()

    my_attempt = await _serialize_attempt(db, my_attempt_row, user.full_name or user.email) if my_attempt_row else None

    is_ops = any(r in user.role_values for r in ("operations", "admin", "facilitator"))
    all_attempts = []
    if is_ops:
        rows = (
            await db.execute(
                select(PreSessionQuizAttempt)
                .where(PreSessionQuizAttempt.session_id == session_id)
                .order_by(PreSessionQuizAttempt.submitted_at.desc())
            )
        ).scalars().all()
        user_ids = [r.user_id for r in rows]
        user_names = {}
        if user_ids:
            u_rows = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
            user_names = {u.id: u.full_name or u.email for u in u_rows}
        for r in rows:
            all_attempts.append(await _serialize_attempt(db, r, user_names.get(r.user_id, "Instructor")))

    return {
        "has_quiz": True,
        "preset": preset_hydrated,
        "my_attempt": my_attempt,
        "all_attempts": all_attempts,
    }


async def submit_session_pre_quiz(
    db: AsyncSession, session_id: UUID, user: User, body: PreSessionQuizSubmitIn
) -> dict:
    assign_info = await get_assignment_for_scope(db, "sessions", session_id)
    preset_id = assign_info.get("preset_id")
    if not preset_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No pre-session quiz is assigned to this session")

    preset_hydrated = await get_preset_hydrated(db, preset_id)
    if not preset_hydrated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Quiz preset not found")

    questions: list[PreSessionQuizQuestion] = preset_hydrated["questions"]
    answers_by_qid = {str(a.question_id): a.model_dump() for a in body.answers}

    graded_answers = []
    auto_score = 0
    pending_count = 0

    for q in questions:
        qid_str = str(q.id)
        ans_in = answers_by_qid.get(qid_str, {})
        q_status = _grade_question(q, ans_in)
        if q_status == "correct":
            auto_score += 1
        elif q_status == "pending_review":
            pending_count += 1

        graded_answers.append({
            "question_id": qid_str,
            "selected_option_index": ans_in.get("selected_option_index"),
            "selected_cells": ans_in.get("selected_cells"),
            "chose_other": bool(ans_in.get("chose_other")),
            "other_text": (ans_in.get("other_text") or "").strip() or None,
            "status": q_status,
            "reviewed_by": None,
            "reviewed_at": None,
            "review_comment": None,
        })

    existing = (
        await db.execute(
            select(PreSessionQuizAttempt).where(
                PreSessionQuizAttempt.session_id == session_id,
                PreSessionQuizAttempt.user_id == user.id,
            )
        )
    ).scalars().first()

    now = datetime.now(timezone.utc)
    if existing:
        existing.preset_id = preset_id
        existing.answers = graded_answers
        existing.auto_score = auto_score
        existing.final_score = auto_score
        existing.total_questions = len(questions)
        existing.pending_review_count = pending_count
        existing.submitted_at = now
        attempt = existing
    else:
        attempt = PreSessionQuizAttempt(
            session_id=session_id,
            preset_id=preset_id,
            user_id=user.id,
            answers=graded_answers,
            auto_score=auto_score,
            final_score=auto_score,
            total_questions=len(questions),
            pending_review_count=pending_count,
            submitted_at=now,
        )
        db.add(attempt)

    await db.commit()
    await db.refresh(attempt)
    return await _serialize_attempt(db, attempt, user.full_name or user.email)


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
