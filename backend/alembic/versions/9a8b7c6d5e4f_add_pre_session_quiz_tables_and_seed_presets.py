"""add pre_session_quiz tables and seed presets

Revision ID: 9a8b7c6d5e4f
Revises: f5e6d7c8b9a0
Create Date: 2026-10-25 22:00:00.000000

"""
import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "9a8b7c6d5e4f"
down_revision = "f5e6d7c8b9a0"
branch_labels = None
depends_on = None


def _row(label: str, c1: tuple[str, bool], c2: tuple[str, bool], c3: tuple[str, bool]) -> dict:
    return {
        "label": label,
        "cells": [
            {"text": c1[0], "is_correct": c1[1]},
            {"text": c2[0], "is_correct": c2[1]},
            {"text": c3[0], "is_correct": c3[1]},
        ],
    }


def upgrade() -> None:
    op.create_table(
        "pre_session_quiz_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("topic", sa.String(length=128), nullable=False, server_default="General"),
        sa.Column("question_type", sa.String(length=32), nullable=False, server_default="pinout_table"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=512), nullable=True),
        sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("table_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("allow_other", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_other_correct", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("explanation_image_url", sa.String(length=512), nullable=True),
        sa.Column("explanation_table", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pre_session_quiz_questions_topic", "pre_session_quiz_questions", ["topic"])

    op.create_table(
        "pre_session_quiz_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("question_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("reference_attachments", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "pre_session_quiz_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=True),
        sa.Column("cohort_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pre_session_quiz_presets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(CASE WHEN program_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN cohort_id IS NOT NULL THEN 1 ELSE 0 END + "
            "CASE WHEN session_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_pre_session_quiz_assignment_one_owner",
        ),
    )
    op.create_index("ix_pre_session_quiz_assignments_program_id", "pre_session_quiz_assignments", ["program_id"])
    op.create_index("ix_pre_session_quiz_assignments_cohort_id", "pre_session_quiz_assignments", ["cohort_id"])
    op.create_index("ix_pre_session_quiz_assignments_session_id", "pre_session_quiz_assignments", ["session_id"])

    op.create_table(
        "pre_session_quiz_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("preset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pre_session_quiz_presets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("auto_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_questions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_review_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_pre_session_quiz_attempts_session_id", "pre_session_quiz_attempts", ["session_id"])
    op.create_index("ix_pre_session_quiz_attempts_user_id", "pre_session_quiz_attempts", ["user_id"])

    # Seed the SpacePoint CDHS & ADCS/APC Board Pinout questions & presets
    now = datetime.now(timezone.utc)
    questions_table = sa.table(
        "pre_session_quiz_questions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("topic", sa.String),
        sa.column("question_type", sa.String),
        sa.column("title", sa.String),
        sa.column("prompt", sa.Text),
        sa.column("image_url", sa.String),
        sa.column("options", postgresql.JSONB),
        sa.column("table_config", postgresql.JSONB),
        sa.column("allow_other", sa.Boolean),
        sa.column("is_other_correct", sa.Boolean),
        sa.column("explanation", sa.Text),
        sa.column("explanation_image_url", sa.String),
        sa.column("explanation_table", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    presets_table = sa.table(
        "pre_session_quiz_presets",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("question_ids", postgresql.JSONB),
        sa.column("reference_attachments", postgresql.JSONB),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    q_cdhs_j3_id = uuid.UUID("11111111-2222-3333-4444-555555550001")
    q_cdhs_j4_id = uuid.UUID("11111111-2222-3333-4444-555555550002")
    q_cdhs_j5_id = uuid.UUID("11111111-2222-3333-4444-555555550003")
    q_cdhs_j6_id = uuid.UUID("11111111-2222-3333-4444-555555550004")
    q_cdhs_j123_id = uuid.UUID("11111111-2222-3333-4444-555555550005")
    q_cdhs_j122_id = uuid.UUID("11111111-2222-3333-4444-555555550006")

    q_adcs_j2_id = uuid.UUID("11111111-2222-3333-4444-555555550007")
    q_adcs_j3_id = uuid.UUID("11111111-2222-3333-4444-555555550008")
    q_adcs_j4_id = uuid.UUID("11111111-2222-3333-4444-555555550009")
    q_adcs_j5_id = uuid.UUID("11111111-2222-3333-4444-555555550010")
    q_adcs_j6_id = uuid.UUID("11111111-2222-3333-4444-555555550011")

    seed_questions = [
        # 1. CDHS Connector J3
        {
            "id": q_cdhs_j3_id,
            "topic": "CDHS",
            "question_type": "pinout_table",
            "title": "CDHS — Connector J3",
            "prompt": "Select the required jumper header pinout positions on Connector J3 (J31–J38) based on the CDHS subsystem and module datasheets. Leave unconnected pins unselected.",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J3",
                "header_subtitle": "J31, J32, J33, J34, J35, J36, J37, J38",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("GND", False)),
                    _row("Pin 2", ("3V3", False), ("Main", True), ("GND", True)),
                    _row("Pin 3", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin 4", ("I2C1_SCL", True), ("Main", True), ("I2C1_SDA", False)),
                    _row("Pin 5", ("I2C1_SCL", False), ("Main", True), ("I2C1_SDA", True)),
                    _row("Pin 6", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin 7", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin 8", ("3V3", False), ("Main", False), ("GND", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pin 1 connects 3V3 to Main, Pin 2 connects Main to GND, Pin 4 connects I2C1_SCL to Main, and Pin 5 connects Main to I2C1_SDA. Pins 3, 6, 7, and 8 remain open.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 2. CDHS Connector J4
        {
            "id": q_cdhs_j4_id,
            "topic": "CDHS",
            "question_type": "pinout_table",
            "title": "CDHS — Connector J4",
            "prompt": "Select the required jumper header pinout positions on Connector J4 (J41–J46) based on the CDHS subsystem and module datasheets.",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J4",
                "header_subtitle": "J41, J42, J43, J44, J45, J46",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("GND", False)),
                    _row("Pin 2", ("3V3", False), ("Main", True), ("GND", True)),
                    _row("Pin 3", ("I2C1_SCL", False), ("Main", True), ("I2C1_SDA", True)),
                    _row("Pin 4", ("I2C1_SCL", True), ("Main", True), ("I2C1_SDA", False)),
                    _row("Pin 5", ("ESP32_Pin4", False), ("Main", False), ("ESP32_Pin8", False)),
                    _row("Pin 6", ("3V3", False), ("Main", False), ("GND", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pin 1 connects 3V3 to Main, Pin 2 connects Main to GND, Pin 3 connects Main to I2C1_SDA, and Pin 4 connects I2C1_SCL to Main. Pins 5 and 6 remain open.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 3. CDHS Connector J5
        {
            "id": q_cdhs_j5_id,
            "topic": "CDHS",
            "question_type": "pinout_table",
            "title": "CDHS — Connector J5",
            "prompt": "Select the required jumper header pinout positions on Connector J5 (J51–J56) based on the CDHS subsystem and module datasheets.",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J5",
                "header_subtitle": "J51, J52, J53, J54, J55, J56",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("GND", False)),
                    _row("Pin 2", ("3V3", False), ("Main", True), ("GND", True)),
                    _row("Pin 3", ("I2C1_SCL", True), ("Main", True), ("I2C1_SDA", False)),
                    _row("Pin 4", ("I2C1_SCL", False), ("Main", True), ("I2C1_SDA", True)),
                    _row("Pin 5", ("Main_Pin5", True), ("3.3V", True), ("Main_Pin6", False)),
                    _row("Pin 6", ("Main_Pin5", False), ("3V3", True), ("Main_Pin6", True)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pins 1 & 2 configure power (3V3 & GND), Pins 3 & 4 configure I2C1 (SCL & SDA), and Pins 5 & 6 connect Main_Pin5 and Main_Pin6 to 3.3V/3V3.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 4. CDHS Connector J6 (Tricky Datasheet Error Question!)
        {
            "id": q_cdhs_j6_id,
            "topic": "CDHS",
            "question_type": "pinout_table",
            "title": "CDHS — Connector J6 (MicroSD SPI Interface)",
            "prompt": "Compare the Connector J6 pinout options below (from the CDHS datasheet) against the actual pinout of the MicroSD module. Select the required jumpers, or if you find a pinout error/mismatch, select 'Other' and explain.",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J6",
                "header_subtitle": "J61, J62, J63, J64, J65, J66",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin 2", ("3V3", False), ("Main", False), ("5V", False)),
                    _row("Pin 3", ("SPI_MISO", False), ("Main", False), ("SPI_MOSI", False)),
                    _row("Pin 4", ("SPI_MISO", False), ("Main", False), ("SPI_MOSI", False)),
                    _row("Pin 5", ("SPI_CLK", False), ("Main", False), ("SPI_CS", False)),
                    _row("Pin 6", ("SPI_CLK", False), ("Main", False), ("SPI_CS", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": True,
            "explanation": "The error is plugged in the CDHS datasheet table above (Pin 1/2/5/6 do not align with the MicroSD module's actual pinout). The actual J6 pinout and required jumper configuration is shown in the table below:",
            "explanation_image_url": None,
            "explanation_table": {
                "connector_name": "J6",
                "header_subtitle": "J61, J62, J63, J64, J65, J66 (Actual Pinout)",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("5V", False)),
                    _row("Pin 2", ("SPI_CLK", False), ("Main", True), ("SPI_CS", True)),
                    _row("Pin 3", ("SPI_MISO", False), ("Main", True), ("SPI_MOSI", True)),
                    _row("Pin 4", ("SPI_CLK", True), ("Main", True), ("SPI_CS", False)),
                    _row("Pin 5", ("SPI_MISO", True), ("Main", True), ("SPI_MOSI", False)),
                    _row("Pin 6", ("3V3", False), ("Main", True), ("GND", True)),
                ],
            },
            "is_active": True,
            "created_at": now,
        },
        # 5. CDHS Connector J123 (5V_ESP32 Jumper)
        {
            "id": q_cdhs_j123_id,
            "topic": "CDHS",
            "question_type": "mcq",
            "title": "CDHS — Connector J123 (5V_ESP32 Power Jumper)",
            "prompt": "You can turn on the ESP32 module using the 5V from the EPS by connecting a jumper between the two pins of connector J123. How should Connector J123 be configured?",
            "image_url": None,
            "options": [
                {"text": "Leave Open", "is_correct": False},
                {"text": "Short (Connect the Jumper Header Between Both Pins)", "is_correct": True},
            ],
            "table_config": None,
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Shorting J123 powers the ESP32 module using the 5V rail from the EPS.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 6. CDHS Connector J122 (3V3_ESP32 Jumper)
        {
            "id": q_cdhs_j122_id,
            "topic": "CDHS",
            "question_type": "mcq",
            "title": "CDHS — Connector J122 (3V3_ESP32 Power Jumper)",
            "prompt": "You can power the system using the 3.3V from the ESP32 module by connecting a jumper between the two pins of connector J122. Warning: You may damage the system if a jumper is connected between the two pins of connector J122 while the system is powered by the EPS. When powered by the EPS, how should J122 be configured?",
            "image_url": None,
            "options": [
                {"text": "Leave Open", "is_correct": True},
                {"text": "Short (Connect the Jumper Header Between Both Pins)", "is_correct": False},
            ],
            "table_config": None,
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "J122 must be left open while the system is powered by the EPS to avoid damaging the board.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 7. ADCS/APC Connector J2
        {
            "id": q_adcs_j2_id,
            "topic": "ADCS/APC",
            "question_type": "pinout_table",
            "title": "ADCS/APC — Connector J2",
            "prompt": "Select the required jumper header pinout positions on ADCS/APC Connector J2 (J23, J24, J25).",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J2",
                "header_subtitle": "J23, J24, J25",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("NA", False), ("3V3", False), ("NA", False)),
                    _row("Pin 2", ("NA", False), ("GND", False), ("NA", False)),
                    _row("Pin 3", ("UART1_RX", True), ("Main", True), ("UART2_RX", False)),
                    _row("Pin 4", ("UART1_TX", True), ("Main", True), ("UART2_TX", False)),
                    _row("Pin 5", ("", False), ("Any Pin", False), ("", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pin 3 connects UART1_RX to Main and Pin 4 connects UART1_TX to Main.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 8. ADCS/APC Connector J3
        {
            "id": q_adcs_j3_id,
            "topic": "ADCS/APC",
            "question_type": "pinout_table",
            "title": "ADCS/APC — Connector J3",
            "prompt": "Select the required jumper header pinout positions on ADCS/APC Connector J3 (J31, J35, J37, J39).",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J3",
                "header_subtitle": "J31, J35, J37, J39",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("GND", False)),
                    _row("Pin 2", ("NA", False), ("GND", False), ("NA", False)),
                    _row("Pin 3", ("NA", False), ("I2C1_SCL", False), ("NA", False)),
                    _row("Pin 4", ("NA", False), ("I2C1_SDA", False), ("NA", False)),
                    _row("Pin 5", ("NA", False), ("Main", False), ("I2C1_SDA", False)),
                    _row("Pin 6", ("NA", False), ("Any Pin", False), ("NA", False)),
                    _row("Pin 7", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin 8", ("NA", False), ("Any Pin", False), ("NA", False)),
                    _row("Pin 9", ("3V3", False), ("Main", False), ("GND", False)),
                    _row("Pin10", ("NA", False), ("Any Pin", False), ("NA", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pin 1 connects 3V3 to Main; the remaining direct center pins (GND, I2C1_SCL, I2C1_SDA) do not require 1-2 or 2-3 bridging.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 9. ADCS/APC Connector J4
        {
            "id": q_adcs_j4_id,
            "topic": "ADCS/APC",
            "question_type": "pinout_table",
            "title": "ADCS/APC — Connector J4 (Reaction Wheel Motor)",
            "prompt": "Select the jumper header pinout positions on ADCS/APC Connector J4 (J43, J44, J41, J42, J45, J46) for the reaction wheel motor driver.",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J4",
                "header_subtitle": "J43, J44, J41, J42, J45, J46",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("GPIOA", True), ("Main", True), ("GPIOB", False)),
                    _row("Pin 2", ("GPIOA", False), ("Main", True), ("GPIOB", True)),
                    _row("Pin 3", ("5V", True), ("Main", True), ("GND", False)),
                    _row("Pin 4", ("5V", False), ("Main", True), ("GND", True)),
                    _row("Pin 5", ("GPIOC", True), ("Main", True), ("GPIOD", False)),
                    _row("Pin 6", ("GPIOC", False), ("Main", True), ("GPIOD", True)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Here, you choose either GPIOA and GPIOB (Pins 1–2) or GPIOC and GPIOD (Pins 5–6) based on which motor slot you connect the reaction wheel to, with 5V (Pin 3) and GND (Pin 4) supplying power.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 10. ADCS/APC Connector J5
        {
            "id": q_adcs_j5_id,
            "topic": "ADCS/APC",
            "question_type": "pinout_table",
            "title": "ADCS/APC — Connector J5",
            "prompt": "Select the required jumper header pinout positions on ADCS/APC Connector J5 (J51, J52, J53, J54, JR12, JR11).",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J5",
                "header_subtitle": "J51, J52, J53, J54, JR12, JR11",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("GND", False)),
                    _row("Pin 2", ("3V3", False), ("Main", True), ("GND", True)),
                    _row("Pin 3", ("I2C1_SCL", True), ("Main", True), ("I2C1_SDA", False)),
                    _row("Pin 4", ("I2C1_SCL", False), ("Main", True), ("I2C1_SDA", True)),
                    _row("Pin 5", ("Main_Pin5", True), ("3.3V", True), ("Main_Pin6", False)),
                    _row("Pin 6", ("Main_Pin5", False), ("3V3", True), ("Main_Pin6", True)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pins 1 & 2 connect 3V3 and GND, Pins 3 & 4 connect I2C1_SCL and I2C1_SDA, and Pins 5 & 6 connect Main_Pin5 and Main_Pin6 to 3.3V/3V3.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
        # 11. ADCS/APC Connector J6
        {
            "id": q_adcs_j6_id,
            "topic": "ADCS/APC",
            "question_type": "pinout_table",
            "title": "ADCS/APC — Connector J6",
            "prompt": "Select the required jumper header pinout positions on ADCS/APC Connector J6 (J61, J62, J63, J64).",
            "image_url": None,
            "options": [],
            "table_config": {
                "connector_name": "J6",
                "header_subtitle": "J61, J62, J63, J64",
                "columns": ["1", "2", "3"],
                "rows": [
                    _row("Pin 1", ("3V3", True), ("Main", True), ("5V", False)),
                    _row("Pin 2", ("UART1_RX", True), ("Main", True), ("UART1_TX", False)),
                    _row("Pin 3", ("UART1_RX", False), ("Main", True), ("UART1_TX", True)),
                    _row("Pin 4", ("NA", False), ("GND", False), ("NA", False)),
                ],
            },
            "allow_other": True,
            "is_other_correct": False,
            "explanation": "Pin 1 connects 3V3 to Main, Pin 2 connects UART1_RX to Main, and Pin 3 connects Main to UART1_TX.",
            "explanation_image_url": None,
            "explanation_table": None,
            "is_active": True,
            "created_at": now,
        },
    ]

    op.bulk_insert(questions_table, seed_questions)

    preset_full_id = uuid.UUID("22222222-3333-4444-5555-666666660001")
    preset_cdhs_id = uuid.UUID("22222222-3333-4444-5555-666666660002")
    preset_adcs_id = uuid.UUID("22222222-3333-4444-5555-666666660003")

    op.bulk_insert(
        presets_table,
        [
            {
                "id": preset_full_id,
                "name": "Board Datasheet Pinout Options (CDHS & ADCS/APC — Full)",
                "description": "Complete pre-session hardware pinout verification covering CDHS (J3–J6, J123, J122) and ADCS/APC (J2–J6), including theConnector J6 MicroSD datasheet discrepancy check.",
                "question_ids": [
                    str(q_cdhs_j3_id),
                    str(q_cdhs_j4_id),
                    str(q_cdhs_j5_id),
                    str(q_cdhs_j6_id),
                    str(q_cdhs_j123_id),
                    str(q_cdhs_j122_id),
                    str(q_adcs_j2_id),
                    str(q_adcs_j3_id),
                    str(q_adcs_j4_id),
                    str(q_adcs_j5_id),
                    str(q_adcs_j6_id),
                ],
                "reference_attachments": [],
                "is_active": True,
                "created_at": now,
            },
            {
                "id": preset_cdhs_id,
                "name": "CDHS Board Pinout Options (J3–J6, J123, J122)",
                "description": "CDHS subsystem connector jumper verification including the tricky J6 MicroSD SPI pinout check and ESP32 power jumpers.",
                "question_ids": [
                    str(q_cdhs_j3_id),
                    str(q_cdhs_j4_id),
                    str(q_cdhs_j5_id),
                    str(q_cdhs_j6_id),
                    str(q_cdhs_j123_id),
                    str(q_cdhs_j122_id),
                ],
                "reference_attachments": [],
                "is_active": True,
                "created_at": now,
            },
            {
                "id": preset_adcs_id,
                "name": "ADCS/APC Board Pinout Options (J2–J6)",
                "description": "ADCS/APC subsystem connector jumper verification including UART, I2C, and reaction wheel motor slot selection.",
                "question_ids": [
                    str(q_adcs_j2_id),
                    str(q_adcs_j3_id),
                    str(q_adcs_j4_id),
                    str(q_adcs_j5_id),
                    str(q_adcs_j6_id),
                ],
                "reference_attachments": [],
                "is_active": True,
                "created_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_pre_session_quiz_attempts_user_id", table_name="pre_session_quiz_attempts")
    op.drop_index("ix_pre_session_quiz_attempts_session_id", table_name="pre_session_quiz_attempts")
    op.drop_table("pre_session_quiz_attempts")

    op.drop_index("ix_pre_session_quiz_assignments_session_id", table_name="pre_session_quiz_assignments")
    op.drop_index("ix_pre_session_quiz_assignments_cohort_id", table_name="pre_session_quiz_assignments")
    op.drop_index("ix_pre_session_quiz_assignments_program_id", table_name="pre_session_quiz_assignments")
    op.drop_table("pre_session_quiz_assignments")

    op.drop_table("pre_session_quiz_presets")

    op.drop_index("ix_pre_session_quiz_questions_topic", table_name="pre_session_quiz_questions")
    op.drop_table("pre_session_quiz_questions")
