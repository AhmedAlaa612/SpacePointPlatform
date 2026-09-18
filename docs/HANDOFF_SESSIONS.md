# Sessions Domain

Back to [`HANDOFF.md`](./HANDOFF.md). See also [`HANDOFF_SPINE.md`](./HANDOFF_SPINE.md) (every
`contact_id` this domain writes resolves through spine), [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md)
(applicant pipeline, payment letters, certificates — the instructor's account side of the
staffing marketplace this file describes from the session side), [`HANDOFF_LMS.md`](./HANDOFF_LMS.md)
(a registration's LMS enrollment is a separate, later concern this domain never talks to directly
— see `sync_registration_lms`), and [`HANDOFF_COMPETITIONS.md`](./HANDOFF_COMPETITIONS.md) (a
competition is a `Program` with `program_type="competition"`, built on Sessions tables, not a
parallel domain).

**Status as of 2026-09-17.** Read every router under `backend/app/routers/sessions/`, every
service under `backend/app/services/sessions/`, every model under `backend/app/models/sessions/`,
`backend/app/services/spine/identity.py`, `backend/app/services/user.py`, the frontend route tree
(`frontend/src/router.tsx`) and nav (`frontend/src/components/layout/Sidebar.tsx`), and every
alembic migration from 2026-07-21 through 2026-09-16 that touches `registrations`, `cohorts`,
`programs`, `sessions`, `contacts`, `contact_roles`, or `contact_role_events`. Everything dated
2026-08-24 or earlier in the sections below has been re-checked against current code; several
claims from that period were wrong and are corrected inline (see the "corrected 2026-09-17" notes).
Registration, bulk import, check-in, the cohort-shaped staffing marketplace, instructor daily
delivery + payment letters, certificates, calendar, the ops dashboard, invite-code program grants,
and an instructor-assessment gate on top of staffing are all shipped. Current test count and
schema head: see `HANDOFF.md` §1 rather than a number here that will drift.

**Corrected 2026-09-17 — three claims below were simply wrong, not just stale:**
- **The ops UI moved from `/admin/*` to `/operations/*` (S6-2) and nothing links to the old paths
  any more.** `router.tsx` keeps `/admin/programs`, `/admin/cohorts`, `/admin/contacts`,
  `/admin/merge-reviews`, `/admin/checkin` only as bare redirects to their `/operations/...`
  equivalents, with a comment confirming "nothing in the app links here any more (verified
  2026-07-28)". There is no `/admin/imports` page at all — bulk import is the `ImportListModal`
  inside Cohort Detail/Cohort Wizard, not a standalone route. Every path in this file below is the
  current `/operations/...` one.
- **`Session.price`/per-session price override was dropped 2026-08-30** (migration
  `c4d9e2f6a813`, operator ask — "people pay for the program/cohort, not a specific session, and
  per-session pricing was never wired to a real payment processor anyway"). A registration's price
  always comes from `Program.price` now; `resolve_registration_price`'s `session_ids` parameter is
  kept only so callers don't need special-casing, it no longer affects the amount.
- **`staffing_status` lives on `Session`, never on `Cohort`** — `Cohort` has no such column at
  all (see its model docstring: "Staffing ... lives on Session, not here"). A cohort with several
  sessions can be partly staffed; there is no single cohort-level staffing state to read.

**2026-09 — the staffing marketplace grew an assessment gate and cohort-shaped closes got a
duplicate-email fix.** Not fully documented here — the assessment/ranking system itself (question
bank, attempts, priority-score weighting) is owned by
[`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md)'s "Instructor Assessment" section — but it
directly gates this domain's endpoints, so know it exists: `services/instructor_assessment/{gate,ranking}.py` (new tables under
`models/instructor_assessment/`) can require an instructor to have submitted an assessment before
`register_interest`/`register_cohort_interest` will accept them (`assert_assessment_passed`,
called from `staffing.py`/`cohort_staffing.py`), and adds ranking/performance columns to
`list_eligible_instructors` and `list_cohort_call_interest`'s output when a cohort opts in via
`AssessmentCohortAssignment`. `programs.default_assessment_config_id` seeds a new cohort's
assignment once at creation (`create_cohort`); editing the program default afterwards never
reaches back into cohorts that already exist. Separately, `_email_recipients`'s `email_mode`
(`none|all|same_city|open_to_work_city`) is now the *only* thing that decides who gets an email
invite on a cohort call — targeting alone used to imply it, and a 2026-09-13 fix collapsed what
used to be one invite email **per session** in the cohort down to one per recipient for the whole
call (it used to fire `len(succeeded)` emails at each targeted instructor).

**2026-09 — several small but real additions to the registration desk:**
- **`registered_via` gained a fourth value: `invite_code`** (2026-09-15,
  `services/lms/invite_grants.py::_register_into_cohort`). An invite code can now grant a whole
  `Program` (not just a course/learning path) — this creates a *real* `Registration` row (roster,
  attendance-eligible, onboarding email), going through the same `register()` ->
  `sync_registration_lms()` chain a human desk-registration does, `payment_status="waived"`
  always. Never raises on failure (no linked contact, full cohort, etc.) — logs and moves on, same
  discipline `sync_registration_lms` itself already follows.
- **`registrations.onboarding_sent_at`** (2026-09-10 migration `a1c4e8f92d63`) tracks the LMS
  "you're registered" / set-password email separately from `ticket_sent_at`. Two new ops actions
  on each registration row (`POST /sessions/registrations/{id}/resend-onboarding-email`,
  `POST .../set-password-link` — the latter hands ops the raw link to paste into WhatsApp/SMS
  instead of emailing it) plus a **"Copy set-password link"** button in the Registrations tab.
- **`last_login_at` / a login-status filter** landed on the Registrations tab 2026-09-16
  (`CohortDetail.tsx`, backed by `list_registrations` in `routers/sessions/cohorts.py`) — "never
  logged in" is queryable and exportable. **XLSX export on that tab is entirely client-side**
  (the `xlsx` npm package, `CohortDetail.tsx`) over whatever rows are already fetched — there is
  no backend export endpoint.
- **Contacts got two fields back, on purpose, the same day they were dropped**: `date_of_birth`
  and `grade` (migration `a7c2e91f0007`, 2026-07-24, CEO's explicit request) — see
  `HANDOFF_SPINE.md` for the full story. They flow through here too: the bulk-import template
  (`services/sessions/importer.py::TEMPLATE_COLUMNS`) has optional `date_of_birth`, `grade`,
  `organization` columns, and `desk_register`/the public form pass them through
  `resolve_or_create_contact`. **Purely informational, gap-fill-only, never enforced** — this does
  not reopen the "no age/minor gating, ever" decision below.

**2026-08-24 — staffing became cohort-shaped, and the instructor's day is now recorded.**
Read this before touching anything below that says staffing is session-scoped; that framing is
now only half true.

- **A call can cover a whole cohort, and an instructor applies to it once.** `cohort_calls`
  already grouped per-session `SessionCall` rows; what was missing was the instructor's side.
  `cohort_call_interests` holds one answer per person per call — the role they want, the cover
  letter, and the operations-doc §2 support questions (transport, ops support, travelling from
  another city, free-text concerns). Registering still writes the per-session
  `InstructorInterest` rows for the days they ticked, so `list_eligible_instructors`, the
  openings waitlist count and `select_instructors`' without-interest flag are untouched. As of
  2026-08-30 (`b3f8c6a91d47`) a standalone single-session `register_interest` asks the exact same
  §2 questions `InstructorInterest` now carries too, not a lighter subset.
- **`cohort_instructor_assignments` brings back a table that was deliberately dropped.**
  `cohort_instructors` went in `e5a2c93f0005` for never being wired up. This is not that table
  returning by accident — see the model docstring for the three reasons (the one-role rule needs
  somewhere to live; the rate must be snapshotted at selection so a later edit can't reprice an
  agreed assignment; a withdrawal needs a record). **It is not a second source of truth for
  staffing state**: `Session.staffing_status`, `fully_staffed()` and `SessionInstructor` still
  decide who teaches which day.
- **One role per instructor per cohort** (operator's rule). Enforced in
  `services/sessions/cohort_staffing.py::_assert_single_role`, which checks live
  `SessionInstructor` rows too — somebody added through the direct-assign path has no assignment
  row and would otherwise slip past. The unique key is `(cohort_id, user_id, role_id)`, looser
  than the rule, so the backfill could represent legacy mixed-role cohorts honestly instead of
  failing or collapsing them.
- **Rates resolve session opening → cohort opening → `DeliveryRole.default_rate_aed`** (the
  global tier, edited at `/operations/delivery-settings`). `openings_for_session` returns
  `rate_source` so the UI can grey an inherited figure.
- **The instructor's day is a real record now** (`instructor_session_days`): check-in or a
  declared absence with a reason, a checklist resolved program → cohort → session
  (override-not-merge, exactly like `session_materials`, plus a `role_id` axis added 2026-08-28 —
  a role-specific checklist replaces the general one at whatever level has its own rows, never
  adds to it), per-item photo proof pointing at an existing `session_reports` row, then submit →
  ops approve or return with a comment. **`status='approved'` AND `att_status='present'` is the
  definition of a paid day** — nothing else decides what counts as delivered. **Since 2026-08-30,
  ops can approve a day at any stage, submitted or not** (`services/sessions/day.py::approve_day`)
  — the checklist is something to look at when reviewing, not a precondition for paying someone
  ops already knows delivered. Approving a never-submitted day stamps `att_status='present'` if it
  was never set at all (that's the other half of what makes a day payable), but never overwrites
  an explicit "absent".
- **Cohorts complete themselves, but no longer draft payment lines when they do.**
  Once every session has `completed_at` and every day row is approved,
  `services/sessions/day.py::maybe_complete_cohort` calls the existing `complete_cohort()`.
  `cohort_is_fully_reviewed` also requires somebody to have been staffed — without that guard a
  cohort nobody taught has zero day rows, "all approved" is vacuously true, and it would complete
  itself. **2026-08-30 reversed an earlier decision**: completion no longer accrues draft payment
  lines automatically. Delivered sessions simply become billable (they show up via
  `services/sessions/journey.py::unbilled_sessions`, surfaced at
  `GET /sessions/billable/{instructor_user_id}`), but nothing is drafted until ops explicitly
  clicks "Create letter" — auto-drafting the moment the last report was approved meant a letter
  existed before anyone decided it should. Payment letters themselves live in
  `HANDOFF_INSTRUCTORS.md`.
- **`/sessions/day-reviews` and `/sessions/available-work` are literal paths.** The day router is
  mounted ahead of the `{session_id}` routers for the same reason openings and journey already
  are; a test asserts it 200s rather than 422ing on "day-reviews" not parsing as a UUID.

**2026-07-26 changes (operator decisions during and after the cutover), still current:**
- **Attendance is `present|absent`.** `late` and `excused` are gone (migration `a1d7f36c0013`
  remaps existing rows) — both for student attendance and (deliberately, per its docstring) for
  the instructor day's `att_status` too; don't reintroduce them on either.
- **Delete exists** for programs, cohorts, sessions and registrations. Programs/cohorts/sessions
  refuse while dependents exist (the schema cascades hard). **Registration delete deliberately
  does not refuse** — it erases the sign-up, its attendance and its certificate, and does not hold
  back once attendance has been taken. `?delete_contact=true` also removes the person, but refuses
  for a contact with a staff account or registrations in other cohorts.
- **Cancel is reversible.** `register()` reinstates a cancelled row (same id, `created_at`, ticket
  token; `ticket_sent_at` cleared) instead of 409ing. Active duplicates still 409. Reinstating is
  capacity-checked. Cancelling also deactivates (not deletes) the registration's LMS enrollments
  (`deactivate_registration_enrollments`).
- **Targeted open calls are a real restriction.** `SessionCallTarget` gates `list_available_sessions`
  and `register_interest` (404, not 403 — don't leak existence). **No target rows means
  unrestricted**, so every pre-existing call is unaffected. `reopen()` carries targeting over; pass
  `[]` to widen.
- **Public ticket page**: `GET /public/ticket/{token}` and `/qr.png`, no auth — the token is the
  credential. The frontend route is `/t/{token}`.
- **`issue_ticket(..., force=False)` is idempotent** on `ticket_sent_at`; `resend-ticket`
  deliberately passes `force=True` — the one place a second send is the point.
- **`RegistrationOut.certificate_issued`** is how you tell whether a student has a certificate.
  `certificate_url` is always null for them: student completion certs are emailed as a PDF
  attachment and never stored (`resolve_url`'s bucket/path-first, file_url-fallback logic still
  correctly leaves this null rather than hiding it — see `routers/sessions/cohorts.py::list_registrations`).

**2026-07-24 session-model rework — still the foundation everything above builds on:**
- A cohort's teaching unit is a first-class **`Session`** (own `title`, `material_url`) — not a
  bare-date `SessionMeeting`. A single-day workshop is just a cohort with one session.
- Instructor assignment is **per-session** via `SessionInstructor`, and **a session can have
  multiple instructors** (their role comes from `delivery_roles`, data since I5-3, not a
  `lead|co` string).
- **`RegistrationSession`** lets a registration cover a subset of a cohort's sessions. An empty
  set (the common case) means "every session in the cohort".
- **No date_of_birth-driven gating, no age band, no minor/guardian enforcement anywhere, period**
  — permanent. (`date_of_birth`/`grade` came back on `Contact` the same day as purely
  informational fields — see the 2026-09 note above and `HANDOFF_SPINE.md` — that has not changed
  this.) Parent/guardian fields are always optional with zero system-side gating.
- **No separate Arabic name field** — `contacts.full_name` is one field.
- **No consent tracking at all** — `ConsentRecord` writes removed from every registration flow.
  The table still exists, untouched, for the real consent service at CRM phase.
- **"Roster" is "Registrations"** everywhere in the UI/API.
- **`programs.program_type`** is `workshop|course|info_session|competition` (the `competition`
  value added 2026-08-24 for the Competitions domain — `Program.is_competition` is the property
  everything keys off, not a raw string comparison).

## What this is

This domain replaced SpacePoint's WhatsApp + Google Sheets registration process. It owns the
commercial registration record (as opposed to spine's identity, or the LMS's educational
enrollment) and the instructor-to-session staffing marketplace.

**Registration vs. enrollment**: a `registration` here is the commercial fact of signing up for a
cohort. Whether that also creates an LMS enrollment (for course material) is handled by
`services/lms/ops_integration.py::sync_registration_lms`, called from every registration entry
point (public form, desk, import, invite-code program grant) — this domain's own service layer
never imports from `services/lms/` the other direction.

## Roles and where each reaches this domain

Role gating is `backend/app/core/dependencies.py::RequireRole` — `admin` passes every check
unconditionally; every other role is listed explicitly.

| Role | Guard(s) | Can do | Frontend |
|---|---|---|---|
| `operations` | `require_operations` (most endpoints); alone among domain roles, reaches every `/sessions/*` and `/spine/*` route | Everything: programs/cohorts/sessions CRUD, registration desk, bulk import, staffing (open/close calls, select, assign, remove), day reviews (approve/return), check-in, contacts, merge review *listing* (not resolving), calendar, delivery-role/rate settings | `/operations/{dashboard,programs,cohorts,cohorts/$id,cohorts/$id/sessions/$id,reviews,calendar,delivery-settings}` are in the sidebar's Programs/Dashboard groups. **`/operations/{contacts,merge-reviews,checkin,this-week}` are reachable but have no sidebar nav entry at all** — see Gotchas |
| `admin` | passes everything above, plus `require_admin`-only merge resolution | Same as operations, plus resolving a `merge_reviews` row | Same pages, reached from `/admin` hub's one "Operations" link (`Sidebar.tsx`, added specifically because S6-2 originally stripped admin's only path into this domain) |
| `instructor` / `facilitator` | `require_instructor_or_facilitator` (interest/browse), `require_session_delivery` = `instructor\|facilitator\|operations` (day/delivery actions — the actual assignment check for the non-ops case happens in `services/sessions/delivery.py`, not the dependency), `require_materials_manager` = `operations\|facilitator` (materials CRUD — plain `instructor` cannot edit teaching material, only view what resolves to their session) | Browse/register/withdraw interest (session- or cohort-level), decline an assignment, check in / submit their day, accept responsibilities, view their assigned sessions | `/instructors/*` — available sessions, my sessions, session detail (`pages/instructors/SessionDetail.tsx`) |
| `coo` / `storekeeper` | **Deliberately excluded** from `require_operations` — see `dependencies.py`'s comment: the narrowness is the point | Nothing in this domain — no session assignments, no registrations, no contacts | N/A |
| `judge` | `require_judge`, separate gate | Nothing in Sessions/Spine directly — scoped to `/missions/instructor`-style competition judging surfaces on top of the same cohort/session tables | `/judge` |
| `student` | n/a to this domain's own endpoints | Is the account a `Registration` may create/link via `sync_registration_lms` | `/learn` |

## Key tables

| Table | What it holds |
|---|---|
| `programs` | A workshop/camp/course/competition template. `pricing_model` (`free`/`paid`) + `price` is the only source of a registration's charge — no per-session override any more (dropped 2026-08-30). `completion_rule_type`/`completion_rule_value` (percentage or a raw session count) replaced a hardcoded 0.7 completion threshold. `default_assessment_config_id` seeds a new cohort's instructor-assessment requirement once, at creation. |
| `cohorts` | One actual run of a program — dates, location, capacity. `status` tracks the registration lifecycle (`planned\|registration_open\|running\|completed\|cancelled`, `VARCHAR(24)` — `registration_open` alone is 17 chars). **Has no `staffing_status` column** — that lives on `Session` (see the corrected-claims note above). `organization_id` + `visibility='private'` models a B2B-only cohort. |
| `sessions` | A real teaching unit inside a cohort — `title`, `material_url`, `UNIQUE(cohort_id, meeting_date, starts_at)`. `staffing_status` (`unstaffed\|open_call\|staffed`) lives here. `started_at`/`completed_at` double as the actual delivery record. No `price` column (dropped 2026-08-30). |
| `session_instructors` | The staffing assignment (role from `delivery_roles`) for one session — a session can have several. |
| `cohort_calls` / `cohort_call_targets` / `cohort_call_interests` | 2026-08-24 cohort-shaped staffing: one standing call grouping a chosen subset of a cohort's per-session `SessionCall` rows; one answer per instructor per call (role, days, support questions), separate from the still-live per-session `InstructorInterest`. |
| `cohort_instructor_assignments` | The *deal* struck with one instructor for a whole cohort (role, `rate_basis` per_session/flat, snapshotted rate, `source` call/direct). **Not** a second source of truth for who's scheduled — `SessionInstructor` still is. `UNIQUE(cohort_id, user_id, role_id)`. |
| `delivery_roles` / `session_openings` / `cohort_openings` / `program_openings` / `session_addons` | The rate/opening configuration chain: a session opening resolves from itself → its cohort's default → its program's default → the role's global `default_rate_aed`. |
| `delivery_checklist_items` / `instructor_session_days` / `instructor_checklist_progress` | The instructor daily loop (2026-08-24) — see the dated section above. `role_id` on checklist items (2026-08-28) is a second override axis alongside program/cohort/session level. |
| `payment_session_coverage` | Which delivered sessions one payment line (`payment_sessions`, owned by `HANDOFF_INSTRUCTORS.md`) actually covers — generalises the old one-`session_id`-per-line rule to N, so a cohort-shaped payment line can cover several days without hiding any of them from the anti-double-billing check. |
| `registrations` | The commercial record — **the ticket IS this row**. `ticket_token` is a 64-char random credential. `UNIQUE(contact_id, cohort_id)`. `registered_via` is now `form\|import\|desk\|invite_code` (invite_code added 2026-09-15). `onboarding_sent_at` (2026-09-10) tracks the LMS welcome email separately from `ticket_sent_at`. |
| `registration_sessions` | Which of a cohort's sessions a registration covers. No rows = covers every session. |
| `attendance_records` | One student's attendance for one session; `recorded_by_user_id` is `NOT NULL`/`RESTRICT`. |
| `instructor_interests` | An instructor's "I'd like this session" signal — session-scoped. Since 2026-08-24 normally a side effect of one `cohort_call_interests` answer; since 2026-08-30 also carries the same §2 support-question columns as `cohort_call_interests` for a standalone single-session call. |
| `session_reports` | A file uploaded after delivering a session; also reused as the storage for checklist photo proof (`instructor_checklist_progress.proof_report_id`). |
| `import_batches` | One bulk-sheet upload. Always dry-run first; `counts` JSONB holds preview/result. Template columns (current): `student_name*, email*, phone*, city*, date_of_birth, grade, organization, parent_name, parent_phone, parent_email` (`*` required) — `date_of_birth`/`grade`/`organization` are optional and purely informational, matching `Contact`'s own fields. |
| `activities`, `activity_versions`, `activity_assignments` | Schema for a live-quiz engine that was never built here — superseded by the real `games`/`game_runs` tables under the LMS domain (see `HANDOFF_LMS.md`). Treat as dead schema, not a roadmap item. |

## Key flows

**Public registration**: `POST /public/register/{cohort_key}` → `resolve_or_create_contact`
(spine, email/phone matching — see `HANDOFF_SPINE.md`) for the student and, if parent fields were
given, the guardian → `ensure_guardian_relationship` → `services/sessions/registration.py::register()`
→ `sync_registration_lms()` (creates/links a student account + enrolls in curriculum, never raises)
→ ticket email enqueued via ARQ (`send_ticket_email`, opt-in via `send_ticket_email` param, no-ops
gracefully if SMTP is unconfigured).

**Desk registration** (`POST /sessions/cohorts/{id}/registrations`, ops-only): same
`resolve_or_create_contact` → `register()` → `sync_registration_lms()` chain, with
`create_lms_account`/`send_welcome_email` as explicit checkboxes (defaulting on). Also the code
path `invite_grants.py::_register_into_cohort` reuses end-to-end for an invite-code "program"
grant, with `payment_status` forced to `"waived"`.

**register()'s duplicate-key handling** (`services/sessions/registration.py`, current since PR
#84, September 2026): the new `Registration` is added and flushed **inside**
`async with db.begin_nested():`, not before it — `begin_nested()` autoflushes whatever is already
pending as the first step of opening its SAVEPOINT, *before* the SAVEPOINT itself exists, so
adding the row earlier would put its INSERT in that pre-SAVEPOINT autoflush and a duplicate-key
`IntegrityError` would poison the whole outer transaction instead of staying contained to the
nested scope. This is the established get-or-create-under-a-unique-constraint pattern in this
codebase (`merge_contacts` in `services/spine/identity.py` uses the same shape for its own
per-row SAVEPOINTs) — copy this ordering, not the "wrap it in `begin_nested()`" idea alone, if you
add another such path.

**Staffing (session-level)**: ops `open_call` → in-app notification to every
instructor/facilitator (or just the targeted subset) + optional emailed invite
(`send_call_invite_emails`, targeted calls only — a public call already surfaces on Available
Sessions, so an email would be noise) → instructors `register_interest` (blocked by
`assert_assessment_passed` if this call's cohort opted into the instructor-assessment gate and
this instructor hasn't submitted one) → ops `list_eligible_instructors`/`select_instructors` →
assignment email + notification per selected instructor.

**Staffing (cohort-level, 2026-08-24+)**: ops `open_cohort_call` (bulk-opens `SessionCall` rows
across a chosen subset of the cohort's sessions, or every unstaffed one) → `_email_recipients`
resolves the actual email audience from `email_mode` (`none|all|same_city|open_to_work_city`,
ops's explicit per-call choice, separate from targeting) → instructors `register_cohort_interest`
once for the whole call, ticking which days they can do → ops `select_for_cohort` assigns people
across the days they ticked in one action, snapshotting the rate and writing one
`CohortInstructorAssignment` + the underlying per-session `SessionInstructor` rows, refusing with
a 409 naming the clash if the instructor already holds a *different* role in this cohort.

**Instructor's day**: check-in (or declared absence) → checklist resolved program → cohort →
session, role-scoped if role-specific rows exist at that level, photo proof on `requires_proof`
items → `submit_day` (an absence auto-approves itself, nothing to review) → ops `approve_day`
(allowed at any stage, stamps `att_status='present'` if never set) or `return_day` (comment
mandatory) → once every session in the cohort is `completed_at` and every day row `approved`,
`maybe_complete_cohort` fires `complete_cohort()` — delivered sessions become billable via
`unbilled_sessions`, but no payment line is drafted until ops explicitly creates one.

**Check-in**: `POST /sessions/checkin` (ops-only; instructor self-service check-in of *their own*
day is the separate delivery flow above, not this one) resolves a scanned/typed token via
`check_in()` in `registration.py` — 404 unknown token, 409 wrong cohort, 409 not covered by this
registration's `RegistrationSession` restriction, 409 already recorded.

## Gotchas

- **The established `contact_id`-first, email-fallback resolution pattern is alive and used
  correctly in the domain's read paths, but three newer ops actions skip it.**
  `_registered_cohort_users` (`services/lms/students.py`) and `list_registrations`
  (`routers/sessions/cohorts.py`, its `last_login_at` column) both correctly resolve `Registration.contact_id`
  → linked `User` by `User.contact_id` first, then fall back to matching `User.email` against the
  `Contact`'s email for whatever didn't resolve — because a real, non-trivial slice of `User` rows
  have `contact_id` unset and are only findable that way (see `HANDOFF_SPINE.md`'s note on
  `users.contact_id` being unique-but-often-NULL). **`resend_onboarding_email` and
  `get_set_password_link`** (`routers/sessions/cohorts.py`) instead do a plain
  `select(User).where(User.contact_id == registration.contact_id)` — no email fallback — and 404
  with "No LMS account linked to this registration" for exactly the accounts the fallback exists
  to find. The spine-domain twin of this same gap (`reset_lms_password`) is called out in
  `HANDOFF_SPINE.md`. If you're fixing one, fix all three the same way.
- **`Session.price` is gone (2026-08-30) — don't resurrect a per-session price field or a "price
  override" UI control.** `resolve_registration_price` always reads `Program.price`; its
  `session_ids` parameter exists only so callers scoping a registration to specific sessions don't
  need a special case, it has no effect on the amount.
- **`cohorts.status` is `VARCHAR(24)`, not `VARCHAR(16)`** — `registration_open` alone is 17
  characters. Caught by a functional insert test, not by reading the DDL.
- **The ticket QR must encode the token/URL, never a guessable id or raw PII.** `ticket_token` is
  a 64-char random string specifically to prevent this. `services/documents/ticket.py` generates
  it — reuse `generate_ticket_qr_png`/`ticket_url`, don't reimplement.
- **`attendance_records.recorded_by_user_id` is `NOT NULL`/`RESTRICT`** — unlike most "who did
  this" columns elsewhere in this codebase (nullable, `SET NULL`), you cannot delete a user who
  has recorded attendance, and `check_in()` hard-fails (FK violation) on a fake/nonexistent
  `actor_user_id` — always a real, logged-in staff user.
- **`register()` doesn't take raw parent/guardian fields** — it takes an already-resolved
  `payer_contact_id`. Finding-or-creating the guardian and writing the `contact_relationships`
  row is the *caller's* job. **There is no minor/guardian enforcement of any kind, anywhere,
  permanently** — parent info is always optional.
- **`register()`/`issue_ticket()` raise `HTTPException` directly**, matching this codebase's
  service-layer convention (`services/interns/epic.py`, `proposal.py`). Status codes: 409 cohort
  full, 409 duplicate registration, 404 unknown ticket (check-in), 409 wrong-cohort or
  already-recorded (check-in), 409 "not registered for this session" if `RegistrationSession` rows
  exist and don't cover the scanned session.
- **`issue_ticket()` never raises on a failed send** — returns `False`, leaves `ticket_sent_at`
  NULL. A registration always succeeds even if the email doesn't go out.
- **`import_batches`'s dry-run and commit MUST stay structurally identical.**
  `services/sessions/importer.py::dry_run()` runs the exact same row-processing code as
  `commit_batch()` inside a SAVEPOINT it then rolls back. If you touch `_process_row`, both paths
  change together automatically; don't add preview-only logic that could drift from what actually
  commits.
- **A row matching an existing contact for a *different* cohort links (or queues a review); the
  same cohort resolves to `already_registered`** (the `UNIQUE(contact_id, cohort_id)` constraint).
- **`/operations/{contacts,merge-reviews,checkin,this-week}` have no sidebar nav entry at all** —
  verified by grepping every `Link`/`navigate` target across `frontend/src` for `/operations/contacts`,
  `/operations/merge-reviews`, `/operations/checkin`: the only hits are the legacy `/admin/*`
  redirect aliases in `router.tsx` (and `/operations/this-week`, which at least gets two links from
  `OpsDashboard.tsx`). An ops user reaches Contacts, Merge Reviews or Check-in only by typing the
  URL or having an old `/admin/...` bookmark that redirects there. This looks like a real
  navigation gap left over from the S6-2 route move rather than an intentional "hide this page"
  decision — flagged, not fixed, by this pass.
- **Rate limiting is still in-memory only** (`app/core/rate_limit.py`) — a plain per-process dict,
  not shared across workers, lost on restart. Give each test a distinct fake `X-Forwarded-For`;
  its state is module-level and persists across the whole pytest session.
- **CORS for public forms is unioned into the app's one global `CORSMiddleware`**, via
  `PUBLIC_FORM_ORIGINS` (`app/core/config.py`) merged with `cors_origins` in `main.py`. Widening it
  doesn't grant extra access — every protected endpoint still needs a valid JWT regardless of
  `Origin`.
- **This app has no `/api` prefix anywhere** — every router mounts at root.
- **Portal routes use the `operations`/`admin` role guard** (`require_operations`) — `admin`
  always passes every role check in this codebase; don't add a separate admin-bypass per route.

## Open questions from this pass

- ~~`services/instructor_assessment/` is a real, load-bearing dependency of this domain's staffing
  endpoints (it can block `register_interest`) but isn't documented anywhere~~ — resolved in the
  same pass that added this note: [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md)'s
  "Instructor Assessment" section now covers the question bank, attempts, and priority-score
  ranking in full. This file still only notes where it hooks into staffing (see the 2026-09 note
  near the top) — read the Instructors doc for the system itself.
- **Whether the `/operations/{contacts,merge-reviews,checkin,this-week}` missing-nav-entry gap
  above is a known, accepted state or an oversight** — I could not find any product decision
  recorded about it either way; flagging rather than guessing.
