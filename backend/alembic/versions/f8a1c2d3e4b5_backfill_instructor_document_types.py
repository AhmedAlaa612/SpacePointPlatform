"""backfill instructor document types for compliance standardization

Revision ID: f8a1c2d3e4b5
Revises: e7b2c91d0049
Create Date: 2026-09-24 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f8a1c2d3e4b5'
down_revision: Union[str, None] = 'e7b2c91d0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE instructor_documents
        SET document_type = 'Emirates ID / National ID'
        WHERE document_type ILIKE 'ID Card' OR document_type ILIKE 'Emirates ID' OR document_type ILIKE 'National ID';
    """)
    op.execute("""
        UPDATE instructor_documents
        SET document_type = 'Residence Visa'
        WHERE document_type ILIKE 'Visa';
    """)
    op.execute("""
        UPDATE instructor_documents
        SET document_type = 'Personal Picture'
        WHERE document_type ILIKE 'Photo' OR document_type ILIKE 'Passport Photo';
    """)


def downgrade() -> None:
    pass
