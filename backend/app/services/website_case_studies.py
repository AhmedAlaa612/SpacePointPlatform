from uuid import UUID
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team
from app.models.website_case_study import WebsiteCaseStudy
from app.schemas.website_case_study import (
    CaseStudyCurriculumChapter,
    CaseStudyMetricItem,
    CaseStudyPartnerItem,
    CaseStudySnapshotOut,
    CaseStudySnapshotRequest,
    CaseStudyStructureSection,
)
from app.services.articles.markdown import slugify


async def unique_case_study_slug(db: AsyncSession, title: str, ignore_id: UUID | None = None) -> str:
    base = slugify(title) or "case-study"
    slug = base
    suffix = 2
    while True:
        stmt = select(WebsiteCaseStudy.id).where(WebsiteCaseStudy.slug == slug)
        if ignore_id is not None:
            stmt = stmt.where(WebsiteCaseStudy.id != ignore_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1


async def pull_case_study_snapshot(
    db: AsyncSession, req: CaseStudySnapshotRequest
) -> CaseStudySnapshotOut:
    """Pull real live/aggregate metrics and structure from Cohorts or Program to pre-fill a case study."""
    cohort_ids: list[UUID] = []
    program: Program | None = None
    sample_cohort: Cohort | None = None

    if req.source_type == "cohort" and req.cohort_id:
        cohort_ids = [UUID(str(req.cohort_id))]
        sample_cohort = (
            await db.execute(select(Cohort).where(Cohort.id == cohort_ids[0]))
        ).scalars().first()
        if sample_cohort:
            program = (
                await db.execute(select(Program).where(Program.id == sample_cohort.program_id))
            ).scalars().first()

    elif req.source_type == "multi_cohort" and req.cohort_ids:
        cohort_ids = [UUID(str(x)) for x in req.cohort_ids]
        sample_cohort = (
            await db.execute(select(Cohort).where(Cohort.id == cohort_ids[0]))
        ).scalars().first()
        if sample_cohort:
            program = (
                await db.execute(select(Program).where(Program.id == sample_cohort.program_id))
            ).scalars().first()

    elif req.source_type == "program" and req.program_id:
        program = (
            await db.execute(select(Program).where(Program.id == req.program_id))
        ).scalars().first()
        c_rows = (
            await db.execute(select(Cohort.id).where(Cohort.program_id == req.program_id))
        ).scalars().all()
        cohort_ids = list(c_rows)

    title = sample_cohort.name if sample_cohort else (program.name if program else "Case Study")
    subtitle = program.name if (sample_cohort and program and sample_cohort.name != program.name) else None
    overview_text = program.description if program and program.description else None
    card_summary = overview_text[:160] if overview_text else f"Hands-on mission program: {title}."

    category_map = {
        "competition": "Challenges & Competitions",
        "course": "National Programs",
        "workshop": "Roadshows",
        "info_session": "Universities",
    }
    category = category_map.get(program.program_type, "National Programs") if program else "Other"

    # Partner / Organization
    partner_name = None
    partner_logo = ""
    org_id = sample_cohort.organization_id if sample_cohort else (program.organization_id if program else None)
    if org_id:
        org = (
            await db.execute(select(Organization).where(Organization.id == org_id))
        ).scalars().first()
        if org:
            partner_name = org.name_latin or org.name_arabic

    partners: list[CaseStudyPartnerItem] = []
    if partner_name:
        partners.append(CaseStudyPartnerItem(name=partner_name, logo_url="", role="In partnership with"))

    # Aggregate Metrics
    metrics: list[CaseStudyMetricItem] = []
    card_metrics: list[CaseStudyMetricItem] = []

    if cohort_ids:
        # Common expressions for deduplication across multi-cohort programs / stages
        # Deduplicate students by contact email (if present) or contact_id
        student_identity = func.coalesce(
            func.nullif(func.lower(func.trim(Contact.email)), ""),
            func.cast(Registration.contact_id, String),
        )

        # Deduplicate teams by external roster_team_id (if present) or name (case-insensitive)
        team_identity = func.coalesce(
            func.nullif(func.lower(func.trim(Team.roster_team_id)), ""),
            func.nullif(func.lower(func.trim(Team.name)), ""),
            func.cast(Team.id, String),
        )

        # Total registered unique participants
        total_participants = (
            await db.execute(
                select(func.count(func.distinct(student_identity)))
                .outerjoin(Contact, Registration.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(cohort_ids),
                    Registration.status != "cancelled",
                )
            )
        ).scalar() or 0

        # Completed / attended unique students
        trained_count = (
            await db.execute(
                select(func.count(func.distinct(student_identity)))
                .outerjoin(Contact, Registration.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(cohort_ids),
                    or_(
                        Registration.status == "completed",
                        Registration.status == "attended",
                    ),
                )
            )
        ).scalar() or 0

        # Unique teams count (excluding observers and promoted duplicates)
        teams_count = 0
        try:
            teams_count = (
                await db.execute(
                    select(func.count(func.distinct(team_identity))).where(
                        Team.cohort_id.in_(cohort_ids),
                        Team.is_observer.is_(False),
                    )
                )
            ).scalar() or 0
        except Exception:
            teams_count = 0

        # Unique prototypes / Finalists (teams with final_locked_at)
        prototypes_count = 0
        try:
            prototypes_count = (
                await db.execute(
                    select(func.count(func.distinct(team_identity))).where(
                        Team.cohort_id.in_(cohort_ids),
                        Team.is_observer.is_(False),
                        Team.final_locked_at.is_not(None),
                    )
                )
            ).scalar() or 0
        except Exception:
            prototypes_count = 0

        # Distinct schools / institutions (via Contact -> organization_id)
        schools_count = 0
        try:
            schools_count = (
                await db.execute(
                    select(func.count(func.distinct(Contact.organization_id)))
                    .join(Registration, Registration.contact_id == Contact.id)
                    .where(
                        Registration.cohort_id.in_(cohort_ids),
                        Registration.status != "cancelled",
                        Contact.organization_id.is_not(None),
                    )
                )
            ).scalar() or 0
        except Exception:
            schools_count = 0

        # Sessions count
        sessions_count = 0
        try:
            sessions_count = (
                await db.execute(
                    select(func.count(Session.id)).where(Session.cohort_id.in_(cohort_ids))
                )
            ).scalar() or 0
        except Exception:
            sessions_count = 0

        # Distinct cities
        cities_list: list[str] = []
        try:
            cities_rows = (
                await db.execute(
                    select(City.name)
                    .join(Location, Location.city_id == City.id)
                    .join(Cohort, Cohort.location_id == Location.id)
                    .where(Cohort.id.in_(cohort_ids))
                    .distinct()
                )
            ).scalars().all()
            cities_list = [c for c in cities_rows if c]
        except Exception:
            cities_list = []

        if trained_count > 0:
            val = f"{trained_count:,}" if trained_count == total_participants or total_participants == 0 else f"{trained_count:,} / {total_participants:,}"
            metrics.append(CaseStudyMetricItem(value=val, label="Students Trained"))
            card_metrics.append(CaseStudyMetricItem(value=val, label="Students Trained"))
        elif total_participants > 0:
            metrics.append(CaseStudyMetricItem(value=f"{total_participants:,}", label="Participants"))
            card_metrics.append(CaseStudyMetricItem(value=f"{total_participants:,}", label="Participants"))

        if teams_count > 0:
            metrics.append(CaseStudyMetricItem(value=f"{teams_count}", label="Teams"))
            if len(card_metrics) < 2:
                card_metrics.append(CaseStudyMetricItem(value=f"{teams_count}", label="Teams"))

        if prototypes_count > 0:
            metrics.append(CaseStudyMetricItem(value=f"{prototypes_count}", label="Prototypes Built"))

        if schools_count > 0:
            metrics.append(CaseStudyMetricItem(value=f"{schools_count}", label="Schools / Universities"))
            if len(card_metrics) < 2:
                card_metrics.append(CaseStudyMetricItem(value=f"{schools_count}", label="Schools"))

        if sessions_count > 0:
            metrics.append(CaseStudyMetricItem(value=f"{sessions_count}", label="Sessions Delivered"))

        if cities_list:
            metrics.append(CaseStudyMetricItem(value=f"{len(cities_list)} Cities", label=" • ".join(cities_list[:3])))

    # Curriculum chapters from LMS if available
    curriculum_chapters: list[CaseStudyCurriculumChapter] = []
    if program:
        lms_prog = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))
        ).scalars().first()
        if lms_prog:
            items = (
                await db.execute(
                    select(LmsProgramItem)
                    .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == lms_prog.id)
                    .order_by(LmsProgramItem.position)
                )
            ).scalars().all()
            for idx, it in enumerate(items[:6]):
                curriculum_chapters.append(
                    CaseStudyCurriculumChapter(
                        chapter_num=f"Ch. {idx + 1}",
                        title=it.title,
                        icon="check" if it.item_type == "checkpoint" else "sat",
                    )
                )

    # Session structure pre-fill if single cohort
    structure_sections: list[CaseStudyStructureSection] = []
    if len(cohort_ids) == 1:
        c_sessions = (
            await db.execute(
                select(Session).where(Session.cohort_id == cohort_ids[0]).order_by(Session.meeting_date, Session.starts_at)
            )
        ).scalars().all()
        if c_sessions:
            day_items = []
            for idx, s in enumerate(c_sessions):
                title_str = s.title or f"Day {idx + 1}"
                day_items.append({
                    "day_title": f"Day {idx + 1} - {title_str}",
                    "milestones": [f"Meeting Date: {s.meeting_date}"] + ([s.title] if s.title else [])
                })
            structure_sections.append(
                CaseStudyStructureSection(
                    id="schedule",
                    badge="Timeline",
                    title="Program Delivery Schedule",
                    subtitle=f"{len(c_sessions)} interactive sessions delivered",
                    days=day_items,
                )
            )

    return CaseStudySnapshotOut(
        title=title,
        subtitle=subtitle,
        category=category,
        card_summary=card_summary,
        overview_text=overview_text,
        partner_name=partner_name,
        partner_logo_url=partner_logo,
        partners=partners,
        metrics=metrics,
        card_metrics=card_metrics,
        curriculum_chapters=curriculum_chapters,
        structure_sections=structure_sections,
    )


async def seed_default_case_studies(db: AsyncSession):
    """Seed the 4 canonical case studies if the table is empty."""
    existing_count = (await db.execute(select(func.count(WebsiteCaseStudy.id)))).scalar() or 0
    if existing_count > 0:
        return

    seed_items = [
        WebsiteCaseStudy(
            slug="planetx",
            title="Planet X – Lander Design Challenge",
            subtitle="National Space Engineering Experience",
            category="Challenges & Competitions",
            card_summary="A national space engineering challenge in collaboration with the UAE Space Agency.",
            cover_image_url="/assets/img/Case studies/Cards Images/PlanetX.jpg",
            partner_logo_url="/assets/img/Case studies/Logos/UAE Space Agency white.png",
            partner_name="UAE Space Agency",
            source_type="manual",
            partners=[
                {"name": "UAE Space Agency", "logo_url": "/assets/img/Case studies/Logos/UAE Space Agency white.png", "role": "In collaboration with"},
                {"name": "Planet X", "logo_url": "/assets/img/Case studies/Logos/PlanetX Logo.png", "role": "In collaboration with"},
                {"name": "MBR Space Centre", "logo_url": "/assets/img/Case studies/Logos/MBR (1).png", "role": "In collaboration with"},
            ],
            overview_text="A National Space Engineering Experience delivered by SpacePoint in collaboration with the UAE Space Agency, aligned with the Emirates Mission to the Asteroid Belt (EMA).\n\nDelivered through an intensive 2-Week Bootcamp where students designed, built & launched a CubeSat Lander.",
            metrics=[
                {"value": "1,750+", "label": "Students Trained", "is_hero": False},
                {"value": "464", "label": "Participants", "is_hero": False},
                {"value": "93", "label": "Teams", "is_hero": False},
                {"value": "48", "label": "Prototypes", "is_hero": False},
                {"value": "22 + 2", "label": "Universities + Schools", "is_hero": False},
            ],
            card_metrics=[
                {"value": "464", "label": "Participants", "is_hero": False},
                {"value": "93", "label": "Teams", "is_hero": False},
            ],
            gallery_images=[
                "/assets/img/Case studies/PLANETX/Planet1.jpg",
                "/assets/img/Case studies/PLANETX/Planet5.jpg",
                "/assets/img/Case studies/PLANETX/Planet6.jpg",
                "/assets/img/Case studies/PLANETX/Planet7.jpg",
                "/assets/img/Case studies/PLANETX/PlanetX 2.jpg",
                "/assets/img/Case studies/PLANETX/PlanetX 3.jpg",
                "/assets/img/Case studies/PLANETX/PlanetX4.jpg",
            ],
            visibility_stats=[
                {"value": "23,000+", "label": "views on day 4 alone", "icon": "eye"},
                {"value": "1.7M+", "label": "views from content creators", "icon": "users"},
                {"value": "85%", "label": "reach from non-followers", "icon": "trending-up"},
                {"value": "83%", "label": "engagement rate on LinkedIn", "icon": "linkedin"},
            ],
            structure_title="Bootcamp Structure",
            structure_sections=[
                {
                    "id": "week-1",
                    "badge": "01",
                    "title": "Week 1 - Online",
                    "subtitle": "Foundational Skills & CAD Modeling Preparation",
                    "image_url": "/assets/img/Case studies/PLANETX/PlanetX 2.jpg",
                    "items": [
                        {"title": "CAD Modeling Masterclass", "description": "Deep-dive masterclass to master mechanical and structural 3D design for space systems."},
                        {"title": "Engineering Tasks & Mentorship", "description": "Hands-on independent tasks guided by remote aerospace mentors to validate design concepts."}
                    ]
                },
                {
                    "id": "week-2",
                    "badge": "02",
                    "title": "Week 2 - OnSite",
                    "subtitle": "Practical Lander Integration, Testing & Final Presentations",
                    "image_url": "/assets/img/Case studies/PLANETX/PlanetX 3.jpg",
                    "days": [
                        {"day_title": "Day 1 - Launch & Foundation", "milestones": ["SatKit Shallow Flight Workshop", "EMA Mission Overview", "Lander Constraints & ConOps", "Sessions by NASA Astronauts"]},
                        {"day_title": "Day 2 - Advanced Integration", "milestones": ["Advanced Space Applications", "Lander Integration"]},
                        {"day_title": "Day 3 - Validation & Testing", "milestones": ["Lander Testing", "Jury Presentations"]},
                        {"day_title": "Day 4 - Showcase & Awards", "milestones": ["Poster Exhibition", "VIP & Space Agency Visits", "Awards Ceremony"]}
                    ]
                }
            ],
            display_order=1,
            is_featured=True,
            is_published=True,
        ),
        WebsiteCaseStudy(
            slug="agf",
            title="Satellite Development Course under the Takween Al Ghurair Program",
            subtitle="Takween Al Ghurair Program",
            category="National Programs",
            card_summary="Hands-on space education where students build and develop their own satellites.",
            cover_image_url="/assets/img/Case studies/Cards Images/AGF.jpg",
            partner_logo_url="/assets/img/Case studies/Logos/AGF white.png",
            partner_name="Abdulla Al Ghurair Foundation",
            source_type="manual",
            partners=[
                {"name": "Abdulla Al Ghurair Foundation", "logo_url": "/assets/img/Case studies/Logos/AGF white.png", "role": "In partnership with"},
                {"name": "Takween Al Ghurair Program", "logo_url": "", "role": "Program Initiative"}
            ],
            hero_metric_enabled=True,
            hero_metric_value="504 out of 520",
            hero_metric_label="Students Trained",
            overview_text="Hands-on space education for Emirati students, where they learn about satellite systems, develop key STEM skills, and experience the full space mission lifecycle.",
            metrics=[
                {"value": "504 / 520", "label": "Students Trained", "is_hero": True},
            ],
            card_metrics=[
                {"value": "504 / 520", "label": "Students Trained", "is_hero": False},
            ],
            gallery_images=[
                "/assets/img/Case studies/AGF/AGF 1.jpg",
                "/assets/img/Case studies/AGF/AGF 2.jpg",
                "/assets/img/Case studies/AGF/AGF 3.jpg",
                "/assets/img/Case studies/AGF/AGF 4.jpg",
                "/assets/img/Case studies/AGF/AGF 5.jpg",
                "/assets/img/Case studies/AGF/AGF 6.jpg",
                "/assets/img/Case studies/AGF/AGF 7.jpg",
                "/assets/img/Case studies/AGF/AGF 8.jpg",
            ],
            highlights=[
                {"title": "Assemble the SatKit", "description": "Perform electrical integration, subsystem wiring, and full mechanical satellite assembly.", "icon": "layers"},
                {"title": "Mission on Madar", "description": "Build custom space missions and experience the full journey on SpacePoint's digital platform.", "icon": "globe"}
            ],
            curriculum_chapters=[
                {"chapter_num": "Ch. 1", "title": "Intro to Sat", "icon": "sat"},
                {"chapter_num": "Ch. 2", "title": "CDHS", "icon": "cpu"},
                {"chapter_num": "Ch. 3", "title": "EPS", "icon": "zap"},
                {"chapter_num": "Ch. 4", "title": "ADCS", "icon": "compass"},
                {"chapter_num": "Ch. 5", "title": "Testing", "icon": "check"},
            ],
            structure_title="Program Formats",
            structure_sections=[
                {
                    "id": "format-breaks",
                    "badge": "01",
                    "title": "Winter & Summer Breaks (Intensive)",
                    "subtitle": "4 Days | 6h Total (~1.5h - 2h per day)",
                    "days": [
                        {"day_title": "Day 1", "milestones": ["Intro to Satellite & CDHS"]},
                        {"day_title": "Day 2", "milestones": ["EPS & ADCS"]},
                        {"day_title": "Day 3", "milestones": ["Mechanical Assembly"]},
                        {"day_title": "Day 4", "milestones": ["Demo Day & Poster Presentations"]}
                    ]
                },
                {
                    "id": "format-semester",
                    "badge": "02",
                    "title": "During Semester Program (Extended)",
                    "subtitle": "6 Weeks | 1 session/week (50-60 min)",
                    "items": [
                        {"title": "Integrated Academic Schedule", "description": "Designed for ongoing learning integrated with academic schedules, offering a weekly session format."}
                    ]
                }
            ],
            spotlights=[
                {
                    "type": "spotlight",
                    "title": "Learner-to-Leader Highlight",
                    "tag": "🌟 Spotlight",
                    "content": "Moza Al Mazrouei & Mazoon Al Mazrouei, former summer students, returned as instructors during winter course, showing the program's impact in creating confident, capable leaders.",
                    "images": ["/assets/img/Case studies/AGF/AGF 1.jpg", "/assets/img/Case studies/AGF/AGF 7.jpg"]
                }
            ],
            testimonials=[
                {
                    "quote": "I learned many things - the different types of satellites, their applications, and the areas where they are used. This workshop really expanded my horizons and helped me think more about future career fields.",
                    "author_name": "Mahra Waleed Al Naqbi",
                    "author_role": "Student Participant",
                    "author_photo_url": "/assets/img/Case studies/AGF/Mahra.jpg",
                    "badge": "Takween Students Voice"
                }
            ],
            cta_label="Press Here >> Satellite Development Course Flyer",
            cta_url="#",
            display_order=2,
            is_featured=False,
            is_published=True,
        ),
        WebsiteCaseStudy(
            slug="hct",
            title="Graduation Projects HCT Satellite Program",
            subtitle="Higher Colleges of Technology",
            category="Universities",
            card_summary="Students developed advanced payloads and tested materials for satellite structures using SatKit.",
            cover_image_url="/assets/img/Case studies/Cards Images/HCT.jpg",
            partner_logo_url="/assets/img/Case studies/Logos/HCT white.png",
            partner_name="Higher Colleges of Technology",
            source_type="manual",
            partners=[
                {"name": "Higher Colleges of Technology", "logo_url": "/assets/img/Case studies/Logos/HCT white.png", "role": "In partnership with"}
            ],
            overview_text="Used SatKit to develop their graduation projects, designing advanced payloads and testing materials for satellite structures.",
            metrics=[
                {"value": "50", "label": "Students", "is_hero": False},
                {"value": "10", "label": "Teams", "is_hero": False},
            ],
            card_metrics=[
                {"value": "50", "label": "Students", "is_hero": False},
                {"value": "10", "label": "Teams", "is_hero": False},
            ],
            gallery_images=[
                "/assets/img/Case studies/HCT/HCT 1.jpg",
                "/assets/img/Case studies/HCT/HCT2.jpg",
                "/assets/img/Case studies/HCT/HCT3.jpg",
                "/assets/img/Case studies/HCT/HCT4.jpg",
            ],
            highlights=[
                {"title": "Electrical Integration", "description": "Teams competed at the HCT Skills Event in power, comms and systems wiring.", "icon": "zap"},
                {"title": "Mechanical Assembly", "description": "Structural 3D design and materials testing for satellite chassis.", "icon": "tool"},
                {"title": "Software Testing", "description": "Flight software compilation, ground telemetry and sensors parsing.", "icon": "terminal"},
            ],
            spotlights=[
                {
                    "type": "showcase",
                    "title": "Presented at GITEX GLOBAL",
                    "tag": "Showcased & Presented",
                    "logo_url": "/assets/img/Case studies/Logos/Gitex logo.png",
                    "images": ["/assets/img/Case studies/HCT/HCT 1.jpg", "/assets/img/Case studies/HCT/HCT2.jpg", "/assets/img/Case studies/HCT/HCT3.jpg"]
                },
                {
                    "type": "future_mission",
                    "title": "HCTSat-2 Development Support",
                    "subtitle": "Upcoming Missions Support",
                    "content": "These projects support HCT's vision for more effective student involvement in upcoming missions, including HCTSat-2.",
                    "images": ["/assets/img/Case studies/HCT/HCT4.jpg"]
                }
            ],
            display_order=3,
            is_featured=False,
            is_published=True,
        ),
        WebsiteCaseStudy(
            slug="space42",
            title="Roadshow SpaceTech Educational Campaign",
            subtitle="SPACE42 & Ministry of Education",
            category="Roadshows",
            card_summary="A national roadshow inspiring students through interactive space education sessions.",
            cover_image_url="/assets/img/Case studies/Cards Images/Space42.jpg",
            partner_logo_url="/assets/img/Case studies/Logos/space42 original.png",
            partner_name="SPACE42 & Ministry of Education",
            source_type="manual",
            partners=[
                {"name": "SPACE42", "logo_url": "/assets/img/Case studies/Logos/space42 original.png", "role": "In partnership with"},
                {"name": "UAE Ministry of Education", "logo_url": "", "role": "In partnership with"}
            ],
            overview_text="SpacePoint served as the educational provider for the national SpaceTech educational roadshow launched by SPACE42 in partnership with the UAE Ministry of Education, as part of the Thuraya 4 campaign.",
            metrics=[
                {"value": "320", "label": "Students Trained", "is_hero": False},
                {"value": "8", "label": "Schools Participated", "is_hero": False},
                {"value": "8", "label": "Interactive Sessions", "is_hero": False},
                {"value": "3 Cities", "label": "Al Ain • Abu Dhabi • Sharjah", "is_hero": False},
            ],
            card_metrics=[
                {"value": "320", "label": "Students", "is_hero": False},
                {"value": "8", "label": "Schools", "is_hero": False},
            ],
            gallery_images=[
                "/assets/img/Case studies/Cards Images/Space42.jpg",
            ],
            highlights=[
                {"title": "Satellite technology", "description": "Gaining hands-on exposure to space technology and payloads.", "icon": "sat"},
                {"title": "Space systems", "description": "Understanding orbital mechanics and satellite subsystems.", "icon": "orbit"},
                {"title": "Real-world applications", "description": "Discovering aerospace careers and real STEM pathways.", "icon": "compass"},
            ],
            testimonials=[
                {
                    "quote": "The workshops teach many things related to space, which can be useful if you want to specialize in the field of space. After the workshop, my opinion about the field I want to specialize in changed. I wanted to study architectural engineering, but now I have started thinking more about space and the future, and I am now exploring everything related to space.",
                    "author_name": "Mohammed Salem Ibrahim",
                    "author_role": "Student Participant",
                    "author_photo_url": "/assets/img/Case studies/Mohammad.jpg",
                    "badge": "Space42 Students Voice"
                }
            ],
            cta_label="Learn More >> Space42 Thuraya 4 Campaign Report",
            cta_url="#",
            display_order=4,
            is_featured=False,
            is_published=True,
        ),
    ]

    for item in seed_items:
        db.add(item)
    await db.commit()
