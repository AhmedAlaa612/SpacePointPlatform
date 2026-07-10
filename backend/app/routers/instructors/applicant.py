import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_applicant
from app.db.session import get_db
from app.models.enums import ApplicationStatus, ModuleSubmissionStatus, VideoSubmissionStatus
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.checklist import ChecklistItem, ChecklistModule, ModuleSection, UserChecklistProgress
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.assessment_submission import AssessmentSubmission
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.instructors.video_submission import VideoSubmission
from app.models.user import User
from app.schemas.instructors.applicant import (
    ApplicationStatusOut,
    AssessmentSubmissionOut,
    ChecklistItemProgressOut,
    ChecklistModuleOut,
    ModuleSectionOut,
    ModuleSubmissionOut,
    PresentationSubmit,
    VideoSubmissionOut,
    VideoSummaryUpdate,
)
from app.services import storage

router = APIRouter(tags=["instructors-applicant"])

MIN_SUMMARY_WORDS = 200

# ── Phase 2: 10 Questions Assessment (unlocked on research_approved) ──
ASSESSMENT_QUESTIONS = [
    {"category_id": "CAT-01", "category_name": "Subsystem Block Diagram and Analysis", "question_id": "CAT-01-Q01",
     "task": "Draw a block diagram of a typical CubeSat Electrical Power System (EPS).",
     "follow_up": "After creating your diagram, identify which critical component might be missing and explain why it is essential for safe and efficient power distribution."},
    {"category_id": "CAT-02", "category_name": "Subsystem Sizing and Engineering Calculation", "question_id": "CAT-02-Q02",
     "task": "Calculate the minimum theoretical battery capacity required for a CubeSat that consumes an average of 4 W during a 35-minute eclipse. The battery operates at 7.4 V, and the depth of discharge is limited to 30%.",
     "follow_up": "Explain what safety margin you would apply when selecting the actual battery."},
    {"category_id": "CAT-03", "category_name": "Identifying the Most Critical Subsystem", "question_id": "CAT-03-Q01",
     "task": "If a satellite beacon is triggered via telecommand from the ground, which subsystem is most critical in ensuring the beacon can be activated successfully?",
     "follow_up": "Explain your reasoning."},
    {"category_id": "CAT-04", "category_name": "Subsystem Anomaly Troubleshooting", "question_id": "CAT-04-Q02",
     "task": "During payload operation, the CubeSat onboard computer repeatedly resets. The resets do not occur when the payload is switched off.",
     "follow_up": "Propose a troubleshooting plan to isolate and fix the issue, considering power stability, electrical noise, software faults, watchdog behavior, and thermal conditions."},
    {"category_id": "CAT-05", "category_name": "Environmental and Qualification Test Planning", "question_id": "CAT-05-Q01",
     "task": "Your team suspects the satellite's payload is highly sensitive to extreme temperature swings.",
     "follow_up": "Design a simple thermal cycling test plan and justify the temperature ranges, duration of tests, and expected outcomes."},
    {"category_id": "CAT-06", "category_name": "Mission Risk Identification and Mitigation", "question_id": "CAT-06-Q02",
     "task": "List three major risks that a CubeSat faces during launch, separation, and early orbit operations.",
     "follow_up": "Suggest at least one specific mitigation strategy for each risk and explain why you chose those strategies."},
    {"category_id": "CAT-07", "category_name": "Failed Mission or Subsystem Evaluation", "question_id": "CAT-07-Q02",
     "task": "Evaluate a case study where a CubeSat mission ended early because the batteries could not maintain sufficient charge during eclipse periods.",
     "follow_up": "How would you restructure the CubeSat's EPS design or operational procedures to prevent a similar failure in future missions?"},
    {"category_id": "CAT-08", "category_name": "Concept of Operations Development", "question_id": "CAT-08-Q02",
     "task": "If you were to draft a Concept of Operations for a 3U Earth-imaging CubeSat, what mission phases would you include and why?",
     "follow_up": "Be specific about target selection, attitude control, image capture, data storage, downlink windows, and power management."},
    {"category_id": "CAT-09", "category_name": "Ground-Station Data Interpretation and Diagnosis", "question_id": "CAT-09-Q01",
     "task": "Your ground station logs indicate intermittent data loss and unexpected signal-strength variations.",
     "follow_up": "What factors could be causing these issues, and how would you systematically diagnose and resolve them?"},
    {"category_id": "CAT-10", "category_name": "Space Mission Case Study and Improvement", "question_id": "CAT-10-Q01",
     "task": "Choose one UAE CubeSat or satellite mission that interests you.",
     "follow_up": "How did the design of this mission's subsystems reflect specific objectives or constraints? Propose one improvement or addition to enhance the mission's success if it were re-launched today."},
]


async def _get_review(db: AsyncSession, user_id: uuid.UUID) -> ApplicationReview:
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Application not found")
    return review


async def _all_videos_submitted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    rows = (await db.execute(select(VideoSubmission).where(VideoSubmission.user_id == user_id))).scalars().all()
    return len(rows) > 0 and all(v.status == VideoSubmissionStatus.submitted for v in rows)


async def _all_modules_submitted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    total = (await db.execute(select(ChecklistModule.id))).scalars().all()
    if not total:
        return False
    submitted = (await db.execute(
        select(ModuleSubmission.module_id).where(
            ModuleSubmission.user_id == user_id,
            ModuleSubmission.status != ModuleSubmissionStatus.rejected,
        )
    )).scalars().all()
    return set(total) <= set(submitted)


# ── Phase 1: video summaries ──────────────────────────────────

# Default URLs used when the facilitator hasn't configured them yet.
_DEFAULT_VIDEO_URLS = [
    "https://youtu.be/6KcV1C1Ui5s",
    "https://youtu.be/qr1AvisQcV8",
    "https://youtu.be/5voQfQOTem8",
]


async def _get_video_urls(db: AsyncSession) -> list[str]:
    """Return the 3 canonical video URLs, reading from portal_settings first
    and falling back to the hardcoded defaults when not yet configured."""
    from app.models.instructors.payment import PortalSetting
    settings = {
        s.key: s.value
        for s in (await db.execute(
            select(PortalSetting).where(PortalSetting.key.like("app_video_%_url"))
        )).scalars().all()
    }
    return [settings.get(f"app_video_{n}_url") or _DEFAULT_VIDEO_URLS[n - 1] for n in range(1, 4)]


@router.get("/videos", response_model=list[VideoSubmissionOut])
async def list_videos(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    rows = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == current_user.id).order_by(VideoSubmission.video_no)
    )).scalars().all()
    video_urls = await _get_video_urls(db)
    if not rows:
        rows = [VideoSubmission(user_id=current_user.id, video_no=n, youtube_url=url) for n, url in enumerate(video_urls, 1)]
        db.add_all(rows)
        await db.commit()
        for r in rows:
            await db.refresh(r)
    else:
        # Backfill missing URLs for rows created before the URL was seeded
        dirty = False
        for row in rows:
            if not row.youtube_url:
                row.youtube_url = video_urls[row.video_no - 1]
                dirty = True
        if dirty:
            await db.commit()
            for r in rows:
                await db.refresh(r)
    return list(rows)


@router.put("/videos/{video_no}", response_model=VideoSubmissionOut)
async def update_video(
    video_no: int,
    body: VideoSummaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    video = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == current_user.id, VideoSubmission.video_no == video_no)
    )).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    word_count = len((body.summary_text or "").split())
    video.youtube_url = body.youtube_url
    video.summary_text = body.summary_text
    video.word_count = word_count

    if body.submit:
        if word_count < MIN_SUMMARY_WORDS:
            raise HTTPException(status_code=400, detail=f"Summary must be at least {MIN_SUMMARY_WORDS} words")
        video.status = VideoSubmissionStatus.submitted
        video.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(video)
    return video


# ── Phase 1: checklist modules ────────────────────────────────

@router.get("/modules", response_model=list[ChecklistModuleOut])
async def list_modules(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    modules = (await db.execute(select(ChecklistModule).order_by(ChecklistModule.sort_order))).scalars().all()
    module_ids = [m.id for m in modules]

    items = (await db.execute(select(ChecklistItem).where(ChecklistItem.module_id.in_(module_ids)))).scalars().all()
    items_by_module: dict[uuid.UUID, list] = {}
    for it in items:
        items_by_module.setdefault(it.module_id, []).append(it)

    item_ids = [it.id for it in items]
    progress_rows = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id,
            UserChecklistProgress.checklist_item_id.in_(item_ids),
        )
    )).scalars().all()
    completed_ids = {p.checklist_item_id for p in progress_rows if p.is_completed}

    submissions = (await db.execute(
        select(ModuleSubmission).where(
            ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id.in_(module_ids)
        )
    )).scalars().all()
    submission_by_module = {s.module_id: s for s in submissions}

    out = []
    for m in modules:
        mod_items = items_by_module.get(m.id, [])
        sub = submission_by_module.get(m.id)
        out.append(ChecklistModuleOut(
            id=m.id,
            title=m.title,
            sort_order=m.sort_order,
            item_count=len(mod_items),
            completed_count=sum(1 for it in mod_items if it.id in completed_ids),
            submission_status=sub.status if sub else None,
            submission_feedback=sub.feedback if sub else None,
        ))
    return out


@router.get("/modules/{module_id}", response_model=ChecklistModuleOut)
async def module_detail(
    module_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    sections = (await db.execute(
        select(ModuleSection).where(ModuleSection.module_id == module_id).order_by(ModuleSection.sort_order)
    )).scalars().all()
    items = (await db.execute(
        select(ChecklistItem).where(ChecklistItem.module_id == module_id).order_by(ChecklistItem.sort_order)
    )).scalars().all()
    progress_rows = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id,
            UserChecklistProgress.checklist_item_id.in_([it.id for it in items]),
        )
    )).scalars().all()
    completed_ids = {p.checklist_item_id for p in progress_rows if p.is_completed}

    def _item_out(it: ChecklistItem) -> ChecklistItemProgressOut:
        return ChecklistItemProgressOut(
            id=it.id, item_code=it.item_code, title=it.title, description=it.description,
            is_required=it.is_required, is_completed=it.id in completed_ids,
        )

    section_groups: list[ModuleSectionOut] = []
    no_section_items = [it for it in items if it.section_id is None]
    if no_section_items:
        section_groups.append(ModuleSectionOut(id=None, title=None, items=[_item_out(it) for it in no_section_items]))
    for sec in sections:
        sec_items = [it for it in items if it.section_id == sec.id]
        section_groups.append(ModuleSectionOut(id=sec.id, title=sec.title, items=[_item_out(it) for it in sec_items]))

    sub = (await db.execute(
        select(ModuleSubmission).where(ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id == module_id)
    )).scalars().first()

    return ChecklistModuleOut(
        id=module.id, title=module.title, sort_order=module.sort_order, sections=section_groups,
        item_count=len(items), completed_count=sum(1 for it in items if it.id in completed_ids),
        submission_status=sub.status if sub else None, submission_feedback=sub.feedback if sub else None,
    )


@router.put("/checklist/items/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    progress = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id, UserChecklistProgress.checklist_item_id == item_id
        )
    )).scalars().first()
    if not progress:
        progress = UserChecklistProgress(user_id=current_user.id, checklist_item_id=item_id, is_completed=True)
        db.add(progress)
    else:
        progress.is_completed = not progress.is_completed

    await db.commit()
    return {"id": str(item_id), "is_completed": progress.is_completed}


@router.post("/modules/{module_id}/submit", response_model=ModuleSubmissionOut)
async def submit_module(
    module_id: uuid.UUID,
    file: UploadFile,
    notes_text: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    if not await _all_videos_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all 3 video summaries before uploading modules")

    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    data = await file.read()
    path = f"{current_user.id}/{module_id}/{file.filename}"
    bucket = "applicant-submissions"
    file_url = await storage.upload_file(bucket, path, data, file.content_type or "application/pdf")

    existing = (await db.execute(
        select(ModuleSubmission).where(ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id == module_id)
    )).scalars().first()
    if existing:
        existing.file_url = file_url
        existing.bucket = bucket
        existing.file_path = path
        existing.original_filename = file.filename
        existing.notes_text = notes_text
        existing.status = ModuleSubmissionStatus.submitted
        existing.feedback = None
        existing.submitted_at = datetime.now(timezone.utc)
        submission = existing
    else:
        submission = ModuleSubmission(
            user_id=current_user.id, module_id=module_id, file_url=file_url,
            bucket=bucket, file_path=path,
            original_filename=file.filename, notes_text=notes_text,
        )
        db.add(submission)

    await db.commit()
    await db.refresh(submission)
    submission.file_url = await storage.resolve_url(submission.bucket, submission.file_path, submission.file_url)
    return submission


# ── Application submit / reopen / status ──────────────────────

@router.post("/application/submit", response_model=ApplicationStatusOut)
async def submit_application(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.in_progress:
        raise HTTPException(status_code=400, detail="Application has already been submitted")
    if not await _all_videos_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all 3 video summaries first")
    if not await _all_modules_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all checklist modules first")

    review.status = ApplicationStatus.under_review
    review.submitted_at = datetime.now(timezone.utc)
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at)


@router.post("/application/reopen", response_model=ApplicationStatusOut)
async def reopen_application(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.rejected:
        raise HTTPException(status_code=400, detail="Only a rejected application can be reopened")
    review.status = ApplicationStatus.in_progress
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at)


@router.post("/presentation/submit", response_model=ApplicationStatusOut)
async def submit_presentation(
    body: PresentationSubmit, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.phase_1_approved:
        raise HTTPException(status_code=400, detail="Phase 2 is only open after Phase 1 approval")

    existing = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == current_user.id)
    )).scalars().first()
    if existing:
        existing.video_link = body.video_link
    else:
        db.add(PresentationSubmission(user_id=current_user.id, video_link=body.video_link))

    review.status = ApplicationStatus.under_review
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at,
                                 presentation_video_link=body.video_link)


@router.get("/assessment/questions")
async def get_assessment_questions(current_user: User = Depends(require_applicant)):
    return ASSESSMENT_QUESTIONS


@router.post("/assessment/submit", response_model=ApplicationStatusOut)
async def submit_assessment(
    file: UploadFile | None = None,
    google_drive_link: str | None = None,
    comments: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.research_approved:
        raise HTTPException(status_code=400, detail="Not eligible to submit assessment at this stage")

    if not file and not google_drive_link:
        raise HTTPException(status_code=400, detail="Please upload a PDF file or provide a Google Drive link.")

    file_url = None
    file_bucket = None
    file_path = None
    if file:
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        data = await file.read()
        file_bucket, file_path = "applicant-submissions", f"{current_user.id}/assessment/{file.filename}"
        file_url = await storage.upload_file(file_bucket, file_path, data, file.content_type or "application/pdf")

    existing = (await db.execute(
        select(AssessmentSubmission).where(AssessmentSubmission.user_id == current_user.id)
    )).scalars().first()
    if existing:
        if file_url:
            existing.file_url = file_url
            existing.bucket = file_bucket
            existing.file_path = file_path
        existing.google_drive_link = google_drive_link
        existing.comments = comments
        existing.submitted_at = datetime.now(timezone.utc)
    else:
        db.add(AssessmentSubmission(
            user_id=current_user.id, file_url=file_url, bucket=file_bucket, file_path=file_path,
            google_drive_link=google_drive_link, comments=comments,
        ))

    review.status = ApplicationStatus.under_review
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at)


@router.get("/status", response_model=ApplicationStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == current_user.id))).scalars().first()
    if not review:
        review = ApplicationReview(user_id=current_user.id, status=ApplicationStatus.in_progress)
        db.add(review)
        await db.commit()
        await db.refresh(review)
    presentation = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == current_user.id)
    )).scalars().first()
    assessment = (await db.execute(
        select(AssessmentSubmission).where(AssessmentSubmission.user_id == current_user.id)
    )).scalars().first()
    return ApplicationStatusOut(
        status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at,
        presentation_video_link=presentation.video_link if presentation else None,
        assessment=AssessmentSubmissionOut.model_validate(assessment) if assessment else None,
    )
