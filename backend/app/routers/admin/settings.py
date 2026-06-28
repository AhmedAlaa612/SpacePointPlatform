import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_admin
from app.db.session import get_db
from app.models.instructors.payment import PortalSetting
from app.models.user import User
from app.schemas.instructors.admin import PortalSettingUpdate
from app.services import storage

router = APIRouter(prefix="/settings", tags=["admin-settings"])


@router.get("")
async def list_settings(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)):
    from app.core.config import settings as app_settings
    rows = (await db.execute(select(PortalSetting))).scalars().all()
    data = {s.key: s.value for s in rows}
    if "admin_signatory_name" not in data:
        data["admin_signatory_name"] = app_settings.DEFAULT_SIGNATORY_NAME
    if "admin_signatory_title" not in data:
        data["admin_signatory_title"] = app_settings.DEFAULT_SIGNATORY_TITLE
    return data


@router.post("")
async def upsert_setting(
    body: PortalSettingUpdate, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    setting = (await db.execute(select(PortalSetting).where(PortalSetting.key == body.key))).scalars().first()
    if setting:
        setting.value = body.value
    else:
        db.add(PortalSetting(key=body.key, value=body.value))
    await db.commit()
    return {"key": body.key, "value": body.value}


@router.post("/admin-signature")
async def upload_admin_signature(
    file: UploadFile, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_admin)
):
    data = await file.read()
    url = await storage.upload_file("instructor-documents", "settings/admin_signature.png", data, file.content_type or "image/png")
    setting = (await db.execute(select(PortalSetting).where(PortalSetting.key == "admin_signature_url"))).scalars().first()
    if setting:
        setting.value = url
    else:
        db.add(PortalSetting(key="admin_signature_url", value=url))
    await db.commit()
    return {"admin_signature_url": url}
