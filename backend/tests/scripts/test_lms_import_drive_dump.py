"""lms_import_drive_dump — title/number/option parsing and the Excel grouping
logic, the pure pieces worth pinning. No network/API calls here (that's
`LmsAdminClient`, a thin requests wrapper not worth re-testing).
"""

import openpyxl
import pytest

from scripts.lms_import_drive_dump import _clean_title, _leading_number, _load_questions_by_video, _option_text


@pytest.mark.parametrize("name,expected", [
    ("1- Introduction", "Introduction"),
    ("2- CDHS", "CDHS"),
    ("2.1 - CDHS Continued", "CDHS Continued"),
    ("3- Types of satellites.mp4", "Types of satellites"),
    ("4- Orbits.mp4", "Orbits"),
    ("No Leading Number.mp4", "No Leading Number"),
    # Real Drive filenames redundantly repeat the leading number at the end
    # too — strip that duplicate, not just the leading one.
    ("1- Intro-1.mp4", "Intro"),
    ("2- What is a satellite-2.mp4", "What is a satellite"),
])
def test_clean_title_strips_leading_number_and_extension(name, expected):
    assert _clean_title(name) == expected


def test_clean_title_keeps_a_trailing_number_that_doesnt_match_the_leading_one():
    """A title can genuinely end in a number (e.g. a historical reference) —
    only strip the trailing one when it's literally the same sequence
    number just stripped from the front."""
    assert _clean_title("5- Sputnik 1.mp4") == "Sputnik 1"
    assert _clean_title("5- Apollo 11.mp4") == "Apollo 11"


@pytest.mark.parametrize("name,expected", [
    ("1- Intro-1.mp4", 1.0),
    ("2.1 - CDHS Continued", 2.1),
    ("9- Challenges and Future.mp4", 9.0),
    ("No Leading Number.mp4", 0.0),
])
def test_leading_number_extracts_sort_key(name, expected):
    assert _leading_number(name) == expected


def test_option_text_casts_integer_floats_cleanly():
    assert _option_text(1957.0) == "1957"
    assert _option_text("The Soviet Union") == "The Soviet Union"
    assert _option_text(3.5) == "3.5"


def _make_xlsx(tmp_path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Video Name", "Video Description", "Question Text", "Option A", "Option B", "Option C", "Option D", "Correct Answer"])
    for row in rows:
        ws.append(row)
    path = tmp_path / "Content and Questions.xlsx"
    wb.save(path)
    return path


def test_load_questions_groups_by_video_and_marks_correct_option(tmp_path):
    xlsx = _make_xlsx(tmp_path, [
        ("1- Intro-1.mp4", "desc", "Who built Sputnik?", "NASA", "The Soviet Union", "China", "Japan", "B"),
        ("1- Intro-1.mp4", "desc", "When was Sputnik launched?", 1947.0, 1957.0, 1969.0, 1981.0, "B"),
        ("2- What is a satellite-2.mp4", "desc", "What is a satellite?", "A star", "An orbiting object", "A rocket", "An atmosphere", "B"),
    ])

    by_video, warnings = _load_questions_by_video(xlsx)

    assert set(by_video.keys()) == {"1- Intro-1.mp4", "2- What is a satellite-2.mp4"}
    assert len(by_video["1- Intro-1.mp4"]) == 2
    assert warnings == []

    first = by_video["1- Intro-1.mp4"][0]
    assert first["prompt"] == "Who built Sputnik?"
    assert first["options"] == [
        {"text": "NASA", "is_correct": False},
        {"text": "The Soviet Union", "is_correct": True},
        {"text": "China", "is_correct": False},
        {"text": "Japan", "is_correct": False},
    ]

    year_question = by_video["1- Intro-1.mp4"][1]
    assert [o["text"] for o in year_question["options"]] == ["1947", "1957", "1969", "1981"]
    assert year_question["options"][1]["is_correct"] is True


@pytest.mark.parametrize("bad_correct", [None, "", "a)", "1", "Option A", "The Soviet Union", "E", "BB"])
def test_load_questions_flags_unparseable_answer_cell(tmp_path, bad_correct):
    """B3 — a Correct Answer cell that isn't a bare A/B/C/D used to produce a
    question with zero correct options and no warning anywhere. Every option
    must come back is_correct=False, and the row must be reported."""
    xlsx = _make_xlsx(tmp_path, [
        ("1- Intro-1.mp4", "desc", "Who built Sputnik?", "NASA", "The Soviet Union", "China", "Japan", bad_correct),
    ])

    by_video, warnings = _load_questions_by_video(xlsx)

    question = by_video["1- Intro-1.mp4"][0]
    assert all(o["is_correct"] is False for o in question["options"])
    assert len(warnings) == 1
    assert "Who built Sputnik?" in warnings[0]
