# Importing models here registers them on Base.metadata so Alembic autogenerate
# and create_all see every table. Add domain models as phases land.
from app.models.user import User  # noqa: F401
from app.models.notification import Notification  # noqa: F401  (shared)
from app.models import interns  # noqa: F401  (Phase 1)

from app.models import ambassadors  # noqa: F401  (Phase 2)

from app.models import instructors  # noqa: F401  (Phase 3)
from app.models.id_card import IdCard  # noqa: F401  (shared, PLAN §4.5 — pulled forward into Phase 3)
from app.models.certificate import Certificate  # noqa: F401  (shared, PLAN §4.5 — pulled forward into Phase 3)
from app.models.document import Document  # noqa: F401  (shared — unified generated letters, replaces rec/intern letters)
from app.models.document_request import DocumentRequest  # noqa: F401  (shared, PLAN §4.5 — Phase 4)
from app.models.document_template import DocumentTemplate  # noqa: F401  (shared, PLAN §4.5)
from app.models.application import Application  # noqa: F401  (shared, unified apply pipeline)
from app.models.application_question import ApplicationQuestion  # noqa: F401  (shared, admin-managed apply form)
from app.models.internship import InternProfile, RoleRequest, InternshipRefCounter  # noqa: F401  (2026-08-20 — intern onboarding + generic extra-role requests)

from app.models import spine  # noqa: F401  (V2 R1-2 — contacts/organizations/consent/touchpoints/identity)
from app.models import sessions  # noqa: F401  (V2 R1-2 — programs/cohorts/registrations/tickets/activities)
from app.models import inventory  # noqa: F401  (I1-1 — locations/items/kits/templates/stock/movements)
from app.models import lms  # noqa: F401  (LM1-1 — courses/modules/items/videos/curriculum/enrollments/progress)
from app.models.team import Team, TeamMember  # noqa: F401  (2026-08-17 — domain-agnostic, shared by missions/competitions)
from app.models.videos import Video  # noqa: F401  (standardized video service — domain-agnostic, replaces ModuleVideo/guideline_url/etc.)
from app.models import missions  # noqa: F401  (Phase 2 Stage 5 — missions/variants/prerequisites/attempts)
from app.models import competitions  # noqa: F401  (2026-08-24 — judging: rubrics/scores/publish/judges)
from app.models.curriculum import Prerequisite  # noqa: F401  (7B-2 — unified course/mission prerequisite DAG)
from app.models import games  # noqa: F401  (Live Games Phase 2C — Kahoot-style live quiz)
from app.models import instructor_assessment  # noqa: F401  (2026-09 — instructor assessment & performance ranking)
from app.models import ground_station  # noqa: F401  (2026-09 — live ground-station telemetry tool, ported from Madar)
from app.models.birthday_log import BirthdayEmailLog  # noqa: F401
from app.models.website_config import WebsiteConfig  # noqa: F401  (Step 1 — website global config singleton)
from app.models.website_program import WebsiteProgram  # noqa: F401  (Step 2 — website flagship programs & pricing)
from app.models.website_sponsor import WebsiteSponsor  # noqa: F401  (Step 3 — website partners & clients showcase)
from app.models.website_faq import WebsiteFaq  # noqa: F401  (Step 4 — website FAQs)
from app.models.website_media import MediaClipping  # noqa: F401  (Step 4 — website media coverage)
from app.models.website_newsletter import Newsletter, WebsiteLead  # noqa: F401  (Step 4 — newsletters & leads)
from app.models.website_article import WebsiteArticle  # noqa: F401  (Step 5 — articles & editorial queue)
from app.models.website_labs import WebsiteLabProject  # noqa: F401  (Step 7 — labs R&D projects)
from app.models.website_people import (  # noqa: F401  (Step 6 — people showcase)
    StudentMission,
    TeamMember,
    WebsiteAlumni,
    WebsiteAmbassador,
)
from app.models.website_event import MegaEvent, WebsiteEvent  # noqa: F401  (Step 8 — events & mega-events)
from app.models import mentors  # noqa: F401  (Mentorship Platform — Satellite & Space Mentors)

