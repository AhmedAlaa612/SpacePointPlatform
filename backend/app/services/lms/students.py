"""Student search (extracted 2026-09-14 from `routers/lms/admin.py::search_students`
so the Competition Judging Assign tab can reuse the exact same search — name/email
substring, invite-code batch filter — instead of re-implementing it, and layer its
own cohort-scoped "already on a team" filter on top (`services/competitions/
team_lookup.py`). Behavior is unchanged from the original inline version; only the
call site moved.
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.lms_admin import StudentSummaryOut


async def search_students(
    db: AsyncSession, *, q: str | None = None, invite_code: str | None = None, limit: int = 50,
) -> list[StudentSummaryOut]:
    """Name/email substring search over student accounts, capped at `limit` rows.

    `invite_code` filters to one batch. The literal string `none` selects
    students with no code at all — the ones who signed up before the gate
    existed; without it they'd be unreachable through the filter, since "no
    code" isn't a code you can type."""
    stmt = select(User).where(User.roles.any("student"))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if invite_code:
        if invite_code.strip().lower() == "none":
            stmt = stmt.where(User.invitation_code_used.is_(None))
        else:
            stmt = stmt.where(User.invitation_code_used == invite_code.strip().upper())
    rows = (await db.execute(stmt.order_by(User.full_name).limit(limit))).scalars().all()

    labels = dict((await db.execute(
        select(InvitationCode.code, InvitationCode.label).where(InvitationCode.kind == "student")
    )).all())

    # School and grade live on the linked spine Contact, not on `users` —
    # resolved in two batched queries rather than one pair per row.
    contact_ids = [u.contact_id for u in rows if u.contact_id]
    contacts = {
        c.id: c for c in (
            (await db.execute(select(Contact).where(Contact.id.in_(contact_ids)))).scalars().all()
            if contact_ids else []
        )
    }
    org_ids = {c.organization_id for c in contacts.values() if c.organization_id}
    orgs = {
        o.id: o for o in (
            (await db.execute(select(Organization).where(Organization.id.in_(org_ids)))).scalars().all()
            if org_ids else []
        )
    }

    out = []
    for u in rows:
        contact = contacts.get(u.contact_id) if u.contact_id else None
        org = orgs.get(contact.organization_id) if contact and contact.organization_id else None
        out.append(StudentSummaryOut(
            id=u.id, full_name=u.full_name, nickname=u.nickname, email=u.email,
            invite_code=u.invitation_code_used,
            invite_label=labels.get(u.invitation_code_used) if u.invitation_code_used else None,
            school_name=org.name_latin if org else None,
            grade=contact.grade if contact else None,
            status=u.status,
            created_at=u.created_at,
        ))
    return out
