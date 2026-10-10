"""website articles

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-09

Step 5 — Articles, Blog & Editorial Review Queue: creates the `articles`
table and seeds the two flagship articles as published (attributed to the
oldest user account when one exists, skipped otherwise).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'a5b6c7d8e9f0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


SEED_3_MARKDOWN = """Traditional space education has often been constrained by high-level mathematics and purely theoretical models. While calculating orbital trajectories and studying atmospheric attenuation are crucial, they can feel disconnected from the day-to-day realities of operational space missions. To bridge this gap, modern classrooms are integrating real-time simulation platforms that replicate the high-stakes environment of a mission control center.

At the heart of this educational revolution is SpacePoint's custom platform, Madar. Madar provides students with a live interface that connects directly to physical or simulated CubeSats. Through this portal, students do not just read about telemetry; they actively query sensors, parse data packets, and visualize critical parameters such as angular velocities, battery temperatures, and subsystem voltages in real time.

## Interactive Telemetry and Commanding

Using real-time simulation interfaces, students participate in structured scenarios where they assume specific mission roles:

- **Flight Controller:** Monitoring live plots and identifying out-of-limit readings before they trigger a system-level failure.
- **Operations Manager:** Deciding when to execute commands, taking into account the satellite's power reserves and orbital visibility.
- **Systems Engineer:** Troubleshooting sensor communication failures and writing code patches to correct telemetry anomalies.

By simulating complex flight scenarios—such as detumbling a spinning satellite or managing battery constraints during an eclipse—students learn to apply critical thinking and real-time decision making under pressure. These hands-on exercises demonstrate how aerospace theory applies directly to real missions, providing students with the technical and collaborative skills required for the UAE's rapidly growing space sector.
"""

SEED_1_MARKDOWN = """Nanosatellites, commonly known as CubeSats, have fundamentally changed the dynamics of space exploration. By drastically lowering structural barriers and deployment costs, they have democratized access to Earth's orbit, enabling academic institutions and private enterprises alike to conduct valid experiments and collect valuable orbital data. For students, this presents an unprecedented opportunity to gain hands-on training with physical space systems.

Inside a modern space engineering workshop, students are not merely studying textbooks; they are working directly with educational integration kits like the SatKit. This practical approach shifts the learning paradigm, requiring students to wire sub-modules, integrate structural sensors, and perform structural safety validation. Working at this scale exposes learners to real-world complexities such as electrical ground loops, data bus addressing, and noise attenuation.

## The Subsystem Integration Process

A satellite is a collection of interconnected systems, each performing a vital function. When students perform electrical integration, they gain exposure to the four core pillars:

- **CDHS (Command and Data Handling System):** The central computer executing the scripts, processing sensor telemetry, and storing payload data.
- **EPS (Electrical Power System):** Regulating voltage, managing solar panels, and ensuring rechargeable batteries safely distribute power.
- **ADCS (Attitude Determination and Control System):** Orienting the satellite in space using reaction wheels, magnetorquers, and gyroscopes.
- **Mechanical Assembly & Testing:** Structuring the CubeSat to survive the extreme vibration of launch and thermal dynamics of space.

Finally, these workshops empower students by cultivating future-ready cognitive capabilities. The process of debugging communication errors, aligning sensors, and writing script patches requires team coordination, rigorous documentation, and critical analysis. These are the same capabilities that prepare the next generation of engineers to enter UAE space initiatives and general aerospace roles.
"""

SEED_2_MARKDOWN = """The United Arab Emirates has rapidly positioned itself as a key player in the global space exploration sector. With historic accomplishments such as the Hope Probe's arrival at Mars, the deployment of local astronauts to the International Space Station, and the ambitious Emirates Mission to the Asteroid Belt (EMA), the region has shown that its space goals are long-term, structural, and state-of-the-art.

However, to sustain these aerospace achievements, a strong connection must be forged between the space sector and academic curricula. Space education cannot rely solely on dry textbook theories. Instead, schools and universities must integrate practical, project-based engineering opportunities that reflect the active workflows of contemporary mission control rooms and mechanical integration labs.

Collaborations between specialized education groups like SpacePoint and national entities (such as the UAE Space Agency and the Abdulla Al Ghurair Foundation) are vital in establishing this hands-on model. By bringing satellite hardware, interactive simulation platforms, and customized training frameworks directly to students, these entities are converting passive learners into active creators and technical leaders.

As we look to the future, the expansion of regional STEM programs is essential. Educating the next generation with aerospace capabilities ensures that local talent will not only support upcoming GCC space programs but will actively lead scientific discoveries. The mission begins in the classroom, where inspiring space education builds the foundations for tomorrow's orbital engineering.
"""


def upgrade() -> None:
    op.create_table(
        'articles',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('content_markdown', sa.Text(), nullable=False),
        sa.Column('content_html', sa.Text(), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='EDUCATION'),
        sa.Column('cover_image_url', sa.String(length=512), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='draft'),
        sa.Column('author_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_display_name', sa.String(length=255), nullable=False),
        sa.Column('author_role', sa.String(length=128), nullable=True),
        sa.Column('author_initials', sa.String(length=8), nullable=True),
        sa.Column('reviewer_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewer_feedback', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('featured_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('slug'),
    )
    op.create_index('ix_articles_slug', 'articles', ['slug'], unique=True)

    # Render seed HTML with the same pipeline the routers use, so seeded
    # rows look exactly like contributor-published ones.
    from app.services.articles.markdown import render_markdown_to_html

    conn = op.get_bind()
    for article_id, slug, title, summary, md, category, cover, byline, role, initials, published_at, order in [
        (
            '30000000-0000-4000-8000-000000000003',
            'mission-control-real-time-simulation-platforms-in-the-classroom',
            'Mission Control: Real-time Simulation Platforms in the Classroom',
            'Fatima Al Hashimi discusses how real-time simulation platforms like Madar transform classroom learning into active mission control centers.',
            SEED_3_MARKDOWN,
            'SCIENCE',
            '/assets/img/WhatsApp_Image_2026-03-03_at_4.37.46_PM.jpeg',
            'Rayan Al Dahre',
            'Lead Systems Engineer',
            'RA',
            '2026-02-01T00:00:00Z',
            1,
        ),
        (
            '30000000-0000-4000-8000-000000000001',
            'designing-the-future-a-students-guide-to-cubesat-engineering',
            "Designing the Future: A Student's Guide to CubeSat Engineering",
            'Sarah Al Kaabi shares insights into CubeSat engineering, hands-on assembly, and space systems integration for students.',
            SEED_1_MARKDOWN,
            'TECHNOLOGY',
            '/assets/img/The Mission.jpg',
            'Sarah Al Kaabi',
            'Aerospace Instructor',
            'SA',
            '2026-01-01T00:00:00Z',
            2,
        ),
        (
            '30000000-0000-4000-8000-000000000002',
            'bridging-the-gap-space-education-in-the-uae-and-gcc-region',
            'Bridging the Gap: Space Education in the UAE and GCC Region',
            'Ahmad Al Falasi shares insights into space education programs, national visions, and academic integrations across the UAE and GCC.',
            SEED_2_MARKDOWN,
            'EDUCATION',
            '/assets/img/The Journey.jpg',
            'Ahmad Al Falasi',
            'Space Education Expert',
            'AA',
            '2026-01-15T00:00:00Z',
            3,
        ),
    ]:
        conn.execute(
            sa.text(
                """
                INSERT INTO articles
                    (id, title, slug, summary, content_markdown, content_html,
                     category, cover_image_url, status, author_id,
                     author_display_name, author_role, author_initials,
                     published_at, featured_order)
                SELECT
                    :id, :title, :slug, :summary, :md, :html,
                    :category, :cover, 'published', u.id,
                    :byline, :author_role, :initials,
                    CAST(:published_at AS timestamptz), :featured_order
                FROM (SELECT id FROM users ORDER BY created_at LIMIT 1) AS u
                WHERE NOT EXISTS (SELECT 1 FROM articles WHERE slug = :slug)
                """
            ),
            {
                "id": article_id,
                "title": title,
                "slug": slug,
                "summary": summary,
                "md": md,
                "html": render_markdown_to_html(md),
                "category": category,
                "cover": cover,
                "byline": byline,
                "author_role": role,
                "initials": initials,
                "published_at": published_at,
                "featured_order": order,
            },
        )


def downgrade() -> None:
    op.drop_index('ix_articles_slug', table_name='articles')
    op.drop_table('articles')
