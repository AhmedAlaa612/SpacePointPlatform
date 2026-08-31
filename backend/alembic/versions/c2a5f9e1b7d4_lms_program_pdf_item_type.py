"""replace the LMS program 'article' step type with an uploaded 'pdf' one,
merging heads: design component datasheet + drop session price override

Article steps only ever held an external link; a PDF step instead hosts its
own file (same two-step create-then-upload shape as a module attachment),
resolved through the same no-download PdfViewer as the Curriculum Library.
There's no way to auto-derive a hosted file from an old article's link, so
any existing 'article' rows become 'pdf' rows with nothing uploaded yet —
same "needs a re-upload pass" posture the datasheet migration (b18889c4e94d)
already established for component library links.

Also reconciles the two heads main had already drifted into
(b18889c4e94d/c4d9e2f6a813, from two separately-merged PRs neither of
which resolved the other's head) — same shape as the earlier
b88f272265ef merge migration.

Revision ID: c2a5f9e1b7d4
Revises: b18889c4e94d, c4d9e2f6a813
Create Date: 2026-08-31 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c2a5f9e1b7d4'
down_revision: Union[str, None] = ('b18889c4e94d', 'c4d9e2f6a813')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('lms_program_items', sa.Column('pdf_path', sa.String(length=512), nullable=True))
    op.execute(
        "UPDATE lms_program_items SET item_type = 'pdf', external_url = NULL WHERE item_type = 'article'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE lms_program_items SET item_type = 'article' WHERE item_type = 'pdf'"
    )
    op.drop_column('lms_program_items', 'pdf_path')
