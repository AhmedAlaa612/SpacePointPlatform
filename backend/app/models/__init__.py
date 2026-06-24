# Importing models here registers them on Base.metadata so Alembic autogenerate
# and create_all see every table. Add domain models as phases land.
from app.models.user import User  # noqa: F401

# Phase 1 — interns:     from app.models.interns import *
# Phase 2 — ambassadors: from app.models.ambassadors import *
# Phase 3 — instructors: from app.models.instructors import *
