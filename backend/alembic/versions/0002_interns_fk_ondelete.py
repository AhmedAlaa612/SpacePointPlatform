"""interns domain + recommendation_letters: add ondelete to users.id FKs

Phase 1 (interns) never got the ondelete=CASCADE/SET NULL treatment that
Phase 2 (ambassadors) and Phase 3 (instructors) got, so deleting a user who
is e.g. still a team member raises an unhandled IntegrityError instead of
either cascading cleanly or being blocked with a clear error. This brings
the interns domain in line with the rest of the schema's convention:
  - join/membership rows (team_members, task_assignees) -> CASCADE
  - leaf "owned content" rows (task_submissions, proposals) -> CASCADE
  - nullable "soft" creator/reviewer references -> SET NULL
recommendation_letters.generated_by had the same gap relative to its sibling
certificates.generated_by, which is already nullable + SET NULL.

teams.leader_id and projects.created_by are intentionally left alone here:
both are NOT NULL references on aggregate-root rows (a team's epics, a
project's whole epic/module/task tree hang off them), so neither CASCADE
(silently wipes the tree) nor SET NULL (column isn't nullable) is safe.
Those are guarded at the service layer instead (app/services/user.py).

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-26

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (constraint_name, table, column, ondelete)
CASCADE_FKS = [
    ("team_members_user_id_fkey", "team_members", "user_id"),
    ("task_assignees_user_id_fkey", "task_assignees", "user_id"),
    ("task_submissions_submitted_by_fkey", "task_submissions", "submitted_by"),
    ("proposals_proposed_by_fkey", "proposals", "proposed_by"),
]

SET_NULL_FKS = [
    ("tasks_created_by_fkey", "tasks", "created_by"),
    ("proposals_reviewed_by_fkey", "proposals", "reviewed_by"),
    ("modules_created_by_fkey", "modules", "created_by"),
    ("task_mind_map_notes_updated_by_fkey", "task_mind_map_notes", "updated_by"),
    ("epics_created_by_fkey", "epics", "created_by"),
]

RECOMMENDATION_LETTER_FK = "recommendation_letters_generated_by_fkey"


def upgrade() -> None:
    for name, table, column in CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [column], ["id"], ondelete="CASCADE")

    for name, table, column in SET_NULL_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [column], ["id"], ondelete="SET NULL")

    op.alter_column("recommendation_letters", "generated_by", nullable=True)
    op.drop_constraint(RECOMMENDATION_LETTER_FK, "recommendation_letters", type_="foreignkey")
    op.create_foreign_key(
        RECOMMENDATION_LETTER_FK, "recommendation_letters", "users", ["generated_by"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    op.drop_constraint(RECOMMENDATION_LETTER_FK, "recommendation_letters", type_="foreignkey")
    op.create_foreign_key(
        RECOMMENDATION_LETTER_FK, "recommendation_letters", "users", ["generated_by"], ["id"]
    )
    op.alter_column("recommendation_letters", "generated_by", nullable=False)

    for name, table, column in SET_NULL_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [column], ["id"])

    for name, table, column in CASCADE_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, "users", [column], ["id"])
