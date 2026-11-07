"""Default certificate body expansion (operator wording request 2026-11):

The default certificates issued by competitions and workshops read:

    For successfully completing <program>
    Held on <start>                      # start date only
    Held from <start> to <end>           # both dates
    ... at <venue>                       # only when a location resolves

with the date/venue line dropped entirely when there is nothing to say.
Pure functions, no DB/Redis/HTTP.
"""

from datetime import date

from app.services.documents.certificate import (
    STUDENT_COMPLETION_FALLBACK_BODY,
    expand_certificate_body_template, format_certificate_when_phrase,
)


def test_start_date_only_says_held_on():
    assert format_certificate_when_phrase(starts_on=date(2026, 2, 10)) == "Held on Feb 10, 2026"


def test_start_and_end_dates_say_held_from():
    assert format_certificate_when_phrase(
        starts_on=date(2026, 2, 10), ends_on=date(2026, 2, 12),
    ) == "Held from Feb 10, 2026 to Feb 12, 2026"


def test_location_is_appended_with_at_when_dates_exist():
    assert format_certificate_when_phrase(
        starts_on=date(2026, 2, 10), location="Marsam Hall",
    ) == "Held on Feb 10, 2026 at Marsam Hall"
    assert format_certificate_when_phrase(
        starts_on=date(2026, 2, 10), ends_on=date(2026, 2, 12), location="Marsam Hall",
    ) == "Held from Feb 10, 2026 to Feb 12, 2026 at Marsam Hall"


def test_no_dates_but_a_venue_reads_held_at_the_venue():
    assert format_certificate_when_phrase(location="Marsam Hall") == "Held at Marsam Hall"


def test_neither_dates_nor_venue_is_an_empty_line():
    assert format_certificate_when_phrase() == ""
    assert format_certificate_when_phrase(location=None, starts_on=None) == ""


def test_same_day_start_and_end_count_as_start_only():
    assert format_certificate_when_phrase(
        starts_on=date(2026, 2, 10), ends_on=date(2026, 2, 10),
    ) == "Held on Feb 10, 2026"


def test_stored_date_range_rebuilds_the_from_to_wording():
    phrase = format_certificate_when_phrase(
        stored_dates="Feb 10, 2026 \u2013 Feb 12, 2026", location="Marsam Hall",
    )
    assert phrase == "Held from Feb 10, 2026 to Feb 12, 2026 at Marsam Hall"


def test_stored_single_date_rebuilds_the_held_on_wording():
    assert format_certificate_when_phrase(stored_dates="Feb 10, 2026") == "Held on Feb 10, 2026"


def test_default_completion_body_drops_the_line_when_there_is_nothing_to_say():
    body = expand_certificate_body_template(
        STUDENT_COMPLETION_FALLBACK_BODY,
        program_name="SpaceStation Design Challenge",
        starts_on=None, ends_on=None, location=None,
    )
    assert body == "For successfully completing<br/><b>SpaceStation Design Challenge</b>"


def test_default_completion_body_range_with_location():
    body = expand_certificate_body_template(
        STUDENT_COMPLETION_FALLBACK_BODY,
        program_name="SpaceStation Design Challenge",
        starts_on=date(2026, 2, 10), ends_on=date(2026, 2, 12), location="Marsam Hall",
    )
    assert body == (
        "For successfully completing<br/><b>SpaceStation Design Challenge</b>"
        "<br/>Held from Feb 10, 2026 to Feb 12, 2026 at Marsam Hall"
    )


def test_default_completion_body_start_only_without_location():
    body = expand_certificate_body_template(
        STUDENT_COMPLETION_FALLBACK_BODY,
        program_name="SpaceStation Design Challenge",
        starts_on=date(2026, 2, 10), location=None,
    )
    assert body == (
        "For successfully completing<br/><b>SpaceStation Design Challenge</b>"
        "<br/>Held on Feb 10, 2026"
    )


def test_program_name_is_html_escaped():
    body = expand_certificate_body_template(
        STUDENT_COMPLETION_FALLBACK_BODY,
        program_name='Nano <Sat"x>',
        starts_on=date(2026, 2, 10),
    )
    assert "Nano &lt;Sat&quot;x&gt;" in body


def test_when_line_override_and_certificate_type_tokens():
    body = expand_certificate_body_template(
        "For active participation in<br/>{program_name}<br/>{dates_line}<br/>{type}",
        program_name="Rocketry Basics",
        when_line="Held on Oct 3, 2026 at Muscat",
        certificate_type_label="Participation",
    )
    assert body == (
        "For active participation in<br/>Rocketry Basics"
        "<br/>Held on Oct 3, 2026 at Muscat<br/>Participation"
    )


def test_whitespace_only_spacer_lines_are_dropped():
    body = expand_certificate_body_template(
        "line one<br/>   <br/>{dates_line}<br/>tail",
        starts_on=date(2026, 2, 10),
    )
    assert body == "line one<br/>Held on Feb 10, 2026<br/>tail"


def test_deliberate_nbsp_spacer_lines_survive():
    body = expand_certificate_body_template(
        "line one<br/>&nbsp;<br/>{dates_line}",
        starts_on=date(2026, 2, 10),
    )
    assert body == "line one<br/>&nbsp;<br/>Held on Feb 10, 2026"
