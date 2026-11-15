"""Team certificates, template kinds, and global certificate email templates.

Revision ID: aa11bb22cc33
Revises: ff99ab12cd34
Create Date: 2026-11-15
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "aa11bb22cc33"
down_revision: Union[str, None] = "ff99ab12cd34"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    with op.get_context().autocommit_block():
        conn.execute(sa.text("ALTER TYPE certificate_type ADD VALUE IF NOT EXISTS 'team_completion'"))

    # Ensure team/item penalty columns exist in all environments migrated via Alembic
    conn.execute(sa.text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_penalty DOUBLE PRECISION"))
    conn.execute(sa.text("ALTER TABLE learner_teams ADD COLUMN IF NOT EXISTS final_lock_notes VARCHAR(255)"))
    conn.execute(sa.text("ALTER TABLE lms_program_team_item_progress ADD COLUMN IF NOT EXISTS penalty_points DOUBLE PRECISION"))
    conn.execute(sa.text("ALTER TABLE lms_program_team_item_progress ADD COLUMN IF NOT EXISTS penalty_notes VARCHAR(255)"))

    # 1. program_certificate_templates.kind
    op.add_column(
        "program_certificate_templates",
        sa.Column("kind", sa.String(24), nullable=False, server_default="individual"),
    )

    # 2. programs.default_team_certificate_template_id
    op.add_column(
        "programs",
        sa.Column("default_team_certificate_template_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_programs_default_team_certificate_template_id",
        "programs",
        "program_certificate_templates",
        ["default_team_certificate_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # 3. certificates team/delivery tracking + per-(registration_id, type) uniqueness
    op.add_column("certificates", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "certificates",
        sa.Column("delivery_mode", sa.String(24), nullable=False, server_default="email"),
    )
    op.add_column("certificates", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("certificates", sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_certificates_team_id",
        "certificates",
        "learner_teams",
        ["team_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_certificates_template_id",
        "certificates",
        "program_certificate_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_certificates_team_id", "certificates", ["team_id"])
    op.create_index(
        "uq_certificates_registration_type",
        "certificates",
        ["registration_id", "type"],
        unique=True,
        postgresql_where=sa.text("registration_id IS NOT NULL"),
    )

    # 4. Global certificate_email_templates table + seeded defaults
    op.create_table(
        "certificate_email_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False, server_default="individual"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    seed_rows = [
        (
            str(uuid.uuid4()),
            "Student Certificate (Attached)",
            "individual",
            "Your SpacePoint certificate — {program_name}",
            (
                "<p>Hi {student_name},</p>"
                "<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>"
                "<p>Your certificate is attached to this email as a PDF.</p>"
                "<p>— SpacePoint</p>"
            ),
            True,
        ),
        (
            str(uuid.uuid4()),
            "Team Certificate (Attached)",
            "team",
            "Your Team Certificate — {program_name}",
            (
                "<p>Hi {student_name},</p>"
                "<p>Congratulations to team <strong>{team_name}</strong> in <strong>{program_name}</strong> ({dates})!</p>"
                "<p>Your team certificate is attached to this email as a PDF.</p>"
                "<p>— SpacePoint</p>"
            ),
            True,
        ),
        (
            str(uuid.uuid4()),
            "Both Certificates (Attached)",
            "combined",
            "Your SpacePoint certificates — {program_name}",
            (
                "<p>Hi {student_name},</p>"
                "<p>Congratulations on your achievements in <strong>{program_name}</strong> ({dates})!</p>"
                "<p>Your {certificate_list} are attached to this email as PDFs.</p>"
                "<p>— SpacePoint</p>"
            ),
            True,
        ),
        (
            str(uuid.uuid4()),
            "Published to Profile",
            "profile",
            "Your SpacePoint certificate is ready — {program_name}",
            (
                "<p>Hi {student_name},</p>"
                "<p>Your {certificate_list} for <strong>{program_name}</strong> ({dates}) is now available in your SpacePoint profile.</p>"
                "<p><a href=\"{profile_link}\">View your certificates</a></p>"
                "<p>— SpacePoint</p>"
            ),
            True,
        ),
    ]
    tbl = sa.table(
        "certificate_email_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("kind", sa.String),
        sa.column("subject", sa.String),
        sa.column("body_html", sa.Text),
        sa.column("is_default", sa.Boolean),
    )
    op.bulk_insert(
        tbl,
        [
            {
                "id": uuid.UUID(rid),
                "name": name,
                "kind": kind,
                "subject": subj,
                "body_html": body,
                "is_default": is_def,
            }
            for rid, name, kind, subj, body, is_def in seed_rows
        ],
    )


def downgrade() -> None:
    op.drop_table("certificate_email_templates")
    op.drop_index("uq_certificates_registration_type", table_name="certificates")
    op.drop_index("ix_certificates_team_id", table_name="certificates")
    op.drop_constraint("fk_certificates_template_id", "certificates", type_="foreignkey")
    op.drop_constraint("fk_certificates_team_id", "certificates", type_="foreignkey")
    op.drop_column("certificates", "template_id")
    op.drop_column("certificates", "published_at")
    op.drop_column("certificates", "delivery_mode")
    op.drop_column("certificates", "team_id")
    op.drop_constraint("fk_programs_default_team_certificate_template_id", "programs", type_="foreignkey")
    op.drop_column("programs", "default_team_certificate_template_id")
    op.drop_column("program_certificate_templates", "kind")
