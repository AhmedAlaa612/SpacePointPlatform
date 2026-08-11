"""unified course/mission prerequisites (7B-2, Missions Phase 2B, 2026-08-12)

`mission_prerequisites` only ever let a mission require another mission.
D2 (operator's explicit call): courses and missions become interchangeable
"items" in one DAG — a course can require a mission be passed, a mission
can require a course be completed, and the existing mission-to-mission
edges keep working unchanged.

`prerequisites` is a polymorphic edge table: (item_type, item_id) requires
(requires_type, requires_id), each type 'course'|'mission'. No FK on the
id columns — item_id can point at either `courses` or `missions`, and a
single column can't carry two FK targets; existence is checked at the
service layer when an edge is authored instead. This migration backfills
every existing `mission_prerequisites` row (item_type=requires_type=
'mission') before dropping that table, so no edge is lost.

Revision ID: ee33eb03e57d
Revises: 94eaeb5ddbde
Create Date: 2026-08-11 15:11:23.627847

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ee33eb03e57d'
down_revision: Union[str, None] = '94eaeb5ddbde'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prerequisites",
        sa.Column("item_type", sa.String(8), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requires_type", sa.String(8), nullable=False),
        sa.Column("requires_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "item_type", "item_id", "requires_type", "requires_id", name="pk_prerequisites",
        ),
        sa.CheckConstraint("item_type IN ('course', 'mission')", name="ck_prerequisites_item_type"),
        sa.CheckConstraint("requires_type IN ('course', 'mission')", name="ck_prerequisites_requires_type"),
        sa.CheckConstraint(
            "NOT (item_type = requires_type AND item_id = requires_id)",
            name="ck_prerequisites_not_self",
        ),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        "INSERT INTO prerequisites (item_type, item_id, requires_type, requires_id) "
        "SELECT 'mission', mission_id, 'mission', requires_mission_id FROM mission_prerequisites"
    ))

    op.drop_table("mission_prerequisites")


def downgrade() -> None:
    op.create_table(
        "mission_prerequisites",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requires_mission_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("missions.id", ondelete="CASCADE"), nullable=False),
        sa.PrimaryKeyConstraint("mission_id", "requires_mission_id", name="pk_mission_prerequisites"),
        sa.CheckConstraint("mission_id != requires_mission_id", name="ck_mission_prereq_not_self"),
    )

    conn = op.get_bind()
    # only mission-mission edges survive the downgrade — a course-involving
    # edge has nowhere to go in the old schema and is dropped, same as any
    # downgrade that discards data the old shape couldn't represent.
    conn.execute(sa.text(
        "INSERT INTO mission_prerequisites (mission_id, requires_mission_id) "
        "SELECT item_id, requires_id FROM prerequisites "
        "WHERE item_type = 'mission' AND requires_type = 'mission'"
    ))

    op.drop_table("prerequisites")
