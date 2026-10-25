"""Add internal checklist and published materials.

Revision ID: c2b3d4e5f6a7
Revises: b1a2c3d4e5f6
Create Date: 2026-10-25 17:50:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c2b3d4e5f6a7"
down_revision: Union[str, None] = "b1a2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. session_materials: add is_published (defaults existing to true, new to false)
    op.add_column(
        "session_materials",
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.alter_column("session_materials", "is_published", server_default=sa.text("false"))

    # 2. delivery_checklist_items: add target_audience, material_id, link_url
    op.add_column(
        "delivery_checklist_items",
        sa.Column("target_audience", sa.String(length=20), nullable=False, server_default=sa.text("'instructor'")),
    )
    op.add_column(
        "delivery_checklist_items",
        sa.Column(
            "material_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("session_materials.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "delivery_checklist_items",
        sa.Column("link_url", sa.Text(), nullable=True),
    )

    # 3. session_ops_checklist_progress table
    op.create_table(
        "session_ops_checklist_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "checklist_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("delivery_checklist_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "proof_report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("session_reports.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "completed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("session_id", "checklist_item_id", name="uq_session_ops_checklist_progress"),
    )
    op.create_index(
        "ix_session_ops_checklist_progress_session_id",
        "session_ops_checklist_progress",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_session_ops_checklist_progress_session_id", table_name="session_ops_checklist_progress")
    op.drop_table("session_ops_checklist_progress")
    op.drop_column("delivery_checklist_items", "link_url")
    op.drop_column("delivery_checklist_items", "material_id")
    op.drop_column("delivery_checklist_items", "target_audience")
    op.drop_column("session_materials", "is_published")
