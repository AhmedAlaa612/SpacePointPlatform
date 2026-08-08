"""resolve_country_code() (2026-08-08) — case/whitespace-insensitive name-or-code
resolution used by both the country-code migration and, potentially, any future
country-matching query. No DB involved, pure function.
"""

from app.services.countries import resolve_country_code


def test_resolves_exact_name():
    assert resolve_country_code("United Arab Emirates") == "AE"


def test_resolves_name_case_and_whitespace_insensitively():
    assert resolve_country_code("  united arab emirates  ") == "AE"


def test_passes_through_an_already_valid_code():
    assert resolve_country_code("ae") == "AE"


def test_resolves_known_alias():
    assert resolve_country_code("UAE") == "AE"


def test_blank_and_none_resolve_to_none():
    assert resolve_country_code(None) is None
    assert resolve_country_code("") is None
    assert resolve_country_code("   ") is None


def test_unrecognized_value_resolves_to_none():
    assert resolve_country_code("Not A Real Country") is None
