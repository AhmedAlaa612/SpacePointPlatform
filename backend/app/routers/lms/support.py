"""Support-widget routes — `/lms/support/*`.

One read-only route, backing the Fin (Intercom) messenger mounted on the
student surface (`frontend/src/components/FinWidget.tsx`).

**It takes no user id.** The caller is resolved from their own token and the
payload describes them and nobody else, so there is no parameter to tamper
with — the whole IDOR class is absent rather than defended against. Any
future "look up student X for support" need is a different route with a
different guard, never a parameter bolted onto this one.

Under `/lms` rather than hanging off `auth.py`: team and cohort are LMS
concepts, the LMS router already aggregates sub-routers, and `auth.py` is
long enough already.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.lms import ChatIdentityOut, SupportConfigOut
from app.services.lms.support import chat_identity
from app.services.settings import get_portal_setting

router = APIRouter(prefix="/lms/support", tags=["lms-support"])


@router.get("/config", response_model=SupportConfigOut)
async def get_support_config(db: AsyncSession = Depends(get_db)):
    """Public/student read-only endpoint returning support messenger availability."""
    val = await get_portal_setting(db, "fin_support_enabled", default="true")
    is_enabled = val.lower() not in ("false", "0", "off", "no")
    return SupportConfigOut(fin_enabled=is_enabled)


@router.get("/chat-identity", response_model=ChatIdentityOut)
async def chat_identity_route(
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """The caller's own Fin messenger identity.

    Open to any authenticated account rather than gated on `student`, matching
    how `/lms/my-courses` is deliberately scoped (see the student router's
    docstring): staff who were granted an LMS course reach `/learn/*` too, and
    the widget is mounted for them there.

    503 when `INTERCOM_IDENTITY_SECRET` is unset. A blank secret would still
    produce a syntactically valid HMAC — one keyed on the empty string, which
    every deployment sharing that misconfiguration could forge. Failing loudly
    is the point: the frontend falls back to booting anonymously, which is
    exactly the pre-identity behaviour and degrades rather than breaks.
    """
    val = await get_portal_setting(db, "fin_support_enabled", default="true")
    if val.lower() in ("false", "0", "off", "no"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Fin support messenger is disabled by administrator",
        )

    if not settings.INTERCOM_IDENTITY_SECRET:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat identity is not configured",
        )
    return await chat_identity(db, user=current, secret=settings.INTERCOM_IDENTITY_SECRET)
