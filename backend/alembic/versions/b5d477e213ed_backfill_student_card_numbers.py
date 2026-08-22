"""backfill: renumber existing students onto card_seq_student (2026-08-22)

One-time cleanup, operator-requested: every account that already held a
`card_number` from the old shared `card_seq_person` pool *and* holds the
`student` role gets reassigned a fresh number from `card_seq_student`
(created in 63d7c6fcb3f2), so no student account is left displaying a
number that looks like it came from the staff pool. Safe to run any time —
no student has ever gone through the physical-card-generation flow in
practice (that's a staff-facing page), so there's no printed card anywhere
carrying the old number.

Not meaningfully reversible: the old numbers aren't preserved anywhere, so
`downgrade()` is a no-op — a plain schema rollback wouldn't undo a renumber
correctly either way.

Revision ID: b5d477e213ed
Revises: 63d7c6fcb3f2
"""

from alembic import op

revision = "b5d477e213ed"
down_revision = "63d7c6fcb3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET card_number = nextval('card_seq_student') "
        "WHERE 'student'::user_role = ANY(roles) AND card_number IS NOT NULL"
    )


def downgrade() -> None:
    pass  # not reversible — old numbers weren't preserved, see docstring
