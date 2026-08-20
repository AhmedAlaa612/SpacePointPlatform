"""intern onboarding: intern_profiles, role_requests, internship_ref_counters

Revision ID: 97af2eb4adcb
Revises: 9a46ca83d607
Create Date: 2026-08-20

`intern_profiles` mirrors `instructor_profiles` (1:1 intern record, populated
by scripts/bulk_import_interns.py for historical rows or by approving a
`RoleRequest` for new ones). `role_requests` is deliberately generic — an
already-authenticated user requesting an additional role, not tied to
"intern" specifically — gated by an application-level allowlist, not a
schema constraint, so a future direction (e.g. intern -> instructor) needs
no migration. `internship_ref_counters` backs the per-year auto-incrementing
"N/YYYY" internship-letter reference number.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '97af2eb4adcb'
down_revision: Union[str, None] = '9a46ca83d607'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'internship_ref_counters',
        sa.Column('year', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('year'),
    )

    op.create_table(
        'intern_profiles',
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ref_number', sa.String(length=50), nullable=True),
        sa.Column('university_id_number', sa.String(length=100), nullable=True),
        sa.Column('department', sa.String(length=100), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('duration_weeks', sa.Integer(), nullable=True),
        sa.Column('hours_per_week', sa.Integer(), nullable=True),
        sa.Column('work_city_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('supervisor_name', sa.String(length=255), nullable=True),
        sa.Column('supervisor_email', sa.String(length=255), nullable=True),
        sa.Column('supervisor_phone', sa.String(length=50), nullable=True),
        sa.Column('letter_path', sa.String(), nullable=True),
        sa.Column('signed_letter_path', sa.String(), nullable=True),
        sa.Column('letter_signature_data', sa.Text(), nullable=True),
        sa.Column('letter_signed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['work_city_id'], ['cities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_index(op.f('ix_intern_profiles_ref_number'), 'intern_profiles', ['ref_number'], unique=False)

    op.create_table(
        'role_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requester_user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_role', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('resolution', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['requester_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_role_requests_requester_user_id'), 'role_requests', ['requester_user_id'], unique=False)
    op.create_index(op.f('ix_role_requests_target_role'), 'role_requests', ['target_role'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_role_requests_target_role'), table_name='role_requests')
    op.drop_index(op.f('ix_role_requests_requester_user_id'), table_name='role_requests')
    op.drop_table('role_requests')
    op.drop_index(op.f('ix_intern_profiles_ref_number'), table_name='intern_profiles')
    op.drop_table('intern_profiles')
    op.drop_table('internship_ref_counters')
