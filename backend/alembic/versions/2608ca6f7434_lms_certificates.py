"""LMS completion certificates (2026-08-13)

Two new `certificate_type` values (lms_course_completion, lms_path_completion)
plus the columns recording what was completed to earn one.

The `certificates` table already carries a natural idempotency key for every
existing type (registration_id for student_completion, payment_session_id for
workshop_delivery). LMS certs had none, and they're issued from a hot write
path (every item-progress POST re-checks completion), so the partial unique
indexes below are what actually stop a duplicate — not application-level
checking alone, which races under concurrent requests.

Also seeds the two system `document_templates` rows, same shape as
`student_completion` (migration d8a2c94e0035): is_system=True, roles=[] so
they stay out of the self-service "request a document" picker while still
being admin-editable.

Revision ID: 2608ca6f7434
Revises: 746750d9b5b9
Create Date: 2026-08-13
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2608ca6f7434"
down_revision: Union[str, None] = "746750d9b5b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COURSE_BODY = "For successfully completing the course<br/><b>{course_name}</b><br/>{date}"
PATH_BODY = "For successfully completing the learning path<br/><b>{path_name}</b><br/>{date}"


def upgrade() -> None:
    conn = op.get_bind()

    # ALTER TYPE ... ADD VALUE cannot be used in the same transaction that
    # later references the new value (PG restriction), and alembic wraps the
    # whole migration in one — so the enum additions run in their own
    # autocommit block ahead of everything else.
    with op.get_context().autocommit_block():
        conn.execute(sa.text("ALTER TYPE certificate_type ADD VALUE IF NOT EXISTS 'lms_course_completion'"))
        conn.execute(sa.text("ALTER TYPE certificate_type ADD VALUE IF NOT EXISTS 'lms_path_completion'"))

    op.add_column("certificates", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("certificates", sa.Column("learning_path_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_certificates_course_id", "certificates", "courses", ["course_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_certificates_learning_path_id", "certificates", "learning_paths",
        ["learning_path_id"], ["id"], ondelete="CASCADE",
    )

    # Partial: only LMS rows have these set, so the index must not fire on
    # the thousands of existing rows where both are NULL.
    op.create_index(
        "uq_certificates_user_course", "certificates", ["user_id", "course_id"],
        unique=True, postgresql_where=sa.text("course_id IS NOT NULL"),
    )
    op.create_index(
        "uq_certificates_user_learning_path", "certificates", ["user_id", "learning_path_id"],
        unique=True, postgresql_where=sa.text("learning_path_id IS NOT NULL"),
    )

    for key, name, body in (
        ("lms_course_completion", "LMS Course Completion Certificate", COURSE_BODY),
        ("lms_path_completion", "LMS Learning Path Certificate", PATH_BODY),
    ):
        if conn.execute(sa.text("SELECT 1 FROM document_templates WHERE key = :key"), {"key": key}).first():
            continue
        conn.execute(
            sa.text(
                "INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text) "
                "VALUES (:id, :key, :name, 'certificate', TRUE, ARRAY[]::varchar[], :body)"
            ),
            {"id": str(uuid.uuid4()), "key": key, "name": name, "body": body},
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "DELETE FROM document_templates WHERE key IN ('lms_course_completion', 'lms_path_completion')"
    ))
    # Drop the rows before the columns — they're unreachable once the type
    # values go, and PG won't let an enum value be removed at all (there is
    # no DROP VALUE), so the enum additions are deliberately not reversed.
    conn.execute(sa.text(
        "DELETE FROM certificates WHERE type IN ('lms_course_completion', 'lms_path_completion')"
    ))
    op.drop_index("uq_certificates_user_learning_path", table_name="certificates")
    op.drop_index("uq_certificates_user_course", table_name="certificates")
    op.drop_constraint("fk_certificates_learning_path_id", "certificates", type_="foreignkey")
    op.drop_constraint("fk_certificates_course_id", "certificates", type_="foreignkey")
    op.drop_column("certificates", "learning_path_id")
    op.drop_column("certificates", "course_id")
