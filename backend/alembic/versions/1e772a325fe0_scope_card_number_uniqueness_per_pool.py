"""scope card_number uniqueness per pool (2026-08-22)

`idx_users_card_number` was a *global* unique index on the raw integer,
predating the student/staff sequence split (63d7c6fcb3f2). With two
independent sequences that both start at 1, a student and a staff member
inevitably land on the same raw number sooner or later — harmless now that
`format_card_id()` prefixes them differently, but the old global index
doesn't know that and blocks it outright (confirmed live: the very next
migration's backfill hit `UniqueViolation` on this exact index the first
time a real DB had both an existing staff card_number=1 and a student
getting renumbered to card_seq_student's first value, also 1).

Replaced with two partial unique indexes — one per pool — which is the
actual invariant that matters: no two *staff* accounts share a number, no
two *student* accounts share a number, but a student and a staff member
sharing a raw integer is fine since their card_id strings never collide.

Revision ID: 1e772a325fe0
Revises: 63d7c6fcb3f2
"""

from alembic import op

revision = "1e772a325fe0"
down_revision = "63d7c6fcb3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_card_number")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number_staff ON public.users (card_number) "
        "WHERE card_number IS NOT NULL AND NOT ('student'::user_role = ANY(roles))"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number_student ON public.users (card_number) "
        "WHERE card_number IS NOT NULL AND 'student'::user_role = ANY(roles)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_student")
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_staff")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number ON public.users (card_number) WHERE (card_number IS NOT NULL)"
    )
