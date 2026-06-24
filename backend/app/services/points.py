"""Points service (PLAN §8.4).

Shared award path used by the ambassadors domain (leads converted, tasks
approved, sessions delivered) and by the instructors domain when an application
is approved for an ambassador-referred applicant.

Full implementation lands in Phase 2 (ported from
`ambassadorsV1/backend/app/services/points.py`). Signature is fixed now so other
domains can depend on it.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def award_points(db: AsyncSession, user_id: UUID, amount: int, reason: str) -> None:
    raise NotImplementedError("award_points is implemented in Phase 2 (ambassadors domain).")
