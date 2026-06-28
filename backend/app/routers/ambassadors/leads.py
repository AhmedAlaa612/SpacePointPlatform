import uuid
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user, require_ambassador, require_admin
from app.models.user import User
from app.models.ambassadors.lead import Lead
from app.models.ambassadors.lead_comment import LeadComment
from app.schemas.ambassadors.lead import LeadCreate, LeadOut, LeadStatusUpdate, LeadUpdate, LeadCommentCreate, LeadCommentOut
from app.services.points import award_points, adjust_points, get_setting_int
from app.services.notification import create_notification as notify
from app.services.ambassadors import achievements

logger = logging.getLogger("leads")
router = APIRouter(prefix="/leads", tags=["ambassador-leads"])


def _lead_label(lead) -> str:
    """Human label for notifications and ledger reasons — B2C leads have no company."""
    return lead.company or lead.contact_name


async def _get_lead_for_user(db: AsyncSession, lead_id: uuid.UUID, user: User) -> Lead:
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if "admin" not in user.role_values and lead.ambassador_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized for this lead")
    return lead


@router.post("", response_model=LeadOut, status_code=201)
async def create_lead(
    body: LeadCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_ambassador),
):
    if body.type == "B2B" and not (body.company or "").strip():
        raise HTTPException(status_code=400, detail="Company is required for B2B leads")
    lead = Lead(
        ambassador_id=current_user.id,
        contact_name=body.contact_name,
        company=(body.company or "").strip() or None,
        type=body.type,
        notes=body.notes,
        status="submitted",
    )
    db.add(lead)
    # Notify admins — find them and notify each
    admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
    for admin in admins:
        await notify(db, admin.id, "New Lead Submitted", f"{current_user.full_name} submitted a lead for {_lead_label(lead)}.", type="ambassador")
    await db.commit()
    await db.refresh(lead)
    return lead


@router.get("", response_model=list[LeadOut])
async def list_leads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if "admin" in current_user.role_values:
        rows = (await db.execute(
            select(Lead, User.full_name, User.email)
            .join(User, Lead.ambassador_id == User.id)
            .order_by(Lead.created_at.desc())
        )).all()
        out = []
        for lead, name, email in rows:
            d = LeadOut.model_validate(lead)
            d.ambassador_name, d.ambassador_email = name, email
            out.append(d)
        return out
    elif "ambassador" in current_user.role_values:
        rows = (await db.execute(
            select(Lead).where(Lead.ambassador_id == current_user.id).order_by(Lead.created_at.desc())
        )).scalars().all()
        return list(rows)
    raise HTTPException(status_code=403, detail="Not authorized")


@router.put("/{lead_id}/status", response_model=LeadOut)
async def update_lead_status(
    lead_id: uuid.UUID,
    body: LeadStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if body.status not in ("submitted", "in review", "converted", "closed"):
        raise HTTPException(status_code=400, detail="Invalid status")

    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalars().first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.status = body.status
    reward = await get_setting_int(db, "lead_points_reward", 1000)

    if body.status == "converted" and not lead.points_awarded:
        await award_points(db, lead.ambassador_id, reward, f"Lead converted: {_lead_label(lead)}")
        lead.points_awarded = True
        await notify(db, lead.ambassador_id, "Lead Converted!",
                     f"Your lead '{lead.contact_name}' was converted — you earned {reward} points.")
        await db.flush()
        await achievements.check_and_grant(db, lead.ambassador_id)
    elif body.status != "converted" and lead.points_awarded:
        await adjust_points(db, lead.ambassador_id, -reward, f"Lead conversion reverted: {_lead_label(lead)}")
        lead.points_awarded = False
        await notify(db, lead.ambassador_id, "Lead Update",
                     f"Your lead '{lead.contact_name}' is now '{body.status}' — {reward} points were reversed.")
    elif body.status != "converted":
        await notify(db, lead.ambassador_id, "Lead Update",
                     f"Your lead '{lead.contact_name}' is now '{body.status}'.")

    await db.commit()
    await db.refresh(lead)
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
async def edit_lead(
    lead_id: uuid.UUID,
    body: LeadUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Ambassadors can fix their own lead while it's still 'submitted'; admins anytime."""
    lead = await _get_lead_for_user(db, lead_id, current_user)
    if "admin" not in current_user.role_values and lead.status != "submitted":
        raise HTTPException(status_code=400, detail="A lead can only be edited while it's still 'submitted'")

    data = body.model_dump(exclude_unset=True)
    if "company" in data:
        data["company"] = (data["company"] or "").strip() or None
    new_type = data.get("type", lead.type)
    new_company = data.get("company", lead.company)
    if new_type == "B2B" and not new_company:
        raise HTTPException(status_code=400, detail="Company is required for B2B leads")
    for k, v in data.items():
        setattr(lead, k, v)
    await db.commit()
    await db.refresh(lead)
    return lead


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    lead = await _get_lead_for_user(db, lead_id, current_user)
    if "admin" not in current_user.role_values and lead.status not in ("submitted", "in review"):
        raise HTTPException(status_code=400, detail="Only a 'submitted' or 'in review' lead can be withdrawn")
    if lead.points_awarded:
        reward = await get_setting_int(db, "lead_points_reward", 1000)
        await adjust_points(db, lead.ambassador_id, -reward, f"Lead deleted: {_lead_label(lead)}")
    await db.delete(lead)
    await db.commit()
    return {"status": "deleted"}


# ── Comments ──────────────────────────────────────────────────

@router.get("/{lead_id}/comments", response_model=list[LeadCommentOut])
async def list_comments(
    lead_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    await _get_lead_for_user(db, lead_id, current_user)
    rows = (await db.execute(
        select(LeadComment, User.full_name, User.roles)
        .outerjoin(User, LeadComment.author_id == User.id)
        .where(LeadComment.lead_id == lead_id)
        .order_by(LeadComment.created_at.asc())
    )).all()
    out = []
    for c, name, roles in rows:
        d = LeadCommentOut.model_validate(c)
        d.author_name = name
        d.author_role = roles[0] if roles else None
        out.append(d)
    return out


@router.post("/{lead_id}/comments", response_model=LeadCommentOut, status_code=201)
async def add_comment(
    lead_id: uuid.UUID,
    body: LeadCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment can't be empty")
    lead = await _get_lead_for_user(db, lead_id, current_user)

    comment = LeadComment(lead_id=lead_id, author_id=current_user.id, body=text)
    db.add(comment)

    if "admin" in current_user.role_values:
        await notify(db, lead.ambassador_id, "New comment on your lead",
                     f"An admin commented on your lead '{lead.contact_name}'.", type="ambassador")
    else:
        admins = (await db.execute(select(User).where(User.roles.any("admin")))).scalars().all()
        for admin in admins:
            await notify(db, admin.id, "New comment on a lead",
                         f"{current_user.full_name} commented on lead '{lead.contact_name}'.", type="ambassador")

    await db.commit()
    await db.refresh(comment)
    result = LeadCommentOut.model_validate(comment)
    result.author_name = current_user.full_name
    result.author_role = current_user.role_values[0] if current_user.role_values else None
    return result
