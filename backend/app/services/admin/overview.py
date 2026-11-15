from datetime import datetime, timezone
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.application import Application
from app.models.document_request import DocumentRequest
from app.models.enums import ApplicationStatus, PaymentLetterStatus
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.payment import PaymentLetter
from app.models.internship import RoleRequest
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.admin.overview import (
    ActionQueueItem,
    AdminCommandOverviewOut,
    BusinessOverview,
    OnboardingSummary,
    PaymentsStatusSummary,
    PendingRequestsSummary,
)
from app.services.sessions.journey import pending_payment_instructors


_DOC_LABELS = {
    "recommendation_letter": "Recommendation Letter",
    "confirmation_letter": "Confirmation Letter",
    "completion_letter": "Completion Letter",
    "certificate": "Completion Certificate",
}


async def get_admin_command_overview(db: AsyncSession) -> AdminCommandOverviewOut:
    # 1. Pending applications, role requests, and document requests
    pending_apps = (
        await db.execute(
            select(Application)
            .where(Application.status == "pending")
            .order_by(Application.created_at.desc())
        )
    ).scalars().all()

    pending_role_rows = (
        await db.execute(
            select(RoleRequest, User)
            .join(User, User.id == RoleRequest.requester_user_id)
            .where(RoleRequest.status == "pending")
            .order_by(RoleRequest.created_at.desc())
        )
    ).all()

    pending_doc_rows = (
        await db.execute(
            select(DocumentRequest, User)
            .join(User, User.id == DocumentRequest.user_id)
            .where(DocumentRequest.status == "pending")
            .order_by(DocumentRequest.created_at.desc())
        )
    ).all()

    # 2. Onboarding reviews (Phase 1..3 pending vs under_review)
    review_rows = (
        await db.execute(
            select(ApplicationReview, User)
            .join(User, User.id == ApplicationReview.user_id)
            .where(
                ApplicationReview.status.in_([
                    ApplicationStatus.in_progress,
                    ApplicationStatus.phase_1_approved,
                    ApplicationStatus.research_approved,
                    ApplicationStatus.under_review,
                ])
            )
            .order_by(ApplicationReview.last_status_change_at.desc())
        )
    ).all()

    phase1_in_progress = sum(1 for r, _ in review_rows if r.status == ApplicationStatus.in_progress)
    phase2_in_progress = sum(1 for r, _ in review_rows if r.status == ApplicationStatus.research_approved)
    phase3_in_progress = sum(1 for r, _ in review_rows if r.status == ApplicationStatus.phase_1_approved)
    phase2_or_3_in_progress = phase2_in_progress + phase3_in_progress
    to_review_rows = [(r, u) for r, u in review_rows if r.status == ApplicationStatus.under_review]

    # 3. Payments status counts (no AED amounts)
    unbilled = await pending_payment_instructors(db)
    letter_rows = (
        await db.execute(
            select(PaymentLetter, User)
            .join(User, User.id == PaymentLetter.instructor_user_id)
            .where(
                PaymentLetter.status.in_([
                    PaymentLetterStatus.draft,
                    PaymentLetterStatus.published,
                    PaymentLetterStatus.signed,
                ])
            )
            .order_by(PaymentLetter.updated_at.desc())
        )
    ).all()

    draft_letters = [(l, u) for l, u in letter_rows if l.status == PaymentLetterStatus.draft]
    published_letters = [(l, u) for l, u in letter_rows if l.status == PaymentLetterStatus.published]
    signed_letters = [(l, u) for l, u in letter_rows if l.status == PaymentLetterStatus.signed]

    # 4. Business user/role + partner org totals
    # Partner-organization fence: `organizations` also holds login-less school/university
    # rows created by student intake (`owner_user_id IS NULL`). Only count onboarded
    # partner organizations that own a portal account.
    role_rows = (await db.execute(select(User.roles))).scalars().all()
    org_count = (
        await db.execute(
            select(func.count())
            .select_from(Organization)
            .where(Organization.owner_user_id.is_not(None))
        )
    ).scalar_one()

    role_counts: dict[str, int] = {}
    for roles in role_rows:
        for r in roles or []:
            val = r.value if hasattr(r, "value") else str(r)
            role_counts[val] = role_counts.get(val, 0) + 1

    business = BusinessOverview(
        total_users=len(role_rows),
        students=role_counts.get("student", 0),
        instructors=role_counts.get("instructor", 0),
        interns=role_counts.get("intern", 0),
        organizations=int(org_count or 0),
        ambassadors=role_counts.get("ambassador", 0),
        mentors=role_counts.get("mentor", 0),
        facilitators=role_counts.get("facilitator", 0),
        applicants=role_counts.get("applicant", 0),
        org_members=role_counts.get("organization", 0),
        ops_admin=sum(
            1
            for roles in role_rows
            if any(
                (r.value if hasattr(r, "value") else str(r)) in ("admin", "operations", "coo", "storekeeper")
                for r in (roles or [])
            )
        ),
    )

    # 6. Unified Actions feed
    actions: list[ActionQueueItem] = []

    for app in pending_apps:
        actions.append(
            ActionQueueItem(
                id=str(app.id),
                kind="app",
                tag="Application",
                tone="purple",
                title=f"{app.full_name} — {app.role.title()}",
                subtitle="Pending application review",
                cta="Review",
                href=f"/admin/applications?id={app.id}",
                created_at=app.created_at,
            )
        )

    for req, u in pending_role_rows:
        actions.append(
            ActionQueueItem(
                id=str(req.id),
                kind="role_request",
                tag="Role Request",
                tone="purple",
                title=f"{u.full_name} — Requested {req.target_role.title()} role",
                subtitle="Role upgrade request",
                cta="Review",
                href=f"/admin/role-requests?id={req.id}",
                created_at=req.created_at,
            )
        )

    for doc_req, u in pending_doc_rows:
        doc_label = _DOC_LABELS.get(doc_req.type, doc_req.type.replace("_", " ").title())
        role_note = f"{doc_req.requested_role.title()} role" if doc_req.requested_role else "Document request"
        actions.append(
            ActionQueueItem(
                id=str(doc_req.id),
                kind="doc_request",
                tag="Document",
                tone="purple",
                title=f"{u.full_name} — {doc_label}",
                subtitle=role_note,
                cta="Generate",
                href=f"/admin/documents?tab=requests&requestId={doc_req.id}",
                created_at=doc_req.created_at,
            )
        )

    for review, u in to_review_rows:
        actions.append(
            ActionQueueItem(
                id=str(u.id),
                kind="applicant",
                tag="Onboarding",
                tone="purple",
                title=f"{u.full_name} — To be reviewed",
                subtitle="Instructor onboarding submission ready for decision",
                cta="Review",
                href=f"/instructors/admin/applicants/{u.id}",
                created_at=review.submitted_at or review.last_status_change_at,
            )
        )

    for letter, u in signed_letters:
        actions.append(
            ActionQueueItem(
                id=str(letter.id),
                kind="payment",
                tag="Payment Signed",
                tone="emerald",
                title=f"{u.full_name} — {letter.reference}",
                subtitle="Signed by instructor, ready to mark paid",
                cta="Open Letter",
                href=f"/instructors/admin/payments?letterId={letter.id}",
                created_at=letter.signed_at or letter.updated_at,
            )
        )

    for letter, u in draft_letters:
        actions.append(
            ActionQueueItem(
                id=str(letter.id),
                kind="payment",
                tag="Payment Draft",
                tone="neutral",
                title=f"{u.full_name} — {letter.reference}",
                subtitle="Draft letter waiting to generate PDF and publish",
                cta="Open Letter",
                href=f"/instructors/admin/payments?letterId={letter.id}",
                created_at=letter.updated_at or letter.created_at,
            )
        )

    if unbilled:
        actions.append(
            ActionQueueItem(
                id="unbilled-todo",
                kind="payment",
                tag="Payment Pending",
                tone="neutral",
                title=f"{len(unbilled)} instructor{'s' if len(unbilled) != 1 else ''} with unbilled sessions",
                subtitle="Completed sessions waiting to be drafted into payment letters",
                cta="Open Payments",
                href="/instructors/admin/payments#todo",
                created_at=datetime.now(timezone.utc),
            )
        )

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    actions.sort(
        key=lambda a: (a.created_at.replace(tzinfo=timezone.utc) if a.created_at and a.created_at.tzinfo is None else (a.created_at or epoch)),
        reverse=True,
    )

    return AdminCommandOverviewOut(
        pending_requests=PendingRequestsSummary(
            applications=len(pending_apps),
            role_requests=len(pending_role_rows),
            documents=len(pending_doc_rows),
        ),
        onboarding=OnboardingSummary(
            pending=phase1_in_progress + phase2_or_3_in_progress,
            to_be_reviewed=len(to_review_rows),
            phase1_in_progress=phase1_in_progress,
            phase2_in_progress=phase2_in_progress,
            phase3_in_progress=phase3_in_progress,
            phase2_or_3_in_progress=phase2_or_3_in_progress,
        ),
        payments=PaymentsStatusSummary(
            pending=len(unbilled) + len(draft_letters),
            published=len(published_letters),
            signed=len(signed_letters),
        ),
        actions=actions,
        business=business,
    )
