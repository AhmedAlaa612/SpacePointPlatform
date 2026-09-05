"""Generalize training_videos' PDF support to any uploaded file (2026-09).

d4e8a1f6c930 added PDF support to Training, narrowly. The actual need is a
generic "file upload" mode exactly like LibraryResource already has — a PDF
gets an inline viewer, anything else (PPTX, DOCX, ...) just opens as a
link, same isInlinePdf-vs-plain-link split the Library UI already makes off
its own `format` field. Renames `pdf_path` -> `file_path` for honesty; not
yet deployed anywhere, so a plain rename costs nothing (no data to migrate).

Revision ID: e21b9a4d7f18
Revises: d4e8a1f6c930
Create Date: 2026-09-05 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e21b9a4d7f18'
down_revision: Union[str, None] = 'd4e8a1f6c930'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('training_videos', 'pdf_path', new_column_name='file_path')


def downgrade() -> None:
    op.alter_column('training_videos', 'file_path', new_column_name='pdf_path')
