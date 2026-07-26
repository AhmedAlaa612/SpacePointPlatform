"""Collapse attendance to present|absent.

Operator decision (2026-07-26): "it's either present or no". The four-state
model was also inconsistent in practice — the ops registrations list counted
`late` as attended while the certificate completion rule counted only
`present`, so the attendance figure ops saw disagreed with the one deciding
certificates.

Mapping: `late` -> `present` (they turned up, which is the fact being
recorded), `excused` -> `absent` (they did not attend; excusing it was a
judgement the completion rule already ignored). Existing rows are remapped
rather than left stranded in a value the app no longer accepts.

No CHECK constraint is added: `att_status` is a plain VARCHAR(12) and the
allowed values are enforced by the Pydantic Literal at the API boundary,
matching how every other status column in this schema works.

Revision ID: a1d7f36c0013
Revises: f9c2e08b0012
Create Date: 2026-07-26
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "a1d7f36c0013"
down_revision = "f9c2e08b0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE attendance_records SET att_status = 'present' WHERE att_status = 'late'")
    op.execute("UPDATE attendance_records SET att_status = 'absent' WHERE att_status = 'excused'")


def downgrade() -> None:
    # Irreversible by nature: once late has been folded into present there is
    # no record of which rows were which. Restoring the four-state vocabulary
    # is a schema no-op anyway (the column already accepts any short string),
    # so this deliberately does nothing rather than guess.
    pass
