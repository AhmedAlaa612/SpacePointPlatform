# Spine Domain

Back to [`HANDOFF.md`](./HANDOFF.md). See also [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md) (the
first, and so far only, real consumer of `contact_id` — every registration, guardian and payer
link resolves through this domain instead of storing its own name/phone/email) and
[`HANDOFF_LMS.md`](./HANDOFF_LMS.md) (a `User` account is linked to a `Contact` via
`users.contact_id`, and student-account creation lives in `services/lms/ops_integration.py`, not
here).

**Status as of 2026-09-17.** Read `backend/app/models/spine/*.py`, `backend/app/routers/spine/*.py`,
`backend/app/services/spine/{identity,role_history,learning_panel}.py`, `backend/app/services/user.py`,
`backend/app/services/lms/{students,ops_integration}.py`, the frontend route tree (`router.tsx`)
and nav (`Sidebar.tsx`), and every alembic migration from 2026-07-21 through 2026-09-16 touching
`contacts`, `contact_relationships`, `identity_aliases`, `merge_reviews`, `contact_role_events`, or
`users.contact_id`. Two claims from the last "verified" pass (2026-08-04) turned out to be
outright wrong, not just stale — corrected below, not just noted. Everything else in the
2026-07-24 sections has been re-checked and still holds.

**Corrected 2026-09-17:**
- **`users.contact_id` is now `UNIQUE`.** Migration `efeef0a62c62` ("D1", 2026-08-10, LMS Phase 2
  Stage 1) added `uq_users_contact_id` after first checking production for existing duplicates and
  refusing loudly (not a raw `UniqueViolation`) if it found any. `merge_contacts` (below) has a
  special case for the `users` FK specifically because of this: a merge that would collide two
  accounts onto one contact no longer repoints blindly — it files a `dual_lms_accounts`
  `merge_reviews` row and leaves both accounts untouched instead. **This does not mean every
  `User` row has a `contact_id`** — plenty are still NULL, which is exactly why the
  contact_id-first/email-fallback pattern below is still necessary, just for a different reason
  than "duplicates" (there are none any more) — see Gotchas. Note `services/lms/ops_integration.py::get_or_create_student_account`
  still carries a stale code comment as of this writing ("contact_id isn't unique yet ... D1 ...
  fixes it properly") — the migration it's waiting for has already shipped; the comment just never
  got updated. Don't trust that comment over the actual schema.
- **`contacts.date_of_birth`/`grade` are back**, re-added the *same day* they were dropped
  (migration `a7c2e91f0007`, 2026-07-24) at the CEO's explicit request. The 2026-07-24 section
  below is kept verbatim for the history — it really did happen, in that order, hours apart — but
  don't read "dropped entirely, permanently" as the current state. **What is still permanently
  true**: no age/minor enforcement is reintroduced anywhere. These are plain stored data,
  gap-fill-only, read by nothing that gates on them. `nationality` (free text, citizenship not
  residence) was added 2026-09-14 alongside them, for the competition roster import's
  nationality-gated eligibility — same purely-informational posture.
- **The role-edit → `contact_roles` sync gap flagged in the 2026-07-24 bug-fix note below is
  closed.** `services/user.py::update_user` now calls `ensure_user_contact` +
  `record_role_diff` + an additive-only `contact_roles` sync **at role-edit time**, not just on
  the next `backfill_user_contacts()` run — see Key flows.

**2026-07-24 schema simplification (operator decision), unchanged:** `contacts.full_name_latin`/
`full_name_arabic` collapsed into one `contacts.full_name` ("name is name, it might be english and
might be arabic they do what they want" — no script/language distinction anywhere).
`contacts.date_of_birth`/`is_minor` were dropped in migration `d4f1b82e0004` — then `date_of_birth`
(without `is_minor`) came back the same day in `a7c2e91f0007` as informational-only data (see the
correction above). No age/minor enforcement exists at any point in this history.

**2026-07-24 bug fix — Contacts role-filter dropping a staff account:** an admin account holding
every role disappeared when filtering Contacts by role. Not a query bug
(`Contact.contact_roles.any(role)` is correct) — `backfill_user_contacts()` only ever created
contacts for never-linked users, so a contact's `contact_roles` snapshot went stale once the
linked user's `users.roles` changed afterward. Fixed by adding an additive-only (union,
never-removes) role re-sync pass for already-linked users. **As of the correction above, this gap
is now also closed live** — editing roles in `/admin/users` syncs `contact_roles` at edit time, not
just on the next script run.

**2026-07-24 feature — contact role history:** `contact_role_events` (migration `f6b3d84a0006`)
records every role a contact gains or loses, with a timestamp, source, and who did it — GET
`/spine/contacts/{id}/role-history`, rendered as a timeline on the Contacts detail page.
`services/spine/role_history.py::record_role_diff()` is the one diff-and-log function; every
mutation point calls it (`resolve_or_create_contact`, `update_contact`, `create_user`/`update_user`).
A staff account's role edit records the **raw `users.roles` strings** (applicant/instructor/...);
a contact-only change records the **`contact_roles` vocabulary** (student/parent_guardian/...) —
deliberately two vocabularies, since they're genuinely different sources of truth.
`services/spine/identity.py::ensure_user_contact()` links a user to a contact eagerly, at
`create_user` and at the first role edit, rather than waiting for the periodic backfill script.
Not retroactive: role changes from before this shipped have no history row.

## What this is

The one identity behind every person the platform ever deals with — a student registering for a
workshop today may be an instructor next year, and both need to resolve to the same underlying
record. Every other domain (sessions, and later CRM/marketing) points at a `contact_id`, never
storing a name/phone/email of its own.

Two things this domain deliberately does NOT do: **(1) use name for matching, at all** — not
fuzzy, not as a hint, not in any form. Matching is email + phone only: an exact email match
auto-merges (the only automatic outcome), a phone match always goes to a human via
`merge_reviews`, and that's it. `contacts.full_name` exists purely for a human to read and to
search by (`GET /spine/contacts?q=`); nothing in `services/spine/identity.py` reads it. Operator
call, 2026-07-22 — a false merge mixes two people's history and is hard to undo. **(2) no consent
tracking at all** — the `consent_records` table exists in the schema but nothing writes to it; the
real consent service ships at CRM phase start.

## Roles and where each reaches this domain

| Role | Guard | Can do | Frontend |
|---|---|---|---|
| `operations` | `require_operations` on every `routers/spine/contacts.py` route, and on **listing** merge reviews (`GET /spine/merge-reviews`) | Search/read/edit contacts, create the LMS account for a contact or reset its password, create relationships, manage organizations, read role history, **browse** merge reviews | `/operations/contacts`, `/operations/merge-reviews` (both reachable, **neither has a sidebar nav entry** — see Gotchas) |
| `admin` | passes everything above, plus `require_admin`-only on **resolving** a merge review (`POST /spine/merge-reviews/{id}/resolve`) | Same as operations, plus actually merging two contacts | Same pages, via `/admin` hub's single "Operations" link |
| everyone else | — | No direct access to `/spine/*` at all | — |

No marketer/sales-facing role or wider guard exists yet — that's explicitly deferred to the CRM
phase (see the 2026-07-24 status note history above; unchanged as of this pass).

## Key tables

| Table | What it holds |
|---|---|
| `contacts` | The identity — `full_name` (single field), phones, email, `contact_roles` array, `lifecycle_stage`, optional org link, plus `date_of_birth`/`grade`/`nationality` (all informational-only, see the correction above). `merged_into_id` marks a soft-retired duplicate — never delete a contact. |
| `contact_relationships` | Household links (`guardian_of`, `child_of`, etc.). Parent/guardian info is always optional; nothing here is ever system-enforced by age. |
| `organizations` | Schools, sponsors, B2B clients, government bodies. Circularly linked with `contacts` (`primary_contact_id`) — see Gotchas. |
| `consent_records` | Schema only — no code writes to this table. |
| `touchpoints` | Every interaction, every channel — raw material for a future CRM timeline. |
| `identity_aliases` | External identifiers resolving to a contact (email, phone, etc.). `UNIQUE(alias_type, alias_value_hash)` makes exact-match lookup a simple query. |
| `merge_reviews` | A pending human decision when two contacts might be the same person, or when a merge would collide two `User` accounts onto one contact (`reason="dual_lms_accounts"`, 2026-08-10+). Never auto-resolved. |
| `contact_role_events` | One role gained/lost by a contact, timestamped, with source + who did it. |

## Key flows

**Intake matching** (`services/spine/identity.py::evaluate()` → `resolve_or_create_contact()`,
called from every intake path — public registration form, desk registration, bulk import): exact
email match → `EXACT_MERGE`, attach directly, no human involved, gap-fill any new phone/email/
`date_of_birth`/`grade`/`nationality`/`organization_name` onto the existing contact (never
overwrite what's already there). Phone match with no email match → `REVIEW`: create the new
contact anyway (the public flow never blocks on ambiguity) and queue a `merge_reviews` row for a
human. No match at all → `NEW`, create fresh. `resolve_or_create_contact()` is the **only** place
that writes `identity_aliases` from an intake flow — `evaluate()` only ever reads them, so skipping
this on a new intake path means every later submission with the same phone/email comes back `NEW`
forever.

**Role sync on a staff account edit** (`services/user.py::update_user`, current since the
correction above): when a `PATCH` actually changes `roles` (guarded by
`update_data.get("roles") is not None`, not just `"roles" in update_data`, so `UserSelfUpdate`'s
`roles`-less shape can never be misread as "clear every role"), it (1) calls `ensure_user_contact`
to get-or-create the linked contact, (2) `record_role_diff` logs the raw role strings that were
added/removed, (3) if `instructor` was newly granted directly (not via applicant approval), backfills
`InstructorProfile.instructor_since` if it's missing, and (4) unions
`contact_roles_for_user(user)`'s mapped roles onto `contact.contact_roles` — **additive only,
never removes** a role a human set directly on the contact with no corresponding user role (e.g.
`alumnus`). No separate history event for step 4 — step 2 already narrates why.

**Merging two contacts** (`services/spine/identity.py::merge_contacts`, called from an
`EXACT_MERGE` auto-match or a human resolving a `merge_reviews` row): walks `MERGE_FK_REGISTRY`
(the list of every `(table, column)` FK to `contacts.id`), repointing each loser's row to the
winner. Most entries go row-by-row inside a SAVEPOINT (`db.begin_nested()`) — a conflict (the
winner already has an equivalent row under a unique constraint that includes the FK column) drops
the loser's duplicate instead of erroring. **`(users, contact_id)` is special-cased** (since the
UNIQUE constraint landed, see the correction above): if both winner and loser hold a real login,
the generic "drop the duplicate" behavior would silently delete somebody's account, so instead it
files a `dual_lms_accounts` `merge_reviews` row and leaves both accounts untouched — that's a human
decision (whose login survives) this function deliberately refuses to make automatically. After the
FK sweep: scalar fields gap-fill onto the winner (never overwrite), `contact_roles`/
`secondary_phones` union, the loser gets `merged_into_id` set (never deleted).

## Gotchas

- **The contact_id-first, email-fallback resolution pattern for mapping a `Registration`/`Contact`
  to its `User` account is real, load-bearing, and inconsistently applied across this codebase —
  know both the correct shape and where it's skipped.** Reference implementations:
  `services/lms/students.py::_registered_cohort_users` and
  `routers/sessions/cohorts.py::list_registrations`'s `last_login_at` column both (1) collect the
  `contact_id`s in play, (2) resolve as many as possible via `User.contact_id.in_(...)`, then (3)
  for whatever's still unresolved, look up the `Contact`'s email and match it against
  `User.email.in_(...)`. This exists because a real slice of `User` rows have `contact_id` NULL —
  `users.contact_id` being `UNIQUE` (2026-08-10+) only means *no two users share one contact*, it
  says nothing about how many users have none at all — and those accounts are only findable by
  email. **Three newer call sites skip the fallback and do a plain `User.contact_id == contact_id`
  lookup**: this domain's own `routers/spine/contacts.py::reset_lms_password` (~line 318-320:
  `select(User).where(User.contact_id == contact_id)`, no email fallback), plus
  `routers/sessions/cohorts.py::resend_onboarding_email` and `::get_set_password_link` — see
  `HANDOFF_SESSIONS.md`'s Gotchas for those two. Each 404s with "no linked account" for a
  genuinely-existing account whose `contact_id` just never got backfilled. **`services/lms/ops_integration.py::get_or_create_student_account`
  is a third, more conservative variant, not a bug**: on no `contact_id` match it checks whether
  the contact's email is already on a *different* account and, if so, deliberately does **not**
  link or return that account — it logs a warning and returns `(None, False)` rather than silently
  adopting an unrelated pre-existing login. That's a correct, intentional refusal-to-guess, not the
  same gap as the plain-lookup call sites above.
- **Two circular foreign keys, both hand-fixed post-autogenerate.** `contacts.organization_id` →
  `organizations` is a normal FK; `organizations.primary_contact_id` → `contacts` is added via a
  separate `create_foreign_key()` call after both tables exist. Same pattern for
  `contacts.source_touchpoint_id` → `touchpoints`. **Alembic's autogenerate does not handle this
  correctly on its own** — check the emitted order by hand if you ever regenerate a migration
  touching these columns.
- **`MERGE_FK_REGISTRY`** (`backend/app/services/spine/identity.py`) is a list of `(table, column)`
  pairs, one per contact-referencing FK. **Any new column that FKs to `contacts.id` must be added
  to this list in the same migration that creates it**, or a merge silently leaves stale
  references. `merge_reviews.candidate_a/candidate_b` are deliberately excluded (audit trail, not
  live references). `(users, contact_id)` has its own special-case branch in `merge_contacts` —
  see Key flows — don't assume every registry entry gets the same generic handling.
- **Column widths**: `identity_aliases.alias_type` is `VARCHAR(32)`, not `VARCHAR(24)` —
  `legacy_inventory_instructor` alone is 27 characters.
- **Nothing populates `identity_aliases` automatically.** `find_candidates`/`evaluate` only *read*
  it. Any new intake path must call `resolve_or_create_contact` (or `ensure_alias` directly) or
  `evaluate()` returns `NEW` for every submission, forever.
- **A minimal pytest harness exists** (`backend/pytest.ini`, `backend/tests/conftest.py`) against a
  dedicated `spacepoint_test` database. If you add async fixtures: the engine must be created
  *inside* a fixture, not at module-import time, and `pytest.ini` needs both
  `asyncio_default_fixture_loop_scope = session` **and** `asyncio_default_test_loop_scope = session`.
- **No `citext` extension.** `contacts.email` is a plain `String` — case-insensitive matching is
  the application layer's job (`normalize_email`), not the DB's.
- **`identity.py`'s alias-writing helper is public: `ensure_alias(db, contact_id, alias_type, value)`.**
  Idempotent — no-ops if the (type, value) pair is already recorded, never reassigns an existing
  alias's owner.
- **`routers/spine/contacts.py`/`merge_reviews.py` mount at `/spine`**, not `/api/spine` — this app
  has no `/api` prefix anywhere.
- **`/operations/contacts` and `/operations/merge-reviews` have no sidebar nav entry.** Verified by
  grepping every `Link`/`navigate` target in `frontend/src` for those two paths: the only hits are
  the legacy `/admin/contacts`/`/admin/merge-reviews` redirect aliases in `router.tsx` (kept
  specifically so old bookmarks still land somewhere — see `HANDOFF_SESSIONS.md`'s matching note,
  which also covers `/operations/checkin`). Reaching either page today requires knowing the URL or
  following an old link. Flagged, not fixed, by this pass — see Open questions.
- **`backfill_user_contacts()` still exists and is still safe to re-run** (`scripts/backfill_user_contacts.py`)
  — a plain create for any never-linked user (no `evaluate()`/matching, since a never-backfilled
  user has no prior submission history to reconcile against), and its role-resync pass for
  already-linked users is unchanged. It is no longer the *only* place that resync happens, though
  — `update_user` does the live version now (see Key flows) — so don't assume a stale
  `contact_roles` value means the script hasn't run recently; it may just predate this fix.

## Open questions from this pass

- **Whether the missing sidebar entries for `/operations/contacts` and `/operations/merge-reviews`
  are an intentional "ops shouldn't casually browse this" decision or a leftover gap from the
  S6-2 route move** — no product decision either way was found in code comments or commit
  messages. Flagging rather than guessing; whoever owns the operations nav should confirm.
- **`services/instructor_assessment/`** touches `users`/staffing but not this domain's own tables
  directly — noted in `HANDOFF_SESSIONS.md` as an undocumented cross-domain dependency, not
  repeated here since it never reads/writes `contacts`.
