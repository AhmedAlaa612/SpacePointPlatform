"""Instructor bank details: bank location (city/emirate) (2026-08-31)

The payment-letter template has always carried a `Bank Location
(City/Emirate):` line, but no code ever wrote it and no column backed it, so
it printed as an empty labelled line on every letter ever generated. This is
the missing column.

Nullable and deliberately left out of `InstructorBankDetails.is_complete`:
every instructor who has already saved bank details has it empty, so making
it required would mark them all incomplete and block them from signing until
they returned to the form — the same trap that requiring SWIFT/BIC set.

Revision ID: e4b7d92a5c18
Revises: b98b7f457e5b
"""

import sqlalchemy as sa
from alembic import op

revision = "e4b7d92a5c18"
down_revision = "b98b7f457e5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "instructor_bank_details",
        sa.Column("bank_location", sa.String(length=120), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("instructor_bank_details", "bank_location")
