"""Post-walkthrough UI fixes — role/item detail, per-role open calls

Four additive columns, one story: the operator's first hands-on pass over the
inventory + instructor-journey screens surfaced gaps the backend-only build
hadn't hit yet.

**`delivery_roles.description`** (B1). An instructor picking a role on the
invite needs to know what it means, not just its name.

**`instructor_interests.role_id`** (B1). Register-interest becomes a real
per-role application instead of a bare note — nullable and SET NULL, same
as every other "don't let this person's departure erase history" FK here,
and because existing rows and sessions with no `session_openings` configured
have nothing to point it at.

**`session_openings.is_open`** (B2). An open call was all-or-nothing for the
whole session; this lets ops solicit interest for just the roles still
needed (e.g. "we still need 2 Assistants") without reopening ones already
filled. Defaults true, so every existing opening — and every one created
before this shipped — behaves exactly as it did: visible the moment the
session is `open_call`.

**`items.description` / `image_bucket` / `image_path`** (B3). The equipment
picker moves from a search box to a browsable shelf; items can now carry an
optional photo and blurb so instructors recognise what they're picking up.
Image storage follows the same bucket+path facade as every other file here
(`services/storage.py`) — nullable because most items won't have one.

Revision ID: e1f4a92c0025
Revises: d4a9f62b0024
Create Date: 2026-07-31
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "e1f4a92c0025"
down_revision = "d4a9f62b0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("delivery_roles", sa.Column("description", sa.Text(), nullable=True))

    op.add_column(
        "instructor_interests",
        sa.Column(
            "role_id", UUID(as_uuid=True),
            sa.ForeignKey("delivery_roles.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_instructor_interests_role_id", "instructor_interests", ["role_id"])

    op.add_column(
        "session_openings",
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.add_column("items", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("items", sa.Column("image_bucket", sa.String(64), nullable=True))
    op.add_column("items", sa.Column("image_path", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("items", "image_path")
    op.drop_column("items", "image_bucket")
    op.drop_column("items", "description")
    op.drop_column("session_openings", "is_open")
    op.drop_index("ix_instructor_interests_role_id", table_name="instructor_interests")
    op.drop_column("instructor_interests", "role_id")
    op.drop_column("delivery_roles", "description")
