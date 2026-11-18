"""Add users.org_role — the sandbox role inside a partner organization.

Revision ID: cc33dd44ee55
Revises: bb22cc33dd44
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cc33dd44ee55"
down_revision: Union[str, None] = "bb22cc33dd44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("org_role", sa.String(length=32), nullable=True))
    op.create_index("ix_users_org_role", "users", ["org_role"], unique=False)

    # Owners first — `organizations.owner_user_id` is the primary/legal owner.
    op.execute(
        "UPDATE users SET org_role = 'owner' "
        "WHERE org_role IS NULL AND id IN "
        "(SELECT owner_user_id FROM organizations WHERE owner_user_id IS NOT NULL)"
    )
    # Existing partner-org team members (the `organization` role on a row whose
    # org has an owner) become coordinators. School-affiliated students are
    # deliberately NOT backfilled: affiliation is not membership.
    op.execute(
        "UPDATE users u SET org_role = 'coordinator' "
        "FROM organizations o "
        "WHERE u.organization_id = o.id AND o.owner_user_id IS NOT NULL "
        "AND u.id <> o.owner_user_id AND u.org_role IS NULL "
        "AND 'organization' = ANY(u.roles::text[])"
    )


def downgrade() -> None:
    op.drop_index("ix_users_org_role", table_name="users")
    op.drop_column("users", "org_role")
