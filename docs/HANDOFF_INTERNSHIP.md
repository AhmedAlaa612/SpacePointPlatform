# Internship Request/Letter Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

Not the interns kanban domain ([`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md) — projects, epics,
tasks, teams — a completely different bounded context that just happens to share the word
"intern"). This is the HR-side pipeline: a person requests the `intern` role, an admin reviews
and approves, an internship letter is generated and signed in-app — mirrors the instructor
contract-signing flow closely (`HANDOFF_INSTRUCTORS.md` §"In-app contract signing").

Added 2026-08-20 alongside `scripts/bulk_import_interns.py` (bulk-onboarded 76 historical interns
from a sheet — data only, no letter, since they'd already started; see that script's own
docstring).

## Roles and permissions

- **Any authenticated user** whose current role is allowed to request `intern` (today: just
  `instructor`, via `services/internship/allowed_role_requests.py`'s `ALLOWED_ROLE_REQUESTS` dict
  — deliberately a plain allowlist, not a schema constraint, so a future direction like
  `intern -> instructor` is one dict entry + an approval side-effect handler, no migration) can
  `POST /me/role-requests`. Frontend: the "Apply for Internship" card on
  `pages/shared/PersonalDocuments.tsx`, shown only when the allowlist covers the active role.
- **`admin`** — reviews the queue (`GET /admin/role-requests`), approves (sets the internship
  letter's salutation, activity description, supervisor name/email/phone, and can override the
  requester's city/duration/hours/ref-number) or rejects. Frontend:
  `pages/admin/RoleRequests.tsx`, linked from the admin dashboard with a pending-count badge.
- **`intern`** (role granted on approval, added to whatever roles the user already held — never
  replaces them) — views and signs their own internship letter. `GET /intern/internship-letter`,
  `POST /intern/internship-letter/sign`. Frontend: the "Internship Letter" section on the same
  shared `PersonalDocuments.tsx` page everyone else uses — not a separate page.

## Key flows

### Request -> approve -> letter -> sign

`RoleRequest` (`target_role`, `details` JSONB — university ID, preferred city, requested start
date/duration) starts `pending`. Admin approval (`routers/internship.py::approve_role_request`)
dispatches on `target_role` — today only `"intern"` has a handler
(`services/internship/approval.py::approve_internship`), which:

1. Grants the `intern` role if not already held (reassigns the array, doesn't append in place —
   same SQLAlchemy gotcha as `onboard_application` in the instructors domain).
2. Creates/updates `InternProfile` from the admin's approval-time input — city/duration/hours/
   supervisor/ref-number all admin-set (fully editable per request, not just applicant-supplied),
   falling back to the requester's own `details` for city/duration when the admin doesn't
   override.
3. Allocates a reference number (`services/internship/ref_number.py`) — format `N/YYYY`,
   auto-incrementing per calendar year, row-locked, admin-overridable (override to `Y` and the
   next auto-number in that year becomes `Y + 1`; rolls over to `1` on the first approval of a new
   year). Lazily seeded per year from the highest `ref_number` already on `intern_profiles`, which
   is what lets the bulk-imported historical rows (up to `85/2026`) and this counter coexist
   without a separate seeding step.
4. Generates the unsigned letter (`services/documents/internship_letter.py` — docxtpl fills
   `app/static/templates/docx/internship_letter.docx` -> LibreOffice -> PDF, same technique as
   `services/documents/contract.py`, including the anchored-signature-image trick), uploads to the
   `internship-letters` bucket, emails the intern.
5. Freezes `letter_date` (the printed `Date:` field) at first-generation time — same
   `instructor_since` convention as the instructor contract; it must never drift to `today()` on a
   later re-render (e.g. at signing).

The intern signs in-app (`SignaturePad`, same component instructors use for their contract) —
backend re-renders the full letter from the frozen `InternProfile` fields (including `salutation`/
`supervisor_title`, persisted specifically so the re-render reproduces identical text rather than
going blank — nothing in the schema captures gender/title anywhere, so these are admin-typed at
approval and stored, not inferred), adds the intern's signature the same anchor-clone way
`contract.py` adds the facilitator's, stores the signed PDF, emails it back with a welcome-aboard
message.

### Public application path

Not yet wired up. `POST /apply/intern` (the anonymous new-signup path, `routers/apply.py`) doesn't
collect the internship-specific fields or trigger `approve_internship` on admin approval yet —
`approve_application` (`routers/admin/applications.py`) still only creates a plain
`intern`-role `User`, no letter. The `RoleRequest`/`approve_internship` core is shared and ready
for this; only the entry point (an `Application`-side equivalent of `/me/role-requests`, since
`Application` assumes a brand-new account is being created and a public applicant has no existing
user to attach a `RoleRequest` to) still needs building.

## Main DB tables

| Table | What it holds |
|---|---|
| `role_requests` | Generic "existing user requests an additional role" — `target_role`, `details`/`resolution` JSONB, status, admin review fields |
| `intern_profiles` | 1:1 intern record: ref number, university ID, department (doubles as the letter's activity description), start date, duration/hours, work city, supervisor, letter paths + signature + frozen `letter_date` |
| `internship_ref_counters` | One row per year, backs the auto-incrementing ref number |

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Request/review/sign | `routers/internship.py`, `services/internship/{approval,ref_number,allowed_role_requests}.py`, `schemas/internship.py`, model `models/internship.py` | `pages/shared/PersonalDocuments.tsx` (apply + sign), `pages/admin/RoleRequests.tsx` (review), `api/internship.ts` |
| Letter generation | `services/documents/internship_letter.py`, template `static/templates/docx/internship_letter.docx` | — |
| Bulk import (historical) | `scripts/bulk_import_interns.py` | — |
