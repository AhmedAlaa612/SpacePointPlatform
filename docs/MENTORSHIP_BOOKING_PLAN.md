# Mentorship Booking — Plan (not built yet)

Back to [`HANDOFF.md`](./HANDOFF.md). This is a pre-build spec, same status as
`MISSIONS_INTERN_SPEC.md` — nothing described here exists in the schema or routers yet.

**Ask (verbatim, from the operator's boss):** an AdPlist-style flow inside the LMS — any portal
user can become a mentor (portfolio + available slots), students explore mentors and book a
slot, with notes.

---

## 1. Product shape

AdPlist's actual mechanic, reduced to what's relevant here:

1. Anyone eligible flips on a "mentor" toggle, fills a **portfolio** (headline, bio, topics/tags,
   links) and a **weekly availability rule** (not one-off slots hand-typed forever).
2. The system expands that rule into concrete, bookable time slots for the next N weeks.
3. A student browses/filters mentors by topic, opens a profile, picks an open slot, and **leaves
   a note** ("what I want to talk about") when booking.
4. The mentor sees the booking with the student's note, can accept/decline if approval is
   required, and after the call leaves their own **session notes**.
5. Both sides get reminders; either side can cancel within a policy window; a completed session
   can carry a rating.

Two concepts must not be conflated (this codebase already draws exactly this line elsewhere,
e.g. Missions "readiness vs. grant", LMS Programs "assignment vs. progress"):

- **Being a mentor** — an opt-in profile + availability, independent of `UserRole`.
- **Booking a session** — a transaction between one student and one mentor for one time slot.

## 2. Where this sits relative to existing domains

- **Not a new `UserRole`.** The ask is explicit: "any portal user could be a mentor." Roles
  gate *portal surfaces*; being a mentor is a *capability* a user opts into regardless of which
  of the 13 roles they already hold (instructor, intern, ambassador, ops, admin, …). Modeled as
  a `mentor_profiles` row keyed on `user_id`, same idiom as `instructor_profiles` — its mere
  existence (and `is_active`) is the "is this person a mentor" check, not a role list.
- **Who can book**: the ask says "students explore and book" — i.e. the `student` role, the LMS
  learner surface (`/learn`). This is intentionally narrower than "who can be a mentor": any
  portal user can list themselves, only `student` accounts book. (Open question in §9 if the
  boss actually wants portal-to-portal mentorship too — nothing here blocks widening it later,
  the booking model doesn't care about the booker's role.)
- **Lives beside the LMS, reuses its plumbing, isn't bolted onto `courses`/`missions`.** New
  top-level domain `mentorship` (own models/routers/services/schemas directories, mirroring
  every other domain in this repo), the same way Competitions was called out as "a `Program`
  with extra tables," not forced into an unrelated table. Reuses: `services/notification.py`
  for in-app pings, the ARQ worker (`app/workers/tasks/`) for reminder emails, `services/
  storage.py` if a portfolio photo is wanted (bucket `mentor-portfolios`), and the existing
  `require_lms_student` guard for the booking side.
- **Frontend split mirrors the existing `/learn` vs. portal split** (`HANDOFF_LMS.md` §1):
  - **Becoming/managing a mentor** happens in the normal portal shell (`AppShell`/`Sidebar`),
    reachable by any authenticated non-student account — a new "Mentorship" sidebar entry that
    shows for everyone (not role-gated on the frontend, since eligibility is "any portal user",
    but the page itself starts blank/opt-in until the user toggles on).
  - **Browsing and booking** happens on `/learn/mentorship` inside the existing student shell —
    same reasoning as every other student-facing surface in `HANDOFF_LMS.md`.
  - `admin`/`operations` get a light oversight list (who's a mentor, all bookings, deactivate a
    mentor) — not a full moderation queue for v1.

## 3. Data model

New tables, `backend/app/models/mentorship/`:

```
mentor_profiles
  user_id            PK, FK users.id ON DELETE CASCADE   -- one profile per account
  headline           String                               -- "Flight software engineer @ X"
  bio                Text
  expertise_tags     ARRAY(String) or a join table (see note below)
  links              JSONB          -- {linkedin, github, website, ...}, small + free-form
  photo_url          String, nullable                     -- via services/storage.py
  timezone           String (IANA, e.g. "Asia/Dubai")      -- mentor's own tz, availability is authored in this
  session_length_minutes  Integer, default 30              -- v1: one fixed length per mentor
  meeting_link       String, nullable                      -- their standing Meet/Zoom/Teams link
  booking_notice_hours    Integer, default 24              -- can't book inside this window
  cancellation_notice_hours  Integer, default 12
  requires_approval  Boolean, default false                -- false = auto-confirm (AdPlist default)
  is_active          Boolean, default true                 -- pause without deleting history
  created_at / updated_at

mentor_availability_rules        -- the weekly recurring pattern, not concrete slots
  id                 PK
  mentor_user_id     FK mentor_profiles.user_id ON DELETE CASCADE
  weekday            Integer 0-6
  start_time         Time (naive, interpreted in mentor_profiles.timezone)
  end_time           Time
  is_active          Boolean, default true                 -- turn a weekday off without deleting it
  created_at / updated_at

mentor_availability_exceptions   -- one-off "I'm out this day" / "I'm free this extra day"
  id                 PK
  mentor_user_id     FK
  date               Date
  kind               Enum(blocked, added)
  start_time / end_time   Time, nullable (whole day if null, only for "blocked")
  created_at

mentorship_bookings
  id                 PK
  mentor_user_id     FK users.id ON DELETE RESTRICT   -- keep booking history if a mentor account is later removed from the role, not silently orphaned
  student_user_id    FK users.id ON DELETE RESTRICT
  starts_at          DateTime(timezone=True)          -- always stored UTC, resolved from the rule + mentor tz at slot-generation time
  ends_at            DateTime(timezone=True)
  status             Enum(pending, confirmed, cancelled, completed, no_show)
  student_note       Text                              -- "what I want to talk about", required at booking
  mentor_notes       Text, nullable                    -- filled after the call
  meeting_link       String, nullable                  -- snapshot of the mentor's link at booking time
  cancelled_by       FK users.id, nullable
  cancellation_reason  Text, nullable
  rating             Integer 1-5, nullable             -- student-submitted, post-completion
  rating_comment     Text, nullable
  reminder_sent_at   DateTime, nullable
  created_at / updated_at
  UNIQUE(mentor_user_id, starts_at)   -- one booking per mentor per slot start, the same
                                       -- double-booking guard `cohorts`/`registrations`
                                       -- already use elsewhere in this codebase
```

Notes on shape, matched against conventions already in this repo (`HANDOFF.md` §8):

- **Expertise tags**: start with `ARRAY(String)` on the profile plus a simple `GET /mentorship/
  tags/popular` for autocomplete, not a normalized tag table with a join — no cross-domain
  reporting need for it yet (same "don't build a table nobody queries" judgment call as
  `BulkGrantIn`'s docstring in `HANDOFF_LMS.md` §13). Revisit only if search/filter performance
  or admin tag-merging becomes a real ask.
- **No stored "slots" table.** Concrete bookable slots are *computed* on read (rule × exceptions
  × existing bookings × notice window), the same way this codebase already treats "readiness" in
  the curriculum DAG as computed, never stored. Storing generated slots would need a cleanup job
  and a way to keep them in sync with rule edits — pure downside for a fixed-length-slot v1.
  Only reconsider this if mentors ever get variable-length or multi-mentor group slots.
- **Booking rows FK to `users.id`, not to a `contacts.id` or a role-specific profile table** — a
  booking involves two portal accounts, and neither `mentor_profiles` deletion nor role changes
  should be able to orphan booking history (hence `ON DELETE RESTRICT`, matching
  `attendance_records.recorded_by_user_id`'s existing precedent in `HANDOFF_SESSIONS.md`).
- **No `contacts.id` FK anywhere in this domain** → nothing to add to `MERGE_FK_REGISTRY`. Worth
  double-checking at implementation time in case a "public, no-login mentor request" surface
  gets added later (it isn't part of this ask).
- **Timezone handling is the single riskiest correctness detail.** Store the rule's `start_time`/
  `end_time` as naive `Time` + the mentor's own IANA `timezone` string (never store the rule
  pre-converted to UTC — DST shifts would silently drift it). Convert to UTC only at
  slot-generation time, using the *current* wall-clock rule for future dates. `mentorship_
  bookings.starts_at`/`ends_at` are the one place UTC is stored, because a confirmed booking must
  never move if the mentor's DST rules change later.

## 4. Booking lifecycle & rules

```
pending ──(mentor accepts, if requires_approval)──► confirmed ──(time passes)──► completed
   │                                                    │
   └──(mentor declines / either side cancels)──► cancelled            (no-show marked by either side)
```

- **Default is auto-confirm** (`requires_approval=false`) — matches AdPlist's actual default and
  is dramatically simpler to ship first; approval-required is a per-mentor opt-in, not two
  separate systems.
- **Booking a slot**: `POST /mentorship/mentors/{user_id}/bookings` — server re-validates the
  slot is still open (re-derives available slots server-side, never trusts a client-supplied
  "this slot is free," same posture as `register()`'s capacity check in `HANDOFF_SESSIONS.md`),
  inserts inside the existing per-row-SAVEPOINT pattern this codebase already uses for unique-
  constraint races (`HANDOFF_SESSIONS.md` "duplicate-registration handling" gotcha) — the
  `UNIQUE(mentor_user_id, starts_at)` index is the real backstop against two students racing the
  same slot.
- **Cancellation**: either side can cancel outside `cancellation_notice_hours`; inside that
  window, only an ops/admin override can. Cancelling frees the slot immediately (nothing to
  clean up, since slots are computed, not stored).
- **Reminders**: an ARQ job (new `app/workers/tasks/mentorship.py`, registered in
  `WorkerSettings.functions` — same pattern as every other scheduled email in this repo) sends a
  reminder ~24h and ~1h before `starts_at`; `reminder_sent_at` prevents double-send exactly like
  `ticket_sent_at` does for registrations. Degrades the same way `issue_ticket()` does when SMTP
  isn't configured — never raises, never blocks the booking.
- **Marking completed / no-show**: a scheduled sweep (same worker) flips `confirmed` bookings
  whose `ends_at` has passed to `completed` by default; either side can instead mark `no_show`
  up to 48h after, which suppresses the rating prompt.
- **Notes, the actual ask's "with notes" part**: `student_note` is required input on the booking
  call itself (not editable after, to keep it an honest record of intent — mirrors how `Mission
  Attempt.payload["override"]`'s decision fields are append-only for audit purposes). `mentor_
  notes` is a separate field the mentor can write/edit any time after the session starts, visible
  only to the mentor and staff — never to the student, unless a later phase explicitly asks for
  shared notes (that's a real product decision, don't default to shared).

## 5. API surface (`/mentorship/*`, mirrors the rest of this backend — no `/api` prefix)

**Mentor self-service** (any authenticated account, `require_lms_content`/role-list-free — the
check is just "is there a `mentor_profiles` row for `current_user.id`, or are they creating one"):

- `GET/PUT /mentorship/me/profile` — create/edit portfolio, toggle `is_active`.
- `GET/PUT /mentorship/me/availability` — CRUD the weekly rules + exceptions.
- `GET /mentorship/me/bookings?status=` — the mentor's own booking queue.
- `POST /mentorship/me/bookings/{id}/accept` / `/decline` (only meaningful if `requires_approval`).
- `POST /mentorship/me/bookings/{id}/cancel`.
- `PUT /mentorship/me/bookings/{id}/notes` — mentor session notes.
- `POST /mentorship/me/bookings/{id}/no-show`.

**Student-facing** (`require_lms_student`, under `/mentorship/` not `/lms/` — separate domain,
same split Competitions kept from LMS Programs):

- `GET /mentorship/mentors?tag=&q=` — browse/search, only `is_active=true` profiles.
- `GET /mentorship/mentors/{user_id}` — profile + computed open slots for the next N weeks.
- `POST /mentorship/mentors/{user_id}/bookings` — book a slot + `student_note`.
- `GET /mentorship/me/student-bookings` — "My Sessions" (upcoming/past).
- `POST /mentorship/bookings/{id}/cancel`.
- `POST /mentorship/bookings/{id}/rating` — only once, only after `completed`.

**Admin/ops oversight** (`require_operations`):

- `GET /mentorship/admin/mentors` — every profile, active or paused, for visibility.
- `PATCH /mentorship/admin/mentors/{user_id}` — force-deactivate a mentor (abuse/complaint).
- `GET /mentorship/admin/bookings` — full ledger, filterable.

## 6. Frontend

**Portal side** (`frontend/src/pages/mentorship/`, normal `AppShell`):

- `MentorshipProfile.tsx` — "Become a mentor" empty state → portfolio form → availability editor
  (a simple weekly grid, click-and-drag time ranges, same interaction shape as most calendar-
  picker components rather than inventing a new one) once opted in.
- `MentorshipBookings.tsx` — the mentor's upcoming/past sessions, notes, accept/decline if
  approval is required.
- New `Sidebar.tsx` entry, visible for every non-student portal role (`mk("Mentorship", "/
  mentorship")` in every role's nav block — this is the one nav item in the whole app that isn't
  role-scoped, since eligibility is deliberately role-agnostic).

**Student side** (`frontend/src/pages/learn/`, `LearnShell`):

- `LearnMentors.tsx` — browse/filter grid of mentor cards (photo, headline, tags, next available
  slot) — `/learn/mentorship`.
- `LearnMentorProfile.tsx` — full portfolio + a slot picker (grouped by day, mentor's slots shown
  converted to the *student's* browser timezone — display-only conversion, storage stays UTC) +
  the note textbox on booking.
- `LearnMySessions.tsx` — booked sessions, cancel action, rating prompt once completed.
- Add "Mentorship" to `LearnNav.tsx`'s tab bar.

## 7. What this deliberately does NOT include in v1

Flagged explicitly so nobody assumes it's covered by "just like AdPlist":

- **No in-app video calling.** Mentor supplies their own external meeting link (Meet/Zoom/
  Teams), same posture this codebase already took for the Design mission's poster tool
  ("link-only, a real editor was explicitly deferred" — `HANDOFF_LMS.md` §4). Revisit only if
  link-only proves insufficient.
- **No payments.** All mentorship sessions are free in v1 — the ask doesn't mention pricing, and
  bolting Stripe onto this before the core loop is validated would be premature (compare: paid
  courses took a dedicated phase on top of an already-working free enrollment flow).
- **No calendar sync (Google/Outlook OAuth).** Reminders are in-app + email only for v1. An
  ICS attachment on the confirmation email is cheap and worth including (this repo already
  generates PDFs/QR codes via `services/documents/`; an ICS is a few lines of `icalendar` and no
  new dependency category) — a full two-way calendar sync is a separate, much larger project.
- **No group/panel sessions.** One mentor, one student, one slot — matches the ask literally
  ("students explore and book" reads singular-transaction, not cohort-style).
- **No public/anonymous browsing.** Both sides need a portal account, consistent with every
  other domain in this codebase requiring auth (`/public/*` is deliberately narrow — registration
  forms and the ticket page only).

## 8. Build sequencing (small, reviewable PRs — matches how every other domain here shipped)

1. **Schema + mentor self-service** — `mentor_profiles`, `mentor_availability_rules`,
   `mentor_availability_exceptions`; profile CRUD; availability CRUD; slot-computation service
   function with unit tests covering DST edges and exceptions. No booking yet.
2. **Booking core** — `mentorship_bookings` table; book/cancel/list endpoints; the
   SAVEPOINT-guarded race-safe insert; student-facing browse/profile/slot-picker pages.
3. **Notes + lifecycle** — mentor notes, accept/decline for `requires_approval` mentors,
   completed/no-show sweep job, rating.
4. **Notifications** — in-app via `services/notification.py`, reminder emails via ARQ,
   ICS attachment.
5. **Admin oversight** — the light ops list/deactivate screen.
6. **Polish** — search/filter UX, empty states, mentor pause ("on vacation") banner.

Each step is independently shippable and testable (`pytest` from `backend/`, Redis-free per
`HANDOFF.md` §8 convention 9 — only step 4's reminder-enqueue test needs `arq_client`).

## 9. Open questions for the boss (need an answer before or during step 2/3, not step 1)

1. **Who can book** — students only (as literally asked), or eventually staff-to-staff
   mentorship too? Doesn't change the schema, only the router's role guard.
2. **Approval-required vs. always-auto-confirm** — is per-mentor choice enough, or does ops want
   a platform-wide switch (e.g. require approval for anyone below some trust bar)?
3. **Rating visibility** — shown publicly on the mentor's card (AdPlist does this), or
   private/ops-only for v1?
4. **Session length** — fixed per mentor (this plan's default) or does a mentor need to offer
   multiple lengths (15 vs 30 vs 60 min)? Changes `mentor_profiles.session_length_minutes` into
   a small per-length table if yes — worth deciding before step 1's migration, not after.
5. **Any cap on how many sessions one student can book with the same mentor** (AdPlist limits
   repeat bookings per mentor per period to spread access) — not in scope unless asked.
6. **Does a mentor need admin approval to go live**, or is opting in itself sufficient (with
   ops able to deactivate after the fact, as this plan assumes)?

---

*Status: plan only — no migration, model, router, or page in this list exists yet. Follow the
build sequencing in §8 once approved; check the open questions in §9 before starting step 3.*
