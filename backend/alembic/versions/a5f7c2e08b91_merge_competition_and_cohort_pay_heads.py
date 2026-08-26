"""Merge heads: competition domain (#17) + cohort-aggregated pay (#16)

Both PRs branched their migration chains off the same `main` tip
(`b5d477e213ed`) independently, so merging both leaves two disconnected
Alembic heads: `c0ecdcecc91c` (competition judging) and `d4e81f3a06c5`
(cohort payment lines). Neither PR's migrations touch the same tables, so
there is nothing to reconcile beyond declaring the fork point — this is a
pure merge marker, no schema change.

Revision ID: a5f7c2e08b91
Revises: c0ecdcecc91c, d4e81f3a06c5
Create Date: 2026-08-26
"""

revision = "a5f7c2e08b91"
down_revision = ("c0ecdcecc91c", "d4e81f3a06c5")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
