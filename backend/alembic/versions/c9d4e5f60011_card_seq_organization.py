"""separate card number sequence for organization accounts (2026-10)

Pure organization accounts (`roles == ['organization']`) previously shared
`card_seq_person` with staff, so they rendered as `SP-####-UAE` — visually
indistinguishable from staff — and any student linked to a school (via
`contact.organization_id`) leaked into the admin Organizations tab looking
like an org with an `SP-ST-` number (frontend filter bug, fixed separately).

New `card_seq_organization` sequence + `SP-ORG-####-UAE` prefix in
`services/documents/card_id.py::format_card_id`, mirroring the 2026-08-22
student split (63d7c6fcb3f2). No data backfill: existing org accounts keep
whatever number they already have from the shared pool; only the displayed
prefix changes (read-time formatting), plus the stored `id_cards.card_id`
strings which `ensure_card_id` rewrites on next view.

Uniqueness: the two partial indexes from 1e772a325fe0 assumed every
non-student row lives in one staff pool. Pure-org rows move to their own
pool, so the staff index must exclude them — otherwise a staff member and
an org sharing a raw integer (harmless now that the strings never collide)
would trip the staff unique index.

Revision ID: c9d4e5f60011
Revises: d8e2f4a6b9c0
"""

from alembic import op

revision = "c9d4e5f60011"
down_revision = "d8e2f4a6b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE SEQUENCE IF NOT EXISTS public.card_seq_organization "
        "START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1"
    )
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_staff")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number_staff ON public.users (card_number) "
        "WHERE card_number IS NOT NULL "
        "AND NOT ('student'::user_role = ANY(roles)) "
        "AND NOT (roles = ARRAY['organization'::user_role])"
    )
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_organization")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number_organization ON public.users (card_number) "
        "WHERE card_number IS NOT NULL "
        "AND roles = ARRAY['organization'::user_role]"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_organization")
    op.execute("DROP INDEX IF EXISTS idx_users_card_number_staff")
    op.execute(
        "CREATE UNIQUE INDEX idx_users_card_number_staff ON public.users (card_number) "
        "WHERE card_number IS NOT NULL AND NOT ('student'::user_role = ANY(roles))"
    )
    op.execute("DROP SEQUENCE IF EXISTS public.card_seq_organization")
