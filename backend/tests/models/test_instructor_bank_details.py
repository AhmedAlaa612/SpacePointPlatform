"""Completeness rule for instructor bank details.

`is_complete` decides whether an instructor may sign a payment letter at all
(routers/instructors/payments.py) and drives the admin directory's "bank details
missing" badge and filter (routers/instructors/admin.py). A letter, once signed,
is immutable — so a wrong answer here either blocks someone who is ready to be
paid, or finalises a letter with nowhere to send the money.

Redis-free, HTTP-free, DB-free: it's a plain property on an unsaved instance.
"""

from app.models.instructors.payment import InstructorBankDetails


def _bank(**overrides) -> InstructorBankDetails:
    fields = {
        "account_holder_name": "Jane Doe",
        "bank_name": "Emirates NBD Bank PJSC",
        "iban": "AE070331234567890123456",
        "swift_bic": "EBILAEAD",
    }
    fields.update(overrides)
    return InstructorBankDetails(**fields)


def test_a_row_with_every_field_is_complete():
    assert _bank().is_complete is True


def test_swift_is_optional_so_its_absence_does_not_block_signing():
    """A domestic AED transfer to a UAE IBAN needs no BIC, and the letter
    template's own label reads "SWIFT/BIC (if applicable)". Requiring it only
    blocked instructors who already had everything the payout needs."""
    assert _bank(swift_bic=None).is_complete is True
    assert _bank(swift_bic="").is_complete is True


def test_each_of_the_three_required_fields_is_actually_required():
    for field in ("account_holder_name", "bank_name", "iban"):
        assert _bank(**{field: None}).is_complete is False, f"{field} should be required"
        assert _bank(**{field: ""}).is_complete is False, f"{field} should be required"


def test_whitespace_does_not_count_as_filled_in():
    """Otherwise a stray space in the IBAN box reads as a payable account."""
    assert _bank(iban="   ").is_complete is False


def test_an_entirely_empty_row_is_not_complete():
    """The row exists as soon as the instructor saves the form once, so an empty
    one is the normal starting state rather than an edge case."""
    assert InstructorBankDetails().is_complete is False
