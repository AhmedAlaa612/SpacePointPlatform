"""website content

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-09

Step 4 — FAQs, Media Coverage & Monthly Newsletters: creates
`website_faqs`, `media_clippings`, `newsletters`, and `website_leads`,
and seeds sample FAQs plus the Gulf News / WAM clippings when empty.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'website_faqs',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=False, server_default='General'),
        sa.Column('question', sa.String(length=255), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'media_clippings',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('publisher_name', sa.String(length=255), nullable=False),
        sa.Column('article_title', sa.String(length=255), nullable=False),
        sa.Column('article_url', sa.String(length=512), nullable=False),
        sa.Column('published_date', sa.String(length=64), nullable=False),
        sa.Column('logo_url', sa.String(length=512), nullable=True),
        sa.Column('is_arabic', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('snippet', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'newsletters',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('issue_date', sa.String(length=64), nullable=False),
        sa.Column('cover_url', sa.String(length=512), nullable=True),
        sa.Column('file_url', sa.String(length=512), nullable=False),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'website_leads',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('lead_type', sa.String(length=32), nullable=False, server_default='newsletter'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='new'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_website_leads_email_type', 'website_leads', ['email', 'lead_type'])

    conn = op.get_bind()
    conn.execute(sa.text(
        """
        INSERT INTO website_faqs
            (id, category, question, answer, display_order, is_active)
        SELECT * FROM (VALUES
            ('20000000-0000-4000-8000-000000000001'::uuid, 'General', 'What is SpacePoint?', 'SpacePoint is a UAE-based space education company that delivers hands-on satellite engineering workshops, programs, and educational kits for schools, universities, and institutions.', 1, true),
            ('20000000-0000-4000-8000-000000000002'::uuid, 'General', 'Who are SpacePoint programs designed for?', 'Our programs are designed for school students (Ages 12+), university students, STEM clubs, educational institutions, youth organizations, and future space enthusiasts.', 2, true),
            ('20000000-0000-4000-8000-000000000003'::uuid, 'General', 'Do students need prior engineering or programming experience?', 'No. Most of our workshops are beginner-friendly and designed to guide students step-by-step through their learning journey.', 3, true),
            ('20000000-0000-4000-8000-000000000004'::uuid, 'General', 'What makes SpacePoint different?', 'Unlike traditional workshops that focus mainly on theory, SpacePoint allows students to experience real satellite engineering workflows including assembly, testing, mission planning, and subsystem integration.', 4, true),
            ('20000000-0000-4000-8000-000000000005'::uuid, 'Programs', 'What happens during the workshop?', 'Students work in teams to explore satellite subsystems, assemble components, test systems, simulate missions, and understand how real satellites are developed.', 5, true),
            ('20000000-0000-4000-8000-000000000006'::uuid, 'Programs', 'Are the workshops practical or theoretical?', 'Our workshops are heavily hands-on and project-based, combining practical engineering activities with guided explanations of theoretical concepts.', 6, true),
            ('20000000-0000-4000-8000-000000000007'::uuid, 'Programs', 'How long are the workshops?', '<ul class="list-disc pl-5 space-y-1"><li>2-3 hour introductory workshops</li><li>6-10 hour intermediate programs</li><li>18-24 hour full mission experiences</li></ul>', 7, true),
            ('20000000-0000-4000-8000-000000000008'::uuid, 'Programs', 'Do you provide online workshops?', 'Yes. SpacePoint offers both in-person and online learning experiences depending on the program.', 8, true),
            ('20000000-0000-4000-8000-000000000009'::uuid, 'Outcomes', 'What do students learn?', '<p class="mb-4">Students gain a hands-on understanding of satellite development and advanced technologies through practical experiences:</p><div class="space-y-4"><div><h5 class="text-space-accent font-bold text-xs uppercase tracking-widest mb-2">Technical Skills</h5><ul class="list-disc pl-5 space-y-1"><li><strong>Satellite Systems:</strong> Understanding subsystems (power, comms, computing) and applications (GPS, Earth observation).</li><li><strong>Integration:</strong> Wiring, sensors, and electronic subsystem connectivity.</li><li><strong>Software & Programming:</strong> Embedded systems, simulations, and troubleshooting.</li><li><strong>Systems Thinking:</strong> Engineering trade-offs and mission-based problem solving.</li></ul></div><div><h5 class="text-space-accent font-bold text-xs uppercase tracking-widest mb-2">Future-Ready Skills</h5><ul class="list-disc pl-5 space-y-1"><li>Teamwork & Leadership</li><li>Critical Thinking</li><li>Public Speaking & Technical Presentation</li><li>Innovation & Creativity</li></ul></div></div>', 9, true),
            ('20000000-0000-4000-8000-000000000010'::uuid, 'Outcomes', 'What career paths does this qualify students for?', '<p class="mb-3">Our programs build foundations for careers in high-growth sectors:</p><div class="grid grid-cols-1 sm:grid-cols-2 gap-4"><ul class="list-disc pl-5 space-y-1 text-xs"><li><strong>Space:</strong> Satellite / Systems Engineer, Mission Specialist.</li><li><strong>Tech:</strong> Robotics, Embedded Systems, AI Engineer.</li><li><strong>General:</strong> Electrical, Mechanical, Software Engineer.</li><li><strong>Future:</strong> Tech Entrepreneur, STEM Researcher.</li></ul></div>', 10, true),
            ('20000000-0000-4000-8000-000000000011'::uuid, 'Outcomes', 'Will students receive certificates?', 'Yes. Participants receive certificates upon successful completion of the program.', 11, true),
            ('20000000-0000-4000-8000-000000000012'::uuid, 'Outcomes', 'Can these workshops help with space careers?', 'Absolutely. Our programs are designed to expose students to real-world aerospace engineering concepts and future STEM career pathways.', 12, true),
            ('20000000-0000-4000-8000-000000000013'::uuid, 'Outcomes', 'Do students build a real satellite?', 'Students work with educational satellite development systems and engineering workflows inspired by real CubeSat missions.', 13, true),
            ('20000000-0000-4000-8000-000000000014'::uuid, 'Safety', 'Is the workshop safe for younger students?', 'Yes. All workshop activities are designed for educational use and are supervised by trained instructors.', 14, true),
            ('20000000-0000-4000-8000-000000000015'::uuid, 'Safety', 'How many students can join one workshop?', 'Workshop capacity depends on the selected program, venue, and available equipment. We can support both small groups and large cohorts.', 15, true),
            ('20000000-0000-4000-8000-000000000016'::uuid, 'Safety', 'Do schools need to provide equipment?', 'Usually no. SpacePoint provides the required educational kits and workshop materials unless agreed otherwise.', 16, true),
            ('20000000-0000-4000-8000-000000000017'::uuid, 'Safety', 'Can workshops be conducted at our school?', 'Yes. We can deliver programs directly at your campus, innovation hub, lab, or event venue across the UAE and GCC.', 17, true),
            ('20000000-0000-4000-8000-000000000018'::uuid, 'Partnerships', 'Has SpacePoint worked with schools before?', 'Yes. SpacePoint has delivered workshops and collaborations with multiple schools, universities, and organizations across the UAE and beyond.', 18, true),
            ('20000000-0000-4000-8000-000000000019'::uuid, 'Partnerships', 'Can organizations partner with SpacePoint?', 'Yes. We actively collaborate with educational institutions, innovation hubs, youth organizations, and industry partners.', 19, true),
            ('20000000-0000-4000-8000-000000000020'::uuid, 'Partnerships', 'Do you support competitions or hackathons?', 'Yes. We can support STEM competitions, innovation challenges, demo days, and educational events.', 20, true),
            ('20000000-0000-4000-8000-000000000021'::uuid, 'Products', 'What is the Ground Station store?', 'Ground Station is SpacePoint’s educational store featuring satellite kits, hardware, learning tools, and branded merchandise.', 21, true),
            ('20000000-0000-4000-8000-000000000022'::uuid, 'Products', 'When will the products become available?', 'Some products are currently listed as “Coming Soon.” Users can register interest to receive updates when products launch.', 22, true)
        ) AS seed(id, category, question, answer, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM website_faqs)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO media_clippings
            (id, publisher_name, article_title, article_url, published_date,
             logo_url, is_arabic, snippet, display_order, is_active)
        SELECT * FROM (VALUES
            ('20000000-0000-4000-8000-000000000101'::uuid, 'WAM', 'Sheraa champions startup-led innovation at Make it in the Emirates', 'https://www.wam.ae/en/article/bjr4hkp-sheraa-champions-startup-led-innovation-make-the', 'May 2025', '/assets/img/Media Coverage/May 2025.png', false, NULL, 1, true),
            ('20000000-0000-4000-8000-000000000102'::uuid, 'Zawya', 'UAE edtech SpacePoint to advance space engineering education via partnership with UK firm Advanced Rocket Technologies', 'https://www.zawya.com/en/press-release/companies-news/uae-edtech-spacepoint-to-advance-space-engineering-education-via-partnership-with-uk-firm-advanced-rocket-technologies-qd0l9579', 'June 2025', '/assets/img/Media Coverage/June 2025.png', false, NULL, 2, true),
            ('20000000-0000-4000-8000-000000000103'::uuid, 'Zawya', 'Expo City Dubai’s Changemakers Academy awards 10 aspiring UAE entrepreneurs with support to turn bold ideas into impact', 'https://www.zawya.com/en/press-release/companies-news/expo-city-dubais-changemakers-academy-awards-10-aspiring-uae-entrepreneurs-with-support-to-turn-bold-ideas-into-impact-hz7pnxpu', '', '/assets/img/Media Coverage/Expo City Dubai’s.png', false, NULL, 3, true),
            ('20000000-0000-4000-8000-000000000104'::uuid, 'Al Khaleej', '«سبيس بوينت» تعزز منظومة تعليم هندسة الفضاء', 'https://www.alkhaleej.ae/2025-06-17/%D8%B3%D8%A8%D9%8A%D8%B3-%D8%A8%D9%88%D9%8A%D9%86%D8%AA-%D8%AA%D8%B9%D8%B2%D8%B2-%D9%85%D9%86%D8%B8%D9%88%D9%85%D8%A9-%D8%AA%D8%B9%D9%84%D9%8A%D9%85-%D9%87%D9%86%D8%AF%D8%B3%D8%A9-%D8%A7%D9%84%D9%81%D8%B6%D8%A7%D8%A1-5963366/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1-%D9%85%D9%86-%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1-%D9%85%D9%86-%D8%A7%D9%84%D8%AF%D8%A7%D8%B1', '', '/assets/img/Media Coverage/سبيس بوينت» تعزز منظومة تعليم هندسة الفضاء.png', true, NULL, 4, true),
            ('20000000-0000-4000-8000-000000000105'::uuid, 'The National', 'Expo City Dubai to fund 10 start-ups as new academy launched', 'https://www.thenationalnews.com/news/uae/2025/06/26/expo-city-dubai-to-fund-10-start-ups-as-new-academy-launched/', '', '/assets/img/Media Coverage/Expo City Dubai to fund 10 start-ups.png', false, NULL, 5, true),
            ('20000000-0000-4000-8000-000000000106'::uuid, 'Khaleej Times', 'الإماراتية سارة الكعبي تطور نظاماً ذكياً لإدارة الفيضانات', 'https://www.khaleejtimes.com/arabic/uae/%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA%D9%8A%D8%A9-%D8%B3%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D9%83%D8%B9%D8%A8%D9%8A-%D8%AA%D8%B7%D9%88%D8%B1-%D9%86%D8%B8%D8%A7%D9%85%D8%A7-%D8%B0%D9%83%D9%8A%D8%A7-%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D9%81%D9%8A%D8%B6%D8%A7%D9%86%D8%A7%D8%AA', '', '/assets/img/Media Coverage/لإماراتية سارة الكعبي.png', true, NULL, 6, true),
            ('20000000-0000-4000-8000-000000000107'::uuid, 'SpaceTech Gulf', 'Empowering the Next Generation of Space Innovators', 'https://spacetech-gulf.com/2025/07/empowering-the-next-generation-of-space-innovators/', 'July 2025', '/assets/img/Media Coverage/July 2025.png', false, NULL, 7, true),
            ('20000000-0000-4000-8000-000000000108'::uuid, 'Al Bayan', 'تأهّل 6 مشاريع لمرحلة المنافسات النهائية ضمن مبادرة «حلول شبابية»', 'https://www.albayan.ae/news/uae/society/199382', '', '/assets/img/Media Coverage/تأهّل 6 مشاريع.png', true, NULL, 8, true),
            ('20000000-0000-4000-8000-000000000109'::uuid, 'Malta Invest', 'Malta-based startup accelerator welcomes ‘most financially mature’ cohort yet', 'https://maltainvest.mt/malta-based-startup-accelerator-welcomes-most-financial-mature-cohort-yet/', 'September 2025', '/assets/img/Media Coverage/September 2025.png', false, NULL, 9, true),
            ('20000000-0000-4000-8000-000000000110'::uuid, 'UAE Space Agency', 'الإمارات تشارك في المؤتمر الدولي للملاحة الفضائية 2025', 'https://space.gov.ae/ar/media-center/news/30/9/2025/uae-is-joining-global-space-community-at-international-astronautical-congress-2025', '', '/assets/img/Media Coverage/الإمارات تشارك في المؤتمر الدولي للملاحة الفضائية 2025.png', true, NULL, 10, true),
            ('20000000-0000-4000-8000-000000000111'::uuid, 'Al Etihad', 'حمدان بن محمد يزور معرض «إكسباند نورث ستار 2025» الأكبر عالمياً للشركات الناشئة والمستثمرين', 'https://www.aletihad.ae/news/%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA/4613532', 'October 2025', '/assets/img/Media Coverage/October 2025.png', true, NULL, 11, true),
            ('20000000-0000-4000-8000-000000000112'::uuid, 'Al Shorouk', 'شباب مصر يسطّرون قصص نجاح ملهمة في رواد الشباب العربي بأبوظبي', 'https://www.shorouknews.com/news/view.aspx?cdate=16092025&id=d5173814-177a-44a5-bbaf-cbf5d25f46f3', 'September 2025', '/assets/img/Media Coverage/شباب مصر يسطّرون قصص نجاح ملهمة في رواد الشباب العربي بأبوظبي.png', true, NULL, 12, true)
        ) AS seed(id, publisher_name, article_title, article_url, published_date,
                  logo_url, is_arabic, snippet, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM media_clippings)
        """
    ))
    conn.execute(sa.text(
        """
        INSERT INTO newsletters
            (id, title, issue_date, cover_url, file_url, display_order, is_active)
        SELECT * FROM (VALUES
            ('20000000-0000-4000-8000-000000000201'::uuid, 'SpacePoint Newsletter - Issue 6', 'Latest updates on space missions and educational workshops.', '/assets/img/Newsletter/Issue 6 Photo.jpg', '/assets/docs/Issue 6.pdf', 1, true),
            ('20000000-0000-4000-8000-000000000202'::uuid, 'SpacePoint Newsletter - Issue 5', 'Exploring the future of satellite technology in the UAE.', '/assets/img/Newsletter/Issue 5 Photo.jpg', '/assets/docs/Issue 5.pdf', 2, true),
            ('20000000-0000-4000-8000-000000000203'::uuid, 'SpacePoint Newsletter - Issue 4', 'Student missions and hands-on engineering highlights.', '/assets/img/Newsletter/Issue 4.jpg', '/assets/docs/Issue 4.pdf', 3, true),
            ('20000000-0000-4000-8000-000000000204'::uuid, 'SpacePoint Newsletter - Issue 3', 'Insights into regional space educational programs.', '/assets/img/Newsletter/Issue 3 Photo.jpg', '/assets/docs/Issue 3.pdf', 4, true),
            ('20000000-0000-4000-8000-000000000205'::uuid, 'SpacePoint Newsletter - Issue 2', 'Building the next generation of space engineers.', '/assets/img/Newsletter/Issue 2 Photo.jpg', '/assets/docs/Issue 2.pdf', 5, true),
            ('20000000-0000-4000-8000-000000000206'::uuid, 'SpacePoint Newsletter - Issue 1', 'Initial launch and the vision for UAE space education.', '/assets/img/Newsletter/Issue 1 Photo.jpg', '/assets/docs/Issue 1.pdf', 6, true)
        ) AS seed(id, title, issue_date, cover_url, file_url, display_order, is_active)
        WHERE NOT EXISTS (SELECT 1 FROM newsletters)
        """
    ))

def downgrade() -> None:
    op.drop_index('ix_website_leads_email_type', table_name='website_leads')
    op.drop_table('website_leads')
    op.drop_table('newsletters')
    op.drop_table('media_clippings')
    op.drop_table('website_faqs')
