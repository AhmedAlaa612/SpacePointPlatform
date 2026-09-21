"""program_certificate_templates — Custom layout and typography templates
configured per program (2026-09).

Revision ID: f5a1c92d0047
Revises: e2a91c6f4b58
Create Date: 2026-09-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'f5a1c92d0047'
down_revision: Union[str, None] = 'e2a91c6f4b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'program_certificate_templates',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('program_id', UUID(as_uuid=True), sa.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('background_type', sa.String(24), nullable=False, server_default='custom'),
        sa.Column('background_file_path', sa.String(512), nullable=True),
        sa.Column('background_file_url', sa.String(512), nullable=True),
        sa.Column('name_font_size', sa.Integer(), nullable=False, server_default='34'),
        sa.Column('name_y', sa.Numeric(6, 2), nullable=False, server_default='298.0'),
        sa.Column('name_color', sa.String(32), nullable=False, server_default='#9778be'),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('body_font_size', sa.Integer(), nullable=False, server_default='20'),
        sa.Column('body_y', sa.Numeric(6, 2), nullable=False, server_default='260.0'),
        sa.Column('body_color', sa.String(32), nullable=False, server_default='#9778be'),
        sa.Column('body_max_width', sa.Numeric(6, 2), nullable=False, server_default='600.0'),
        sa.Column('body_alignment', sa.String(16), nullable=False, server_default='center'),
        sa.Column('show_signature', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('signature_image_path', sa.String(512), nullable=True),
        sa.Column('signature_image_url', sa.String(512), nullable=True),
        sa.Column('signature_x', sa.Numeric(6, 2), nullable=True),
        sa.Column('signature_y', sa.Numeric(6, 2), nullable=False, server_default='90.0'),
        sa.Column('signature_width', sa.Numeric(6, 2), nullable=False, server_default='140.0'),
        sa.Column('signature_height', sa.Numeric(6, 2), nullable=False, server_default='50.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        'ix_program_certificate_templates_program_id',
        'program_certificate_templates',
        ['program_id'],
    )

    op.add_column('programs', sa.Column('default_certificate_template_id', UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_programs_default_certificate_template_id',
        'programs',
        'program_certificate_templates',
        ['default_certificate_template_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_programs_default_certificate_template_id', 'programs', type_='foreignkey')
    op.drop_column('programs', 'default_certificate_template_id')
    op.drop_index('ix_program_certificate_templates_program_id', table_name='program_certificate_templates')
    op.drop_table('program_certificate_templates')
