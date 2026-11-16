"""Cohort quiz answers export (.xlsx) — mirrors the styling conventions of
services/lms/submissions_export.py (2026-11).

Two sheet kinds per workbook:
- One "matrix" sheet per quiz: one row per student, one column per question
  (in the template's authored order) — picked option text for MCQs, the
  written answer for open-ended, "(timed out)"/"(blank)" when nothing was
  picked, plus score columns.
- A trailing "Answer Details" sheet: one row per individual answer with
  correctness, timing and timestamps, for sorting/pivoting.
"""

from __future__ import annotations

import io
import uuid

import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.cohort_quiz import (
    CohortQuizAnswer,
    CohortQuizAttempt,
    CohortQuizQuestion,
    CohortQuizTemplateQuestion,
)
from app.models.lms.program import LmsProgramAssignment, LmsProgramItem
from app.models.user import User
from app.services.lms.submissions_export import (  # shared openpyxl styling helpers
    _autosize_and_linkify,
    _style_header,
    _unique_sheet_title,
)

MATRIX_PROMPT_CHARS = 60


def _fmt_dt(dt) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def _picked_option_texts(selected_index, selected_indices, options_json) -> str:
    """Human-readable text of the option(s) the student picked, if any."""
    idxs: list[int] = []
    if selected_index is not None:
        idxs = [selected_index]
    elif selected_indices:
        idxs = [i for i in selected_indices if isinstance(i, int)]
    texts: list[str] = []
    for i in idxs:
        opt = options_json[i] if (isinstance(options_json, list) and 0 <= i < len(options_json)) else None
        if isinstance(opt, dict) and opt.get("text"):
            texts.append(str(opt["text"]))
        else:
            texts.append(f"Option {i + 1}")
    return " + ".join(texts)


def _answer_cell(answer: CohortQuizAnswer, options_json) -> str:
    """The matrix cell for one answer: written text wins, then picked
    option(s), then the timeout/blank markers."""
    text = (answer.text_answer or "").strip()
    if text:
        return text
    picked = _picked_option_texts(answer.selected_option_index, answer.selected_option_indices, options_json)
    if picked:
        return picked
    if answer.timed_out:
        return "(timed out)"
    return "(blank)"


async def export_cohort_quiz_answers_workbook(
    db: AsyncSession, *, cohort_id: uuid.UUID, mode: str = "student",
) -> bytes:
    """Builds the .xlsx bytes for every submitted cohort-quiz answer in a cohort."""
    observer_ids = list((await db.execute(
        select(LmsProgramAssignment.user_id).where(
            LmsProgramAssignment.cohort_id == cohort_id,
            LmsProgramAssignment.mode == "observer",
        )
    )).scalars().all())

    effective_mode = mode or "student"

    attempts_stmt = (
        select(CohortQuizAttempt, LmsProgramItem.title.label("quiz_title"), User)
        .join(User, CohortQuizAttempt.user_id == User.id)
        .outerjoin(LmsProgramItem, CohortQuizAttempt.program_item_id == LmsProgramItem.id)
        .where(CohortQuizAttempt.cohort_id == cohort_id, CohortQuizAttempt.status == "submitted")
    )
    # Same observer partitioning as get_cohort_quiz_analysis: 'student'
    # excludes observers so staff test runs never pollute the export.
    attempts_stmt_final = None
    if effective_mode == "observer":
        if observer_ids:
            attempts_stmt_final = attempts_stmt.where(CohortQuizAttempt.user_id.in_(observer_ids))
    elif effective_mode != "all" and observer_ids:
        attempts_stmt_final = attempts_stmt.where(CohortQuizAttempt.user_id.not_in(observer_ids))

    wb = openpyxl.Workbook()
    used_titles: set[str] = set()

    attempt_rows: list = []
    if attempts_stmt_final is not None:
        attempt_rows = list((await db.execute(
            attempts_stmt_final.order_by(LmsProgramItem.title, User.full_name)
        )).all())

    if not attempt_rows:
        sheet = wb.active
        sheet.title = "Quiz Answers"
        sheet.append(["Notice", "No quiz submissions found for this cohort/mode."])
        _style_header(sheet)
        _autosize_and_linkify(sheet)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    attempt_ids = [a.id for a, _, _ in attempt_rows]

    # All answers for these attempts, with the question's own shape when the
    # question row still exists (retired questions keep their answers).
    answer_rows = list((await db.execute(
        select(CohortQuizAnswer, CohortQuizQuestion.prompt, CohortQuizQuestion.question_type, CohortQuizQuestion.options)
        .outerjoin(CohortQuizQuestion, CohortQuizAnswer.question_id == CohortQuizQuestion.id)
        .where(CohortQuizAnswer.attempt_id.in_(attempt_ids))
        .order_by(CohortQuizAnswer.answered_at)
    )).all())
    answers_by_attempt: dict[uuid.UUID, list[tuple]] = {}
    for ans, prompt, qtype, options_json in answer_rows:
        answers_by_attempt.setdefault(ans.attempt_id, []).append((ans, prompt, qtype, options_json))

    # Authored question order per template — the same order every student in
    # the cohort saw (attempts freeze question_order at start; the template
    # order is the closest stable approximation for the export's columns).
    template_ids = {a.cohort_quiz_template_id for a, _, _ in attempt_rows if a.cohort_quiz_template_id}
    tq_rows = list((await db.execute(
        select(
            CohortQuizTemplateQuestion.template_id,
            CohortQuizTemplateQuestion.question_id,
            CohortQuizTemplateQuestion.position,
        )
        .where(CohortQuizTemplateQuestion.template_id.in_(template_ids))
        .order_by(CohortQuizTemplateQuestion.template_id, CohortQuizTemplateQuestion.position)
    )).all()) if template_ids else []
    question_order_by_template: dict[uuid.UUID, list[uuid.UUID]] = {}
    for tid, qid, _pos in tq_rows:
        if qid is not None:
            question_order_by_template.setdefault(tid, []).append(qid)

    # Group attempts per quiz (program item), preserving the sorted order.
    quizzes: dict[uuid.UUID, dict] = {}
    for attempt, quiz_title, user in attempt_rows:
        entry = quizzes.setdefault(
            attempt.program_item_id,
            {"quiz_title": quiz_title or "Cohort Knowledge Quiz", "attempts": []},
        )
        entry["attempts"].append((attempt, user))

    first_matrix = True
    for quiz in quizzes.values():
        # Column order: template questions first, then any stragglers in
        # first-seen answer order.
        ordered_qids: list[uuid.UUID] = []
        first_template = next(
            (a.cohort_quiz_template_id for a, _ in quiz["attempts"] if a.cohort_quiz_template_id), None,
        )
        if first_template is not None:
            ordered_qids.extend(question_order_by_template.get(first_template, []))
        for attempt, _user in quiz["attempts"]:
            for ans, _prompt, _qtype, _options in answers_by_attempt.get(attempt.id, []):
                if ans.question_id and ans.question_id not in ordered_qids:
                    ordered_qids.append(ans.question_id)

        # question metadata (prompt/options) per question id, from any answer
        qmeta: dict[uuid.UUID, tuple] = {}
        for attempt, _user in quiz["attempts"]:
            for ans, prompt, qtype, options_json in answers_by_attempt.get(attempt.id, []):
                if ans.question_id and ans.question_id not in qmeta:
                    qmeta[ans.question_id] = (prompt, qtype, options_json)

        matrix_title = _unique_sheet_title(quiz["quiz_title"], used_titles)
        if first_matrix:
            matrix_sheet = wb.active
            matrix_sheet.title = matrix_title
            first_matrix = False
        else:
            matrix_sheet = wb.create_sheet(matrix_title)

        q_headers = []
        for i, qid in enumerate(ordered_qids, start=1):
            prompt = (qmeta.get(qid, (None, None, None))[0] or "Question")
            if len(prompt) > MATRIX_PROMPT_CHARS:
                prompt = prompt[: MATRIX_PROMPT_CHARS - 3].rstrip() + "..."
            q_headers.append(f"Q{i}: {prompt}")
        matrix_sheet.append(["Student Name", "Email", *q_headers, "Score", "Total", "%", "Submitted At"])

        for attempt, user in quiz["attempts"]:
            by_qid: dict[uuid.UUID, tuple] = {}
            for ans, prompt, qtype, options_json in answers_by_attempt.get(attempt.id, []):
                if ans.question_id:
                    by_qid[ans.question_id] = (ans, options_json)
            cells = [_answer_cell(by_qid[qid][0], by_qid[qid][1]) if qid in by_qid else "(no record)"
                     for qid in ordered_qids]
            score_val = attempt.score if attempt.score is not None else 0
            total_val = attempt.total or 0
            pct_val = f"{round(100 * int(score_val) / int(total_val))}%" if total_val else "0%"
            matrix_sheet.append([
                user.full_name or "",
                user.email or "",
                *cells,
                score_val,
                total_val,
                pct_val,
                _fmt_dt(attempt.submitted_at),
            ])

        _style_header(matrix_sheet)
        _autosize_and_linkify(matrix_sheet)

    # Trailing long-format sheet: one row per answer, grouped by attempt in
    # the same (quiz → student) order as the matrix sheets.
    detail_sheet = wb.create_sheet("Answer Details")
    detail_sheet.append([
        "Quiz", "Question", "Type", "Topic", "Student", "Email",
        "Selected Option(s)", "Text Answer", "Correct", "Timed Out",
        "Time (s)", "Answered At",
    ])
    for attempt, quiz_title, user in attempt_rows:
        qorder = {qid: i for i, qid in enumerate(
            question_order_by_template.get(attempt.cohort_quiz_template_id, []), start=1,
        )}
        for ans, prompt, qtype, options_json in answers_by_attempt.get(attempt.id, []):
            pos = qorder.get(ans.question_id) if ans.question_id else None
            detail_sheet.append([
                quiz_title or "Cohort Knowledge Quiz",
                f"Q{pos}" if pos else "Q?",
                prompt or "(question unavailable)",
                qtype or "mcq",
                ans.topic,
                user.full_name or "",
                user.email or "",
                _picked_option_texts(ans.selected_option_index, ans.selected_option_indices, options_json),
                (ans.text_answer or "").strip(),
                ("yes" if ans.is_correct else "no") if ans.is_correct is not None else "",
                "yes" if ans.timed_out else "no",
                ans.time_taken_seconds if ans.time_taken_seconds is not None else "",
                _fmt_dt(ans.answered_at),
            ])
    _style_header(detail_sheet)
    _autosize_and_linkify(detail_sheet)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
