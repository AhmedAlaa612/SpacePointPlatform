"""Deep cascade deletion for @spacepoint.local test accounts.

Enforces two hard safety invariants:
1. Target email MUST belong to settings.TEST_EMAIL_DOMAIN (@spacepoint.local).
2. Target account MUST NOT hold the 'admin' role or match settings.ADMIN_EMAIL.
"""

from __future__ import annotations

import logging
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.application import Application
from app.models.certificate import Certificate
from app.models.document import Document
from app.models.instructors.instructor_document import InstructorDocument
from app.models.instructors.instructor_profile import InstructorProfile
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.payment import PaymentLetter
from app.models.spine.contact import Contact, ContactRelationship
from app.models.user import User
from app.services import storage
from app.services.spine.identity import normalize_user_email, user_email_matches

logger = logging.getLogger(__name__)


def assert_test_email_allowed(email: str | None) -> str:
    norm = normalize_user_email(email)
    if not norm or not settings.is_test_email(norm):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only @{settings.TEST_EMAIL_DOMAIN} test accounts can be managed or cascade-deleted here.",
        )
    if norm == normalize_user_email(settings.ADMIN_EMAIL):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The primary admin account cannot be modified or deleted.",
        )
    return norm


def assert_test_user_allowed(user: User) -> None:
    assert_test_email_allowed(user.email)
    if "admin" in user.role_values:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts cannot be modified or deleted from Operations.",
        )


async def _collect_and_delete_storage_files(
    db: AsyncSession, user_id: UUID | None, email: str
) -> int:
    """Best-effort cleanup of stored files belonging to the test user/application."""
    files_to_delete: list[tuple[str, str]] = []

    if user_id:
        user = await db.get(User, user_id)
        if user and user.photo_path:
            files_to_delete.append(("profile_pictures", user.photo_path))

        for doc in (await db.execute(select(Document).where(Document.user_id == user_id))).scalars().all():
            if doc.bucket and doc.file_path:
                files_to_delete.append((doc.bucket, doc.file_path))

        for cert in (await db.execute(select(Certificate).where(Certificate.user_id == user_id))).scalars().all():
            if cert.bucket and cert.file_path:
                files_to_delete.append((cert.bucket, cert.file_path))

        for idoc in (await db.execute(select(InstructorDocument).where(InstructorDocument.user_id == user_id))).scalars().all():
            if idoc.bucket and idoc.file_path:
                files_to_delete.append((idoc.bucket, idoc.file_path))

        for msub in (await db.execute(select(ModuleSubmission).where(ModuleSubmission.user_id == user_id))).scalars().all():
            if msub.bucket and msub.file_path:
                files_to_delete.append((msub.bucket, msub.file_path))

        prof = await db.get(InstructorProfile, user_id)
        if prof:
            if prof.contract_path:
                files_to_delete.append(("contracts", prof.contract_path))
            if prof.signed_contract_path:
                files_to_delete.append(("contracts", prof.signed_contract_path))

        for letter in (await db.execute(select(PaymentLetter).where(PaymentLetter.instructor_user_id == user_id))).scalars().all():
            if letter.pdf_path:
                files_to_delete.append(("payment-letters", letter.pdf_path))
            if letter.signed_pdf_path:
                files_to_delete.append(("payment-letters", letter.signed_pdf_path))

    for app_row in (
        await db.execute(select(Application).where(func.lower(Application.email) == email))
    ).scalars().all():
        if app_row.cv_path:
            files_to_delete.append(("cvs", app_row.cv_path))

    deleted_count = 0
    for bucket, path in files_to_delete:
        try:
            await storage.delete_file(bucket, path)
            deleted_count += 1
        except Exception:
            logger.debug("Storage delete skipped for %s/%s", bucket, path, exc_info=True)
    return deleted_count


async def purge_mailpit_messages(email: str) -> int:
    """Best-effort delete of all Mailpit messages involving `email`."""
    if not settings.MAILPIT_API_URL:
        return 0
    auth = None
    if settings.MP_UI_AUTH and ":" in settings.MP_UI_AUTH:
        u, p = settings.MP_UI_AUTH.split(":", 1)
        auth = (u, p)
    url = f"{settings.MAILPIT_API_URL.rstrip('/')}/api/v1/search"
    try:
        async with httpx.AsyncClient(timeout=3.0, auth=auth) as client:
            resp = await client.request("DELETE", url, params={"query": email})
            if resp.status_code < 300:
                return 1
    except Exception:
        logger.debug("Mailpit purge skipped for %s", email, exc_info=True)
    return 0


async def _delete_intern_epic_tree(db: AsyncSession, epic_id: UUID) -> None:
    task_ids = (
        await db.execute(
            text("SELECT t.id FROM tasks t JOIN modules m ON m.id = t.module_id WHERE m.epic_id = :eid"),
            {"eid": epic_id},
        )
    ).scalars().all()
    for tid in task_ids:
        await db.execute(text("DELETE FROM task_mind_map_notes WHERE task_id = :tid"), {"tid": tid})
        await db.execute(text("DELETE FROM task_submissions WHERE task_id = :tid"), {"tid": tid})
        await db.execute(text("DELETE FROM task_assignees WHERE task_id = :tid"), {"tid": tid})
        await db.execute(text("DELETE FROM tasks WHERE id = :tid"), {"tid": tid})
    await db.execute(text("DELETE FROM modules WHERE epic_id = :eid"), {"eid": eid})
    await db.execute(text("DELETE FROM mind_map_layouts WHERE epic_id = :eid"), {"eid": eid})
    await db.execute(text("DELETE FROM proposals WHERE epic_id = :eid"), {"eid": eid})
    await db.execute(text("DELETE FROM epics WHERE id = :eid"), {"eid": eid})


async def _table_exists(db: AsyncSession, table_name: str) -> bool:
    res = await db.execute(text(f"SELECT to_regclass('public.{table_name}')"))
    return res.scalar() is not None


async def cascade_delete_test_account(
    db: AsyncSession,
    *,
    user_id: UUID | None = None,
    email: str | None = None,
) -> dict:
    """Completely wipes a @spacepoint.local test user, their linked Spine
    Contact, orphan guardian contacts, applications, RESTRICT FK rows,
    storage files, and Mailpit inbox messages."""
    user: User | None = None
    if user_id is not None:
        user = await db.get(User, user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        assert_test_user_allowed(user)
        target_email = normalize_user_email(user.email)
    elif email is not None:
        target_email = assert_test_email_allowed(email)
        user = (await db.execute(select(User).where(user_email_matches(target_email)))).scalars().first()
        if user:
            assert_test_user_allowed(user)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="user_id or email required")

    uid = user.id if user else None
    contact_ids: set[UUID] = set()
    if user and user.contact_id:
        contact_ids.add(user.contact_id)

    # Also locate any Spine contacts carrying this @spacepoint.local email
    email_contacts = (
        await db.execute(select(Contact.id).where(func.lower(Contact.email) == target_email))
    ).scalars().all()
    contact_ids.update(email_contacts)

    # 1. Delete storage files before DB rows disappear
    deleted_files = await _collect_and_delete_storage_files(db, uid, target_email)

    if uid is not None:
        # 2. Live Games (RESTRICT FKs on users.id)
        await db.execute(
            text("DELETE FROM game_answers WHERE participant_id IN (SELECT id FROM game_participants WHERE user_id = :uid)"),
            {"uid": uid},
        )
        await db.execute(text("DELETE FROM game_participants WHERE user_id = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM game_runs WHERE created_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM game_session_assignments WHERE assigned_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM games WHERE created_by = :uid"), {"uid": uid})

        # 3. Missions & Learner Teams (RESTRICT FKs on users.id and learner_teams.id)
        await db.execute(text("DELETE FROM mission_attempt_members WHERE user_id = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM mission_attempts WHERE user_id = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM design_custom_components WHERE user_id = :uid"), {"uid": uid})

        # Find learner_teams where this user is a member or creator and no other members remain
        solo_team_ids = (
            await db.execute(
                text("""
                    SELECT lt.id
                    FROM learner_teams lt
                    LEFT JOIN learner_team_members ltm ON ltm.team_id = lt.id AND ltm.user_id != :uid
                    WHERE (lt.created_by = :uid OR EXISTS (
                        SELECT 1 FROM learner_team_members m2 WHERE m2.team_id = lt.id AND m2.user_id = :uid
                    ))
                    GROUP BY lt.id
                    HAVING COUNT(ltm.user_id) = 0
                """),
                {"uid": uid},
            )
        ).scalars().all()

        for tid in solo_team_ids:
            await db.execute(text("DELETE FROM mission_attempts WHERE team_id = :tid"), {"tid": tid})
            await db.execute(text("DELETE FROM learner_teams WHERE id = :tid"), {"tid": tid})

        await db.execute(text("DELETE FROM learner_team_members WHERE user_id = :uid"), {"uid": uid})
        await db.execute(text("UPDATE learner_teams SET created_by = NULL WHERE created_by = :uid"), {"uid": uid})
        await db.execute(text("UPDATE learner_teams SET final_locked_by = NULL WHERE final_locked_by = :uid"), {"uid": uid})
        await db.execute(text("UPDATE learner_teams SET ops_scored_by = NULL WHERE ops_scored_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM mission_proposals WHERE submitted_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM missions WHERE authored_by = :uid"), {"uid": uid})

        # 4. Interns domain (tables without ondelete CASCADE)
        await db.execute(text("DELETE FROM task_assignees WHERE user_id = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM task_submissions WHERE submitted_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM team_members WHERE user_id = :uid"), {"uid": uid})

        # Delete intern projects created by this test user (if no non-test epics/teams rely on them)
        proj_ids = (
            await db.execute(text("SELECT id FROM projects WHERE created_by = :uid"), {"uid": uid})
        ).scalars().all()
        for pid in proj_ids:
            epic_ids = (
                await db.execute(text("SELECT id FROM epics WHERE project_id = :pid"), {"pid": pid})
            ).scalars().all()
            for eid in epic_ids:
                await _delete_intern_epic_tree(db, eid)
            await db.execute(text("DELETE FROM project_teams WHERE project_id = :pid"), {"pid": pid})
            await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": pid})

        # Delete intern teams led by this test user
        led_team_ids = (
            await db.execute(text("SELECT id FROM teams WHERE leader_id = :uid"), {"uid": uid})
        ).scalars().all()
        for itid in led_team_ids:
            epic_ids = (
                await db.execute(text("SELECT id FROM epics WHERE team_id = :itid"), {"itid": itid})
            ).scalars().all()
            for eid in epic_ids:
                await _delete_intern_epic_tree(db, eid)
            await db.execute(text("DELETE FROM project_teams WHERE team_id = :itid"), {"itid": itid})
            await db.execute(text("DELETE FROM team_members WHERE team_id = :itid"), {"itid": itid})
            await db.execute(text("DELETE FROM teams WHERE id = :itid"), {"itid": itid})

        # 5. LMS, Sessions, & Inventory RESTRICT FKs
        await db.execute(text("DELETE FROM attendance_records WHERE recorded_by_user_id = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM kit_checks WHERE checked_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM session_kits WHERE created_by = :uid"), {"uid": uid})
        await db.execute(text("DELETE FROM cohort_kits WHERE created_by = :uid"), {"uid": uid})
        # Delete test-created learning_paths and courses
        lp_ids = (
            await db.execute(text("SELECT id FROM learning_paths WHERE created_by = :uid"), {"uid": uid})
        ).scalars().all()
        for lpid in lp_ids:
            await db.execute(text("DELETE FROM learning_path_steps WHERE path_id = :lpid"), {"lpid": lpid})
            await db.execute(text("DELETE FROM learning_paths WHERE id = :lpid"), {"lpid": lpid})

        course_ids = (
            await db.execute(text("SELECT id FROM courses WHERE created_by = :uid"), {"uid": uid})
        ).scalars().all()
        for cid in course_ids:
            await db.execute(text("DELETE FROM learning_path_steps WHERE course_id = :cid"), {"cid": cid})
            await db.execute(text("DELETE FROM course_modules WHERE course_id = :cid"), {"cid": cid})
            await db.execute(text("DELETE FROM courses WHERE id = :cid"), {"cid": cid})

        # 6. Website events & Owned Organizations
        has_website_events = await _table_exists(db, "website_events")
        if has_website_events:
            await db.execute(
                text("UPDATE website_events SET created_by_user_id = NULL WHERE created_by_user_id = :uid"),
                {"uid": uid},
            )
        owned_orgs = (
            await db.execute(text("SELECT id FROM organizations WHERE owner_user_id = :uid"), {"uid": uid})
        ).scalars().all()
        for oid in owned_orgs:
            if has_website_events:
                await db.execute(
                    text("UPDATE website_events SET organization_id = NULL WHERE organization_id = :oid"),
                    {"oid": oid},
                )
            await db.execute(
                text("UPDATE contacts SET organization_id = NULL WHERE organization_id = :oid"),
                {"oid": oid},
            )
            cohort_cnt = (
                await db.execute(text("SELECT COUNT(*) FROM cohorts WHERE organization_id = :oid"), {"oid": oid})
            ).scalar_one()
            if cohort_cnt == 0:
                await db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": oid})
            else:
                await db.execute(
                    text("UPDATE organizations SET owner_user_id = NULL WHERE id = :oid"),
                    {"oid": oid},
                )

        # Nullify referrals pointing to this user
        await db.execute(text("UPDATE users SET invited_by_id = NULL WHERE invited_by_id = :uid"), {"uid": uid})
        if await _table_exists(db, "user_invitation_codes"):
            await db.execute(text("DELETE FROM user_invitation_codes WHERE user_id = :uid"), {"uid": uid})

        # 7. Delete User row (cascades 35+ dependent tables)
        await db.delete(user)
        await db.flush()

    # 8. Delete Applications matching target_email
    await db.execute(text("DELETE FROM applications WHERE LOWER(email) = :email"), {"email": target_email})
    if await _table_exists(db, "cohort_media_consents"):
        await db.execute(
            text("DELETE FROM cohort_media_consents WHERE LOWER(student_email_raw) = :email OR LOWER(parent_email) = :email"),
            {"email": target_email},
        )

    # 9. Delete Spine Contacts + Orphan Guardian Contacts
    orphan_guardian_ids: set[UUID] = set()
    for cid in contact_ids:
        guardian_links = (
            await db.execute(
                select(ContactRelationship.contact_id).where(
                    ContactRelationship.related_contact_id == cid,
                    ContactRelationship.relation == "guardian_of",
                )
            )
        ).scalars().all()
        for gid in guardian_links:
            if gid in contact_ids:
                continue
            other_kids = (
                await db.execute(
                    select(func.count()).select_from(ContactRelationship).where(
                        ContactRelationship.contact_id == gid,
                        ContactRelationship.related_contact_id != cid,
                    )
                )
            ).scalar_one()
            has_user = (
                await db.execute(select(User.id).where(User.contact_id == gid).limit(1))
            ).first()
            if other_kids == 0 and not has_user:
                orphan_guardian_ids.add(gid)

    all_contacts_to_delete = contact_ids | orphan_guardian_ids
    for cid in all_contacts_to_delete:
        await db.execute(text("UPDATE users SET contact_id = NULL WHERE contact_id = :cid"), {"cid": cid})
        await db.execute(
            text("UPDATE organizations SET primary_contact_id = NULL WHERE primary_contact_id = :cid"),
            {"cid": cid},
        )
        await db.execute(
            text("UPDATE contacts SET merged_into_id = NULL WHERE merged_into_id = :cid"),
            {"cid": cid},
        )
        await db.execute(
            text("UPDATE registrations SET payer_contact_id = NULL WHERE payer_contact_id = :cid"),
            {"cid": cid},
        )
        await db.execute(
            text("UPDATE consent_records SET guardian_contact_id = NULL WHERE guardian_contact_id = :cid"),
            {"cid": cid},
        )
        if await _table_exists(db, "cohort_media_consents"):
            await db.execute(text("DELETE FROM cohort_media_consents WHERE matched_contact_id = :cid"), {"cid": cid})
        await db.execute(text("DELETE FROM touchpoints WHERE contact_id = :cid"), {"cid": cid})
        await db.execute(text("DELETE FROM contacts WHERE id = :cid"), {"cid": cid})

    db.expire_all()
    await db.commit()

    # 10. Purge Mailpit inbox for this test address
    await purge_mailpit_messages(target_email)

    return {
        "detail": f"Cascade deleted test account {target_email}",
        "email": target_email,
        "deleted_user_id": str(uid) if uid else None,
        "deleted_contacts": len(all_contacts_to_delete),
        "deleted_files": deleted_files,
    }
