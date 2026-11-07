"""Point the default student completion body at the conditional {dates_line}.

Operator wording request 2026-11: on the default certificates issued by
competitions and workshops (both render the `student_completion` template),
the date/venue witness line must read "Held on <start>" for a start-only
cohort and "Held from <start> to <end>" for a range, with "at <venue>"
appended whenever a location resolves. The old body printed the bare `{dates}`
blob ("Date to be confirmed" / "a – b").

Only rows that still carry the stock seeded body — the exact text migration
d8a2c94e0035 inserts — are rewritten; an admin-customized body is left alone.
`{dates}` keeps expanding everywhere either way, so customized bodies simply
keep the old companion wording while the code gains the new conditional line.

Revision ID: f7a1c93b0050
Revises: 7ce8193a4b13
Create Date: 2026-11-07
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a1c93b0050"
down_revision = "7ce8193a4b13"
branch_labels = None
depends_on = None

LEGACY_BODY = "For successfully completing<br/><b>{program_name}</b><br/>{dates}"
NEW_BODY = "For successfully completing<br/><b>{program_name}</b><br/>{dates_line}"


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE document_templates SET body_text = :new_body "
            "WHERE key = 'student_completion' AND body_text = :legacy_body"
        ),
        {"new_body": NEW_BODY, "legacy_body": LEGACY_BODY},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE document_templates SET body_text = :legacy_body "
            "WHERE key = 'student_completion' AND body_text = :new_body"
        ),
        {"new_body": NEW_BODY, "legacy_body": LEGACY_BODY},
    )
