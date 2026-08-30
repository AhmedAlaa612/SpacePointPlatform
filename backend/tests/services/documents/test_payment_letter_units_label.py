"""What prints in the payment letter's shared "Sessions / Duration" column
(2026-08-30 — flipped to prefer the hours ops actually enters in the
editable table over the old "count x rate" breakdown, which used to win
whenever a line had both a session count and a rate, making the hours
field silently ignored on the printed document)."""

from app.services.documents.payment_letter import _units_label


def test_duration_hours_wins_when_set():
    assert _units_label({"duration_hours": 20.0, "session_count": 4, "rate_aed": 500}) == "20.0 hrs"


def test_falls_back_to_count_times_rate_when_no_hours_set():
    assert _units_label({"duration_hours": None, "session_count": 4, "rate_aed": 500}) == "4 x 500"


def test_falls_back_to_session_count_when_no_hours_or_rate():
    assert _units_label({"duration_hours": None, "session_count": 3, "rate_aed": None}) == "3 sessions"


def test_blank_when_nothing_is_set():
    assert _units_label({"duration_hours": None, "session_count": None, "rate_aed": None}) == ""


def test_a_single_session_with_no_rate_and_no_hours_is_blank_not_1_sessions():
    assert _units_label({"duration_hours": None, "session_count": 1, "rate_aed": None}) == ""
