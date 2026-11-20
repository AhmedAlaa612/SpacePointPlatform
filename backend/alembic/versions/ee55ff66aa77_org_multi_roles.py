"""Add multi-role users.org_roles array for partner organization sandbox.

Revision ID: ee55ff66aa77
Revises: dd44ee55ff66
Create Date: 2026-11-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ee55ff66aa77"
down_revision: Union[str, None] = "dd44ee55ff66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "org_roles",
            postgresql.ARRAY(sa.String(length=32)),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )

    op.execute(
        """
        UPDATE users
        SET org_roles = CASE
              WHEN org_role IS NOT NULL AND org_role NOT IN ('owner', 'coordinator')
                THEN ARRAY['owner', org_role]::varchar(32)[]
              ELSE ARRAY['owner']::varchar(32)[]
            END,
            org_role = 'owner'
        WHERE id IN (SELECT owner_user_id FROM organizations WHERE owner_user_id IS NOT NULL)
          AND (org_roles IS NULL OR cardinality(org_roles) = 0);
        """
    )
    op.execute(
        """
        UPDATE users
        SET org_roles = ARRAY[org_role]::varchar(32)[]
        WHERE org_role IS NOT NULL
          AND (org_roles IS NULL OR cardinality(org_roles) = 0);
        """
    )
    op.execute(
        """
        UPDATE users u
        SET org_roles = ARRAY['coordinator']::varchar(32)[],
            org_role = 'coordinator'
        FROM organizations o
        WHERE u.organization_id = o.id
          AND o.owner_user_id IS NOT NULL
          AND u.id <> o.owner_user_id
          AND 'organization' = ANY(u.roles::text[])
          AND (u.org_roles IS NULL OR cardinality(u.org_roles) = 0);
        """
    )


def downgrade() -> None:
    op.drop_column("users", "org_roles")

