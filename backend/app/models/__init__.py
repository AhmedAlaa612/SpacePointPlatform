# Importing models here registers them on Base.metadata so Alembic autogenerate
# and create_all see every table. Add domain models as phases land.
from app.models.user import User  # noqa: F401
from app.models.notification import Notification  # noqa: F401  (shared)
from app.models import interns  # noqa: F401  (Phase 1)

from app.models import ambassadors  # noqa: F401  (Phase 2)

from app.models import instructors  # noqa: F401  (Phase 3)
from app.models.id_card import IdCard  # noqa: F401  (shared, PLAN §4.5 — pulled forward into Phase 3)
from app.models.certificate import Certificate  # noqa: F401  (shared, PLAN §4.5 — pulled forward into Phase 3)

