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

from app.models import spine  # noqa: F401  (V2 R1-2 — contacts/organizations/consent/touchpoints/identity)
from app.models import sessions  # noqa: F401  (V2 R1-2 — programs/cohorts/registrations/tickets/activities)
from app.models import inventory  # noqa: F401  (I1-1 — locations/items/kits/templates/stock/movements)
from app.models import lms  # noqa: F401  (LM1-1 — courses/modules/items/videos/curriculum/enrollments/progress)
from app.models import missions  # noqa: F401  (Phase 2 Stage 5 — missions/variants/prerequisites/attempts)
from app.models.curriculum import Prerequisite  # noqa: F401  (7B-2 — unified course/mission prerequisite DAG)
from app.models import games  # noqa: F401  (Live Games Phase 2C — Kahoot-style live quiz)

