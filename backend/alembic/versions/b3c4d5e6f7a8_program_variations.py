"""Add program_variations and program_variation_days with non-destructive template backfill.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-11-21
"""

from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _index_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name) if idx.get("name")}


def upgrade() -> None:
    bind = op.get_bind()
    tables = _table_names(bind)

    if "program_variations" not in tables:
        op.create_table(
            "program_variations",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "program_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("1")),
            sa.Column("duration_hours", sa.Numeric(5, 2), nullable=True),
            sa.Column("default_capacity", sa.Integer(), nullable=True),
            sa.Column("poster_template_url", sa.String(512), nullable=True),
            sa.Column("keep_course_access_after_completion", sa.Boolean(), nullable=True),
            sa.Column("pricing_model", sa.String(24), nullable=True),
            sa.Column("price", sa.Numeric(10, 2), nullable=True),
            sa.Column("completion_rule_type", sa.String(16), nullable=True),
            sa.Column("completion_rule_value", sa.Numeric(6, 2), nullable=True),
            sa.Column(
                "default_assessment_config_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("assessment_configs.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "default_certificate_template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_certificate_templates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "default_team_certificate_template_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_certificate_templates.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        )
        op.create_index("ix_program_variations_program_id", "program_variations", ["program_id"])

    if "program_variation_days" not in tables:
        op.create_table(
            "program_variation_days",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("day_number", sa.Integer(), nullable=False),
            sa.Column("title", sa.String(256), nullable=True),
            sa.Column("duration_hours", sa.Numeric(5, 2), nullable=True),
            sa.Column("starts_at", sa.Time(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
            sa.UniqueConstraint("variation_id", "day_number", name="uq_program_variation_day_number"),
        )
        op.create_index("ix_program_variation_days_variation_id", "program_variation_days", ["variation_id"])

    # Cohorts additions
    cohort_cols = _column_names(bind, "cohorts")
    if "variation_id" not in cohort_cols:
        op.add_column(
            "cohorts",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )
        op.create_index("ix_cohorts_variation_id", "cohorts", ["variation_id"])
    if "is_template_legacy" not in cohort_cols:
        op.add_column(
            "cohorts",
            sa.Column("is_template_legacy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        )
    for col_name, col_type in (
        ("pricing_model", sa.String(24)),
        ("price", sa.Numeric(10, 2)),
        ("completion_rule_type", sa.String(16)),
        ("completion_rule_value", sa.Numeric(6, 2)),
    ):
        if col_name not in cohort_cols:
            op.add_column("cohorts", sa.Column(col_name, col_type, nullable=True))
    for fk_col in ("default_certificate_template_id", "default_team_certificate_template_id"):
        if fk_col not in cohort_cols:
            op.add_column(
                "cohorts",
                sa.Column(
                    fk_col,
                    postgresql.UUID(as_uuid=True),
                    sa.ForeignKey("program_certificate_templates.id", ondelete="SET NULL"),
                    nullable=True,
                ),
            )

    # DeliveryChecklistItem additions
    dci_cols = _column_names(bind, "delivery_checklist_items")
    if "variation_id" not in dci_cols:
        op.add_column(
            "delivery_checklist_items",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index("ix_delivery_checklist_items_variation_id", "delivery_checklist_items", ["variation_id"])
    if "variation_day_id" not in dci_cols:
        op.add_column(
            "delivery_checklist_items",
            sa.Column(
                "variation_day_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variation_days.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_delivery_checklist_items_variation_day_id", "delivery_checklist_items", ["variation_day_id"]
        )
    op.execute("ALTER TABLE delivery_checklist_items DROP CONSTRAINT IF EXISTS ck_delivery_checklist_exactly_one_owner;")
    op.execute(
        """
        ALTER TABLE delivery_checklist_items
        ADD CONSTRAINT ck_delivery_checklist_exactly_one_owner CHECK (
            (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_day_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
        """
    )

    # PreSessionQuizAssignment additions
    pqa_cols = _column_names(bind, "pre_session_quiz_assignments")
    if "variation_id" not in pqa_cols:
        op.add_column(
            "pre_session_quiz_assignments",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_pre_session_quiz_assignments_variation_id", "pre_session_quiz_assignments", ["variation_id"]
        )
    if "variation_day_id" not in pqa_cols:
        op.add_column(
            "pre_session_quiz_assignments",
            sa.Column(
                "variation_day_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variation_days.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_pre_session_quiz_assignments_variation_day_id",
            "pre_session_quiz_assignments",
            ["variation_day_id"],
        )
    op.execute("ALTER TABLE pre_session_quiz_assignments DROP CONSTRAINT IF EXISTS ck_pre_session_quiz_assignment_one_owner;")
    op.execute(
        """
        ALTER TABLE pre_session_quiz_assignments
        ADD CONSTRAINT ck_pre_session_quiz_assignment_one_owner CHECK (
            (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_day_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
        """
    )

    # ProgramOpening additions
    po_cols = _column_names(bind, "program_openings")
    op.alter_column("program_openings", "program_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    if "variation_id" not in po_cols:
        op.add_column(
            "program_openings",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index("ix_program_openings_variation_id", "program_openings", ["variation_id"])
    op.execute("ALTER TABLE program_openings DROP CONSTRAINT IF EXISTS uq_program_opening_role;")
    op.execute("DROP INDEX IF EXISTS uq_program_opening_role;")
    op.execute("DROP INDEX IF EXISTS uq_program_opening_variation_role;")
    op.execute("ALTER TABLE program_openings DROP CONSTRAINT IF EXISTS ck_program_opening_one_owner;")
    op.execute(
        """
        ALTER TABLE program_openings
        ADD CONSTRAINT ck_program_opening_one_owner CHECK (
            (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_program_opening_role ON program_openings (program_id, role_id) WHERE program_id IS NOT NULL;"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_program_opening_variation_role ON program_openings (variation_id, role_id) WHERE variation_id IS NOT NULL;"
    )

    # Material additions
    mat_cols = _column_names(bind, "session_materials")
    if "variation_id" not in mat_cols:
        op.add_column(
            "session_materials",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index("ix_session_materials_variation_id", "session_materials", ["variation_id"])
    op.execute("ALTER TABLE session_materials DROP CONSTRAINT IF EXISTS ck_material_exactly_one_owner;")
    op.execute(
        """
        ALTER TABLE session_materials
        ADD CONSTRAINT ck_material_exactly_one_owner CHECK (
            (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN variation_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
             CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        );
        """
    )

    # CompetitionRubric additions
    rubric_cols = _column_names(bind, "competition_rubrics")
    if "variation_id" not in rubric_cols:
        op.add_column(
            "competition_rubrics",
            sa.Column(
                "variation_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("program_variations.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        op.create_index("ix_competition_rubrics_variation_id", "competition_rubrics", ["variation_id"])
        op.create_unique_constraint("uq_competition_rubrics_variation_id", "competition_rubrics", ["variation_id"])

    # ── Non-destructive backfill of legacy draft [Template] cohorts ───────
    # Strictly copies days/checklists/quizzes out of unused draft [Template]
    # shells into program_variations + program_variation_days and sets
    # is_template_legacy = true on the draft shell. Never deletes any cohorts
    # or sessions, and never touches planned/running/completed cohorts.
    draft_templates = bind.execute(
        sa.text(
            """
            SELECT c.id, c.program_id, c.duration_hours
            FROM cohorts c
            WHERE c.status = 'draft'
              AND (c.name ILIKE '[Template]%' OR lower(trim(c.name)) = 'template')
              AND NOT EXISTS (SELECT 1 FROM registrations r WHERE r.cohort_id = c.id)
              AND NOT EXISTS (SELECT 1 FROM lms_program_assignments lpa WHERE lpa.cohort_id = c.id)
              AND NOT EXISTS (
                  SELECT 1 FROM sessions s
                  JOIN session_instructors si ON si.session_id = s.id
                  WHERE s.cohort_id = c.id
              )
              AND NOT EXISTS (
                  SELECT 1 FROM sessions s
                  JOIN instructor_session_days isd ON isd.session_id = s.id
                  WHERE s.cohort_id = c.id
              )
              AND NOT EXISTS (SELECT 1 FROM session_reports sr WHERE sr.cohort_id = c.id)
            ORDER BY c.created_at ASC
            """
        )
    ).mappings().all()

    seen_programs: set = set()
    for tpl in draft_templates:
        prog_id = tpl["program_id"]
        existing_var = bind.execute(
            sa.text("SELECT id FROM program_variations WHERE program_id = :pid LIMIT 1"),
            {"pid": prog_id},
        ).scalar()
        if existing_var is not None or prog_id in seen_programs:
            bind.execute(
                sa.text("UPDATE cohorts SET is_template_legacy = true WHERE id = :cid"),
                {"cid": tpl["id"]},
            )
            continue
        seen_programs.add(prog_id)

        var_id = uuid.uuid4()
        bind.execute(
            sa.text(
                """
                INSERT INTO program_variations (
                    id, program_id, name, is_default, is_active, sort_order, duration_hours
                ) VALUES (
                    :id, :program_id, 'Default', true, true, 1, :duration_hours
                )
                """
            ),
            {"id": var_id, "program_id": prog_id, "duration_hours": tpl["duration_hours"]},
        )

        # Copy cohort-level checklist items on the template shell (if any)
        tpl_cohort_items = bind.execute(
            sa.text(
                """
                SELECT role_id, target_audience, material_id, link_url, attachments, sub_items,
                       title, description, requires_proof, is_required, sort_order, created_by
                FROM delivery_checklist_items
                WHERE cohort_id = :cid
                ORDER BY sort_order, created_at
                """
            ),
            {"cid": tpl["id"]},
        ).mappings().all()
        for ci in tpl_cohort_items:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO delivery_checklist_items (
                        id, variation_id, role_id, target_audience, material_id, link_url,
                        attachments, sub_items, title, description, requires_proof, is_required,
                        sort_order, created_by
                    ) VALUES (
                        :id, :variation_id, :role_id, :target_audience, :material_id, :link_url,
                        CAST(:attachments AS jsonb), CAST(:sub_items AS jsonb),
                        :title, :description, :requires_proof, :is_required, :sort_order, :created_by
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "variation_id": var_id,
                    "role_id": ci["role_id"],
                    "target_audience": ci["target_audience"],
                    "material_id": ci["material_id"],
                    "link_url": ci["link_url"],
                    "attachments": sa.json.dumps(ci["attachments"] or []) if hasattr(sa, "json") else __import__("json").dumps(ci["attachments"] or []),
                    "sub_items": __import__("json").dumps(ci["sub_items"] or []),
                    "title": ci["title"],
                    "description": ci["description"],
                    "requires_proof": ci["requires_proof"],
                    "is_required": ci["is_required"],
                    "sort_order": ci["sort_order"],
                    "created_by": ci["created_by"],
                },
            )

        tpl_cohort_quiz = bind.execute(
            sa.text("SELECT preset_id FROM pre_session_quiz_assignments WHERE cohort_id = :cid LIMIT 1"),
            {"cid": tpl["id"]},
        ).scalar()
        if tpl_cohort_quiz is not None:
            bind.execute(
                sa.text(
                    "INSERT INTO pre_session_quiz_assignments (id, variation_id, preset_id) VALUES (:id, :vid, :pid)"
                ),
                {"id": uuid.uuid4(), "vid": var_id, "pid": tpl_cohort_quiz},
            )

        # Copy template sessions into program_variation_days
        tpl_sessions = bind.execute(
            sa.text(
                """
                SELECT id, title, duration_hours, starts_at
                FROM sessions
                WHERE cohort_id = :cid
                ORDER BY meeting_date, starts_at, created_at
                """
            ),
            {"cid": tpl["id"]},
        ).mappings().all()

        import json

        for day_idx, ts in enumerate(tpl_sessions, start=1):
            day_id = uuid.uuid4()
            bind.execute(
                sa.text(
                    """
                    INSERT INTO program_variation_days (
                        id, variation_id, day_number, title, duration_hours, starts_at
                    ) VALUES (
                        :id, :variation_id, :day_number, :title, :duration_hours, :starts_at
                    )
                    """
                ),
                {
                    "id": day_id,
                    "variation_id": var_id,
                    "day_number": day_idx,
                    "title": ts["title"],
                    "duration_hours": ts["duration_hours"],
                    "starts_at": ts["starts_at"],
                },
            )

            day_items = bind.execute(
                sa.text(
                    """
                    SELECT role_id, target_audience, material_id, link_url, attachments, sub_items,
                           title, description, requires_proof, is_required, sort_order, created_by
                    FROM delivery_checklist_items
                    WHERE session_id = :sid
                    ORDER BY sort_order, created_at
                    """
                ),
                {"sid": ts["id"]},
            ).mappings().all()
            for di in day_items:
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO delivery_checklist_items (
                            id, variation_day_id, role_id, target_audience, material_id, link_url,
                            attachments, sub_items, title, description, requires_proof, is_required,
                            sort_order, created_by
                        ) VALUES (
                            :id, :variation_day_id, :role_id, :target_audience, :material_id, :link_url,
                            CAST(:attachments AS jsonb), CAST(:sub_items AS jsonb),
                            :title, :description, :requires_proof, :is_required, :sort_order, :created_by
                        )
                        """
                    ),
                    {
                        "id": uuid.uuid4(),
                        "variation_day_id": day_id,
                        "role_id": di["role_id"],
                        "target_audience": di["target_audience"],
                        "material_id": di["material_id"],
                        "link_url": di["link_url"],
                        "attachments": json.dumps(di["attachments"] or []),
                        "sub_items": json.dumps(di["sub_items"] or []),
                        "title": di["title"],
                        "description": di["description"],
                        "requires_proof": di["requires_proof"],
                        "is_required": di["is_required"],
                        "sort_order": di["sort_order"],
                        "created_by": di["created_by"],
                    },
                )

            day_quiz = bind.execute(
                sa.text("SELECT preset_id FROM pre_session_quiz_assignments WHERE session_id = :sid LIMIT 1"),
                {"sid": ts["id"]},
            ).scalar()
            if day_quiz is not None:
                bind.execute(
                    sa.text(
                        "INSERT INTO pre_session_quiz_assignments (id, variation_day_id, preset_id) VALUES (:id, :did, :pid)"
                    ),
                    {"id": uuid.uuid4(), "did": day_id, "pid": day_quiz},
                )

        bind.execute(
            sa.text("UPDATE cohorts SET is_template_legacy = true WHERE id = :cid"),
            {"cid": tpl["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()

    if "variation_id" in _column_names(bind, "competition_rubrics"):
        op.drop_constraint("uq_competition_rubrics_variation_id", "competition_rubrics", type_="unique")
        op.drop_index("ix_competition_rubrics_variation_id", table_name="competition_rubrics")
        op.drop_column("competition_rubrics", "variation_id")

    if "variation_id" in _column_names(bind, "session_materials"):
        op.execute("ALTER TABLE session_materials DROP CONSTRAINT IF EXISTS ck_material_exactly_one_owner;")
        op.execute("DELETE FROM session_materials WHERE variation_id IS NOT NULL;")
        op.execute(
            """
            ALTER TABLE session_materials
            ADD CONSTRAINT ck_material_exactly_one_owner CHECK (
                (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
            );
            """
        )
        op.drop_index("ix_session_materials_variation_id", table_name="session_materials")
        op.drop_column("session_materials", "variation_id")

    if "variation_id" in _column_names(bind, "program_openings"):
        op.execute("DROP INDEX IF EXISTS uq_program_opening_variation_role;")
        op.execute("DROP INDEX IF EXISTS uq_program_opening_role;")
        op.execute("ALTER TABLE program_openings DROP CONSTRAINT IF EXISTS ck_program_opening_one_owner;")
        op.execute("DELETE FROM program_openings WHERE variation_id IS NOT NULL;")
        op.alter_column("program_openings", "program_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
        op.create_unique_constraint("uq_program_opening_role", "program_openings", ["program_id", "role_id"])
        op.drop_index("ix_program_openings_variation_id", table_name="program_openings")
        op.drop_column("program_openings", "variation_id")

    pqa_cols = _column_names(bind, "pre_session_quiz_assignments")
    if "variation_id" in pqa_cols or "variation_day_id" in pqa_cols:
        op.execute("ALTER TABLE pre_session_quiz_assignments DROP CONSTRAINT IF EXISTS ck_pre_session_quiz_assignment_one_owner;")
        op.execute("DELETE FROM pre_session_quiz_assignments WHERE variation_id IS NOT NULL OR variation_day_id IS NOT NULL;")
        op.execute(
            """
            ALTER TABLE pre_session_quiz_assignments
            ADD CONSTRAINT ck_pre_session_quiz_assignment_one_owner CHECK (
                (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
            );
            """
        )
        if "variation_day_id" in pqa_cols:
            op.drop_index("ix_pre_session_quiz_assignments_variation_day_id", table_name="pre_session_quiz_assignments")
            op.drop_column("pre_session_quiz_assignments", "variation_day_id")
        if "variation_id" in pqa_cols:
            op.drop_index("ix_pre_session_quiz_assignments_variation_id", table_name="pre_session_quiz_assignments")
            op.drop_column("pre_session_quiz_assignments", "variation_id")

    dci_cols = _column_names(bind, "delivery_checklist_items")
    if "variation_id" in dci_cols or "variation_day_id" in dci_cols:
        op.execute("ALTER TABLE delivery_checklist_items DROP CONSTRAINT IF EXISTS ck_delivery_checklist_exactly_one_owner;")
        op.execute("DELETE FROM delivery_checklist_items WHERE variation_id IS NOT NULL OR variation_day_id IS NOT NULL;")
        op.execute(
            """
            ALTER TABLE delivery_checklist_items
            ADD CONSTRAINT ck_delivery_checklist_exactly_one_owner CHECK (
                (CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END +
                 CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1
            );
            """
        )
        if "variation_day_id" in dci_cols:
            op.drop_index("ix_delivery_checklist_items_variation_day_id", table_name="delivery_checklist_items")
            op.drop_column("delivery_checklist_items", "variation_day_id")
        if "variation_id" in dci_cols:
            op.drop_index("ix_delivery_checklist_items_variation_id", table_name="delivery_checklist_items")
            op.drop_column("delivery_checklist_items", "variation_id")

    cohort_cols = _column_names(bind, "cohorts")
    for col in (
        "default_team_certificate_template_id",
        "default_certificate_template_id",
        "completion_rule_value",
        "completion_rule_type",
        "price",
        "pricing_model",
        "is_template_legacy",
    ):
        if col in cohort_cols:
            op.drop_column("cohorts", col)
    if "variation_id" in cohort_cols:
        op.drop_index("ix_cohorts_variation_id", table_name="cohorts")
        op.drop_column("cohorts", "variation_id")

    tables = _table_names(bind)
    if "program_variation_days" in tables:
        op.drop_table("program_variation_days")
    if "program_variations" in tables:
        op.drop_table("program_variations")
