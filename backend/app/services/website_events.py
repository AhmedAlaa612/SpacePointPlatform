import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import MegaEvent, WebsiteEvent


def slugify_event(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s or "event"


async def unique_mega_event_slug(db: AsyncSession, base_text: str, exclude_id: UUID | None = None) -> str:
    base = slugify_event(base_text)
    slug = base
    idx = 2
    while True:
        stmt = select(MegaEvent.id).where(MegaEvent.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(MegaEvent.id != exclude_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{idx}"
        idx += 1


async def unique_website_event_slug(db: AsyncSession, base_text: str, exclude_id: UUID | None = None) -> str:
    base = slugify_event(base_text)
    slug = base
    idx = 2
    while True:
        stmt = select(WebsiteEvent.id).where(WebsiteEvent.slug == slug)
        if exclude_id is not None:
            stmt = stmt.where(WebsiteEvent.id != exclude_id)
        if (await db.execute(stmt)).first() is None:
            return slug
        slug = f"{base}-{idx}"
        idx += 1


async def resolve_user_organization(db: AsyncSession, user: User) -> Organization | None:
    org = (
        await db.execute(
            select(Organization).where(Organization.owner_user_id == user.id)
        )
    ).scalars().first()
    if org is not None:
        return org
    if user.contact_id:
        contact = await db.get(Contact, user.contact_id)
        if contact and contact.organization_id:
            return await db.get(Organization, contact.organization_id)
    return None


async def ensure_default_events_seeded(db: AsyncSession) -> None:
    """Idempotently seed World Space Week UAE ('wsw') as a MegaEvent and
    SatForge UAE 2026 ('satforge-2026') as a WebsiteEvent inside WSW so the
    platform launches pre-populated out of the box."""
    wsw = (
        await db.execute(select(MegaEvent).where(MegaEvent.slug == "wsw"))
    ).scalars().first()

    if wsw is None:
        wsw = MegaEvent(
            slug="wsw",
            country="uae",
            title="World Space Week UAE 2026",
            title_ar="أسبوع الفضاء العالمي في الإمارات ٢٠٢٦",
            subtitle="One Week. One Ecosystem. Endless Possibilities.",
            tagline="Discover. Participate. Connect. Measure Impact.",
            banner_url="/assets/img/The Mission.jpg",
            date_label="October 2026 • Across All 7 Emirates",
            about_text=(
                "A public platform bringing together events, speakers, mentors, volunteers and "
                "organizations participating in World Space Week across the UAE.\n\n"
                "Discover space events across the UAE, connect with speakers and mentors, "
                "volunteer with participating organizations, or bring World Space Week to your own community."
            ),
            official_note=(
                "This platform supports outreach and coordination for World Space Week activities in the UAE. "
                "Organizers are encouraged to register their events through the official World Space Week website."
            ),
            official_url="https://www.worldspaceweek.org",
            primary_cta_label="Explore UAE Events",
            primary_cta_url="#events-directory",
            at_a_glance=[
                {"highlight": "7 Emirates", "details": "Nationwide UAE Coverage"},
                {"highlight": "Universities & Schools", "details": "Campus & Community Activities"},
                {"highlight": "Industry Mentors", "details": "Space Professionals & Experts"},
                {"highlight": "Global Initiative", "details": "Connected to World Space Week"},
            ],
            host_steps=[
                {
                    "stage": "Step 1",
                    "title": "Develop Your Event",
                    "description": "Plan a workshop, talk, competition, exhibition, panel, hackathon, or stargazing activity for your community.",
                },
                {
                    "stage": "Step 2",
                    "title": "Register Officially with WSW",
                    "description": "Register your activity on the official global World Space Week website (worldspaceweek.org).",
                },
                {
                    "stage": "Step 3",
                    "title": "Submit to the UAE Hub",
                    "description": "Sign up as a partner organization on SpacePoint and add your event so participants across the UAE can discover it.",
                },
                {
                    "stage": "Step 4",
                    "title": "Connect & Collaborate",
                    "description": "Engage speakers, mentors, and WSW UAE Space Ambassadors to support your activity.",
                },
                {
                    "stage": "Step 5",
                    "title": "Measure & Share Impact",
                    "description": "Submit your post-event outcomes to contribute to the UAE World Space Week National Impact Report.",
                },
            ],
            coordinator_info={
                "name": "Abdullah AlSalmani",
                "role": "UAE National Coordinator – World Space Week",
                "email": "a.alsalmani@spacepoint.ae",
                "note": "The UAE World Space Week Hub is an ecosystem coordination and outreach initiative supporting participation in the official World Space Week campaign.",
            },
            partners=[
                {"name": "World Space Week Association", "role": "Global Initiative", "logo_url": ""},
                {"name": "SpacePoint", "role": "UAE Ecosystem Hub Platform", "logo_url": ""},
            ],
            faqs=[
                {
                    "question": "Does this platform replace the official World Space Week registration?",
                    "answer": "No. This hub complements the official World Space Week platform by providing a UAE-specific discovery and coordination layer. Every organizer is encouraged to register their event on worldspaceweek.org first.",
                },
                {
                    "question": "How can our university, school, or organization list an event?",
                    "answer": "Organizations can sign up on the SpacePoint Portal, create their event page using our standardized template, and submit it for publication under World Space Week UAE.",
                },
                {
                    "question": "Do visitors need an account to browse events?",
                    "answer": "No. All public event listings, schedules, and registration links are openly accessible without logging in.",
                },
            ],
            display_order=1,
            is_published=True,
        )
        db.add(wsw)
        await db.flush()

    satforge = (
        await db.execute(select(WebsiteEvent).where(WebsiteEvent.slug == "satforge-2026"))
    ).scalars().first()

    if satforge is None:
        satforge = WebsiteEvent(
            slug="satforge-2026",
            mega_event_id=wsw.id,
            country="uae",
            city="Al Ain",
            event_type="competition",
            audience="Universities",
            venue_type="hybrid",
            title="SatForge UAE 2026",
            title_ar="سات فورج الإمارات 2026: التحدي الوطني للجامعات في هندسة وتصميم الأقمار الصناعية",
            subtitle="National University Satellite Engineering Challenge",
            tagline="From Campus Innovation to Future Space Missions",
            banner_url="/assets/img/The Mission.jpg",
            host_org_name="Abu Dhabi University",
            date_label="11 October – 11 November 2026",
            location="Abu Dhabi University — Al Ain Campus",
            registration_url="https://forms.cloud.microsoft/r/RB8u7Zruqt",
            guidelines_url="https://drive.google.com/file/d/1SfIpUkt_aL7uePCOxZuLUz3IdRZ_8bZk/view",
            wsw_official_url="https://www.worldspaceweek.org",
            about_text=(
                "SatForge UAE 2026: National University Satellite Engineering Challenge is a nationwide "
                "university-level satellite engineering competition that brings together talented students "
                "from higher education institutions across the United Arab Emirates to design, develop, and "
                "demonstrate innovative CubeSat-inspired satellite systems.\n\n"
                "Hosted by the College of Engineering at Abu Dhabi University, with support from the UAE Space "
                "Agency, National Space Academy, SpacePoint, Research Institute for AI & Emerging Technologies, "
                "and IEEE ADU Student Branch, the competition offers an immersive, hands-on learning experience "
                "that bridges academic knowledge and practical satellite engineering.\n\n"
                "Participants progress through technical training, mission conceptualization, electronic circuit "
                "design, simulation, 3D modeling, software development, data visualization, and hardware prototyping. "
                "With guidance from space and advanced technology professionals, teams turn ideas into functional "
                "satellite prototypes.\n\n"
                "Approximately 10 outstanding teams will advance to the final stage for on-site technical "
                "preparation and a national showcase evaluated by industry experts."
            ),
            benefits=[
                {
                    "title": "Hands-on engineering experience",
                    "description": "Apply theory to mission design, simulation, electronics, programming, testing, and prototyping.",
                },
                {
                    "title": "Industry mentorship",
                    "description": "Learn from professionals working in the UAE space and advanced technology sectors.",
                },
                {
                    "title": "Interdisciplinary collaboration",
                    "description": "Work with students from diverse engineering and technical disciplines.",
                },
                {
                    "title": "National exposure",
                    "description": "Showcase solutions to representatives of the UAE space ecosystem.",
                },
                {
                    "title": "Professional development",
                    "description": "Build teamwork, problem-solving, project management, technical communication, and presentation skills.",
                },
                {
                    "title": "Awards and recognition",
                    "description": "Compete for monetary prizes and other recognition.",
                },
            ],
            at_a_glance=[
                {"highlight": "Target participation", "details": "Approximately 500 students (indicative)"},
                {"highlight": "Team size", "details": "2–4 students"},
                {"highlight": "Finalist teams", "details": "Approximately 10"},
                {"highlight": "Prototype budget", "details": "AED 300 per team"},
            ],
            eligibility_intro="SatForge UAE 2026 welcomes eligible students enrolled in universities and higher education institutions across the UAE.",
            eligibility_rows=[
                {"label": "Enrollment", "requirement": "Currently enrolled at a UAE university or higher education institution"},
                {"label": "Age", "requirement": "16–24 years inclusive"},
                {"label": "Team size", "requirement": "2–4 students"},
                {"label": "UAE national representation", "requirement": "At least one Emirati member per team"},
                {"label": "Cross-university teams", "requirement": "Permitted, including across campuses"},
                {"label": "Academic disciplines", "requirement": "Open to all disciplines; engineering and related fields encouraged"},
            ],
            eligibility_note="Participation is particularly encouraged from Electrical, Computer, Mechanical, Aerospace, and Biomedical Engineering and related programs. Multidisciplinary teams are welcome.",
            journey_stages=[
                {
                    "stage": "Stage 1",
                    "title": "Form Your Team & Register",
                    "description": "Assemble an eligible team of 2–4 students and complete registration.",
                },
                {
                    "stage": "Stage 2",
                    "title": "Learn & Prepare",
                    "description": "Access the SpacePoint learning platform, attend training, and explore satellite engineering resources.",
                },
                {
                    "stage": "Stage 3",
                    "title": "Design & Simulate",
                    "description": "Develop the mission concept, electronic circuits, 3D model, simulations, and data dashboard.",
                },
                {
                    "stage": "Stage 4",
                    "title": "Build & Qualify",
                    "description": "Construct a functional prototype, integrate sensor data with a dashboard and submit documentation.",
                },
                {
                    "stage": "Stage 5",
                    "title": "Final Showcase",
                    "description": "Approximately 10 shortlisted teams refine their prototypes and demonstrate them before judges.",
                },
            ],
            timeline=[
                {"date": "11 October", "milestone": "Student team registration opens"},
                {"date": "15 October", "milestone": "Official kick-off — Abu Dhabi University Auditorium, Al Ain Campus"},
                {"date": "15–21 October", "milestone": "SpacePoint platform onboarding"},
                {"date": "21 October, 6:00 PM", "milestone": "Registration deadline"},
                {"date": "22 October, 5:00 PM", "milestone": "First online clarification session (60 minutes)"},
                {"date": "26 October, 5:00 PM", "milestone": "Second online clarification and Q&A (60 minutes)"},
                {"date": "30 October, 12:00 PM", "milestone": "Phase 1 digital design submission"},
                {"date": "4 November, 12:00 PM", "milestone": "Final qualifier submission"},
                {"date": "6 November", "milestone": "Announcement of approximately 10 finalist teams"},
                {"date": "9–10 November (TBC), 9 AM–2 PM", "milestone": "On-site preparation and mentoring"},
                {"date": "11 November (TBC), 9 AM–2 PM", "milestone": "Final showcase and judging"},
            ],
            timeline_note="All times are UAE local time. Final on-site dates are tentative. Registration may close early when the participation target is reached.",
            deliverables=[
                {
                    "phase": "Phase 1 — Digital Design & Simulation",
                    "deadline": "30 October 2026, 12:00 PM (noon)",
                    "items": [
                        "Electronic circuit and simulation: Tinkercad circuit design link, Multisim simulation and screen recording.",
                        "3D prototype design: 3D model using Tinkercad 3D or Fusion 360.",
                        "Interactive dashboard: Live dashboard displaying relevant satellite mission or system data.",
                        "Competition poster: Mission, concept, design and key technical information; Canva link with editor access.",
                    ],
                },
                {
                    "phase": "Phase 2 — Hardware Prototype & Qualification",
                    "deadline": "4 November 2026, 12:00 PM (noon)",
                    "items": [
                        "Functional hardware prototype connected to an interactive sensor-data dashboard.",
                        "Technical report: System architecture, components, circuit design, code, testing and results.",
                        "Prototype demonstration video showing the working hardware and dashboard.",
                        "Recorded team presentation: MP4, maximum five minutes, covering mission, design, implementation, prototype and results.",
                        "Updated competition poster, where applicable; Canva link with editor access.",
                    ],
                },
            ],
            deliverables_note="Prototype budget: Teams are challenged to build their functional CubeSat model within AED 300. Refer to the official guidelines for full requirements and early/late submission scoring adjustments.",
            awards_text=(
                "Following evaluation of qualifier submissions, approximately 10 finalist teams will be selected "
                "for the national final competition. Finalists participate in two days of on-site prototype development, "
                "testing, refinement and mentoring, followed by a third day of live demonstrations, judging and recognition.\n\n"
                "Winning teams will receive monetary prizes and other recognition for innovation, engineering achievement "
                "and competition performance. The final showcase provides exposure to professionals and representatives "
                "of the UAE space and advanced technology ecosystem."
            ),
            registration_text=(
                "Ready to turn your satellite engineering ideas into reality? Form your team, confirm eligibility, "
                "and submit one official registration form containing complete details for all team members."
            ),
            registration_deadline="21 October 2026, 6:00 PM UAE time. Registration may close earlier if the participation target is reached.",
            whatsapp_url="",
            registration_note="Students without a team are encouraged to connect with eligible participants through the team-formation WhatsApp group.",
            faqs=[
                {
                    "question": "Can students from different universities form one team?",
                    "answer": "Yes. Cross-university and cross-campus teams are permitted if all eligibility requirements are satisfied.",
                },
                {
                    "question": "Is an Emirati student required in each team?",
                    "answer": "Yes. Each team must include at least one UAE national (Emirati) member.",
                },
                {
                    "question": "Can students from non-engineering disciplines participate?",
                    "answer": "Yes. The competition welcomes all academic disciplines and encourages multidisciplinary teams.",
                },
                {
                    "question": "Do we need previous satellite development experience?",
                    "answer": "Previous experience is not listed as an eligibility requirement. Training resources and technical guidance are provided.",
                },
                {
                    "question": "Do teams need to build actual hardware?",
                    "answer": "Yes. A functional hardware prototype connected to an interactive data dashboard is required for qualification.",
                },
                {
                    "question": "What is the allowed prototype budget?",
                    "answer": "AED 300 for a functional CubeSat model.",
                },
                {
                    "question": "How many teams will reach the finals?",
                    "answer": "Approximately 10 teams are expected to be shortlisted.",
                },
                {
                    "question": "Are the final dates confirmed?",
                    "answer": "No. 9–11 November 2026 are tentative, subject to confirmation.",
                },
                {
                    "question": "Are transportation and accommodation provided?",
                    "answer": "The supplied competition guidelines do not specify transportation or accommodation arrangements; confirm with organizers.",
                },
            ],
            partners=[
                {"name": "Abu Dhabi University", "role": "Host Institution", "logo_url": ""},
                {"name": "UAE Space Agency", "role": "Supporting Partner", "logo_url": ""},
                {"name": "National Space Academy", "role": "Supporting Partner", "logo_url": ""},
                {"name": "SpacePoint", "role": "Technical Platform Partner", "logo_url": ""},
                {"name": "IEEE ADU Student Branch", "role": "Supporting Partner", "logo_url": ""},
            ],
            partners_note="",
            contacts=[
                {
                    "name": "Dr. Jawad Yousaf",
                    "role": "College of Engineering, Electrical, Computer and Biomedical Engineering Department",
                    "organization": "Abu Dhabi University",
                    "email": "jawad.yousaf@adu.ac.ae",
                },
                {
                    "name": "Mr. Abdullah Salmani",
                    "role": "SpacePoint Space",
                    "organization": "SpacePoint",
                    "email": "a.alsalmani@spacepoint.ae",
                },
            ],
            contact_meta=[
                {"label": "Competition", "value": "SatForge UAE 2026", "url": ""},
                {"label": "Host institution", "value": "Abu Dhabi University — Al Ain Campus", "url": ""},
                {"label": "Official Registration Form", "value": "Register Your Team", "url": "https://forms.cloud.microsoft/r/RB8u7Zruqt"},
                {"label": "Technical Platform", "value": "spacepoint.ae", "url": "https://www.spacepoint.ae"},
                {"label": "Competition Guidelines", "value": "Download PDF Guidelines", "url": "https://drive.google.com/file/d/1SfIpUkt_aL7uePCOxZuLUz3IdRZ_8bZk/view"},
            ],
            display_order=1,
            is_published=True,
        )
        db.add(satforge)

    await db.commit()


async def serialize_mega_events(
    db: AsyncSession, rows: list[MegaEvent], published_only_counts: bool = False
) -> list[dict]:
    if not rows:
        return []
    ids = [r.id for r in rows]
    stmt = (
        select(WebsiteEvent.mega_event_id, func.count(WebsiteEvent.id))
        .where(WebsiteEvent.mega_event_id.in_(ids))
    )
    if published_only_counts:
        stmt = stmt.where(WebsiteEvent.is_published.is_(True))
    stmt = stmt.group_by(WebsiteEvent.mega_event_id)
    counts = dict((await db.execute(stmt)).all())

    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        d["events_count"] = counts.get(r.id, 0)
        out.append(d)
    return out


async def serialize_website_events(db: AsyncSession, rows: list[WebsiteEvent]) -> list[dict]:
    if not rows:
        return []
    mega_ids = {r.mega_event_id for r in rows if r.mega_event_id}
    org_ids = {r.organization_id for r in rows if r.organization_id}

    megas_by_id: dict[UUID, MegaEvent] = {}
    if mega_ids:
        megas = (await db.execute(select(MegaEvent).where(MegaEvent.id.in_(mega_ids)))).scalars().all()
        megas_by_id = {m.id: m for m in megas}

    orgs_by_id: dict[UUID, Organization] = {}
    if org_ids:
        orgs = (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
        orgs_by_id = {o.id: o for o in orgs}

    out = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in r.__table__.columns}
        mega = megas_by_id.get(r.mega_event_id) if r.mega_event_id else None
        org = orgs_by_id.get(r.organization_id) if r.organization_id else None
        d["mega_event_slug"] = mega.slug if mega else None
        d["mega_event_title"] = mega.title if mega else None
        d["organization_name"] = org.name_latin if org else r.host_org_name
        out.append(d)
    return out
