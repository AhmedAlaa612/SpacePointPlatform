"""Bulk-add live-quiz questions from a filled-in Excel template.

Mirrors `services/documents/payment_letter.py`'s parse/generate pair (same
openpyxl usage, same "collect per-row errors and keep going" posture) — this
just targets `GameQuestionIn` instead of payment-letter rows. A bad row is
skipped and reported, not fatal: the good rows in the same file still get
created, since one typo shouldn't cost a facilitator the rest of the sheet.
"""

from __future__ import annotations

import io

from pydantic import ValidationError

from app.schemas.games_admin import GameQuestionIn, GameQuestionOptionIn

OPTION_LETTERS = "ABCD"
TEMPLATE_HEADERS = [
    "Prompt", "Option A", "Option B", "Option C", "Option D",
    "Correct Option (A-D)", "Time Limit (seconds)", "Points Mode (normal/double)",
]


def parse_game_question_import(file_bytes: bytes) -> tuple[list[GameQuestionIn], list[str]]:
    """One row per question. Option A/B are required, C/D optional. Time
    limit blank = the game's own default; points mode blank = 'normal'."""
    import openpyxl

    questions: list[GameQuestionIn] = []
    errors: list[str] = []
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as e:
        errors.append(f"Cannot open file: {e}")
        return questions, errors

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        errors.append("The sheet is empty.")
        return questions, errors

    headers = [str(h).strip().lower() if h else "" for h in rows[0]]

    def col(name: str) -> int | None:
        try:
            return headers.index(name.lower())
        except ValueError:
            return None

    prompt_col = col("Prompt")
    option_cols = [col(f"Option {letter}") for letter in OPTION_LETTERS]
    correct_col = col("Correct Option (A-D)")
    time_limit_col = col("Time Limit (seconds)")
    points_mode_col = col("Points Mode (normal/double)")

    if prompt_col is None or correct_col is None or option_cols[0] is None or option_cols[1] is None:
        errors.append("Sheet is missing required columns: Prompt, Option A, Option B, Correct Option (A-D).")
        return questions, errors

    def cell(row: tuple, idx: int | None):
        return row[idx] if idx is not None and idx < len(row) else None

    for row_idx, row in enumerate(rows[1:], start=2):
        prompt_raw = cell(row, prompt_col)
        prompt = str(prompt_raw).strip() if prompt_raw is not None else ""
        if not prompt:
            continue  # blank row — skip silently, same as a blank email in the payments importer

        filled = []
        for letter, idx in zip(OPTION_LETTERS, option_cols):
            val = cell(row, idx)
            text = str(val).strip() if val is not None else ""
            if text:
                filled.append((letter, text))
        if len(filled) < 2:
            errors.append(f"Row {row_idx}: needs at least two options filled in")
            continue

        correct_raw = cell(row, correct_col)
        correct_letter = str(correct_raw).strip().upper() if correct_raw is not None else ""
        filled_letters = {letter for letter, _ in filled}
        if correct_letter not in filled_letters:
            errors.append(f"Row {row_idx}: Correct Option must be one of {', '.join(sorted(filled_letters))}")
            continue

        time_limit = None
        time_limit_raw = cell(row, time_limit_col)
        if time_limit_raw not in (None, ""):
            try:
                time_limit = int(time_limit_raw)
            except (TypeError, ValueError):
                errors.append(f"Row {row_idx}: Time limit must be a whole number of seconds")
                continue

        points_mode_raw = cell(row, points_mode_col)
        points_mode = str(points_mode_raw).strip().lower() if points_mode_raw not in (None, "") else "normal"
        if points_mode not in ("normal", "double"):
            errors.append(f"Row {row_idx}: Points Mode must be 'normal' or 'double', got '{points_mode_raw}'")
            continue

        try:
            questions.append(GameQuestionIn(
                prompt=prompt,
                options=[GameQuestionOptionIn(text=text, is_correct=letter == correct_letter) for letter, text in filled],
                time_limit_seconds=time_limit,
                points_mode=points_mode,
            ))
        except ValidationError as e:
            errors.append(f"Row {row_idx}: {e.errors()[0]['msg']}")

    return questions, errors


def generate_game_question_template_xlsx() -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter  # not cell.column_letter — see instructors/HANDOFF.md known bugs

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Questions"
    for col_idx, header in enumerate(TEMPLATE_HEADERS, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="653f84")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(col_idx)].width = 22
    example = [
        "Which burn raises apoapsis?", "Prograde burn at periapsis", "Retrograde burn at periapsis",
        "Radial burn", "Normal burn", "A", 20, "normal",
    ]
    for col_idx, val in enumerate(example, 1):
        ws.cell(row=2, column=col_idx, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
