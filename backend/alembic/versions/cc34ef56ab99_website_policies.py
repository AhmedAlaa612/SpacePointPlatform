"""website_policies table and initial seeds

Revision ID: cc34ef56ab99
Revises: cb23de45ef88
Create Date: 2026-11-01 02:50:00.000000

"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "cc34ef56ab99"
down_revision = "cb23de45ef88"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "website_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("slug", sa.String(128), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("eyebrow", sa.String(128), nullable=True),
        sa.Column("meta", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("show_in_footer", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_website_policies_slug", "website_policies", ["slug"])


def downgrade() -> None:
    op.drop_index("ix_website_policies_slug", table_name="website_policies")
    op.drop_table("website_policies")
