# Importing models here registers them on Base.metadata so Alembic autogenerate
# and create_all see every table. Add domain models as phases land.
from app.models.user import User  # noqa: F401
from app.models.notification import Notification  # noqa: F401  (shared)
from app.models import interns  # noqa: F401  (Phase 1)

# Phase 2 — ambassadors: from app.models import ambassadors
# Phase 3 — instructors: from app.models import instructors
