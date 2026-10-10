"""website people showcase

Revision ID: b6c7d8e9f0a1
Revises: a5b6c7d8e9f0
Create Date: 2026-10-09

Step 6 — People Showcase: creates `website_team_members`, `website_ambassadors`,
`website_alumni`, and `student_missions`, seeding records that mirror the
marketing site's existing cards (only when each table is empty).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = 'b6c7d8e9f0a1'
down_revision = 'a5b6c7d8e9f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'website_team_members',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=128), nullable=False),
        sa.Column('department', sa.String(length=64), nullable=False, server_default='Engineering'),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=False),
        sa.Column('linkedin_url', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'website_ambassadors',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('university', sa.String(length=255), nullable=False),
        sa.Column('major', sa.String(length=128), nullable=True),
        sa.Column('year', sa.String(length=32), nullable=True),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=False),
        sa.Column('badge', sa.String(length=64), nullable=True),
        sa.Column('linkedin_url', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'website_alumni',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('program_completed', sa.String(length=128), nullable=False),
        sa.Column('current_role', sa.String(length=255), nullable=False),
        sa.Column('testimonial', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=False),
        sa.Column('linkedin_url', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'student_missions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_name', sa.String(length=255), nullable=False),
        sa.Column('project_title', sa.String(length=255), nullable=False),
        sa.Column('category', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('docx_url', sa.String(length=512), nullable=True),
        sa.Column('photo_url', sa.String(length=512), nullable=True),
        sa.Column('metrics_json', JSONB(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO website_team_members
            (id, name, role, department, photo_url, display_order, is_active)
        SELECT * FROM (VALUES
            ('40000000-0000-4000-8000-000000000001'::uuid, 'Abdullah AlSalmani', 'CEO, Co-Founder', 'Leadership', '/assets/img/Team/Abdullah.png', 1, true),
            ('40000000-0000-4000-8000-000000000002'::uuid, 'Abubaker Alzubaidi', 'COO, Co-Founder', 'Leadership', '/assets/img/Team/Abubaker.png', 2, true),
            ('40000000-0000-4000-8000-000000000003'::uuid, 'Ahmad Yacine', 'Operations & Program Development Lead', 'Operations', '/assets/img/Team/Ahmad.png', 3, true),
            ('40000000-0000-4000-8000-000000000004'::uuid, 'Fatme Faour', 'Marketing Lead', 'Operations', '/assets/img/Team/Fatme.png', 4, true),
            ('40000000-0000-4000-8000-000000000005'::uuid, 'Rayan AlDhaheri', 'Instructor Lead', 'Education', '/assets/img/Team/Rayan.png', 5, true),
            ('40000000-0000-4000-8000-000000000006'::uuid, 'Mizna Alzahmi', 'Instructor Lead', 'Education', '/assets/img/Team/Mizna.png', 6, true)
        ) AS seed(id, name, role, department, photo_url, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM website_team_members)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO website_ambassadors
            (id, name, university, badge, photo_url, display_order, is_active)
        SELECT * FROM (VALUES
            ('40000000-0000-4000-8000-000000000011'::uuid, 'Miryam El Samad', 'Lebanon', '🇱🇧', '/assets/img/Ambassadors/Miryam El Samad.png', 1, true),
            ('40000000-0000-4000-8000-000000000012'::uuid, 'Derrick Tebusweke', 'Uganda', '🇺🇬', '/assets/img/Ambassadors/Derrick TebuswekeGboyinde.png', 2, true),
            ('40000000-0000-4000-8000-000000000013'::uuid, 'Samuel Gboyinde', 'Nigeria', '🇳🇬', '/assets/img/Ambassadors/Samuel Gboyinde.png', 3, true),
            ('40000000-0000-4000-8000-000000000014'::uuid, 'Tumo Fortunate Kedumele', 'Botswana', '🇧🇼', '/assets/img/Ambassadors/Tumo Fortunate Kedumele BotswanaEl Samad.png', 4, true),
            ('40000000-0000-4000-8000-000000000015'::uuid, 'Emebet Mehabaw', 'Ethiopia', '🇪🇹', '/assets/img/Ambassadors/Emebet Mehabaw.png', 5, true),
            ('40000000-0000-4000-8000-000000000016'::uuid, 'Eden Abeselom', 'Ethiopia', '🇪🇹', '/assets/img/Ambassadors/Eden Abeselom.png', 6, true),
            ('40000000-0000-4000-8000-000000000017'::uuid, 'Basma Eldrsee', 'Libya', '🇱🇾', '/assets/img/Ambassadors/Basma Eldrsee.png', 7, true)
        ) AS seed(id, name, university, badge, photo_url, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM website_ambassadors)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO website_alumni
            (id, name, program_completed, "current_role", photo_url, linkedin_url, display_order, is_active)
        SELECT * FROM (VALUES
            ('40000000-0000-4000-8000-000000000021'::uuid, 'Rayan AlDhaheri', 'Electrical Engineering', 'Intern, EDGE', '/assets/img/Alumni/Rayan.png', 'https://www.linkedin.com/in/rayan-aldhaheri', 1, true),
            ('40000000-0000-4000-8000-000000000022'::uuid, 'Halima Barshed', 'Communication Engineering', 'Engineer, Ericsson', '/assets/img/Alumni/Halima Barshed.png', 'https://www.linkedin.com/in/halima-barshed-911741208', 2, true),
            ('40000000-0000-4000-8000-000000000023'::uuid, 'Lameya AlDhaheri', 'Electrical Engineering', 'Research Assistant, UAEU | ADNOC', '/assets/img/Alumni/Lameya AlDhaheri.png', 'https://www.linkedin.com/in/lameya-aldhaheri-194bb5289', 3, true),
            ('40000000-0000-4000-8000-000000000024'::uuid, 'Hassa Alketbi', 'Aerospace Engineering', 'Satellite Engineer, NSSTC', '/assets/img/Alumni/Hassa Alketbi.png', 'https://www.linkedin.com/in/hassa-alketbi-0a08b430a', 4, true),
            ('40000000-0000-4000-8000-000000000025'::uuid, 'Sami Meetani', 'Electrical Engineering', 'Amazon Robotics, USA', '/assets/img/Alumni/Sami Meetani.png', 'https://www.linkedin.com/in/samimeetani', 5, true),
            ('40000000-0000-4000-8000-000000000026'::uuid, 'Muzoon Almazrouei', 'Aerospace Engineering', 'Intern, Dassault Aviation, France', '/assets/img/Alumni/Muzoon Almazrouei.png', 'https://www.linkedin.com/in/muzoon-almazrouei-62b184369', 6, true),
            ('40000000-0000-4000-8000-000000000027'::uuid, 'Noor Albastaki', 'Health, Safety and Environment', 'Intern, ADNOC Group | Rashid Hospital', '/assets/img/Alumni/Noor Albastaki.png', 'https://www.linkedin.com/in/noor-albastaki', 7, true),
            ('40000000-0000-4000-8000-000000000028'::uuid, 'Ziad Sefelnasr', 'Master’s Degree', 'Germany', '/assets/img/Alumni/Ziad Sefelnasr.png', 'https://www.linkedin.com/in/ziad-sefelnasr-7ba3a220b', 8, true),
            ('40000000-0000-4000-8000-000000000029'::uuid, 'Kassam Dakhlalah', 'Robotics and Embedded Systems', 'Engineer, Lootah Tech', '/assets/img/Alumni/Kassam Dakhlalah.png', 'https://www.linkedin.com/in/eng-kassam-dakhlalah-2b44bb207', 9, true),
            ('40000000-0000-4000-8000-000000000030'::uuid, 'Osama Akila', 'Machine Learning', 'Intern, Smart Link', '/assets/img/Alumni/Osama Akila.png', 'https://www.linkedin.com/in/osama-mahmoud-akila-9a847a268', 10, true),
            ('40000000-0000-4000-8000-000000000031'::uuid, 'Mariam Alketbi', 'Thermal Engineering', 'Intern, MBRSC  Dassault Aviation', '/assets/img/Alumni/Mariam Alketbi.png', 'https://www.linkedin.com/in/maryam-al-ketbi-9a88b8290', 11, true),
            ('40000000-0000-4000-8000-000000000032'::uuid, 'Sawsan Omira', 'Aerospace Engineering', 'Intern, Emirates', '/assets/img/Alumni/Sawsan Omira.png', 'https://www.linkedin.com/in/sawsanomira', 12, true)
        ) AS seed(id, name, program_completed, "current_role", photo_url, linkedin_url, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM website_alumni)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO student_missions
            (id, student_name, project_title, category, description, docx_url, photo_url, metrics_json, display_order, is_active)
        SELECT * FROM (VALUES
            ('40000000-0000-4000-8000-000000000041'::uuid, 'Abdalla Osama', 'Satellite Telemetry Dashboard', 'Student Research', 'This project focuses on building a complete real-time telemetry dashboard system for a satellite simulation. The system starts from sensor data acquisition on the satellite side using ESP32, then transmits the data wirelessly via HC-12, passes through an MQTT broker, and finally gets stored and visualized using InfluxDB and Grafana dashboards.

I started this project to understand how real-time data flows from hardware all the way to user interfaces. Throughout the process, I gained hands-on experience in embedded systems, communication protocols like MQTT, and data visualization tools. I also worked on integrating multiple technologies together, including microcontrollers, Python scripting, and web-based dashboards.

What stood out to me the most is how everything connects as one pipeline. Instead of seeing each part separately, I began to understand how data moves across systems in real-time, turning raw sensor readings into meaningful visual insights', NULL, '/Students Projects/Abdalla Osama (Internship Project)/Abdalla Osama (Internship Project).jpg', NULL::jsonb, 1, true),
            ('40000000-0000-4000-8000-000000000042'::uuid, 'Jouri Ahmed Alobaidly', 'ATMO-1', 'School Project', 'This project focuses on designing a CubeSat mission, ATMO-1, by integrating key subsystems like power (solar panels), data handling (CDHS), memory (FRAM & SRAM), and signal processing, while considering orbit selection (GEO) for continuous Earth monitoring.

I started this project to understand how satellites function as complete systems rather than separate parts. Through it, I explored power distribution, data processing, and how design choices impact performance.

What stood out most is how everything connects, shifting my thinking from individual components to a fully integrated, real-world satellite system.', NULL, '/Students Projects/Jouri Ahmed Alobaidly (School Project)/Jouri Ahmed Alobaidly (School Project).jpeg', NULL::jsonb, 2, true),
            ('40000000-0000-4000-8000-000000000043'::uuid, 'Kassam Dakhlalah', 'LoRa-Based Satellite Dashboard', 'Student Research', 'This project focuses on designing a real time interactive CubeSat telemetry dashboard that serves as a complete ground station interface. The system architecture begins with raw telemetry packets received from a CubeSat, which are processed, stored, and then dynamically visualized. The dashboard provides a comprehensive view of the satellite’s health through live data charts, 3D orientation models, global tracking maps, and historical logs to analyze performance over time.

Working through the development process inspired me to see the potential of data visualization, giving me the ideas and skills to build my own custom dashboards for various sensor readings in my future personal projects.', NULL, '/Students Projects/Kassam Dakhlalah/Kassam Dakhlalah.jpeg', NULL::jsonb, 3, true),
            ('40000000-0000-4000-8000-000000000044'::uuid, 'Lameya AlDhaheri', 'Debris Avoidance System', 'AI Project', 'This project focuses on designing an embedded system for space debris detection and orientation stabilization. The system starts with capturing images using a camera, followed by processing them through an AI-based model to detect debris and determine its position (left, center, or right). Based on this output, the system makes a decision and uses an IMU and a reaction wheel to adjust and stabilize the system’s orientation.

I started this project out of curiosity about how perception and control can work together in real-time, especially in space-related applications. As I worked through it, I gained experience in computer vision, dataset preparation, model training, and embedded system design, including RTOS-based task structuring.

What meant the most to me is how it shifted my thinking from isolated components to a complete system. Instead of just focusing on AI or hardware alone, I started seeing how sensing, decision-making, and control all come together to create an intelligent and responsive system.', NULL, '/Students Projects/Lamya AlDhaheri (AI Project)/Lamya AlDhaheri (AI Project).jpeg', NULL::jsonb, 4, true),
            ('40000000-0000-4000-8000-000000000045'::uuid, 'Nour Arnaout', 'Thermal Analysis', 'Thermal Analysis', 'Thermal management is usually overlooked in CubeSat projects, but when I started thinking about how a satellite swings between extreme heat in sunlight and freezing cold in eclipse every 90 minutes, it became something I really wanted to understand.

In this project, I worked on the thermal analysis and simulation of SpacePoint’s 1U CubeSat. I started with simplified lumped-system hand calculations, then moved to detailed simulations using ANSYS Fluent. I analyzed the hot case with maximum solar flux, albedo, and Earth IR while all components are running, the cold case in full eclipse with almost no external heat, and a transient simulation of a full 90-minute orbit (60 minutes in sunlight and 30 minutes in shadow) to capture real temperature cycling.

Through this, I gained hands-on experience with radiative heat transfer, emissivity and absorptivity calculations for materials and solar panels, internal heat generation based on component datasheets, CAD simplification, and both steady-state and transient simulations.

What really stood out is how I stopped seeing it as separate parts and started seeing it as one complete thermal system, where every surface, placement, and material choice directly affects the satellite’s reliability and survival in space', NULL, '/Students Projects/Nour Arnaout (Thermal Analysis)/Nour Arnaout (Thermal Analysis).jpg', NULL::jsonb, 5, true),
            ('40000000-0000-4000-8000-000000000046'::uuid, 'Rayan AlDhaheri', 'EPS Project', 'EPS Project', 'This project focuses on designing a complete Electrical Power System (EPS) for a CubeSat satellite. The system architecture begins with the solar panels’ energy, followed by an MPPT stage, then battery storage, and finally regulated power distribution to all subsystems such as the onboard computer and sensors.

I started this project out of a genuine curiosity to understand how satellites actually manage and sustain their power in space. As I worked through it, I gained experience in power electronics, PCB design, and system integration.

What meant the most to me is how it changed the way I think. I stopped looking at parts separately and started seeing the whole system come together into something real and reliable.', NULL, '/Students Projects/Rayan AlDhaheri (EPS Project)/Rayan AlDhaheri (EPS Project).jpeg', NULL::jsonb, 6, true)
        ) AS seed(id, student_name, project_title, category, description, docx_url, photo_url, metrics_json, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM student_missions)
        """
    ))

def downgrade() -> None:
    op.drop_table('student_missions')
    op.drop_table('website_alumni')
    op.drop_table('website_ambassadors')
    op.drop_table('website_team_members')
