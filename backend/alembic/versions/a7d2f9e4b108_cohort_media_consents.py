"""Add cohort_media_consents table for student media consent tracking

Revision ID: a7d2f9e4b108
Revises: f8a1c2d3e4b5
Create Date: 2026-09-27 18:50:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7d2f9e4b108'
down_revision: Union[str, None] = 'f8a1c2d3e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cohort_media_consents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('cohort_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('registration_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('registrations.id', ondelete='SET NULL'), nullable=True),
        sa.Column('matched_contact_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('contacts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('student_name_raw', sa.String(length=255), nullable=True),
        sa.Column('school_name_raw', sa.String(length=255), nullable=True),
        sa.Column('parent_name', sa.String(length=255), nullable=False),
        sa.Column('relationship', sa.String(length=64), nullable=True),
        sa.Column('parent_phone', sa.String(length=64), nullable=True),
        sa.Column('parent_email', sa.String(length=255), nullable=True),
        sa.Column('consent_choice', sa.String(length=32), nullable=False, server_default='consented'),
        sa.Column('permission_grants', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'),
        sa.Column('declaration_agreed', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('date_of_signing', sa.Date(), nullable=True),
        sa.Column('source', sa.String(length=32), nullable=False, server_default='google_form'),
        sa.Column('match_status', sa.String(length=32), nullable=False, server_default='unmatched'),
        sa.Column('match_method', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_cohort_media_consents_cohort_id', 'cohort_media_consents', ['cohort_id'])
    op.create_index('ix_cohort_media_consents_registration_id', 'cohort_media_consents', ['registration_id'])
    op.create_index('ix_cohort_media_consents_matched_contact_id', 'cohort_media_consents', ['matched_contact_id'])
    op.create_index('ix_cohort_media_consents_created_at', 'cohort_media_consents', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_cohort_media_consents_created_at', table_name='cohort_media_consents')
    op.drop_index('ix_cohort_media_consents_matched_contact_id', table_name='cohort_media_consents')
    op.drop_index('ix_cohort_media_consents_registration_id', table_name='cohort_media_consents')
    op.drop_index('ix_cohort_media_consents_cohort_id', table_name='cohort_media_consents')
    op.drop_table('cohort_media_consents')
