"""design custom components (student-defined parts, attempt-scoped privacy)

Students define proprietary payloads/sensors/modules inside the Design
Mission wizard. A custom row belongs to exactly one attempt (attempt_id is
the ONLY query key); no other student can ever list or add it. Operations
sees it via design-detail and the admin custom-components explorer.

`design_components` gains a nullable `custom_component_id` (+ `is_custom`
and custom-spec snapshot columns) with an XOR CHECK against
`library_component_id` (OR-pattern, matching
ck_mission_attempts_user_xor_team) so exactly one source is ever set.

Revision ID: c9d2e5f6a7b8
Revises: e2f3a4b5c6d7
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'c9d2e5f6a7b8'
down_revision = 'e2f3a4b5c6d7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'design_custom_components',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('attempt_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('mission_attempts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('learner_teams.id', ondelete='SET NULL'), nullable=True),
        sa.Column('component_name', sa.String(length=128), nullable=False),
        sa.Column('subsystem', sa.String(length=40), nullable=False),
        sa.Column('purpose_function', sa.Text(), nullable=False),
        sa.Column('voltage_v', sa.Float(), nullable=False),
        sa.Column('current_ma', sa.Float(), nullable=False),
        sa.Column('pins_used', sa.Text(), nullable=False),
        sa.Column('measurement_output', sa.Text(), nullable=False),
        sa.Column('measurement_range', sa.Text(), nullable=True),
        sa.Column('datasheet_reference', sa.String(length=512), nullable=True),
        sa.Column('mass_g', sa.Float(), nullable=False),
        sa.Column('length_mm', sa.Float(), nullable=False),
        sa.Column('width_mm', sa.Float(), nullable=False),
        sa.Column('height_mm', sa.Float(), nullable=False),
        sa.Column('cost_aed', sa.Float(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_design_custom_components_attempt_id', 'design_custom_components', ['attempt_id'])
    op.create_index('ix_design_custom_components_user_id', 'design_custom_components', ['user_id'])
    op.create_index('ix_design_custom_components_team_id', 'design_custom_components', ['team_id'])

    # Existing rows are all library picks: custom ID starts NULL, is_custom False.
    op.add_column('design_components',
                  sa.Column('custom_component_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('design_components',
                  sa.Column('is_custom', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('design_components', sa.Column('purpose_function', sa.Text(), nullable=True))
    op.add_column('design_components', sa.Column('pins_used', sa.Text(), nullable=True))
    op.add_column('design_components', sa.Column('measurement_output', sa.Text(), nullable=True))
    op.add_column('design_components', sa.Column('measurement_range', sa.Text(), nullable=True))
    op.add_column('design_components', sa.Column('power_computed_mw', sa.Float(), nullable=True))
    op.add_column('design_components', sa.Column('datasheet_reference', sa.String(length=512), nullable=True))

    # Library FK must become nullable (custom rows have no library row).
    op.alter_column('design_components', 'library_component_id',
                    existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key('fk_design_components_custom_component_id',
                          'design_components', 'design_custom_components',
                          ['custom_component_id'], ['id'], ondelete='RESTRICT')
    op.create_check_constraint(
        'ck_design_components_library_xor_custom', 'design_components',
        '(library_component_id IS NOT NULL AND custom_component_id IS NULL) OR '
        '(library_component_id IS NULL AND custom_component_id IS NOT NULL)',
    )


def downgrade() -> None:
    op.drop_constraint('ck_design_components_library_xor_custom', 'design_components', type_='check')
    op.drop_constraint('fk_design_components_custom_component_id', 'design_components', type_='foreignkey')
    op.alter_column('design_components', 'library_component_id',
                    existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    for col in ('datasheet_reference', 'power_computed_mw', 'measurement_range',
                'measurement_output', 'pins_used', 'purpose_function',
                'is_custom', 'custom_component_id'):
        op.drop_column('design_components', col)
    op.drop_index('ix_design_custom_components_team_id', table_name='design_custom_components')
    op.drop_index('ix_design_custom_components_user_id', table_name='design_custom_components')
    op.drop_index('ix_design_custom_components_attempt_id', table_name='design_custom_components')
    op.drop_table('design_custom_components')
