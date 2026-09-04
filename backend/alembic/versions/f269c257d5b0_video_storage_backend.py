"""Add videos.storage_backend — per-video R2/VPS location (2026-09).

Before this, where a video's student-facing bytes live was decided by one
global setting (`VIDEO_STORAGE_BACKEND`) read fresh on every request — flip
it and every video moves at once, with no way to have some videos on R2 and
others still on local disk at the same time. That makes an incremental,
"migrate 3 courses today, the rest later" cutover impossible, and it also
means a re-encode-in-place has no way to write new output somewhere without
the row already claiming to be there.

This column is the per-row source of truth instead: NULL (every existing
row, unchanged) means local/VPS; "r2" means the row's HLS output (or, for
`direct` mode, its source file) lives on Cloudflare R2. `video_service.py`'s
`_hls_backend`/`_source_backend` read this now, not the global setting.

Revision ID: f269c257d5b0
Revises: f2c8a916e731
Create Date: 2026-09-04 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f269c257d5b0'
down_revision: Union[str, None] = 'f2c8a916e731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("videos", sa.Column("storage_backend", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "storage_backend")
