"""cohort readiness pipeline upgrade and seed data

Revision ID: ca12bc34de77
Revises: c9e1f2a3b4d5
Create Date: 2026-10-31 20:30:00.000000

"""
import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ca12bc34de77"
down_revision = "c9e1f2a3b4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add phases column to pre_session_quiz_presets
    op.add_column(
        "pre_session_quiz_presets",
        sa.Column("phases", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )

    # 2. Upgrade pre_session_quiz_attempts to cohort-scoped state machine
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Backfill cohort_id from sessions table
    op.execute(
        """
        UPDATE pre_session_quiz_attempts a
        SET cohort_id = s.cohort_id
        FROM sessions s
        WHERE a.session_id = s.id
        """
    )

    # Remove any orphan attempts with null cohort_id
    op.execute("DELETE FROM pre_session_quiz_attempts WHERE cohort_id IS NULL")

    # Deduplicate existing attempts per (cohort_id, user_id), keeping the latest submitted_at
    op.execute(
        """
        DELETE FROM pre_session_quiz_attempts
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY cohort_id, user_id
                    ORDER BY submitted_at DESC NULLS LAST, id
                ) as rnum
                FROM pre_session_quiz_attempts
            ) t
            WHERE t.rnum > 1
        )
        """
    )

    # Set cohort_id NOT NULL and add foreign key & index
    op.alter_column("pre_session_quiz_attempts", "cohort_id", nullable=False)
    op.create_foreign_key(
        "fk_pre_session_quiz_attempts_cohort_id",
        "pre_session_quiz_attempts",
        "cohorts",
        ["cohort_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_pre_session_quiz_attempts_cohort_id",
        "pre_session_quiz_attempts",
        ["cohort_id"],
    )

    # Allow session_id to be nullable
    op.alter_column("pre_session_quiz_attempts", "session_id", nullable=True)

    # Add unique constraint (cohort_id, user_id)
    op.create_unique_constraint(
        "uq_pre_session_quiz_attempt_cohort_user",
        "pre_session_quiz_attempts",
        ["cohort_id", "user_id"],
    )

    # Add pipeline state machine columns to pre_session_quiz_attempts
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="in_progress"),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("current_phase_index", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True, server_default=sa.text("now()")),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("total_duration_seconds", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pre_session_quiz_attempts",
        sa.Column("phase_states", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    # Mark existing submitted attempts as completed
    op.execute("UPDATE pre_session_quiz_attempts SET status = 'completed' WHERE submitted_at IS NOT NULL")

    # 3. Create pre_session_quiz_phase_trials table
    op.create_table(
        "pre_session_quiz_phase_trials",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("pre_session_quiz_attempts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("phase_id", sa.String(length=64), nullable=False),
        sa.Column("phase_index", sa.Integer(), nullable=False),
        sa.Column("phase_type", sa.String(length=32), nullable=False),
        sa.Column("trial_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_pct", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("pass_percentage_required", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index(
        "ix_pre_session_quiz_phase_trials_attempt_id",
        "pre_session_quiz_phase_trials",
        ["attempt_id"],
    )
    op.create_index(
        "ix_pre_session_quiz_phase_trials_phase_id",
        "pre_session_quiz_phase_trials",
        ["phase_id"],
    )

    # 4. Synthesize default phases for existing presets where phases is empty
    conn = op.get_bind()
    presets_res = conn.execute(
        sa.text("SELECT id, name, question_ids, reference_attachments FROM pre_session_quiz_presets WHERE phases = '[]'::jsonb")
    )
    for p_id, p_name, q_ids, refs in presets_res.fetchall():
        q_list = q_ids if isinstance(q_ids, list) else json.loads(q_ids or "[]")
        ref_list = refs if isinstance(refs, list) else json.loads(refs or "[]")
        synth_phases = []
        if ref_list:
            synth_phases.append({
                "id": f"phase-explore-{uuid.uuid4().hex[:6]}",
                "phase_type": "explore_datasheets",
                "title": "Explore Data Sheets",
                "subtitle": "Review module datasheets and user guides",
                "instructions": [
                    "Review module datasheets and technical pinout guides.",
                    "Click View PDF to inspect specifications before proceeding.",
                ],
                "pass_percentage": 100,
                "cooldown_seconds": 0,
                "show_correct_on_fail": False,
                "show_explanation_on_fail": False,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [],
            })
        if q_list:
            synth_phases.append({
                "id": f"phase-quiz-{uuid.uuid4().hex[:6]}",
                "phase_type": "quiz",
                "title": f"{p_name} — Pinout Verification",
                "subtitle": "Interactive connector jumper and MCQ verification",
                "instructions": [
                    "Select correct pins for each connector.",
                    "If a datasheet error exists, choose Other and specify the reason.",
                ],
                "pass_percentage": 100,
                "cooldown_seconds": 60,
                "show_correct_on_fail": False,
                "show_explanation_on_fail": False,
                "show_bucket_target_counts": True,
                "allow_datasheet_lookup": True,
                "question_ids": [str(qid) for qid in q_list],
            })
        if synth_phases:
            conn.execute(
                sa.text("UPDATE pre_session_quiz_presets SET phases = :phases WHERE id = :id"),
                {"phases": json.dumps(synth_phases), "id": p_id},
            )

    # 5. Seed Phase 4 (Addressing) & Phase 5 (Scenario) Questions
    now = datetime.now(timezone.utc)
    q_addr_collision_id = uuid.uuid4()
    q_addr_protocol_id = uuid.uuid4()
    q_addr_range_id = uuid.uuid4()
    q_addr_jumper_id = uuid.uuid4()
    q_scen_lockup_id = uuid.uuid4()
    q_scen_eps_drop_id = uuid.uuid4()

    new_questions = [
        {
            "id": q_addr_collision_id,
            "topic": "Addressing",
            "question_type": "mcq",
            "title": "I2C Slave Address Collision Impact",
            "prompt": "What happens if two devices connected to the same shared I2C bus have the exact same 7-bit slave address?",
            "image_url": None,
            "options": json.dumps([
                {"text": "Bus contention occurs; both slaves acknowledge simultaneously and drive SDA during read cycles, corrupting data reads.", "is_correct": True},
                {"text": "The secondary device automatically reassigns itself to a random unassigned address on the bus.", "is_correct": False},
                {"text": "The I2C master communicates with both devices simultaneously with doubled bus throughput.", "is_correct": False},
                {"text": "The clock frequency automatically drops by 50% to prevent packet collisions.", "is_correct": False},
            ]),
            "table_config": None,
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "I2C uses open-drain lines with pull-up resistors. If two devices share the same address, both respond with ACK during address phase and both attempt to drive SDA during reads. When one device outputs 0 (pulling line low) while the other outputs 1 (floating), the low state wins, causing bus arbitration failure and corrupting data.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
        {
            "id": q_addr_protocol_id,
            "topic": "Addressing",
            "question_type": "mcq",
            "title": "I2C Addressing Architecture vs. UART",
            "prompt": "Which of the following describes device addressing on a shared bus, and how does UART communication differ?",
            "image_url": None,
            "options": json.dumps([
                {"text": "I2C uses 7-bit/10-bit software addressing on a shared 2-wire bus (SDA/SCL); UART is point-to-point (TX/RX) without hardware bus addressing.", "is_correct": True},
                {"text": "UART uses 8-bit hex device addresses; I2C is strictly point-to-point between two chips.", "is_correct": False},
                {"text": "Both I2C and UART require dedicated chip-select lines for every connected peripheral.", "is_correct": False},
                {"text": "UART supports up to 127 devices on a single TX wire without needing addresses.", "is_correct": False},
            ]),
            "table_config": None,
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "I2C is an addressable multi-drop serial bus where every slave has a unique 7-bit (or 10-bit) address sent in the first byte of every transaction. UART is asynchronous point-to-point communication between two endpoints (TX to RX, RX to TX) and has no inherent bus addressing mechanism.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
        {
            "id": q_addr_range_id,
            "topic": "Addressing",
            "question_type": "mcq",
            "title": "Valid Standard 7-Bit I2C Slave Address Range",
            "prompt": "Which range represents valid standard 7-bit I2C slave addresses allocatable to sensor and actuator ICs?",
            "image_url": None,
            "options": json.dumps([
                {"text": "0x08 to 0x77 (addresses 0x00–0x07 and 0x78–0x7F are reserved by the I2C specification).", "is_correct": True},
                {"text": "0x00 to 0xFF (all 256 byte values are valid 7-bit addresses).", "is_correct": False},
                {"text": "0x80 to 0xFE (only upper half of 8-bit memory).", "is_correct": False},
                {"text": "0x01 to 0x3F (6-bit range).", "is_correct": False},
            ]),
            "table_config": None,
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "In 7-bit I2C addressing, 0x00–0x07 (general call, CBUS, start byte) and 0x78–0x7F (10-bit addressing prefixes and reserved IDs) are reserved, providing 112 assignable addresses from 0x08 to 0x77.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
        {
            "id": q_addr_jumper_id,
            "topic": "Addressing",
            "question_type": "mcq",
            "title": "Hardware Address Pin State Calculation (A2, A1, A0)",
            "prompt": "An I2C sensor module uses address pins A2, A1, A0. In default configuration (A2=1, A1=0, A0=1), the module resolves to address 0x4D. What is the resulting 7-bit address when the jumpers are changed to (A2=0, A1=1, A0=1)?",
            "image_url": None,
            "options": json.dumps([
                {"text": "0x4B", "is_correct": True},
                {"text": "0x48", "is_correct": False},
                {"text": "0x4E", "is_correct": False},
                {"text": "0x52", "is_correct": False},
            ]),
            "table_config": json.dumps({
                "connector_name": "Address Jumpers",
                "header_subtitle": "Hardware Pin Strap Configuration",
                "columns": ["A2", "A1", "A0", "Resulting 7-Bit Address"],
                "rows": [
                    {
                        "label": "Default Connection",
                        "cells": [
                            {"text": "1 (VCC)", "is_correct": True},
                            {"text": "0 (GND)", "is_correct": True},
                            {"text": "1 (VCC)", "is_correct": True},
                            {"text": "0x4D", "is_correct": True},
                        ],
                    },
                    {
                        "label": "Modified Connection",
                        "cells": [
                            {"text": "0 (GND)", "is_correct": True},
                            {"text": "1 (VCC)", "is_correct": True},
                            {"text": "1 (VCC)", "is_correct": True},
                            {"text": "0x4B", "is_correct": True},
                        ],
                    },
                ],
            }),
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "The base prefix for the module is 0b1001xxx (0x48 base). With A2=1, A1=0, A0=1 (binary offset 5), the address is 0x48 + 5 = 0x4D. When modified to A2=0, A1=1, A0=1 (binary offset 3), the resulting address is 0x48 + 3 = 0x4B.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
        {
            "id": q_scen_lockup_id,
            "topic": "Scenarios",
            "question_type": "mcq",
            "title": "I2C Bus Lockup Diagnostics & Recovery",
            "prompt": "During a live cohort satellite assembly, an instructor discovers that the I2C bus hangs and all telemetry reads time out. An oscilloscope indicates that the SDA line is held LOW indefinitely while SCL is idle HIGH. What is the standard recovery sequence?",
            "image_url": None,
            "options": json.dumps([
                {"text": "Generate up to 9 SCL clock pulses while keeping SDA released so the slave outputs the rest of its byte, followed by an I2C STOP condition.", "is_correct": True},
                {"text": "Replace the 4.7kΩ bus pull-up resistors with 100kΩ resistors to reduce line capacitance.", "is_correct": False},
                {"text": "Send a UART break pulse over the TX line to clear the sensor hardware buffer.", "is_correct": False},
                {"text": "Invert SDA and SCL pin connections on the microcontroller header.", "is_correct": False},
            ]),
            "table_config": None,
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "When a microcontroller resets or aborts mid-read while a slave is transmitting a logic 0 on SDA, the slave holds SDA LOW waiting for SCL clocks. Toggling SCL up to 9 times allows the slave to finish transmitting its byte and release SDA, after which the master can issue a STOP condition to restore bus operation.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
        {
            "id": q_scen_eps_drop_id,
            "topic": "Scenarios",
            "question_type": "written",
            "title": "EPS 3.3V Power Rail Drop Troubleshooting",
            "prompt": "Explain the step-by-step diagnostic procedure you would follow if the 3.3V EPS rail drops to 1.8V when connecting a newly assembled sub-board during a workshop session.",
            "image_url": None,
            "options": json.dumps([]),
            "table_config": None,
            "allow_other": False,
            "is_other_correct": False,
            "explanation": "Key diagnostic steps: (1) Immediately disconnect the new sub-board to prevent regulator thermal damage. (2) Unpowered continuity/resistance check with DMM between 3V3 and GND on the sub-board to check for low-resistance shorts. (3) Visual inspection under magnification for solder bridges, reversed polarized capacitors, or IC misalignment. (4) Bench supply current-limited power-up to isolate faulty component.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
    ]

    for q in new_questions:
        conn.execute(
            sa.text(
                """
                INSERT INTO pre_session_quiz_questions (
                    id, topic, question_type, title, prompt, image_url, options,
                    table_config, allow_other, is_other_correct, explanation,
                    explanation_image_url, explanation_table, is_active, created_by, created_at
                ) VALUES (
                    :id, :topic, :question_type, :title, :prompt, :image_url, CAST(:options AS jsonb),
                    CAST(:table_config AS jsonb), :allow_other, :is_other_correct, :explanation,
                    :explanation_image_url, CAST(:explanation_table AS jsonb), :is_active, :created_by, :created_at
                )
                """
            ),
            q,
        )

    # 6. Create / Update Standard 5-Phase Hardware Readiness Preset
    default_datasheets = [
        {
            "id": "ds-esp32",
            "title": "ESP32 Microcontroller Module Data Sheet",
            "url": "/files/datasheets/esp32_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "CDHS",
            "image_url": None,
            "is_file": True,
        },
        {
            "id": "ds-tmp102",
            "title": "TMP102 Temperature Sensor Data Sheet",
            "url": "/files/datasheets/tmp102_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "CDHS",
            "image_url": None,
            "is_file": True,
        },
        {
            "id": "ds-mpu6050",
            "title": "MPU-6050 6-Axis Motion Tracking IMU Data Sheet",
            "url": "/files/datasheets/mpu6050_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "ADCS/APC",
            "image_url": None,
            "is_file": True,
        },
        {
            "id": "ds-ina219",
            "title": "INA219 High-Side DC Current and Power Sensor Data Sheet",
            "url": "/files/datasheets/ina219_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "EPS",
            "image_url": None,
            "is_file": True,
        },
        {
            "id": "ds-solar-eps",
            "title": "Solar Panel Regulator & Li-Ion Charging Module User Guide",
            "url": "/files/datasheets/eps_charging_guide.pdf",
            "doc_type": "user_guide",
            "subsystem_tag": "EPS",
            "image_url": None,
            "is_file": True,
        },
        {
            "id": "ds-rw-motor",
            "title": "ADCS Reaction Wheel Brushless DC Motor Driver Data Sheet",
            "url": "/files/datasheets/reaction_wheel_datasheet.pdf",
            "doc_type": "datasheet",
            "subsystem_tag": "ADCS/APC",
            "image_url": None,
            "is_file": True,
        },
    ]

    # Look up existing CDHS and ADCS questions to include in Pinout Quiz
    pinout_q_rows = conn.execute(
        sa.text("SELECT id FROM pre_session_quiz_questions WHERE topic IN ('CDHS', 'ADCS/APC') ORDER BY created_at ASC")
    ).fetchall()
    pinout_q_ids = [str(r[0]) for r in pinout_q_rows]

    five_phases = [
        {
            "id": "phase-explore",
            "phase_type": "explore_datasheets",
            "title": "Explore Data Sheets",
            "subtitle": "Review module datasheets and user guides",
            "instructions": [
                "View the first page of each data sheet.",
                "Review the pinout, voltage requirements, and subsystem assignments.",
                "Click View PDF to inspect specifications before moving to matching.",
            ],
            "pass_percentage": 100,
            "cooldown_seconds": 0,
            "show_correct_on_fail": False,
            "show_explanation_on_fail": False,
            "show_bucket_target_counts": True,
            "allow_datasheet_lookup": True,
            "question_ids": [],
        },
        {
            "id": "phase-matching",
            "phase_type": "subsystem_matching",
            "title": "Match Subsystems",
            "subtitle": "Drag and drop module datasheets into their subsystem buckets",
            "instructions": [
                "Assign each module datasheet card to its correct subsystem bucket.",
                "100% correct placement required to unlock the Pinout Quiz.",
                "A 15-minute review delay applies if any module is misplaced.",
            ],
            "pass_percentage": 100,
            "cooldown_seconds": 900,  # 15 minutes
            "show_correct_on_fail": False,
            "show_explanation_on_fail": False,
            "show_bucket_target_counts": True,
            "allow_datasheet_lookup": True,
            "question_ids": [],
            "matching_config": {
                "buckets": [
                    {"id": "CDHS", "label": "CDHS", "subtitle": "Command & Data Handling System", "color": "purple"},
                    {"id": "EPS", "label": "EPS", "subtitle": "Electrical Power System", "color": "emerald"},
                    {"id": "ADCS/APC", "label": "ADCS/APC", "subtitle": "Attitude Determination & Control System", "color": "blue"},
                ],
                "items": [
                    {"datasheet_id": "ds-esp32", "correct_bucket_id": "CDHS"},
                    {"datasheet_id": "ds-tmp102", "correct_bucket_id": "CDHS"},
                    {"datasheet_id": "ds-ina219", "correct_bucket_id": "EPS"},
                    {"datasheet_id": "ds-solar-eps", "correct_bucket_id": "EPS"},
                    {"datasheet_id": "ds-mpu6050", "correct_bucket_id": "ADCS/APC"},
                    {"datasheet_id": "ds-rw-motor", "correct_bucket_id": "ADCS/APC"},
                ],
            },
        },
        {
            "id": "phase-pinout",
            "phase_type": "quiz",
            "title": "Pinout Quiz",
            "subtitle": "Interactive connector jumper configuration & datasheet discrepancy check",
            "instructions": [
                "Configure jumper headers for CDHS and ADCS connectors.",
                "Watch out for datasheet discrepancies on tricky pins (select Other and explain).",
                "100% pass score required. 1-minute review cooldown applies on incorrect trials.",
            ],
            "pass_percentage": 100,
            "cooldown_seconds": 60,  # 1 minute
            "show_correct_on_fail": False,
            "show_explanation_on_fail": False,
            "show_bucket_target_counts": True,
            "allow_datasheet_lookup": True,
            "question_ids": pinout_q_ids,
        },
        {
            "id": "phase-addressing",
            "phase_type": "quiz",
            "title": "Addressing Questions",
            "subtitle": "I2C/UART address collision, protocol differences, and pin strap calculation",
            "instructions": [
                "Calculate resulting hexadecimal device addresses from hardware jumper changes.",
                "Answer bus arbitration and protocol architecture questions.",
            ],
            "pass_percentage": 100,
            "cooldown_seconds": 60,
            "show_correct_on_fail": False,
            "show_explanation_on_fail": False,
            "show_bucket_target_counts": True,
            "allow_datasheet_lookup": True,
            "question_ids": [
                str(q_addr_collision_id),
                str(q_addr_protocol_id),
                str(q_addr_range_id),
                str(q_addr_jumper_id),
            ],
        },
        {
            "id": "phase-scenarios",
            "phase_type": "quiz",
            "title": "Scenario Questions",
            "subtitle": "Hardware bus recovery & power rail fault diagnostics",
            "instructions": [
                "Diagnose live workshop fault scenarios.",
                "Provide detailed isolation steps for review by Operations.",
            ],
            "pass_percentage": 100,
            "cooldown_seconds": 60,
            "show_correct_on_fail": False,
            "show_explanation_on_fail": False,
            "show_bucket_target_counts": True,
            "allow_datasheet_lookup": True,
            "question_ids": [
                str(q_scen_lockup_id),
                str(q_scen_eps_drop_id),
            ],
        },
    ]

    all_q_ids = pinout_q_ids + [
        str(q_addr_collision_id),
        str(q_addr_protocol_id),
        str(q_addr_range_id),
        str(q_addr_jumper_id),
        str(q_scen_lockup_id),
        str(q_scen_eps_drop_id),
    ]

    standard_preset_id = uuid.uuid4()
    conn.execute(
        sa.text(
            """
            INSERT INTO pre_session_quiz_presets (
                id, name, description, question_ids, reference_attachments, phases, is_active, created_by, created_at
            ) VALUES (
                :id, :name, :description, CAST(:question_ids AS jsonb), CAST(:reference_attachments AS jsonb),
                CAST(:phases AS jsonb), :is_active, :created_by, :created_at
            )
            """
        ),
        {
            "id": standard_preset_id,
            "name": "Standard 5-Phase Instructor Readiness Pipeline",
            "description": "Full cohort-level readiness pipeline covering datasheet review, subsystem classification, pinout jumping, addressing calculations, and hardware troubleshooting.",
            "question_ids": json.dumps(all_q_ids),
            "reference_attachments": json.dumps(default_datasheets),
            "phases": json.dumps(five_phases),
            "is_active": True,
            "created_by": None,
            "created_at": now,
        },
    )


def downgrade() -> None:
    op.drop_index("ix_pre_session_quiz_phase_trials_phase_id", table_name="pre_session_quiz_phase_trials")
    op.drop_index("ix_pre_session_quiz_phase_trials_attempt_id", table_name="pre_session_quiz_phase_trials")
    op.drop_table("pre_session_quiz_phase_trials")

    op.drop_column("pre_session_quiz_attempts", "phase_states")
    op.drop_column("pre_session_quiz_attempts", "total_duration_seconds")
    op.drop_column("pre_session_quiz_attempts", "started_at")
    op.drop_column("pre_session_quiz_attempts", "locked_until")
    op.drop_column("pre_session_quiz_attempts", "phase_started_at")
    op.drop_column("pre_session_quiz_attempts", "current_phase_index")
    op.drop_column("pre_session_quiz_attempts", "status")

    op.drop_constraint("uq_pre_session_quiz_attempt_cohort_user", "pre_session_quiz_attempts", type_="unique")
    op.drop_index("ix_pre_session_quiz_attempts_cohort_id", table_name="pre_session_quiz_attempts")
    op.drop_constraint("fk_pre_session_quiz_attempts_cohort_id", "pre_session_quiz_attempts", type_="foreignkey")
    op.drop_column("pre_session_quiz_attempts", "cohort_id")

    op.drop_column("pre_session_quiz_presets", "phases")
