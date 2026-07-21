# Instructors Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

The instructor/facilitator scholarship pipeline: public application → review → onboarding → contract → paid workshop delivery.

## Roles and permissions

- **`applicant`** — signs up via public `POST /auth/instructor-apply` with an invite code (an admin-issued `invitation_codes` entry, or an ambassador's personal invite code), **or** is routed in by an admin from a pending intern application (`POST /admin/applications/{id}/onboard` — see `docs/HANDOFF.md`'s unified apply flow) instead of a normal invite-code signup. Submits the 3 intro-video summaries, works through facilitator-defined checklist modules (view/toggle items, upload a PDF per module), submits/reopens the overall application, and — once past Phase 1 — submits a presentation link and a written assessment. Frontend: `pages/instructors/Status.tsx`, `pipeline/Videos.tsx`, `pipeline/Modules.tsx`, `pipeline/ModuleDetail.tsx`, `apply/InstructorApply.tsx`.
- **`instructor`** (role granted on approval) — manages their own profile/photo/LinkedIn, signs their employment contract in-app, views/downloads their ID card, manages bank details, has a personal document vault, views and signs payment letters, works through onboarding training, browses the resource library (read-only). Frontend: `Dashboard.tsx`, `Training.tsx`, `TrainingPlayer.tsx`, `Library.tsx`, `Payments.tsx`, `PersonalDocuments.tsx`, `ProfileCard.tsx`.
- **`facilitator`** (admin-created only, no public signup) — full CRUD over training modules/videos and library resources, and owns the applicant-facing content: the 3 intro-video slots and the checklist modules/items applicants work through. Shares profile view/edit with instructors but does **not** sign a contract. Frontend: `facilitator/Training.tsx`, `facilitator/Library.tsx`, `facilitator/Application.tsx`.
- **`admin`** — full oversight: applicant list/detail/review/delete, dossier export, invitation-code management, facilitator account creation, instructor directory, payment batches/letters/sessions/addons (create, generate PDF, publish, mark-paid, bulk Excel import), certificate issuance/deletion. Frontend: `admin/Overview.tsx`, `Applicants.tsx`, `ApplicantReview.tsx`, `Invitations.tsx`, `Instructors.tsx`, `Facilitators.tsx`, `Payments.tsx`, `Certificates.tsx`.

## Key flows

### Applicant pipeline

Status field: `ApplicationReview.status`, one of `in_progress` → `under_review` → (`phase_1_approved` | `rejected`) → `under_review` (Phase 2) → (`research_approved` | `rejected`) → `under_review` (post-assessment) → (`approved` | `rejected`).

Applicant-triggered transitions:
- `POST /application/submit` — requires all 3 videos + all checklist modules submitted; `in_progress` → `under_review`.
- `POST /presentation/submit` — only when `phase_1_approved`; sets `under_review`.
- `POST /assessment/submit` — only when `research_approved`; sets `under_review`.
- `POST /application/reopen` — only from `rejected`, back to `in_progress`.

Admin-triggered: `PUT /admin/applicants/{id}/review` moves an applicant out of `under_review`; blocked once already `approved`/`rejected`. Per-module review is separate (`PUT /admin/applicants/{id}/modules/{module_id}/review`).

On final `approved`: promotes the user's role from `applicant` to `instructor` — or to **both** `instructor` and `intern` if this applicant was routed in from an intern application (`applicant_profiles.also_grant_role`, set by `onboard_application` in `routers/admin/applications.py`) — generates and stores the employment contract PDF, creates an `InstructorProfile`, auto-issues an `instructor_completion` certificate, emails credentials + contract, and — if the applicant came through a referral — awards 1000 points to the referring ambassador.

### In-app contract signing

On approval, `generate_contract_pdf` (`app/services/documents/contract.py`) renders a DOCX template via `docxtpl` with the instructor's name/living-area, converts to PDF via LibreOffice, and uploads to the `contracts` bucket. The instructor later calls `POST /instructor/contract/sign` with a base64 PNG signature (captured client-side via `react-signature-canvas`, `components/SignaturePad.tsx`); the backend re-renders the DOCX with the signing date, injects the signature image, converts to PDF again, and stores the signed copy. One-time only.

### Payment letters/batches

A `PaymentBatch` optionally groups several `PaymentLetter`s (e.g. one cohort). Each `PaymentLetter` (per instructor) has child `PaymentSession` rows (date, workshop, role, location, hours, compensation) and `PaymentAddon` rows (extra line items), with `status`: `draft` → `published` → `signed` → `paid`.

Admin flow (`app/services/documents/payment_letter.py`, `routers/instructors/payments_admin.py`): create batch → create letter → add sessions/addons (individually, or via Excel bulk-import matched to instructors by email) → generate the unsigned draft PDF → publish (emails the instructor) → instructor signs (regenerates the PDF with both signatures, stores it, auto-issues one `workshop_delivery` certificate per session, emails certs, notifies admin) → admin marks paid.

### Certificate issuance

`Certificate` (`app/models/certificate.py`, shared/top-level model) has `type`: `workshop_delivery` | `internship_completion` | `instructor_completion`. `instructor_completion` fires automatically on applicant→instructor approval. `workshop_delivery` fires automatically per session on payment-letter signing, or can be issued manually by admin (freeform workshop name/date/location). All certificates render through the same `generate_completion_certificate_pdf` generator used by the interns domain.

## Main DB tables

| Table | What it holds |
|---|---|
| `applicant_profiles` | Applicant's university/degree/city/background/transportation (1:1 with user) |
| `application_reviews` | Pipeline status, feedback, reviewer, timestamps |
| `video_submissions` | The 3 intro-video summaries |
| `checklist_modules` / `module_sections` / `checklist_items` | Facilitator-managed application checklist structure |
| `user_checklist_progress` | Per-applicant checked/unchecked items |
| `module_submissions` | Applicant's uploaded PDF per checklist module + approve/reject |
| `presentation_submissions` | Phase-2 presentation video link |
| `assessment_submissions` | Phase-2 written assessment (file or link) |
| `invitation_codes` | Admin-managed signup codes (max uses, expiry) |
| `instructor_profiles` | 1:1 instructor record: contract paths, signature, signed timestamp |
| `instructor_documents` | Personal document vault (any role) |
| `training_modules` / `training_videos` / `user_training_progress` | Onboarding training content + completion tracking |
| `library_modules` / `library_resources` | Resource library (files or links) |
| `payment_batches` | Optional grouping of payment letters |
| `payment_letters` | Per-instructor payment letter (status, PDF paths, reference) |
| `payment_sessions` | Line items on a letter |
| `payment_addons` | Extra compensation line items on a letter |
| `instructor_bank_details` | Instructor payout bank info |

Also uses the shared `certificates`, `document_templates`, and `portal_settings` tables.

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Applicant pipeline | `routers/instructors/applicant.py`, `admin.py` (review/dossier), models `application_review.py`, `checklist.py`, `module_submission.py`, `video_submission.py`, `presentation_submission.py`, `assessment_submission.py`, `applicant_profile.py`, service `services/documents/dossier.py` | `pages/instructors/Status.tsx`, `pipeline/*`, `apply/InstructorApply.tsx`, `admin/Applicants.tsx`, `ApplicantReview.tsx` |
| Contracts | `routers/instructors/instructor.py` (sign), `admin.py` (generation on approval), model `instructor_profile.py`, service `services/documents/contract.py` | `components/SignaturePad.tsx`, `ProfileCard.tsx` |
| Payments | `routers/instructors/payments.py` (instructor side), `payments_admin.py` (admin side), model `payment.py`, service `services/documents/payment_letter.py` | `Payments.tsx`, `admin/Payments.tsx` |
| Certificates | `routers/instructors/payments_admin.py`, `admin.py` (auto-issue on approval), `payments.py` (auto-issue on letter sign), model `models/certificate.py`, service `services/documents/certificate.py` | `admin/Certificates.tsx` |
| Training/Library | `training.py`, `library.py` (instructor read), `facilitator.py` (facilitator write), models `training.py`, `library.py` | `Training.tsx`, `TrainingPlayer.tsx`, `Library.tsx`, `facilitator/Training.tsx`, `facilitator/Library.tsx`, `facilitator/Application.tsx` |
