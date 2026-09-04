"""Per-video storage backend.

Adds `videos.storage_backend`: which storage backend THIS video's
student-facing bytes are on. NULL — the value every existing row gets — means
the deployment default, so this migration changes no behaviour on its own.

Why per-row rather than a setting. Where bytes live is a fact about the data,
not about the deployment: video A's segments can sit on the VPS while video B's
sit on R2, and only the row knows which. Held in configuration instead, the
move to object storage becomes one all-or-nothing cutover — pointing the app at
R2 instantly breaks every video whose bytes have not been copied across yet,
and there is no way to move one video, watch it, and only then move the rest.
Held on the row, migration is per-video and so is rollback: copy the bytes,
flip this column, and if anything looks wrong set it back to NULL (the originals
are still on the VPS, because the move copies rather than moves).

Additive and reversible — unlike unify_video_service, this drops nothing.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3e1c07f45a2'
down_revision: Union[str, None] = 'f2c8a916e731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plain String, not sa.Enum, matching every other backend-ish/status-ish
    # column in this codebase — the set of valid backends is enforced by
    # services/storage.py's dispatch, and a DB enum would need its own
    # migration every time one is added.
    op.add_column("videos", sa.Column("storage_backend", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("videos", "storage_backend")
