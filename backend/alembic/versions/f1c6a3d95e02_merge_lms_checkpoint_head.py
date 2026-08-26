"""Merge heads: LMS checkpoint time format (#18) into the combined head

`a4c1e93f0044` (checkpoint start/end seconds -> float) was branched from
`94eaeb5ddbde`, a point ~32 migrations behind the actual `main` tip at merge
time — the PR was stale, not rebased before merge. None of the intervening
migrations touch `video_checkpoints` or any table this one touches, so there
is no real schema conflict, only a graph fork. Pure merge marker.

Revision ID: f1c6a3d95e02
Revises: a5f7c2e08b91, a4c1e93f0044
Create Date: 2026-08-26
"""

revision = "f1c6a3d95e02"
down_revision = ("a5f7c2e08b91", "a4c1e93f0044")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
