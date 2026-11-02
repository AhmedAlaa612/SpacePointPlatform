"""Universal bulk question importer & template generator for the Question Bank.

Supports:
- Excel (.xlsx) workbooks (multi-sheet or single sheet)
- CSV files (.csv) with resilient encoding detection (utf-8, utf-8-sig, cp1252, latin-1)
- Multi-table / multi-section files with title banners (skips title banners and auto-detects header rows)
- Column aliases across all SpacePoint question formats:
  - 71-question Instructor Assessment Scenario format
  - 31-question SatKit Pre-Workshop Assessment format
  - SatKit Photo Inspection format (with image / figure references)
- Letter-based keys ("A", "B", "C", "D") and exact-text answer keys
- Safety/Critical scenario flags ("Yes"/"No", True/False)
- Custom points / weights (default: 1)
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Tuple

from pydantic import BaseModel, Field

OPTION_LETTERS = ["A", "B", "C", "D"]

# Standard column aliases (all lowercase stripped)
ALIAS_MAP = {
    "code": ["question id", "question_id", "id", "code", "q_id", "number", "#"],
    "topic": ["category / topic", "category", "topic", "section", "inspection", "subsystem"],
    "prompt": ["scenario / question", "question", "prompt", "scenario", "title"],
    "option_a": ["option a", "choice a", "option 1", "opt a", "a"],
    "option_b": ["option b", "choice b", "option 2", "opt b", "b"],
    "option_c": ["option c", "choice c", "option 3", "opt c", "c"],
    "option_d": ["option d", "choice d", "option 4", "opt d", "d"],
    "correct_letter": ["correct letter", "answer letter", "letter"],
    "correct_answer": ["correct answer", "answer", "correct", "key", "correct option"],
    "rationale": ["rationale / instructor standard", "rationale", "explanation", "standard", "notes"],
    "critical": ["critical scenario?", "critical?", "critical", "is_critical", "safety critical"],
    "points": ["points", "point", "score", "pts", "weight"],
    "image": ["photo", "image", "figure", "image_url", "image url", "figure_url"],
}


class ImportedQuestionItem(BaseModel):
    code: str | None = None
    topic: str = "General"
    question_type: str = "mcq"
    title: str
    prompt: str
    options: list[dict[str, Any]] = Field(default_factory=list)
    critical: bool = False
    points: int = 1
    explanation: str | None = None
    image_url: str | None = None
    raw_image_bytes: bytes | None = None
    raw_image_ext: str = "png"


def _normalize_header_str(val: Any) -> str:
    if val is None:
        return ""
    s = str(val).strip().lower()
    s = re.sub(r"[^a-z0-9/ ?#]", "", s)
    return " ".join(s.split())


def _find_header_mapping(row: list[Any]) -> dict[str, int] | None:
    """Attempts to match a row to recognized question bank column headers."""
    if not row or not any(row):
        return None
    # Header cells must be concise labels, not full question scenarios (> 60 chars)
    if any(len(str(c)) > 60 for c in row if c is not None):
        return None

    normalized = [_normalize_header_str(c) for c in row]
    if not any(normalized):
        return None

    mapping: dict[str, int] = {}
    for canonical, aliases in ALIAS_MAP.items():
        for idx, val in enumerate(normalized):
            if not val or len(val) > 40:
                continue
            for alias in aliases:
                norm_alias = _normalize_header_str(alias)
                # Exact match or prefix with space boundary (e.g. "option a (text)")
                # Single-letter or very short aliases (<= 3 chars) MUST match exactly
                if val == norm_alias or (len(norm_alias) > 3 and val.startswith(norm_alias + " ")):
                    mapping[canonical] = idx
                    break
            if canonical in mapping:
                break

    # A valid header must at least have prompt/question and at least 2 option columns
    # or prompt and correct answer
    has_prompt = "prompt" in mapping
    option_count = sum(1 for k in ["option_a", "option_b", "option_c", "option_d"] if k in mapping)
    if has_prompt and (option_count >= 2 or "correct_answer" in mapping or "correct_letter" in mapping):
        return mapping

    return None


def _parse_raw_rows(
    raw_rows: list[list[Any]],
    topic_override: str | None = None,
    row_images: dict[int, tuple[bytes, str]] | None = None,
    code_images_cache: dict[str, tuple[bytes, str]] | None = None,
) -> Tuple[list[ImportedQuestionItem], list[str]]:
    questions: list[ImportedQuestionItem] = []
    errors: list[str] = []

    current_mapping: dict[str, int] | None = None
    row_imgs = row_images or {}
    code_imgs = code_images_cache if code_images_cache is not None else {}

    for row_idx, row in enumerate(raw_rows, start=1):
        if not row or not any(str(c).strip() for c in row if c is not None):
            continue

        # Check if this row is a new header
        new_map = _find_header_mapping(row)
        if new_map:
            current_mapping = new_map
            continue

        if not current_mapping:
            # We haven't found a header row yet (e.g. title banners or preamble)
            continue

        def get_cell(key: str) -> str:
            idx = current_mapping.get(key)
            if idx is not None and idx < len(row):
                val = row[idx]
                if val is not None:
                    return str(val).strip()
            return ""

        prompt = get_cell("prompt")
        if not prompt:
            continue

        code = get_cell("code") or None
        raw_topic = get_cell("topic")
        topic = (topic_override or raw_topic or "General").strip()

        # Build options
        opts_raw = [
            get_cell("option_a"),
            get_cell("option_b"),
            get_cell("option_c"),
            get_cell("option_d"),
        ]

        # Filter out trailing empties if only A/B/C present
        while opts_raw and not opts_raw[-1]:
            opts_raw.pop()

        if len(opts_raw) < 2:
            errors.append(f"Row {row_idx}: Question requires at least 2 options ('{prompt[:40]}...')")
            continue

        # Determine correct option
        correct_letter = get_cell("correct_letter").upper()
        correct_answer_str = get_cell("correct_answer")

        correct_idx = -1
        # 1. Try letter matching (A=0, B=1, C=2, D=3)
        candidate_letter = correct_letter or (correct_answer_str.upper() if len(correct_answer_str) == 1 else "")
        if candidate_letter in OPTION_LETTERS:
            letter_idx = OPTION_LETTERS.index(candidate_letter)
            if letter_idx < len(opts_raw):
                correct_idx = letter_idx

        # 2. Try exact / stripped text matching
        if correct_idx == -1 and correct_answer_str:
            norm_target = correct_answer_str.strip().lower()
            for idx, opt_text in enumerate(opts_raw):
                if opt_text.strip().lower() == norm_target:
                    correct_idx = idx
                    break

        # 3. Try letter prefix inside answer string like "B – Explanation..."
        if correct_idx == -1 and correct_answer_str:
            match = re.match(r"^([A-D])[\s\.\:\-\)]", correct_answer_str.strip(), re.IGNORECASE)
            if match:
                letter = match.group(1).upper()
                letter_idx = OPTION_LETTERS.index(letter)
                if letter_idx < len(opts_raw):
                    correct_idx = letter_idx

        if correct_idx == -1:
            errors.append(f"Row {row_idx}: Could not match correct answer '{correct_letter or correct_answer_str}' to options for '{prompt[:40]}...'")
            continue

        options = [
            {"text": opt_text, "is_correct": (i == correct_idx)}
            for i, opt_text in enumerate(opts_raw)
        ]

        # Parse Critical flag
        raw_crit = get_cell("critical").lower()
        critical = raw_crit in ("yes", "y", "true", "1")

        # Parse Points
        raw_points = get_cell("points")
        try:
            points = int(float(raw_points)) if raw_points else 1
        except (ValueError, TypeError):
            points = 1

        explanation = get_cell("rationale") or None
        image_url = get_cell("image") or None
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://") or image_url.startswith("/")):
            # Non-URL filename or label (e.g. "Figure_01.jpg") — don't treat as a broken HTTP URL
            image_url = None

        raw_image_bytes = None
        raw_image_ext = "png"
        if row_idx in row_imgs:
            raw_image_bytes, raw_image_ext = row_imgs[row_idx]
        elif code and code.strip().upper() in code_imgs:
            raw_image_bytes, raw_image_ext = code_imgs[code.strip().upper()]

        if code and raw_image_bytes:
            code_imgs[code.strip().upper()] = (raw_image_bytes, raw_image_ext)

        title = f"[{code}] {prompt[:50]}..." if code else f"{prompt[:60]}..."

        questions.append(
            ImportedQuestionItem(
                code=code,
                topic=topic,
                question_type="mcq",
                title=title,
                prompt=prompt,
                options=options,
                critical=critical,
                points=max(1, points),
                explanation=explanation,
                image_url=image_url,
                raw_image_bytes=raw_image_bytes,
                raw_image_ext=raw_image_ext,
            )
        )

    return questions, errors


def parse_question_import_bytes(
    file_bytes: bytes,
    filename: str,
    topic_override: str | None = None,
) -> Tuple[list[ImportedQuestionItem], list[str]]:
    """Universal parser for .xlsx and .csv files with embedded drawing support."""
    is_csv = filename.lower().endswith(".csv")

    if is_csv:
        # Try decoding with resilient fallbacks
        decoded = None
        for enc in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
            try:
                decoded = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if decoded is None:
            return [], ["Unable to decode CSV file: unsupported character encoding."]

        reader = csv.reader(io.StringIO(decoded))
        raw_rows = [row for row in reader]
        return _parse_raw_rows(raw_rows, topic_override)

    # Otherwise assume openpyxl / Excel
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as e:
        return [], [f"Cannot open Excel file: {e}"]

    # Pass 1: Extract embedded images across all worksheets and build code lookup
    code_images_cache: dict[str, tuple[bytes, str]] = {}
    sheet_row_images: dict[str, dict[int, tuple[bytes, str]]] = {}

    for sheetname in wb.sheetnames:
        ws = wb[sheetname]
        row_map: dict[int, tuple[bytes, str]] = {}
        for img in getattr(ws, "_images", []):
            try:
                anchor = getattr(img, "anchor", None)
                if hasattr(anchor, "_from"):
                    r = anchor._from.row + 1
                elif hasattr(anchor, "row"):
                    r = anchor.row + 1
                else:
                    continue
                img_data = img._data()
                fmt = getattr(img, "format", "png").lower()
                if fmt == "jpeg":
                    fmt = "jpg"
                row_map[r] = (img_data, fmt)

                code_val = ws.cell(r, 1).value or ws.cell(r, 2).value
                if code_val and str(code_val).strip():
                    code_images_cache[str(code_val).strip().upper()] = (img_data, fmt)
            except Exception:
                continue
        sheet_row_images[sheetname] = row_map

    all_questions: list[ImportedQuestionItem] = []
    all_errors: list[str] = []

    for sheetname in wb.sheetnames:
        ws = wb[sheetname]
        raw_rows = list(ws.iter_rows(values_only=True))
        qs, errs = _parse_raw_rows(
            raw_rows,
            topic_override=topic_override,
            row_images=sheet_row_images.get(sheetname),
            code_images_cache=code_images_cache,
        )
        all_questions.extend(qs)
        for err in errs:
            all_errors.append(f"[{sheetname}] {err}")

    # Pass 2: Deduplicate identical questions across sheets (e.g. summary sheet vs section sheet)
    # Merges images and rationale if present on one copy
    deduped: list[ImportedQuestionItem] = []
    seen: dict[str, int] = {}

    for q in all_questions:
        key = q.code.strip().upper() if q.code else q.prompt.strip().lower()
        if key in seen:
            idx = seen[key]
            existing = deduped[idx]
            if q.raw_image_bytes and not existing.raw_image_bytes:
                existing.raw_image_bytes = q.raw_image_bytes
                existing.raw_image_ext = q.raw_image_ext
            if q.image_url and not existing.image_url:
                existing.image_url = q.image_url
            if q.explanation and not existing.explanation:
                existing.explanation = q.explanation
            continue
        seen[key] = len(deduped)
        deduped.append(q)

    return deduped, all_errors


def generate_question_template_xlsx() -> bytes:
    """Generates an official SpacePoint Question Bank Excel template."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # Sheet 1: Questions Template
    ws = wb.active
    ws.title = "Question Bank Template"

    headers = [
        "Question ID",
        "Category / Topic",
        "Scenario / Question",
        "Option A",
        "Option B",
        "Option C",
        "Option D",
        "Correct Answer",
        "Rationale / Instructor Standard",
        "Critical Scenario?",
        "Points",
        "Photo / Figure Reference",
    ]

    header_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # Sample rows demonstrating:
    # 1. Critical Scenario Question
    # 2. Hardware / SatKit Inspection Question with photo
    # 3. Practical Troubleshooting Scenario
    sample_rows = [
        [
            "S01",
            "Safety & PPE",
            "Students are excited to begin integration, but several have not put on the required PPE. What should you do?",
            "PPE is optional while leaving any follow-up discussion until the end of the session.",
            "Allow them to start and remind them later.",
            "Only ask once and then ignore it.",
            "Pause practical work until the required PPE is worn correctly.",
            "D",
            "Safety requirements take priority over schedule or excitement.",
            "Yes",
            1,
            "",
        ],
        [
            "B01",
            "SatKit Inspection",
            "Which sequence of standoff heights is specified from the bottom according to the SatKit inspection reference?",
            "10, 20, 10, 20",
            "10, 10, 9, 20, 10, 20, 10",
            "20, 20, 10, 10, 9, 9",
            "All standoffs must be equal",
            "B",
            "Standoff height sequence follows the mechanical integration guide starting at the base.",
            "No",
            1,
            "Figure_01.jpg",
        ],
        [
            "C01",
            "Practical Troubleshooting",
            "A completed SatKit does not power on. What should the instructor check first?",
            "Replace the ESP32 without testing",
            "Change the code immediately",
            "Disconnect every sensor and guess the cause",
            "Inspect power connections, polarity and the power supply before further troubleshooting",
            "D",
            "Follow structured systematic diagnosis: inspect polarity and power supplies first.",
            "Yes",
            1,
            "",
        ],
    ]

    for row_data in sample_rows:
        ws.append(row_data)

    for row in ws.iter_rows(min_row=2, max_row=len(sample_rows) + 1):
        for cell in row:
            cell.border = thin_border
            cell.alignment = Alignment(vertical="center", wrap_text=True)

    # Column widths
    col_widths = {
        1: 14,   # ID
        2: 24,   # Topic
        3: 45,   # Prompt
        4: 30,   # A
        5: 30,   # B
        6: 30,   # C
        7: 30,   # D
        8: 16,   # Answer
        9: 40,   # Rationale
        10: 18,  # Critical
        11: 10,  # Points
        12: 25,  # Photo
    }
    for col_idx, width in col_widths.items():
        ws.column_dimensions[get_column_letter(col_idx)].width = width

    # Sheet 2: Field Instructions
    ws_info = wb.create_sheet(title="Column Guide")
    info_rows = [
        ["Column Name", "Required", "Accepted Values", "Description"],
        ["Question ID", "Optional", "Text (e.g. A01, B01, 1)", "Question code or identifier for sorting and reference."],
        ["Category / Topic", "Required", "Text", "Topic name (e.g. Safety & PPE, SatKit Inspection, Facilitation)."],
        ["Scenario / Question", "Required", "Text", "The scenario prompt or technical question text."],
        ["Option A - D", "Required", "Text", "Multiple choice answer options."],
        ["Correct Answer", "Required", "A, B, C, D or exact text", "Specifies the correct option (letter or full matching text)."],
        ["Rationale / Instructor Standard", "Optional", "Text", "Explanation shown in test debriefs and review mode."],
        ["Critical Scenario?", "Optional", "Yes / No (default No)", "Flag for safety-critical questions with minimum pass floors."],
        ["Points", "Optional", "Number (default 1)", "Scoring weight per question."],
        ["Photo / Figure Reference", "Optional", "Filename or URL", "Hardware image reference (e.g. Figure_01.jpg or image URL)."],
    ]

    for row in info_rows:
        ws_info.append(row)

    for col_idx in range(1, 5):
        cell = ws_info.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        ws_info.column_dimensions[get_column_letter(col_idx)].width = 28

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
