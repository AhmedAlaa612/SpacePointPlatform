"""add user birthdate, instructor fields, and birthday email logs

Revision ID: 3c283ec9a24c
Revises: f8a1c2d3e4b5
Create Date: 2026-09-27 10:34:35.706219

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '3c283ec9a24c'
down_revision: Union[str, None] = 'f8a1c2d3e4b5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add birthdate to users table
    op.add_column('users', sa.Column('birthdate', sa.Date(), nullable=True))

    # 2. Add extra fields to instructor_profiles
    op.add_column('instructor_profiles', sa.Column('nationality', sa.String(length=100), nullable=True))
    op.add_column('instructor_profiles', sa.Column('work_status', sa.String(length=255), nullable=True))
    op.add_column('instructor_profiles', sa.Column('fluent_languages', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('instructor_profiles', sa.Column('graduated_university', sa.String(length=255), nullable=True))

    # 3. Add extra fields to applicant_profiles
    op.add_column('applicant_profiles', sa.Column('nationality', sa.String(length=100), nullable=True))
    op.add_column('applicant_profiles', sa.Column('work_status', sa.String(length=255), nullable=True))
    op.add_column('applicant_profiles', sa.Column('fluent_languages', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('applicant_profiles', sa.Column('graduated_university', sa.String(length=255), nullable=True))

    # 4. Create birthday_email_logs table
    op.create_table(
        'birthday_email_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sent_at_year', sa.Integer(), nullable=False),
        sa.Column('birth_year_referenced', sa.Integer(), nullable=True),
        sa.Column('nasa_image_url', sa.Text(), nullable=True),
        sa.Column('nasa_title', sa.String(length=512), nullable=True),
        sa.Column('nasa_explanation', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='sent'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_birthday_email_logs_sent_at', 'birthday_email_logs', ['sent_at'], unique=False)
    op.create_index('ix_birthday_email_logs_sent_at_year', 'birthday_email_logs', ['sent_at_year'], unique=False)
    op.create_index('ix_birthday_email_logs_status', 'birthday_email_logs', ['status'], unique=False)
    op.create_index('ix_birthday_email_logs_user_id', 'birthday_email_logs', ['user_id'], unique=False)
    op.create_index('ix_birthday_email_logs_user_year', 'birthday_email_logs', ['user_id', 'sent_at_year'], unique=False)

    # 5. Backfill users.birthdate from contacts.date_of_birth where linked
    op.execute("""
        UPDATE users u
        SET birthdate = c.date_of_birth
        FROM contacts c
        WHERE u.contact_id = c.id
          AND c.date_of_birth IS NOT NULL
          AND u.birthdate IS NULL;
    """)


def downgrade() -> None:
    op.drop_index('ix_birthday_email_logs_user_year', table_name='birthday_email_logs')
    op.drop_index('ix_birthday_email_logs_user_id', table_name='birthday_email_logs')
    op.drop_index('ix_birthday_email_logs_status', table_name='birthday_email_logs')
    op.drop_index('ix_birthday_email_logs_sent_at_year', table_name='birthday_email_logs')
    op.drop_index('ix_birthday_email_logs_sent_at', table_name='birthday_email_logs')
    op.drop_table('birthday_email_logs')

    op.drop_column('applicant_profiles', 'graduated_university')
    op.drop_column('applicant_profiles', 'fluent_languages')
    op.drop_column('applicant_profiles', 'work_status')
    op.drop_column('applicant_profiles', 'nationality')

    op.drop_column('instructor_profiles', 'graduated_university')
    op.drop_column('instructor_profiles', 'fluent_languages')
    op.drop_column('instructor_profiles', 'work_status')
    op.drop_column('instructor_profiles', 'nationality')

    op.drop_column('users', 'birthdate')
