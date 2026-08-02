"""Seed a system template for the student completion certificate.

It was the only certificate type still hardcoded in Python — every other
certificate (workshop_delivery, instructor/intern completion) is rendered
from an editable `document_templates` row. Same shape as `workshop_delivery`
(migration 0008_template_type.sql): `is_system=True`, `roles=[]` — nobody
requests this themselves, the system issues it on cohort completion, so an
empty roles array is what keeps it out of the self-service "request a
document" picker while still being editable by an admin.

Revision ID: d8a2c94e0035
Revises: c4f1a83b0034
Create Date: 2026-08-01
"""

import uuid
import sqlalchemy as sa
from alembic import op

revision = "d8a2c94e0035"
down_revision = "c4f1a83b0034"
branch_labels = None
depends_on = None

BODY_TEXT = "For successfully completing<br/><b>{program_name}</b><br/>{dates}"


def upgrade() -> None:
    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT 1 FROM document_templates WHERE key = 'student_completion'"
    )).first()
    if exists:
        return
    connection.execute(
        sa.text(
            "INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text) "
            "VALUES (:id, 'student_completion', 'Student Completion Certificate', "
            "'certificate', TRUE, ARRAY[]::varchar[], :body_text)"
        ),
        {"id": str(uuid.uuid4()), "body_text": BODY_TEXT},
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM document_templates WHERE key = 'student_completion'"
    ))
