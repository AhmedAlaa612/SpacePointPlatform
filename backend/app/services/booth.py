"""CubeSat Booth Service — capture processing, R2 storage, LMS student provisioning, and branded photo email delivery.
"""

from __future__ import annotations

import base64
import logging
import re
import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import get_password_hash
from app.models.booth import BoothEvent, BoothPhoto
from app.models.enums import UserRole
from app.models.instructors.invitation_code import InvitationCode
from app.models.user import User
from app.services import storage_r2
from app.services.documents.id_card import ensure_card_number
from app.services.email import send_email
from app.services.lms.invite_grants import redeem_invite_code
from app.services.lms.ops_integration import build_set_password_link
from app.services.nicknames import assign_nickname
from app.services.spine.identity import resolve_or_create_contact

logger = logging.getLogger("booth")


def _clean_base64_image(raw_b64: str) -> bytes:
    """Strip data URL scheme if present and decode base64 to bytes."""
    clean = re.sub(r"^data:image/\w+;base64,", "", raw_b64.strip())
    return base64.b64decode(clean)


def _build_photo_email_html(
    *,
    participant_name: str,
    photo_id: str,
    captured_at_str: str,
    activation_link: Optional[str] = None,
    event_name: str = "SpacePoint Experience",
) -> str:
    """Builds clean, Gmail-safe responsive HTML email.
    If activation_link is provided, includes the LMS student onboarding section.
    If None, strictly omits any mention of LMS or accounts.
    """
    lms_cta_html = ""
    if activation_link:
        lms_cta_html = f"""
        <!-- LMS Student Account Invitation (New Students Only) -->
        <div style="margin-top:20px;background:#f3e8ff;border:1px solid #d8b4fe;border-radius:12px;padding:20px;text-align:center;">
          <div style="font-size:16px;font-weight:700;color:#581c87;margin-bottom:6px;">
            🚀 Your SpacePoint Student LMS Account is Ready!
          </div>
          <div style="font-size:13px;color:#6b21a8;line-height:1.5;margin-bottom:16px;max-width:480px;margin-left:auto;margin-right:auto;">
            Want to build and launch real satellites? We've reserved your student account with exclusive mission access. Click below to set your password and begin your space journey.
          </div>
          <a href="{activation_link}" target="_blank"
             style="display:inline-block;background-color:#7e22ce;color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;padding:12px 28px;border-radius:8px;box-shadow:0 3px 6px rgba(126,34,206,0.25);">
            Activate Student Account
          </a>
        </div>
        """

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body style="margin:0;padding:0;background:#0d1117;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#c9d1d9;">
  <div style="max-width:620px;margin:0 auto;padding:24px 16px;">

    <!-- Header Card -->
    <div style="background:#161b22;border:1px solid #30363d;border-radius:14px;padding:24px 20px;text-align:center;">
      <div style="font-size:13px;font-weight:700;color:#8957e5;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;">
        SpacePoint CubeSat Mission
      </div>
      <div style="font-size:22px;font-weight:800;color:#f0f6fc;line-height:1.3;">
        Here is your picture from a satellite! 🛰️
      </div>
      <div style="margin-top:8px;font-size:14px;color:#8b949e;line-height:1.5;">
        Hi {participant_name}, thanks for visiting the SpacePoint CubeSat booth at <strong>{event_name}</strong>.
      </div>
    </div>

    <!-- Photo Preview Card -->
    <div style="margin-top:16px;background:#161b22;border:1px solid #30363d;border-radius:14px;padding:18px 20px;">
      <div style="text-align:center;">
        <img src="cid:cubesat-photo" alt="CubeSat Photo"
          style="max-width:100%;border-radius:10px;border:1px solid #30363d;display:block;margin:0 auto;" />
      </div>

      <div style="margin-top:14px;font-size:12px;color:#8b949e;line-height:1.6;text-align:center;">
        <div>Captured: <strong>{captured_at_str}</strong> (Dubai Time) &nbsp;|&nbsp; Ref: <code style="color:#c9d1d9;">{photo_id}</code></div>
      </div>
    </div>

    {lms_cta_html}

    <!-- CTA Website -->
    <div style="margin-top:24px;text-align:center;">
      <a href="https://spacepoint.ae" target="_blank"
         style="display:inline-block;background-color:#238636;color:#ffffff;text-decoration:none;font-size:14px;font-weight:bold;padding:12px 24px;border-radius:8px;">
        Explore SpacePoint Ecosystem
      </a>
    </div>

    <!-- Footer -->
    <div style="margin-top:20px;text-align:center;color:#6e7681;font-size:12px;line-height:1.6;">
      Download the attached photo file if preview doesn't render.<br />
      © {datetime.now(timezone.utc).year} SpacePoint. All rights reserved.
    </div>

  </div>
</body>
</html>"""


async def process_booth_capture(
    db: AsyncSession,
    *,
    event_slug: str,
    participant_name: str,
    participant_email: str,
    image_base64: str,
    satellite_id: Optional[str] = None,
) -> dict:
    """Processes a photo capture from a CubeSat booth:
    1. Validates the event
    2. Uploads the image to Cloudflare R2 (`settings.R2_BOOTH_BUCKET`)
    3. Checks if user exists in the LMS:
       - If exists: links photo, NO mention of LMS in email.
       - If new & event auto-creates: creates student account, applies invite code grants, generates activation link.
    4. Sends branded photo email via verified SMTP.
    5. Saves BoothPhoto log to database.
    """
    clean_email = participant_email.strip().lower()
    clean_name = participant_name.strip()

    # 1. Fetch Event
    stmt = (
        select(BoothEvent)
        .options(selectinload(BoothEvent.invitation_code))
        .where(BoothEvent.slug == event_slug.strip().lower())
    )
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail=f"Booth event '{event_slug}' not found")
    if not event.is_active:
        raise HTTPException(status_code=400, detail="This booth event is not currently active")

    # 2. Decode & upload to R2
    try:
        image_bytes = _clean_base64_image(image_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 image data: {exc}")

    photo_uuid = str(uuid.uuid4())
    bucket_name = settings.R2_BOOTH_BUCKET or settings.R2_BUCKET or "spacepoint-videos"
    storage_path = f"photos/{event.slug}/{photo_uuid}.jpg"

    try:
        await storage_r2.upload_to_path(
            bucket="photos",
            path=f"{event.slug}/{photo_uuid}.jpg",
            data=image_bytes,
            content_type="image/jpeg",
            r2_bucket=bucket_name,
        )
    except Exception as exc:
        logger.exception("Failed to upload booth photo to R2")
        raise HTTPException(status_code=500, detail=f"Storage upload error: {exc}")

    # 3. Check User & Account Provisioning
    user_stmt = select(User).where(User.email == clean_email)
    user_res = await db.execute(user_stmt)
    existing_user = user_res.scalar_one_or_none()

    linked_user: Optional[User] = None
    is_new_user = False
    activation_link: Optional[str] = None

    if existing_user:
        linked_user = existing_user
        is_new_user = False
        # If event has an invite code, optionally apply any unapplied grants
        if event.invitation_code:
            try:
                await redeem_invite_code(db, user=existing_user, code_str=event.invitation_code.code)
            except Exception:
                logger.warning("Could not redeem invite code for existing user %s", existing_user.id)
    elif event.auto_create_lms_account:
        # Provision new LMS Student Account
        try:
            contact, _ = await resolve_or_create_contact(
                db,
                full_name=clean_name,
                email=clean_email,
                contact_roles=["student"],
                role_event_source="booth_signup",
            )
            # Create user with unactivated password state
            temp_hash = get_password_hash(secrets.token_urlsafe(24))
            new_user = User(
                full_name=clean_name,
                email=clean_email,
                password_hash=temp_hash,
                roles=[UserRole.student],
                status="active",
                must_change_password=True,
                contact_id=contact.id if contact else None,
                invitation_code_used=event.invitation_code.code if event.invitation_code else None,
            )
            db.add(new_user)
            await db.flush()

            await assign_nickname(db, new_user)
            await ensure_card_number(db, new_user)

            if event.invitation_code:
                await redeem_invite_code(db, user=new_user, code_str=event.invitation_code.code)

            linked_user = new_user
            is_new_user = True

            # Generate Option A activation link (valid 7 days)
            activation_link = build_set_password_link(new_user)
        except Exception as exc:
            logger.exception("Error auto-creating student account for %s: %s", clean_email, exc)

    # 4. Save BoothPhoto Record
    now = datetime.now(timezone.utc)
    photo_record = BoothPhoto(
        event_id=event.id,
        participant_name=clean_name,
        participant_email=clean_email,
        storage_bucket=bucket_name,
        storage_path=storage_path,
        satellite_id=satellite_id,
        user_id=linked_user.id if linked_user else None,
        is_new_lms_user=is_new_user,
        email_sent=False,
        created_at=now,
    )
    db.add(photo_record)
    await db.flush()

    # 5. Dispatch Email
    captured_at_str = now.strftime("%Y-%m-%d %H:%M")
    email_html = _build_photo_email_html(
        participant_name=clean_name,
        photo_id=photo_uuid[:8],
        captured_at_str=captured_at_str,
        activation_link=activation_link,
        event_name=event.name,
    )

    subject = event.email_subject or f"Your CubeSat Photo — SpacePoint × {event.name}"

    try:
        await send_email(
            to=clean_email,
            subject=subject,
            body=email_html,
            html=True,
            attachments=[
                (f"cubesat_{photo_uuid[:8]}.jpg", image_bytes, "jpeg"),
            ],
            inline_images={
                "cubesat-photo": (image_bytes, "image", "jpeg"),
            },
        )
        photo_record.email_sent = True
        photo_record.email_sent_at = datetime.now(timezone.utc)
    except Exception as exc:
        logger.exception("Failed to send booth photo email to %s", clean_email)
        photo_record.email_error = str(exc)

    await db.commit()
    await db.refresh(photo_record)

    return {
        "success": True,
        "photo_id": str(photo_record.id),
        "event": event.name,
        "email_sent": photo_record.email_sent,
        "lms_account_created": is_new_user,
        "existing_user": bool(existing_user),
    }


async def get_booth_analytics(db: AsyncSession, event_id: Optional[uuid.UUID] = None) -> dict:
    """Returns analytics summary for an event or all events combined."""
    photo_q = select(func.count(BoothPhoto.id))
    new_users_q = select(func.count(BoothPhoto.id)).where(BoothPhoto.is_new_lms_user.is_(True))
    logged_in_q = (
        select(func.count(func.distinct(BoothPhoto.user_id)))
        .join(User, BoothPhoto.user_id == User.id)
        .where(BoothPhoto.is_new_lms_user.is_(True), User.last_login_at.isnot(None))
    )

    if event_id:
        photo_q = photo_q.where(BoothPhoto.event_id == event_id)
        new_users_q = new_users_q.where(BoothPhoto.event_id == event_id)
        logged_in_q = logged_in_q.where(BoothPhoto.event_id == event_id)

    total_photos = (await db.execute(photo_q)).scalar() or 0
    new_users = (await db.execute(new_users_q)).scalar() or 0
    logged_in_students = (await db.execute(logged_in_q)).scalar() or 0

    return {
        "total_photos": total_photos,
        "new_lms_users_created": new_users,
        "logged_in_students": logged_in_students,
        "login_conversion_rate": round((logged_in_students / new_users * 100), 1) if new_users > 0 else 0.0,
    }
