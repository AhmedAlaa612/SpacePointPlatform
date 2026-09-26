"""Seed script migrating legacy website data into PostgreSQL CMS tables.

Populates:
- 3 Articles from blogs_registry.json (linking to seeded authors)
- 6 Student Mission Showcase Projects with reports and headshots
- 30+ Institutional Sponsors, Clients, and Technical Partners
- 12 Bilingual Press & Media Clippings
"""

import asyncio
from datetime import datetime, timezone
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.cms import Article, MediaClipping, Sponsor, StudentMission
from app.models.user import User
from app.schemas.cms import compile_markdown_to_safe_html, slugify


async def seed_articles(db):
    print("--- Seeding CMS Articles ---")
    users = (await db.execute(select(User))).scalars().all()
    user_by_email = {u.email: u for u in users}

    instructor_user = user_by_email.get("instructor@spacepoint.ae")
    intern_user = user_by_email.get("intern@spacepoint.ae")

    articles_data = [
        {
            "title": "Mission Control: Real-time Simulation Platforms in the Classroom",
            "summary": "Fatima Al Hashimi discusses how real-time simulation platforms like Madar transform classroom learning into active mission control centers.",
            "category": "SCIENCE",
            "author_user": intern_user,
            "author_display_name": "Rayan Al Dahre",
            "author_role": "Lead Systems Engineer",
            "author_initials": "RA",
            "published_at": datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
            "cover_image_url": "/assets/img/WhatsApp_Image_2026-03-03_at_4.37.46_PM.jpeg",
            "featured_order": 1,
            "content_markdown": """Traditional space education has often been constrained by high-level mathematics and purely theoretical models. While calculating orbital trajectories and studying atmospheric attenuation are crucial, they can feel disconnected from the day-to-day realities of operational space missions. To bridge this gap, modern classrooms are integrating real-time simulation platforms that replicate the high-stakes environment of a mission control center.

At the heart of this educational revolution is SpacePoint's custom platform, **Madar**. Madar provides students with a live interface that connects directly to physical or simulated CubeSats. Through this portal, students do not just read about telemetry; they actively query sensors, parse data packets, and visualize critical parameters such as angular velocities, battery temperatures, and subsystem voltages in real time.

### Interactive Telemetry and Commanding

Using real-time simulation interfaces, students participate in structured scenarios where they assume specific mission roles:

- **Flight Controller:** Monitoring live plots and identifying out-of-limit readings before they trigger a system-level failure.
- **Operations Manager:** Deciding when to execute commands, taking into account the satellite's power reserves and orbital visibility.
- **Systems Engineer:** Troubleshooting sensor communication failures and writing code patches to correct telemetry anomalies.

By simulating complex flight scenarios—such as detumbling a spinning satellite or managing battery constraints during an eclipse—students learn to apply critical thinking and real-time decision making under pressure. These hands-on exercises demonstrate how aerospace theory applies directly to real missions, providing students with the technical and collaborative skills required for the UAE's rapidly growing space sector.""",
        },
        {
            "title": "Designing the Future: A Student's Guide to CubeSat Engineering",
            "summary": "Sarah Al Kaabi shares insights into CubeSat engineering, hands-on assembly, and space systems integration for students.",
            "category": "TECHNOLOGY",
            "author_user": instructor_user,
            "author_display_name": "Sarah Al Kaabi",
            "author_role": "Aerospace Instructor",
            "author_initials": "SA",
            "published_at": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
            "cover_image_url": "/assets/img/The Mission.jpg",
            "featured_order": 2,
            "content_markdown": """Nanosatellites, commonly known as CubeSats, have fundamentally changed the dynamics of space exploration. By drastically lowering structural barriers and deployment costs, they have democratized access to Earth's orbit, enabling academic institutions and private enterprises alike to conduct valid experiments and collect valuable orbital data. For students, this presents an unprecedented opportunity to gain hands-on training with physical space systems.

Inside a modern space engineering workshop, students are not merely studying textbooks; they are working directly with educational integration kits like the **SatKit**. This practical approach shifts the learning paradigm, requiring students to wire sub-modules, integrate structural sensors, and perform structural safety validation. Working at this scale exposes learners to real-world complexities such as electrical ground loops, data bus addressing, and noise attenuation.

### The Subsystem Integration Process

A satellite is a collection of interconnected systems, each performing a vital function. When students perform electrical integration, they gain exposure to four core pillars:

- **CDHS (Command and Data Handling System):** The central computer executing scripts, processing sensor telemetry, and storing payload data.
- **EPS (Electrical Power System):** Regulating voltage, managing solar panels, and ensuring rechargeable batteries safely distribute power.
- **ADCS (Attitude Determination and Control System):** Orienting the satellite in space using reaction wheels, magnetorquers, and gyroscopes.
- **Mechanical Assembly & Testing:** Structuring the CubeSat to survive the extreme vibration of launch and thermal dynamics of space.

Finally, these workshops empower students by cultivating future-ready cognitive capabilities. The process of debugging communication errors, aligning sensors, and writing script patches requires team coordination, rigorous documentation, and critical analysis. These are the same capabilities that prepare the next generation of engineers to enter UAE space initiatives and general aerospace roles.""",
        },
        {
            "title": "Bridging the Gap: Space Education in the UAE and GCC Region",
            "summary": "Ahmad Al Falasi shares insights into space education programs, national visions, and academic integrations across the UAE and GCC.",
            "category": "EDUCATION",
            "author_user": None,
            "author_display_name": "Ahmad Al Falasi",
            "author_role": "Space Education Expert",
            "author_initials": "AA",
            "published_at": datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
            "cover_image_url": "/assets/img/The Journey.jpg",
            "featured_order": 3,
            "content_markdown": """The United Arab Emirates has rapidly positioned itself as a key player in the global space exploration sector. With historic accomplishments such as the Hope Probe's arrival at Mars, the deployment of local astronauts to the International Space Station, and the ambitious Emirates Mission to the Asteroid Belt (EMA), the region has shown that its space goals are long-term, structural, and state-of-the-art.

However, to sustain these aerospace achievements, a strong connection must be forged between the space sector and academic curricula. Space education cannot rely solely on dry textbook theories. Instead, schools and universities must integrate practical, project-based engineering opportunities that reflect the active workflows of contemporary mission control rooms and mechanical integration labs.

Collaborations between specialized education groups like **SpacePoint** and national entities (such as the UAE Space Agency and the Abdulla Al Ghurair Foundation) are vital in establishing this hands-on model. By bringing satellite hardware, interactive simulation platforms, and customized training frameworks directly to students, these entities are converting passive learners into active creators and technical leaders.

As we look to the future, the expansion of regional STEM programs is essential. Educating the next generation with aerospace capabilities ensures that local talent will not only support upcoming GCC space programs but will actively lead scientific discoveries. The mission begins in the classroom, where inspiring space education builds the foundations for tomorrow's orbital engineering.""",
        },
    ]

    for item in articles_data:
        slug = slugify(item["title"])
        existing = (await db.execute(select(Article).where(Article.slug == slug))).scalars().first()
        if existing:
            print(f"  Article already exists: {slug}")
            continue

        html = compile_markdown_to_safe_html(item["content_markdown"])
        author = item["author_user"]
        article = Article(
            slug=slug,
            title=item["title"],
            summary=item["summary"],
            category=item["category"],
            author_id=author.id if author else None,
            author_display_name=item["author_display_name"],
            author_role=item["author_role"],
            author_initials=item["author_initials"],
            cover_image_url=item["cover_image_url"],
            content_markdown=item["content_markdown"],
            content_html=html,
            status="published",
            published_at=item["published_at"],
            featured_order=item["featured_order"],
            created_at=item["published_at"],
            updated_at=item["published_at"],
        )
        db.add(article)
        print(f"  Created article: {slug}")

    await db.commit()


async def seed_student_missions(db):
    print("--- Seeding Student Missions ---")
    missions_data = [
        {
            "student_name": "Abdalla Osama",
            "project_title": "Satellite Telemetry Dashboard",
            "category": "Telemetry & Embedded Systems",
            "description": (
                "This project focuses on building a complete real-time telemetry dashboard system for a satellite simulation. "
                "The system starts from sensor data acquisition on the satellite side using ESP32, transmits data wirelessly via HC-12, "
                "passes through an MQTT broker, and finally visualizes critical telemetry using InfluxDB and Grafana dashboards."
            ),
            "photo_url": "/assets/students-projects/Abdalla Osama (Internship Project)/Abdalla Osama (Internship Project).jpg",
            "docx_url": "/assets/students-projects/Abdalla Osama (Internship Project)/Abdalla Osama (Internship Project).docx",
            "display_order": 1,
            "metrics_json": {"subsystems": ["ESP32", "HC-12", "MQTT", "Grafana"], "type": "Internship"},
        },
        {
            "student_name": "Jouri Ahmed Alobaidly",
            "project_title": "ATMO-1 CubeSat Mission",
            "category": "CubeSat Design",
            "description": (
                "This project focuses on designing a CubeSat mission, ATMO-1, by integrating key subsystems like power (solar panels), "
                "data handling (CDHS), memory (FRAM & SRAM), and signal processing, while considering orbit selection (GEO) for continuous Earth monitoring."
            ),
            "photo_url": "/assets/students-projects/Jouri Ahmed Alobaidly (School Project)/Jouri Ahmed Alobaidly (School Project).jpeg",
            "docx_url": "/assets/students-projects/Jouri Ahmed Alobaidly (School Project)/Takween Al Gurair Student Project.docx",
            "display_order": 2,
            "metrics_json": {"subsystems": ["CDHS", "EPS", "FRAM", "Orbit Selection"], "type": "Takween Al Ghurair"},
        },
        {
            "student_name": "Kassam Dakhlalah",
            "project_title": "LoRa-Based Satellite Dashboard",
            "category": "Ground Station & LoRa",
            "description": (
                "This project focuses on designing a real-time interactive CubeSat telemetry dashboard that serves as a complete ground station interface. "
                "Raw telemetry packets received via LoRa from a CubeSat are processed, stored, and dynamically visualized with 3D orientation models."
            ),
            "photo_url": "/assets/students-projects/Kassam Dakhlalah/Kassam Dakhlalah.jpeg",
            "docx_url": "/assets/students-projects/Kassam Dakhlalah/CubeSat Mission Control.docx",
            "display_order": 3,
            "metrics_json": {"subsystems": ["LoRa", "Ground Station", "3D Attitude Model"], "type": "Mission Control"},
        },
        {
            "student_name": "Lameya AlDhaheri",
            "project_title": "Debris Avoidance System",
            "category": "AI & Embedded Vision",
            "description": (
                "This project focuses on designing an embedded system for space debris detection and orientation stabilization. "
                "The system captures camera frames, runs AI models for debris localization, and commands an IMU and reaction wheel to orient the satellite safely."
            ),
            "photo_url": "/assets/students-projects/Lamya AlDhaheri (AI Project)/Lamya AlDhaheri (AI Project).jpeg",
            "docx_url": "/assets/students-projects/Lamya AlDhaheri (AI Project)/AI Project.docx",
            "display_order": 4,
            "metrics_json": {"subsystems": ["Edge AI", "Computer Vision", "Reaction Wheels", "RTOS"], "type": "AI Systems"},
        },
        {
            "student_name": "Nour Arnaout",
            "project_title": "1U CubeSat Thermal Analysis",
            "category": "Thermal Simulation & FEA",
            "description": (
                "Detailed thermal management and orbital cycling simulation of SpacePoint's 1U CubeSat using ANSYS Fluent. "
                "Evaluates maximum solar flux, Earth albedo/IR, eclipse scenarios, and transient 90-minute temperature cycling."
            ),
            "photo_url": "/assets/students-projects/Nour Arnaout (Thermal Analysis)/Nour Arnaout (Thermal Analysis).jpg",
            "docx_url": "/assets/students-projects/Nour Arnaout (Thermal Analysis)/Thermal Analysis.docx",
            "display_order": 5,
            "metrics_json": {"subsystems": ["ANSYS Fluent", "Radiative Heat Transfer", "FEA", "Transient Orbit"], "type": "Thermal Engineering"},
        },
        {
            "student_name": "Rayan AlDhaheri",
            "project_title": "CubeSat Electrical Power System (EPS)",
            "category": "Electrical Power Systems",
            "description": (
                "Complete design of a CubeSat Electrical Power System, from solar panel MPPT tracking to multi-rail voltage regulation, "
                "lithium battery protection, and regulated distribution to onboard sensors and payload."
            ),
            "photo_url": "/assets/students-projects/Rayan AlDhaheri (EPS Project)/Rayan AlDhaheri (EPS Project).jpeg",
            "docx_url": "/assets/students-projects/Rayan AlDhaheri (EPS Project)/EPS Project.docx",
            "display_order": 6,
            "metrics_json": {"subsystems": ["MPPT", "Battery Management", "PCB Design", "Power Buses"], "type": "Power Electronics"},
        },
    ]

    for m in missions_data:
        existing = (
            await db.execute(
                select(StudentMission).where(
                    StudentMission.student_name == m["student_name"],
                    StudentMission.project_title == m["project_title"],
                )
            )
        ).scalars().first()
        if existing:
            print(f"  Mission already exists: {m['project_title']}")
            continue

        mission = StudentMission(
            student_name=m["student_name"],
            project_title=m["project_title"],
            category=m["category"],
            description=m["description"],
            docx_url=m["docx_url"],
            photo_url=m["photo_url"],
            metrics_json=m["metrics_json"],
            display_order=m["display_order"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(mission)
        print(f"  Created student mission: {m['project_title']}")

    await db.commit()


async def seed_sponsors(db):
    print("--- Seeding Sponsors & Partners ---")
    sponsors_list = [
        # Institutional Clients
        ("EDGE Group", "/assets/img/clients/Edge Original.png", "https://edgegroup.ae", "client", 1),
        ("Etlaq", "/assets/img/clients/Etlaq original.png", None, "client", 2),
        ("Fada", "/assets/img/clients/Fada original.png", None, "client", 3),
        ("MBZUAI", "/assets/img/clients/MBZUAI original.png", "https://mbzuai.ac.ae", "client", 4),
        ("Museum of the Future", "/assets/img/clients/Museum of the future original.png", "https://museumofthefuture.ae", "client", 5),
        ("Space42", "/assets/img/clients/Space42 original.png", "https://space42.ai", "client", 6),
        ("Ministry of Community Development (MUD)", "/assets/img/clients/MUD original.png", None, "client", 7),
        ("NASA Space Apps Dubai", "/assets/img/clients/Nasa Dubai original.png", None, "client", 8),

        # Supporters & Government
        ("Abdulla Al Ghurair Foundation", "/assets/img/Case studies/Logos/AGF white.png", "https://alghurairfoundation.org", "supporter", 1),
        ("UAE Space Agency", "/assets/img/Case studies/Logos/UAE Space Agency white.png", "https://space.gov.ae", "supporter", 2),
        ("Maker Faire", "/assets/img/clients/maker fair original.png", None, "supporter", 3),

        # Academic Partners
        ("GEMS Education", "/assets/img/clients/Gems original.png", "https://gemseducation.com", "academic", 1),
        ("Higher Colleges of Technology (HCT)", "/assets/img/clients/HCT original.png", "https://hct.ac.ae", "academic", 2),
        ("Khalifa University", "/assets/img/clients/KU original.png", "https://ku.ac.ae", "academic", 3),
        ("KAUST", "/assets/img/clients/Kaust original.png", "https://kaust.edu.sa", "academic", 4),
        ("UAE University (UAEU)", "/assets/img/clients/UAEU original.png", "https://uaeu.ac.ae", "academic", 5),

        # Technical Partners
        ("Advanced Rocket Technologies (ART)", "/assets/img/partners/ART original.png", None, "partner", 1),
        ("Aeroo", "/assets/img/partners/Aeroo original.png", None, "partner", 2),
        ("AirQ", "/assets/img/partners/AirQ original.png", None, "partner", 3),
        ("Coursetopia", "/assets/img/partners/Coursetopia original.png", None, "partner", 4),
        ("Global Innovation", "/assets/img/partners/Global Innovation original.png", None, "partner", 5),
        ("KL . Space", "/assets/img/partners/KL . Space original.png", None, "partner", 6),
        ("Kush Digital", "/assets/img/partners/Kush Digital original.png", None, "partner", 7),
        ("LyraSense", "/assets/img/partners/LyraSense original.png", None, "partner", 8),
        ("NASA Space Apps Alex", "/assets/img/partners/Nasa space Alex original.png", None, "partner", 9),
        ("NASA Space Apps Dami", "/assets/img/partners/Nasa space Dami original.png", None, "partner", 10),
        ("Payload Logistics (PL)", "/assets/img/partners/PL original.png", None, "partner", 11),
        ("Quantum", "/assets/img/partners/Quantum original.png", None, "partner", 12),
        ("Raise Me", "/assets/img/partners/Raise Me original.png", None, "partner", 13),
        ("Sal7lyy", "/assets/img/partners/Sal7lyy original.png", None, "partner", 14),
        ("SatEx", "/assets/img/partners/SatEx original.png", None, "partner", 15),
        ("School Try", "/assets/img/partners/School Try original.png", None, "partner", 16),
        ("SpaceKids India", "/assets/img/partners/SpaceKids India original.png", None, "partner", 17),
        ("UniTors", "/assets/img/partners/UniTors original.png", None, "partner", 18),
    ]

    for name, logo, url, tier, order in sponsors_list:
        existing = (
            await db.execute(select(Sponsor).where(Sponsor.name == name))
        ).scalars().first()
        if existing:
            continue

        sponsor = Sponsor(
            name=name,
            logo_url=logo,
            website_url=url,
            tier=tier,
            display_order=order,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(sponsor)
        print(f"  Created sponsor: {name} ({tier})")

    await db.commit()


async def seed_media_coverage(db):
    print("--- Seeding Media Coverage ---")
    clippings_data = [
        {
            "publisher_name": "WAM",
            "article_title": "Sheraa champions startup-led innovation at Make it in the Emirates",
            "article_url": "https://www.wam.ae/en/article/bjr4hkp-sheraa-champions-startup-led-innovation-make-the",
            "published_date": datetime(2025, 5, 15, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/May 2025.png",
            "is_arabic": False,
            "snippet": "Sheraa features SpacePoint among visionary startups driving advanced engineering and educational innovation.",
            "display_order": 1,
        },
        {
            "publisher_name": "Zawya",
            "article_title": "UAE edtech SpacePoint to advance space engineering education via partnership with UK firm Advanced Rocket Technologies",
            "article_url": "https://www.zawya.com/en/press-release/companies-news/uae-edtech-spacepoint-to-advance-space-engineering-education-via-partnership-with-uk-firm-advanced-rocket-technologies-qd0l9579",
            "published_date": datetime(2025, 6, 10, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/June 2025.png",
            "is_arabic": False,
            "snippet": "SpacePoint signs strategic MoU with Advanced Rocket Technologies to introduce rocketry and satellite payload curriculums.",
            "display_order": 2,
        },
        {
            "publisher_name": "Zawya",
            "article_title": "Expo City Dubai’s Changemakers Academy awards 10 aspiring UAE entrepreneurs with support to turn bold ideas into impact",
            "article_url": "https://www.zawya.com/en/press-release/companies-news/expo-city-dubais-changemakers-academy-awards-10-aspiring-uae-entrepreneurs-with-support-to-turn-bold-ideas-into-impact-hz7pnxpu",
            "published_date": datetime(2025, 6, 20, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/Expo City Dubai’s.png",
            "is_arabic": False,
            "snippet": "SpacePoint selected among top innovation ventures by Expo City Dubai Changemakers Academy.",
            "display_order": 3,
        },
        {
            "publisher_name": "Al Khaleej",
            "article_title": "«سبيس بوينت» تعزز منظومة تعليم هندسة الفضاء",
            "article_url": "https://www.alkhaleej.ae/2025-06-17/%D8%B3%D8%A8%D9%8A%D8%B3-%D8%A8%D9%88%D9%8A%D9%86%D8%AA-%D8%AA%D8%B9%D8%B2%D8%B2-%D9%85%D9%86%D8%B8%D9%88%D9%85%D8%A9-%D8%AA%D8%B9%D9%84%D9%8A%D9%85-%D9%87%D9%86%D8%AF%D8%B3%D8%A9-%D8%A7%D9%84%D9%81%D8%B6%D8%A7%D8%A1-5963366/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1-%D9%85%D9%86-%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA/%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1-%D9%85%D9%86-%D8%A7%D9%84%D8%AF%D8%A7%D8%B1",
            "published_date": datetime(2025, 6, 17, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/سبيس بوينت» تعزز منظومة تعليم هندسة الفضاء.png",
            "is_arabic": True,
            "snippet": "تسليط الضوء على مبادرات سبيس بوينت لإعداد الكفاءات الوطنية الشابة في مجال الأقمار الاصطناعية وعلوم الفضاء.",
            "display_order": 4,
        },
        {
            "publisher_name": "The National",
            "article_title": "Expo City Dubai to fund 10 start-ups as new academy launched",
            "article_url": "https://www.thenationalnews.com/news/uae/2025/06/26/expo-city-dubai-to-fund-10-start-ups-as-new-academy-launched/",
            "published_date": datetime(2025, 6, 26, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/Expo City Dubai to fund 10 start-ups.png",
            "is_arabic": False,
            "snippet": "New incubator selects SpacePoint to receive acceleration grants and ecosystem deployment.",
            "display_order": 5,
        },
        {
            "publisher_name": "Khaleej Times Arabic",
            "article_title": "الإماراتية سارة الكعبي تطور نظاماً ذكياً لإدارة الفيضانات",
            "article_url": "https://www.khaleejtimes.com/arabic/uae/%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA%D9%8A%D8%A9-%D8%B3%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D9%83%D8%B9%D8%A8%D9%8A-%D8%AA%D8%B7%D9%88%D8%B1-%D9%86%D8%B8%D8%A7%D9%85%D8%A7-%D8%B0%D9%83%D9%8A%D8%A7-%D9%84%D8%A5%D8%AF%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D9%81%D9%8A%D8%B6%D8%A7%D9%86%D8%A7%D8%AA",
            "published_date": datetime(2025, 7, 5, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/لإماراتية سارة الكعبي.png",
            "is_arabic": True,
            "snippet": "مدربة سبيس بوينت سارة الكعبي تحصد إشادة وطنية لتطوير نظام أقمار اصطناعية ذكي لرصد الفيضانات.",
            "display_order": 6,
        },
        {
            "publisher_name": "SpaceTech Gulf",
            "article_title": "Empowering the Next Generation of Space Innovators",
            "article_url": "https://spacetech-gulf.com/2025/07/empowering-the-next-generation-of-space-innovators/",
            "published_date": datetime(2025, 7, 20, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/July 2025.png",
            "is_arabic": False,
            "snippet": "Deep dive into SpacePoint's hands-on CubeSat kits and satellite simulation platform Madar.",
            "display_order": 7,
        },
        {
            "publisher_name": "Al Bayan",
            "article_title": "تأهّل 6 مشاريع لمرحلة المنافسات النهائية ضمن مبادرة «حلول شبابية»",
            "article_url": "https://www.albayan.ae/news/uae/society/199382",
            "published_date": datetime(2025, 8, 12, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/تأهّل 6 مشاريع.png",
            "is_arabic": True,
            "snippet": "مشروع سبيس بوينت يتأهل للمرحلة النهائية في مبادرة حلول شبابية التابعة للمؤسسة الاتحادية للشباب.",
            "display_order": 8,
        },
        {
            "publisher_name": "Malta Invest",
            "article_title": "Malta-based startup accelerator welcomes ‘most financially mature’ cohort yet",
            "article_url": "https://maltainvest.mt/malta-based-startup-accelerator-welcomes-most-financial-mature-cohort-yet/",
            "published_date": datetime(2025, 9, 5, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/September 2025.png",
            "is_arabic": False,
            "snippet": "SpacePoint expands its international footprint by participating in European space tech acceleration.",
            "display_order": 9,
        },
        {
            "publisher_name": "UAE Space Agency",
            "article_title": "الإمارات تشارك في المؤتمر الدولي للملاحة الفضائية 2025",
            "article_url": "https://space.gov.ae/ar/media-center/news/30/9/2025/uae-is-joining-global-space-community-at-international-astronautical-congress-2025",
            "published_date": datetime(2025, 9, 30, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/الإمارات تشارك في المؤتمر الدولي للملاحة الفضائية 2025.png",
            "is_arabic": True,
            "snippet": "وفد دولة الإمارات في IAC 2025 يستعرض الإنجازات التعليمية والمشاريع الطلابية بالتعاون مع سبيس بوينت.",
            "display_order": 10,
        },
        {
            "publisher_name": "Al Etihad",
            "article_title": "حمدان بن محمد يزور معرض «إكسباند نورث ستار 2025» الأكبر عالمياً للشركات الناشئة والمستثمرين",
            "article_url": "https://www.aletihad.ae/news/%D8%A7%D9%84%D8%A5%D9%85%D8%A7%D8%B1%D8%A7%D8%AA/4613532",
            "published_date": datetime(2025, 10, 15, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/October 2025.png",
            "is_arabic": True,
            "snippet": "سمو الشيخ حمدان بن محمد يطلع على حلول تعليم هندسة الفضاء التي تقدمها شركة سبيس بوينت في نورث ستار.",
            "display_order": 11,
        },
        {
            "publisher_name": "Shorouk News",
            "article_title": "شباب مصر يسطّرون قصص نجاح ملهمة في رواد الشباب العربي بأبوظبي",
            "article_url": "https://www.shorouknews.com/news/view.aspx?cdate=16092025&id=d5173814-177a-44a5-bbaf-cbf5d25f46f3",
            "published_date": datetime(2025, 9, 16, tzinfo=timezone.utc),
            "logo_url": "/assets/img/Media Coverage/شباب مصر يسطّرون قصص نجاح ملهمة في رواد الشباب العربي بأبوظبي.png",
            "is_arabic": True,
            "snippet": "برنامج رواد الشباب العربي يكرم رواد الأعمال والمهندسين الشباب في قطاع تكنولوجيا الفضاء.",
            "display_order": 12,
        },
    ]

    for c in clippings_data:
        existing = (
            await db.execute(
                select(MediaClipping).where(MediaClipping.article_title == c["article_title"])
            )
        ).scalars().first()
        if existing:
            continue

        clipping = MediaClipping(
            publisher_name=c["publisher_name"],
            article_title=c["article_title"],
            article_url=c["article_url"],
            published_date=c["published_date"],
            logo_url=c["logo_url"],
            is_arabic=c["is_arabic"],
            snippet=c["snippet"],
            display_order=c["display_order"],
            is_active=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(clipping)
        print(f"  Created media clipping: {c['article_title'][:40]}...")

    await db.commit()


async def main():
    print("Beginning legacy data seeding into PostgreSQL...")
    async with AsyncSessionLocal() as db:
        await seed_articles(db)
        await seed_student_missions(db)
        await seed_sponsors(db)
        await seed_media_coverage(db)
    print("Legacy data seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
