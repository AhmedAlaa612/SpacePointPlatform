# Instructors Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

The instructor/facilitator scholarship pipeline: public application → review → onboarding → contract → paid workshop delivery. This file also covers two adjacent, previously-undocumented pieces: **Instructor Assessment** (a scenario-quiz + performance/rating system that gates *staffing*, unrelated to the applicant-pipeline "assessment" below despite the name clash) and **Documents** (shared platform infrastructure for letters/certs/ID cards/vault uploads — instructors are its biggest user but not its only one).

> **Status — 2026-09-17.** Re-verified against current code: `backend/app/routers/{instructors,instructor_assessment}/`, `backend/app/services/{instructors,instructor_assessment,documents}/`, `backend/app/models/{instructors,instructor_assessment}/`, `backend/app/models/{document,document_request,document_template,id_card,certificate}.py`, `backend/app/routers/documents.py` (single file, not a package), and the corresponding `frontend/src/pages/instructors/**`, `frontend/src/pages/shared/PersonalDocuments.tsx`, `frontend/src/api/{documents,instructor_assessment}.ts`. The Instructors section below was previously accurate (updated 2026-09-09) — confirmed still correct except where noted; Instructor Assessment and Documents are new sections, written from scratch since neither had any prior documentation.

## Roles and permissions

- **`applicant`** — signs up via public `POST /auth/instructor-apply` with an invite code (an admin-issued `invitation_codes` entry, or an ambassador's personal invite code), **or** is routed in by an admin from a pending intern application (`POST /admin/applications/{id}/onboard` — see `docs/HANDOFF.md`'s unified apply flow) instead of a normal invite-code signup. Submits the 3 intro-video summaries, works through facilitator-defined checklist modules (view/toggle items, upload a PDF per module), submits/reopens the overall application, and — once past Phase 1 — submits a presentation link and a written assessment (a fixed 10-question list at `GET /instructor/assessment/questions`, answered off-platform as a PDF or Google Drive link + comments — **not** the scenario-quiz system described under "Instructor Assessment" below; same word, two unrelated features). Frontend: `pages/instructors/Status.tsx`, `pipeline/Videos.tsx`, `pipeline/Modules.tsx`, `pipeline/ModuleDetail.tsx`, `apply/InstructorApply.tsx`.
- **`instructor`** (role granted on approval) — manages their own profile/photo/LinkedIn, signs their employment contract in-app, views/downloads their ID card, manages bank details, has a personal document vault, views and signs payment letters, works through onboarding training, browses the resource library (read-only), and — once assigned to a gated cohort — takes the scenario-based Instructor Assessment quiz before registering staffing interest. Also, since 2026-08-20, can apply for the `intern` role (`HANDOFF_INTERNSHIP.md`) — a button on the same shared documents page. Frontend: `Dashboard.tsx`, `Training.tsx`, `TrainingPlayer.tsx`, `Library.tsx`, `Payments.tsx`, `TakeAssessment.tsx`, `pages/shared/PersonalDocuments.tsx`, `ProfileCard.tsx`.
- **`facilitator`** (admin-created only, no public signup) — full CRUD over training modules/videos and library resources, and owns the applicant-facing content: the 3 intro-video slots and the checklist modules/items applicants work through. Shares profile view/edit with instructors but does **not** sign a contract. Also passes `require_materials_manager` (`["operations", "facilitator"]`), so a facilitator can author Instructor Assessment question banks alongside operations. Frontend: `facilitator/Training.tsx`, `facilitator/Library.tsx`, `facilitator/Application.tsx`.
- **`admin`** — full oversight: applicant list/detail/review/delete, dossier export, invitation-code management, facilitator account creation, instructor directory, payment batches/letters/sessions/addons (create, generate PDF, publish, mark-paid, bulk Excel import), certificate issuance/deletion. `RequireRole` (`core/dependencies.py:80-94`) lets `admin` through every role gate in this domain automatically, including the `operations`-only Instructor Assessment admin surfaces below. Frontend: `admin/Overview.tsx`, `Applicants.tsx`, `ApplicantReview.tsx`, `Invitations.tsx`, `Instructors.tsx`, `Facilitators.tsx`, `Payments.tsx`, `Certificates.tsx`.
- **`operations`** — the actual gate on most Instructor Assessment admin/ops surfaces (`require_operations`, same population as the sessions/staffing domain): assigning a config to a cohort, rating instructors post-program, viewing the Performance Profile drill-down, setting Priority Score weights, and reviewing an instructor's quiz answers from the staffing screens. Not part of this file's own applicant/contract/payment flows.

Note: `pages/instructors/` also hosts several frontend pages that are **not** part of this domain — `AvailableSessions.tsx`, `MySessions.tsx`, `SessionDetail.tsx`, `GameLiveConsole.tsx`, `MyHoldings.tsx`, `components/CohortCallCard.tsx`, `components/Session*Panel.tsx` — these are instructor-facing views of the Sessions/staffing domain (see [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md)), just physically colocated because they're instructor-role pages.

## Key flows

### Applicant pipeline

Status field: `ApplicationReview.status`, one of `in_progress` → `under_review` → (`phase_1_approved` | `rejected`) → `under_review` (Phase 2) → (`research_approved` | `rejected`) → `under_review` (post-assessment) → (`approved` | `rejected`).

Applicant-triggered transitions:
- `POST /application/submit` — requires all 3 videos + all checklist modules submitted; `in_progress` → `under_review`.
- `POST /presentation/submit` — only when `phase_1_approved`; sets `under_review`.
- `POST /assessment/submit` — only when `research_approved`; sets `under_review`.
- `POST /application/reopen` — only from `rejected`, back to `in_progress`.

Admin-triggered: `PUT /admin/applicants/{id}/review` moves an applicant out of `under_review`; blocked once already `approved`/`rejected`. Per-module review is separate (`PUT /admin/applicants/{id}/modules/{module_id}/review`).

On final `approved` (`routers/instructors/admin.py:281-438`): promotes the user's role from `applicant` to `instructor` — or to **both** `instructor` and `intern` if this applicant was routed in from an intern application (`applicant_profiles.also_grant_role`, set by `onboard_application` in `routers/admin/applications.py`) — generates and stores the employment contract PDF, creates an `InstructorProfile`, auto-issues an `instructor_completion` certificate (rendered from the editable `document_templates` row keyed `instructor_completion`, falling back to hardcoded wording only if that template row is missing — `admin.py:404-423`), emails credentials + contract, and — if the applicant came through a referral — awards 1000 points to the referring ambassador. Since 2026-08-20, if `also_grant_role == "intern"` and `applicant_profiles.pending_intern_details` was stashed at onboard time, this same approval also auto-generates the internship letter (`HANDOFF_INTERNSHIP.md` — Path 2).

### In-app contract signing

On approval, `generate_contract_pdf` (`app/services/documents/contract.py`) renders a DOCX template via `docxtpl` with the instructor's name/living-area, converts to PDF via LibreOffice, and uploads to the `contracts` bucket. The instructor later calls `POST /instructor/contract/sign` with a base64 PNG signature (captured client-side via `react-signature-canvas`, `pages/instructors/components/SignaturePad.tsx`, rendered on `pages/shared/PersonalDocuments.tsx` since 2026-08-20 — that page is now the one "My Documents" surface for every role, not an instructor-only page); the backend re-renders the DOCX with the signing date, injects the signature image, converts to PDF again, and stores the signed copy on `InstructorProfile.signed_contract_path`/`signed_contract_url`. One-time only. This is a bespoke, hardcoded flow — it does **not** go through the generic `documents`/`document_requests` system described under "Documents" below, even though it shares that system's storage helpers. The internship letter (`HANDOFF_INTERNSHIP.md`) signs the same way, on the same page, via its own equally-bespoke `services/documents/internship_letter.py`.

### Payment letters/batches

A `PaymentBatch` optionally groups several `PaymentLetter`s (e.g. one cohort). Each `PaymentLetter` (per instructor) has child `PaymentSession` rows (date, workshop, role, location, hours, compensation) and `PaymentAddon` rows (extra line items), with `status`: `draft` → `published` → `signed` → `paid`.

**2026-08-24 — a line is normally a whole cohort, and the amount arrives filled in.**

- A `PaymentSession` row now usually stands for a cohort: `cohort_id` set, `session_id` NULL,
  `session_count` and `rate_aed` filled, and `session_date` holding a **date range**
  (`10/10/2026 - 14/10/2026`). Work delivered outside any cohort assignment still bills one row
  per session, unchanged. The driver is the bank's per-transaction fee past ten a month, so
  several cohorts are settled on one letter and an itemised day list would make it unreadable.
- **The printed range is always the cohort's**, never the days actually delivered. An absence
  shows up only as a smaller `session_count`. Shrinking the dates would leak which specific days
  somebody missed onto a document that deliberately does not itemise attendance.
- `payment_session_coverage` says which sessions a line covers. It is the anti-double-billing key
  generalised from one to N: a session is billed iff `payment_sessions.session_id` names it **or**
  a coverage row under *that instructor's own* letters covers it. The instructor-scoping is what
  stops paying the lead from hiding a session from the assistant.
- **`compensation_aed` is pre-computed** (agreed rate × ops-approved days), reversing the earlier
  "the money is a decision" choice — but keeping the decision: ops sees every figure, can edit any
  cell, and `_refuse_if_signed` still blocks edits once signed. What went away is retyping a number
  the system already agreed at staffing time.
- "Delivered" means a day ops approved with the instructor present (`instructor_session_days`, see
  `HANDOFF_SESSIONS.md`). Cohorts delivered before the daily loop existed have no day rows and fall
  back to `completed_at`, so nothing that used to be billable stopped being so.
- **`bill-sessions` takes `line_ids`**, not `session_ids` — a cohort id, or a session id for a
  single line.
- Cohort completion accrues the draft line automatically (both the auto path and the ops button),
  appending to that instructor's open `draft` letter or starting a new one if theirs has moved past
  `draft`. Idempotent: the lines are derived from what is still unbilled.
- The DOCX needs no new column — the fifth cell prints `5 x 500` for a cohort row and the old hours
  figure otherwise, and its header switches to "Sessions / Duration" when any cohort row is present.
  The template is patched by hardcoded cell index, so a real new column would mean renumbering
  everything below it.

Admin flow (`app/services/documents/payment_letter.py`, `routers/instructors/payments_admin.py`): create batch → create letter → add sessions/addons (individually, or via Excel bulk-import matched to instructors by email) → generate the unsigned draft PDF → publish (emails the instructor) → instructor signs (regenerates the PDF with both signatures, stores it, auto-issues one `workshop_delivery` certificate per session, emails certs, notifies admin) → admin marks paid. Also bespoke (own DOCX template + signature-anchoring technique in `payment_letter.py`), not routed through the generic `documents` system.

### Certificate issuance

`Certificate` (`app/models/certificate.py`, shared/top-level model) has `type`: `workshop_delivery` | `internship_completion` | `instructor_completion` | `student_completion` | `lms_course_completion` | `lms_path_completion`. `instructor_completion` fires automatically on applicant→instructor approval. `workshop_delivery` fires automatically **per `PaymentSession` row** on payment-letter signing, or can be issued manually by admin (freeform workshop name/date/location). Certificates are their own first-class model — never `Document` rows — but the two system ones above and the generic-template-driven ones (see Documents) all render through the same `generate_completion_certificate_pdf` generator in `services/documents/certificate.py`, also used by the LMS domain's own certs.

> Since 2026-08-24 that per-row rule means **one certificate per cohort** with no code change, because a cohort line is one row — `{workshop_date}` simply renders the date range. Two things to know before relying on it: certs stay per-cohort even when one letter aggregates several (never merged), and **`certificates.payment_session_id` is only a natural key, not an enforced unique index** — `models/certificate.py:50-56` is explicit that the enforced ones are the LMS pair. Nothing re-issues today because `_refuse_if_signed` makes signing once-only, so it is safe as-is; just don't build a retry path on a guarantee the database isn't making.

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
| `assessment_submissions` | Phase-2 written assessment (file or link) — **applicant onboarding only**, unrelated to `assessment_attempts`/`assessment_configs` below |
| `invitation_codes` | Admin-managed signup codes (max uses, expiry) |
| `instructor_profiles` | 1:1 instructor record: contract paths, signature, signed timestamp, `instructor_since` |
| `instructor_documents` | Personal upload vault (Emirates ID/Passport/Visa/CV/…) — instructor-only in the UI (`canUseVault = activeRole === "instructor"`, `pages/shared/PersonalDocuments.tsx:62`); distinct table from the shared `documents` table below |
| `training_modules` / `training_videos` / `user_training_progress` | Onboarding training content + completion tracking |
| `library_modules` / `library_resources` | Resource library (files or links) |
| `payment_batches` | Optional grouping of payment letters |
| `payment_letters` | Per-instructor payment letter (status, PDF paths, reference) |
| `payment_sessions` | Line items on a letter |
| `payment_addons` | Extra compensation line items on a letter |
| `instructor_bank_details` | Instructor payout bank info |

Also uses the shared `certificates`, `document_templates`, and `portal_settings` tables, and (since 2026-09) the `instructor_assessment`-domain tables below.

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Applicant pipeline | `routers/instructors/applicant.py`, `admin.py` (review/dossier), models `application_review.py`, `checklist.py`, `module_submission.py`, `video_submission.py`, `presentation_submission.py`, `assessment_submission.py`, `applicant_profile.py`, service `services/documents/dossier.py` | `pages/instructors/Status.tsx`, `pipeline/*`, `apply/InstructorApply.tsx`, `admin/Applicants.tsx`, `ApplicantReview.tsx` |
| Contracts | `routers/instructors/instructor.py` (sign), `admin.py` (generation on approval), model `instructor_profile.py`, service `services/documents/contract.py` | `pages/instructors/components/SignaturePad.tsx`, `pages/shared/PersonalDocuments.tsx` |
| Payments | `routers/instructors/payments.py` (instructor side), `payments_admin.py` (admin side), model `payment.py`, service `services/documents/payment_letter.py` | `Payments.tsx`, `admin/Payments.tsx` |
| Certificates | `routers/instructors/payments_admin.py`, `admin.py` (auto-issue on approval), `payments.py` (auto-issue on letter sign), model `models/certificate.py`, service `services/documents/certificate.py` | `admin/Certificates.tsx` |
| Training/Library | `training.py`, `library.py` (instructor read), `facilitator.py` (facilitator write), models `training.py`, `library.py` | `Training.tsx`, `TrainingPlayer.tsx`, `Library.tsx`, `facilitator/Training.tsx`, `facilitator/Library.tsx`, `facilitator/Application.tsx` |
| Instructor Assessment | `routers/instructor_assessment/**` (see below) | `TakeAssessment.tsx`, `admin/AssessmentQuestions.tsx`, `admin/InstructorPerformance.tsx`, `admin/RateInstructor.tsx` |
| Documents (shared) | `routers/documents.py` (single file), models `document.py`/`document_request.py`/`document_template.py`/`id_card.py`, service `services/documents/{id_card,letters,certificate}.py` | `pages/shared/PersonalDocuments.tsx`, `components/documents/ProfileIdCard.tsx`, `api/documents.ts` |

---

## Instructor Assessment (2026-09)

**What it actually is:** a scenario-based multiple-choice quiz bank, plus post-program peer ratings and a configurable "Priority Score", that gates and ranks instructors for **staffing** (registering interest in a cohort/session opportunity) — not part of the applicant onboarding pipeline above, despite both being called "assessment". It lives under `backend/app/{routers,services,models}/instructor_assessment/`, mounted at `/instructor-assessment/*` (`main.py:22,149`), and is deeply tied into the Sessions/staffing domain (`HANDOFF_SESSIONS.md`) — an instructor never encounters it except through a cohort call's interest-registration flow.

### The three pieces

1. **The gate.** `AssessmentCohortAssignment` (`models/instructor_assessment/assignment.py`) is a per-cohort on/off switch: a cohort with no row here has no assessment requirement at all, and registering interest behaves exactly as if this domain didn't exist. Ops turns it on via `PUT /instructor-assessment/cohorts/{cohort_id}/config` (`require_operations`), naming which `AssessmentConfig` (question bank) applies. `services/instructor_assessment/gate.py::assert_assessment_passed` is called from the staffing/interest-registration code path and raises 409 unless the instructor has a `submitted` `AssessmentAttempt` for that opportunity's `cohort_call_id`. Already-registered applicants are never retroactively required — the gate only affects *new* interest registrations from the moment it's set.
2. **The attempt.** `AssessmentConfig` is a named, reusable question bank (e.g. "Shallow Flight Instructor Assessment", 71 scenario questions) with a configurable `draw_size` (default 15) and `critical_floor` (default 3). `POST /instructor-assessment/attempts/{cohort_call_id}/start` (get-or-create, `require_instructor_or_facilitator`) draws questions via `services/instructor_assessment/attempts.py::draw_questions` — round-robins critical-flagged questions across categories first to hit the floor, then fills the remainder round-robin across all categories, then shuffles into presentation order with independently-shuffled option orders — and persists the draw in `question_order` (JSONB) so a page refresh never reshuffles anything. `POST /instructor-assessment/attempts/{attempt_id}/submit` grades against the persisted draw only, is once-only (409 on a second submit), and the review (`get_attempt_review`) is only ever computed after submission so a partial attempt can't leak correct answers mid-quiz. Ops can review an instructor's completed attempt from either staffing screen via `attempt_review.py`'s `/instructor-assessment/attempts/{cohort-calls|sessions}/{id}/instructors/{user_id}/review`.
3. **Rating and ranking.** `InstructorProgramRating` (`require_operations`, "Project Lead" role gating explicitly parked pending product decision) is a post-program rating of one instructor for one cohort, across 10 fixed dimensions (`RATING_DIMENSIONS` in `models/instructor_assessment/rating.py`) — once per (cohort, instructor, rater), autosaved as a draft until deliberately submitted (`submitted` ratchets forward only, same contract as `CompetitionScore`). `RankingWeightProfile` is the configurable weighting (one active profile at a time) behind the **Priority Score**, computed live (never cached) in `services/instructor_assessment/ranking.py::compute_priority_score` by blending, per active weight: `assessment_score` (last submitted quiz %), `previous_rating` (average rating ÷5 ×100), `relevant_experience` (deliveries on this exact program × 25 capped 75, plus same-program-type deliveries × 5 capped 25), `sessions_hours` (delivered sessions × 5, capped 100), `reliability` (delivered ÷ assigned), and `recent_performance` (most recent rating ÷5 ×100). A factor with no data for a given instructor is dropped and the rest renormalized, rather than counted as zero — a first-time applicant isn't punished for lacking history.

### Roles

- **`instructor` or `facilitator`** (`require_instructor_or_facilitator`) — take their own attempts (`attempts.py`).
- **`operations` + `facilitator`** (`require_materials_manager`) — author question banks/questions, including Excel bulk import (`admin.py`).
- **`operations`** (`require_operations`) — assign/clear a cohort's gate config (`cohorts.py`), submit ratings (`ratings.py`), view the Performance Profile drill-down and manage certification tags (`performance.py`), review an instructor's answers from the staffing screens (`attempt_review.py`), and set Priority Score weights (`ranking.py`). `admin` passes every gate above automatically (`RequireRole`, `core/dependencies.py:88-89`).

### Gotchas

- **Same word, two unrelated systems.** "Instructor assessment" in the applicant pipeline (`assessment_submissions` table, a file/link the applicant uploads once during onboarding) has nothing to do with this module (`assessment_attempts`/`assessment_configs`, a repeatable scenario quiz gating staffing). Don't conflate them when searching the codebase — both use the string "assessment" heavily.
- **`AssessmentAttempt` is unique per `(cohort_call_id, user_id)`**, not a standing quiz — one draw per opportunity, not one draw ever. Grading always re-reads `question_order`, never trusts client-supplied correctness.
- **Deactivating or editing a question mid-attempt is handled by skipping, not erroring** — `get_attempt_questions`/`submit_attempt`/`get_attempt_review` all skip a drawn question whose option count shrank or that's since been deactivated (`services/instructor_assessment/attempts.py:201-207` etc.), rather than 500ing an in-flight attempt.
- **Performance numbers are always derived live, never stored** — same "derive, never cache" convention as the rest of the codebase's leaderboards. "Delivered" for both hours and the reliability ratio means `InstructorSessionDay.att_status == 'present' and status == 'approved'` (`services/instructor_assessment/performance.py:7-11`) — assigned-but-never-checked-in days don't count.
- **`relevant_experience`'s definition is explicitly provisional** (`services/instructor_assessment/ranking.py:68-73`) — parked pending product-owner confirmation of what "relevant" means; isolated in its own function so the formula can change without touching the rest of the blend.
- **Deleting a config is blocked (409, not a raw FK error) while it's assigned to any cohort** (`assessment_cohort_assignments.config_id` is `RESTRICT`) — unassign first.

---

## Documents (shared infrastructure — not Instructors-only)

**This is the canonical description of the platform's document system.** Instructors are its heaviest user, but it is genuinely shared: the internship-letter flow (`HANDOFF_INTERNSHIP.md`) mirrors the instructor contract's signing technique, ID cards render for every role via one endpoint, and the generic template/request system takes a `role` parameter precisely because it's meant to serve `instructor`, `intern`, `facilitator`, `teacher`, `ambassador`, etc. alike.

**The most important finding here: despite living in the same `services/documents/` folder and one top-level `routers/documents.py`, this is not one shared e-sign engine — it's three genuinely separate mechanisms that happen to reuse the same PDF-generation techniques (docxtpl → LibreOffice, or reportlab) and the same storage helpers:**

1. **The generic Document/Request/Template system** — `models/document.py` (`Document`), `document_request.py` (`DocumentRequest`), `document_template.py` (`DocumentTemplate`), all served by `routers/documents.py` (a single top-level router file, not a package — "not nested under any one domain, since recommendation letters apply to any role", per its own module docstring). A user submits `POST /documents/requests` (e.g. `recommendation_letter`), an admin fills in the body and generates it against a `DocumentTemplate` (`POST /documents/requests/{id}/generate`), then approves it (`POST /documents/requests/{id}/approve`) — or an admin free-generates one directly (`POST /documents/admin/generate`). `DocumentTemplate.type` (`letter` | `certificate`) decides the renderer; `{token}` placeholders are filled generically (`_fill_placeholders`, `documents.py:407-423`) and admins can live-preview a template before saving (`POST /documents/admin/templates/preview`, persists nothing). This system covers recommendation/confirmation/completion letters and template-driven certificates — **it does not cover contracts, payment letters, or internship letters.**
2. **Bespoke, hardcoded per-domain generators** in `services/documents/` — `contract.py` (instructor employment contract), `internship_letter.py` (intern letter, explicitly "mirrors `contract.py`'s technique exactly"), `payment_letter.py` (payment letters), `certificate.py` (the two auto-fired system certificates plus every template-driven certificate). Each fills its own DOCX/PDF template with its own fixed field set and stores the result on its **own** domain table (`InstructorProfile.signed_contract_path`, `PaymentLetter`, etc.) — never a `Document`/`DocumentRequest` row. They share `signature_block.py`'s anchored-signature-image trick and the LibreOffice conversion pattern, but are not driven by `DocumentTemplate` rows and are not swappable through the admin template editor.
3. **ID cards** — `IdCard` (`models/id_card.py`, "Shared across all roles" per its own docstring), rendered **on-the-fly, never stored** (`services/documents/id_card.py`; deliberately no `front_url`/`back_url`/`pdf_url` columns) via `GET/POST /documents/id-card` and `GET /documents/id-card/pdf`, generic over `role`. **Gotcha:** `routers/instructors/instructor.py:231-301` has its own duplicate, instructor-hardcoded `GET/POST /instructor/id-card` + `/instructor/id-card/pdf` route set doing the same rendering. The frontend does not call it — `frontend/src/api/instructors/instructor.ts:14-29` re-exports the generic `/documents/id-card` functions under the same names, and the only component that renders a card, `components/documents/ProfileIdCard.tsx`, imports directly from `api/documents`. Treat the `routers/instructors/instructor.py` copy as dead code, not a second source of truth.

There's a **fourth**, separate concept easily confused with the above: **`instructor_documents`** (`InstructorDocument` model, table `instructor_documents`) — a personal upload vault (Emirates ID, Passport, Visa, CV, etc.), served at `/instructors/documents` (`routers/instructors/instructor.py:444-478`, historically instructor-only). The frontend's `api/documents.ts:44-60` calls this "generic per-user, works for any role" in a comment, but `pages/shared/PersonalDocuments.tsx:62` currently gates the vault UI to `activeRole === "instructor"` only — other roles see the request/template flow (#1) but not this vault.

### How `pages/shared/PersonalDocuments.tsx` ties it together

This single page (901 lines) is the "My Documents" surface for every role, and it composes **all four** of the above plus contract/internship-letter signing:
- `listDocumentsApi`/`uploadDocumentApi`/`deleteDocumentApi` → the vault (`/instructors/documents`, instructor-only in the UI).
- `getMyDocumentsApi`/`getMyDocumentRequestsApi`/`createDocumentRequestApi`/`getAvailableTemplatesApi` → the generic Document/Request/Template system (`/documents/*`).
- `getProfileApi`/`signContractApi` (from `api/instructors/instructor`) → the bespoke contract flow, instructor-only.
- `getMyInternshipLetterApi`/`signInternshipLetterApi` (from `api/internship`) → the bespoke internship-letter flow, intern-only — confirms Documents' shared nature: this is the same page, same `SignaturePad.tsx` component, serving a completely different domain's letter.

### Roles

- **Any authenticated user** — `GET /documents/me` (own certs + generated documents), `POST /documents/requests` + `GET /documents/requests/me` (request a letter), `GET/POST /documents/id-card*` for their own role(s).
- **`admin`** (`require_admin`) — everything else: recommendation-letter generation, request review/generate/approve/reject/regenerate, admin-direct generation, template CRUD + preview, storage-bucket browsing/deletion (`GET/DELETE /documents/admin/storage/*`).

### Gotchas

- **Contracts aren't `Document`/`Certificate` rows** — deleting a signed contract PDF via the generic storage browser (`DELETE /documents/admin/storage/files`) has special-cased handling (`documents.py:1126-1142`) that resets `InstructorProfile.contract_signed_at`/`signed_contract_url`/`signed_contract_path`/`contract_signature_data` to `None` so the instructor gets a fresh unsigned contract next load — because `_ensure_contract` (`routers/instructors/instructor.py`) otherwise refuses to regenerate anything once `contract_signed_at` is set, which would strand the instructor.
- **Which placeholders actually get filled depends on which code issues the document, not the template row** (`documents.py:354-366`) — `student_completion` and `workshop_delivery` are rendered by their own bespoke code with a small fixed token set each; everything else goes through `_render_and_store_document`/`admin_generate_document`, which fills a different, larger set. `_placeholder_set()`/`admin/templates/placeholders` exists specifically so the template editor never shows a token that won't actually be substituted on a real document.
- **Each instructor can have two rows in the `contracts` bucket** — the unsigned draft at `{user_id}/agreement.pdf` (re-rendered on every profile load pre-signing) and `{user_id}/signed.pdf`. The storage browser's file-type labeling (`documents.py:1046-1055`) relies on "signed" appearing in the filename and UUID path segments being hex-only (so a user_id can never accidentally contain the substring "signed").
- **`document_templates.is_system`** (seeded, non-deletable, e.g. `workshop_delivery`) blocks `DELETE /documents/admin/templates/{id}` with a 400 — check this before assuming any template is removable.

## Cross-links

- [`HANDOFF.md`](./HANDOFF.md) — platform overview.
- [`HANDOFF_INTERNSHIP.md`](./HANDOFF_INTERNSHIP.md) — the HR-side intern role-request/letter pipeline; its letter-signing flow explicitly mirrors this file's "In-app contract signing" section and shares the Documents infrastructure above.
- [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md) — staffing/cohort-call interest registration that Instructor Assessment's gate hooks into; also owns the instructor-facing session-delivery pages colocated under `pages/instructors/`.
- [`HANDOFF_LMS.md`](./HANDOFF_LMS.md) — `lms_course_completion`/`lms_path_completion` certificates share `Certificate`/`generate_completion_certificate_pdf` with this domain.
