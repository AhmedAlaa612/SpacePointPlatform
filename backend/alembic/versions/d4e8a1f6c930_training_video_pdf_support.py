"""Let a training module item be a PDF instead of only ever a video (2026-09).

Facilitator training could only ever be a video (embed link or upload) —
`training_videos.video_path` was NOT NULL for exactly that reason, there was
no other shape a row could take. Same generalization pattern
`LibraryResource.format` already established: a row is now exactly one of
embed URL (video_path set, format NULL), uploaded video (a `videos` row,
owner_type="training_video"), or an uploaded PDF (format="PDF", pdf_path
set) — never more than one. `video_path` drops NOT NULL since a PDF row has
no video URL at all.

Revision ID: d4e8a1f6c930
Revises: b3e1c07f45a2
Create Date: 2026-09-05 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd4e8a1f6c930'
down_revision: Union[str, None] = 'b3e1c07f45a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('training_videos', sa.Column('format', sa.String(10), nullable=True))
    op.add_column('training_videos', sa.Column('pdf_path', sa.String(), nullable=True))
    op.alter_column('training_videos', 'video_path', existing_type=sa.String(), nullable=True)


def downgrade() -> None:
    # Nothing to backfill going the other way — a PDF row (format='PDF')
    # simply has no video_path to restore; NOT NULL is only safe to bring
    # back if no such row exists, which this does not attempt to guarantee.
    op.alter_column('training_videos', 'video_path', existing_type=sa.String(), nullable=False)
    op.drop_column('training_videos', 'pdf_path')
    op.drop_column('training_videos', 'format')
