"""Seed a system template for the instructor completion certificate.

The certificate auto-issued when an applicant is approved into instructor
(routers/instructors/admin.py::update_application_status) was still hardcoding
its body text as a bare Python string literal ("Instructor Program") instead
of pulling from an editable `document_templates` row — the one certificate
type that hadn't been migrated, despite d8a2c94e0035's docstring claiming it
already had been. That's also why it never appeared in the admin Document
Templates list: there was no row for it. Same shape as `workshop_delivery`
(migration 0008_template_type.sql) and `student_completion` (d8a2c94e0035):
`is_system=True`, `roles=[]` — this is issued automatically on approval, not
requested by instructors themselves, so an empty roles array keeps it out of
the self-service "request a document" picker while remaining editable by an
admin.

Revision ID: a3f7c91d0037
Revises: cd01bf6967f0
Create Date: 2026-08-09
"""

import uuid
import sqlalchemy as sa
from alembic import op

revision = "a3f7c91d0037"
down_revision = "cd01bf6967f0"
branch_labels = None
depends_on = None

BODY_TEXT = "in recognition of successfully completing the<br/><b>SpacePoint Instructor Program</b>"


def upgrade() -> None:
    connection = op.get_bind()
    exists = connection.execute(sa.text(
        "SELECT 1 FROM document_templates WHERE key = 'instructor_completion'"
    )).first()
    if exists:
        return
    connection.execute(
        sa.text(
            "INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text) "
            "VALUES (:id, 'instructor_completion', 'Instructor Program Completion Certificate', "
            "'certificate', TRUE, ARRAY[]::varchar[], :body_text)"
        ),
        {"id": str(uuid.uuid4()), "body_text": BODY_TEXT},
    )


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM document_templates WHERE key = 'instructor_completion'"
    ))
