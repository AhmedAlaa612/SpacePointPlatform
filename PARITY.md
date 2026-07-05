# Instructors Feature Parity — source (`var/www/spacepoint_portal`) vs unified

> Phase 3 of the stakeholder pivot (`../PIVOT_HANDOFF.md`). Source = the live VPS
> instructors app (reference screenshots + inventory in `../reference-screenshots/`).
> Legend: ✅ present · 🟡 closed this phase · ⛔ won't-port (with reason).

## Applicant pipeline (public + assessment)

| Source feature (template / flow) | Unified | Notes |
|---|---|---|
| Landing "Access Gate" (invite code) | ✅ | `apply/InstructorApply.tsx` + `/apply` gate |
| Apply form (gmail-only, university, cities…) | ✅ | `POST /auth/instructor-apply` seeds profile + 3 videos + review |
| Applicant status card (per state) | ✅ | `Status.tsx` — now covers **research_approved** too 🟡 |
| Phase-1 video summaries (≥200 words, counter) | ✅ | `pipeline/Videos.tsx` |
| Learning modules grid + per-module checklist | ✅ | `pipeline/Modules.tsx` / `ModuleDetail.tsx` |
| Phase-2 research presentation (`research.html`) | 🟡 | `research_approved` stage added to enum + status page; presentation link submit already existed on `phase_1_approved` |
| **Admin applicant list** | ✅ | `Admin.tsx` Applications tab |
| **Assessment: profile + adjudication (decision + feedback)** | ✅ | `ApplicantReview.tsx` decision panel |
| **Assessment: Phase-2 "Research Approved" gate** | 🟡 | new decision button + enum value `research_approved` |
| **Assessment: per-module Approve/Reject PDF + Save Note** | 🟡 | was read-only; added `PUT /admin/applicants/{id}/modules/{mid}/review` + per-module buttons/note |
| **Assessment: video summaries (text + word count + status)** | ✅ | shown in `ApplicantReview.tsx` |
| **Assessment: Export Consolidated PDF (dossier)** | 🟡 | `GET /admin/applicants/{id}/dossier` — cover + per-module dividers + merged submission PDFs (pypdf) |
| **Assessment: Delete Application** | 🟡 | `DELETE /admin/applicants/{id}` + confirm button |
| Phase-1 approve → email; Final approve → promote + contract + cert + points | ✅ | `review_applicant` state machine (unchanged) |

## Instructor portal

| Source feature | Unified | Notes |
|---|---|---|
| **Dashboard** (hero + STATUS badge + SatKit proficiency + sessions + ID pin + ID card + Recommended Next Steps) | 🟡 | `Dashboard.tsx` fully rebuilt from the 3-card stub to match `instructor/dashboard.html` |
| SatKit training + inline player | ✅ | `Training.tsx` / `TrainingPlayer.tsx` |
| Library resources | ✅ | `Library.tsx` |
| Personal document vault | ✅ | `UserDocuments.tsx` (vault section) |
| Profile & settings | ✅ | shared `Profile.tsx` |
| Instructor ID card (SP-XXXX-UAE, front/back, regenerate, PDF) | ✅ | `ProfileIdCard` in Documents; **one-ID-per-person is Phase 4** |
| Payments — signature-canvas e-signing (draft→published→signed→paid) | ✅ | `Payments.tsx` + `SignaturePad` |
| Change password (forced first login) | ✅ | shared flow |

## Admin — payments (payment cohorts)

| Source feature | Unified | Notes |
|---|---|---|
| Summary stat cards (Total Spent/Pending/Awaiting Sig/Sessions/Hours) | 🟡 | added, computed client-side from letters |
| All Letters list (instructor, sessions, total AED, status, PDF) | ✅ | now shows batch chip + AED total + delete-draft 🟡 |
| **Batches (= payment cohorts): +New Batch, list, delete** | 🟡 | backend existed; **the entire Batches UI was missing** — added (create/list/delete + letter counts) |
| Assign letters to a batch (new letter + bulk import) | 🟡 | batch dropdown in New Letter dialog + bulk-import confirm; letters filter by batch |
| Bulk Excel import (template, preview, confirm) | ✅ | `PaymentsPanel` bulk import |
| Admin signature settings | ✅ | `/admin/settings` (portal settings / signature) |
| Manage sessions / add-ons per letter | ✅ | manage dialog |

## Admin — other sections

| Source feature | Unified | Notes |
|---|---|---|
| Overview stats + charts (universities / cities / joined trend) | 🟡 partial | counts exist (`/admin/overview` + hub); **the distribution charts are ⛔ not ported** — low-value analytics, no stakeholder ask |
| Applicants / Instructors / Invitation Codes / Facilitators | ✅ | `Admin.tsx` tabs |
| Users (system users) | ✅ | relocated to `/admin/users` (generic, not domain-specific) |
| Certificates (issue / list) | ✅ | `payments_admin` certificates + documents hub |

## Facilitator portal

| Source feature | Unified | Notes |
|---|---|---|
| Library resource management (create module, upload/delete) | ✅ | `facilitator/Library.tsx` |
| SatKit training management (create modules, upload/delete MP4) | ✅ | `facilitator/Training.tsx` |

## Deliberate won't-ports (⛔)

- **Admin overview distribution charts** (universities / cities / joined-users trend): pure analytics eye-candy, not a stakeholder complaint; the underlying counts are already surfaced. Revisit only if asked.
- **Standalone `/instructor/profile-card` route**: the unified app manages the ID card inside the Documents page (`ProfileIdCard`), so a separate route is redundant; dashboard links point at `/instructors/documents`.
