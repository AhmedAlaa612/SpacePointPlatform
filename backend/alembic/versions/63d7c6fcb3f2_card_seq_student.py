"""separate card number sequence for students (2026-08-22)

Students and staff previously shared one `card_seq_person` sequence for
`users.card_number`, so a student and a staff member could end up with the
same-looking `SP-####-UAE` number (never the *same* number, but visually
indistinguishable — the operator's actual complaint). New `card_seq_student`
sequence, same shape as `card_seq_person` (baseline_schema.sql), used
whenever `services/documents/id_card.py::ensure_card_number` allocates a
number for an account holding the `student` role. `format_card_id()` is what
turns the split into a visible prefix (`SP-ST-####-UAE`) — this migration
only adds the sequence, no data backfill: existing student accounts keep
whatever number they already have from the old shared pool.

Revision ID: 63d7c6fcb3f2
Revises: 56fd3d6a9560
"""

from alembic import op

revision = "63d7c6fcb3f2"
down_revision = "56fd3d6a9560"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE SEQUENCE public.card_seq_student START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1"
    )


def downgrade() -> None:
    op.execute("DROP SEQUENCE public.card_seq_student")
