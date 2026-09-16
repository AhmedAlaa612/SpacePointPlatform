# Competition Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status: all three planned stages built** (team-scoped checklists, judging, registration import +
progression). First case is Ru'ya Space Race: SatKit Edition (September 2026). Built in stages,
each section below covering one — this doc grew with each one rather than describing a finished
domain up front.

A competition is deliberately **not** a new top-level entity — it's the existing `Program`/
`Cohort`/`LmsProgram` machinery (see [`HANDOFF_LMS.md`](./HANDOFF_LMS.md)) with a flag and
extensions layered on top: a competition Program has `program_type="competition"`, its checklist
items can be team-scoped instead of per-student, and it gains a judging domain (rubric, blind
per-judge scoring, a publish gate, a `judge` role) that reads that same shared checklist rather
than duplicating it. Everything else — courses, guides, cohort-scoped access, certificates — is
unchanged, reused as-is.

---

## 1. Stage 1 — `program_type="competition"` + team-scoped checklist items (2026-08-24)

### The shape

- **`program_type="competition"`** — a competition is a normal `Program`, just typed as one.
  `program_type` was already a plain `String(24)` (not a DB enum, `workshop|course|info_session`
  by convention only), so this needed no schema change at all. `Program.is_competition` (see
  `models/sessions/program.py`) is a read-only Python property over it — `program.program_type ==
  "competition"` — kept so the many `program.is_competition` call sites across
  `services/competitions/` read the same as before. (An earlier version of this stage added a
  separate `programs.is_competition` boolean column; operator feedback was that a competition
  should just be a program *type*, not a second flag alongside one — that column never shipped
  past this repo's own review.)
- **`lms_program_items.scope`** (`individual|team`, default `individual`) — every item that
  existed before this column stays `individual`, unchanged. `team` is for a competition's
  link-only deliverables (poster, presentation video, Tinkercad circuit, CAD design, hosted
  dashboard — Ru'ya's actual Week 1 qualifier list) where the whole team shares one submission
  instead of each student having their own. Restricted at authoring time
  (`validate_item_payload`, `services/lms/program.py`) to `submission|external_link|manual` —
  `course`/`mission_run`/`article` can never be team-scoped, because each teammate's own course
  progress and Design mission attempt are genuinely personal, not something one submission speaks
  for. (A team collaboratively working one shared Design/Madar mission attempt is a real future
  ask but a materially bigger change — `MissionAttempt` already has a `team_id` column and
  `assign_mission_run` would need to accept a team instead of a user — explicitly not part of
  this stage.)
- **`lms_program_team_item_progress`** *(new table)* — the team-scoped twin of
  `lms_program_item_progress`, same shape, keyed by `(item_id, team_id)` instead of `(item_id,
  assignment_id)`. Every student assigned a competition program still gets an individual
  `LmsProgramItemProgress` row for every item, team-scoped included (`assign_lms_program` is
  unchanged) — that row's own `status`/`submitted_url` are simply never read or written once an
  item is team-scoped. This keeps the "materialized once, at assignment time" invariant
  (`services/lms/program.py`'s module docstring) intact for every item type without exception; a
  team-scoped item's real state lives exclusively in the new table, resolved by
  `checklist_item_write_target()`.
- **`Team`/`TeamMember` (`learner_teams`, 2026-08-17)** — not new. Its own docstring called this
  moment out explicitly ("Competition needs teams too"); this is the first thing outside Missions
  to actually reference it. `team_for_cohort_member(db, cohort_id, user_id)` is the one place that
  resolves "which team is this student on, for this specific cohort" — a student can hold teams
  across several cohorts/programs, never more than one per cohort in practice (not DB-enforced,
  matching `Team`'s own `.first()`-style lookup elsewhere).

### How a team-scoped item resolves

- **Read** (`get_student_checklist`) — for each `scope="team"` item, overlay the caller's team's
  row (`lms_program_team_item_progress`) onto the response in place of the individual row's own
  (always-pending) state. If the student isn't on a team for that cohort, the item just reads as
  untouched (`pending`, no link) rather than erroring — a checklist should never 500 because
  roster assignment hasn't happened yet.
- **Write** (`POST .../complete`, `POST .../submit`) — `checklist_item_write_target()` is the one
  branch point: `individual` items write straight to the caller's own row, exactly as before this
  stage; `team` items resolve (and lazily create, on first write) the shared team row and write
  there instead — any of the 2–3 members calling either endpoint lands on the same row, and a
  later member's edit **overrides** an earlier one outright, on purpose (that's the actual ask,
  not a race condition to fix). Raises 403 if the caller isn't on a team for that cohort.
  `updated_by_user_id`/`updated_at` on the team row are what the checklist displays as "last
  updated by [name]" instead of the individual table's implicit "you".

### Frontend

- `LearnChecklist.tsx` — a `scope="team"` row carries a small "Team" pill next to its type label,
  and its submission block shows "Last updated by [name]" instead of assuming "you" submitted it.
  No other behavior differs — same complete/submit actions, same endpoints.
- `LearnLanding.tsx` — a "My Team" card per cohort-scoped team (self-formed, no-cohort teams from
  the public mission catalog don't get one — there's no checklist to open), linking straight into
  that team's one shared checklist (`/learn/checklists/$assignmentId`) via the matching
  `LmsProgramAssignmentSummary.cohort_id`. This is genuinely the same checklist page every other
  program already uses, not a second "team" surface — see the wireframe note below for why that
  distinction got called out explicitly.

### What's still not built (later stages, tracked in the implementation plan, not here yet)

- Registration import (Excel/CSV → bulk `User`/`Registration`/`Team` creation).
- Progression: the ops "confirm Top 10 → move to Finalists" action + congrats email.

A wireframe set for the ops/judge/student/team views (all four, including stages not yet built)
exists as a Claude Design canvas from the planning pass — ask whoever ran that session for the
link if you need it; it isn't checked into the repo.

---

## 2. Stage 2 — Judging (2026-08-24)

### The shape

Five new tables under `app/models/competitions/judging.py`, all cascading off `programs`/`cohorts`/
`users`/`learner_teams` rather than introducing a parallel identity concept:

- **`competition_rubrics`** / **`competition_rubric_criteria`** — program-scoped (not cohort-scoped:
  the same criteria carry across a competition's stages unless a future need splits them), authored
  by ops rather than hardcoded. `upsert_rubric()` (`services/competitions/judging.py`) is a
  declarative full-sync, same "one call rewrites everything" idiom
  `LmsProgramItemReorderIn`/`reorder_program_items` already use — a criterion whose `key` isn't in
  the payload gets deleted, an existing `key` gets updated in place, a new one gets inserted.
- **`competition_scores`** — one row per `(rubric, team, judge, cohort)`, upserted by
  `submit_score()`. Blindness (a judge never sees another judge's score, even after publish — only
  the aggregate) is enforced by which endpoints expose this table, not by a schema flag: nothing in
  `services/competitions/judging.py` or its routers ever returns one judge's `criterion_scores` to a
  different judge. 409s once the cohort is published.
- **`competition_result_publications`** — the blind-until-published gate, one row per cohort;
  row-exists *is* published, `unpublish()` just deletes it. Publishing closes scoring for every
  judge on that cohort; unpublishing reopens it.
- **`competition_judges`** — a judge's cohort assignment, exact shape of `SessionInstructor`: a
  judge assigned to the Qualifier cohort has no row for Finalists and can't see it.
- **`judge` role** *(new `UserRole` enum value + Postgres `user_role` type value)* — a temporary,
  cohort-scoped account with zero ops access. `require_judge`
  (`core/dependencies.py`) is the role-only gate; `require_judge_cohort_access`/`judge_cohort_ids`
  (`services/competitions/judges.py`) is the per-cohort scope, same split
  `require_instructor_missions`/`cohort_access.py` use for instructors — deliberately **no staff
  bypass** here, since staff reach the same data through the separate `/competitions/admin/*`
  surface, never through the judge one. `invite_judge()` reuses the exact find-or-create +
  set-password-email flow `services/lms/ops_integration.py` already has for student accounts
  (`get_or_create_student_account`/`send_set_password_email`) rather than duplicating it.
  "Temporary" here means the `CompetitionJudge` cohort-assignment is temporary — `revoke_judge`
  only ever deletes that row, never the `judge` role or the account itself, so a revoked judge
  can still be found by email and re-invited later. Ending a judge's access for good is a plain
  admin action, same as any other role: deactivate the account (`PATCH /admin/users/{id}`,
  `status="inactive"` — added 2026-08-26, `Users.tsx`'s new deactivate/reactivate toggle) blocks
  login/every request immediately without touching their `CompetitionScore` rows. `delete_user`
  refuses outright once a judge has actually scored anything, since `CompetitionScore.judge_user_id`
  CASCADEs on delete and would silently erase those teams' evaluations — deactivate is the only
  safe way to retire a judge who's judged.

**Caught mid-build, worth flagging**: the migration added `judge` to the Postgres enum, but nothing
had added it to the Python-side `UserRole` enum (`app/models/enums.py`) — SQLAlchemy validates an
`ARRAY(ENUM(UserRole, ...))` column against the Python enum's members, not the DB's, so every
`User.roles` read on a judge account raised `LookupError` even though the DB was fine. Fixed
alongside this stage; if a future role migration only touches the DB enum, it will hit the exact
same failure.

Score aggregation (leaderboard, `leaderboard()`): a team's score is the **average of every judge's
`total_points`** for that cohort — not specified verbatim anywhere in the source docs, called as a
reasonable default and flagged as such. `export_top()` is just `leaderboard()[:limit]`; there's no
separate "frozen at export time" concept.

### API surface

- **`/competitions/admin/*`** (`require_lms_content` — operations/facilitator/admin, same authoring
  gate `/lms/admin` uses): rubric GET/PUT per program, judges GET/POST/DELETE per cohort,
  leaderboard/export-top20/publish/unpublish per cohort.
- **`/competitions/judge/*`** (`require_judge`): `GET /cohorts` (this judge's own cohort picker —
  which cohorts they hold a `CompetitionJudge` row for), `GET /teams?cohort_id=` (roster + whether
  *this* judge has already scored each team), `GET /teams/{id}` (submissions +
  rubric + this judge's own score, via a new `team_submission_items()` in
  `services/lms/program.py` that resolves a team's cohort → effective checklist items filtered to
  `scope="team"`, joined against `LmsProgramTeamItemProgress` — the judge view reads the *same*
  shared checklist a teammate's Learn page writes, not a judging-only copy), `PUT
  /teams/{id}/score`.
- Mounted at its own top-level `/competitions` prefix (`app/routers/competitions/`, registered in
  `main.py`), not nested under `/lms/` or `/missions/` — judging is neither checklist authoring nor
  a mission attempt, and deliberately not the plan doc's literal bare `/admin/...` paths either,
  to avoid colliding with the pre-existing generic `/admin/*` user-management router.

### Frontend

- **Ops**: `Programs.tsx`'s existing program "Type" dropdown gained a `Competition` option —
  no separate toggle. `ProgramOut` exposes `is_competition` read-only, derived from
  `program_type`; `ProgramCreate`/`ProgramUpdate` don't carry it at all, since `program_type` is
  the only lever. `CohortDetail.tsx` shows a "Judging" header action when the cohort's
  program is a competition (`CohortOut` gained a `program_is_competition` convenience-join field,
  same pattern `program_name` already uses), linking to the new `CompetitionJudging.tsx`
  (`/operations/cohorts/$cohortId/judging`) — Rubric / Judges / Results tabs.
- **Judge**: a new top-level surface at `/judge/*`, same "own separate area, not a portal role"
  treatment `/learn` gives students (`roleHomePath`, `Sidebar.tsx`) — `JudgeTeams.tsx` (cohort
  picker + team roster with a scored/not-scored mark) and `JudgeTeamDetail.tsx` (submissions +
  scoring form). Unlike `/learn`, judges use the ordinary portal shell (`AppShell`/`Sidebar`) rather
  than a standalone shell — nested under `authLayoutRoute`, gated by `active_role === "judge"`.
- `judge` added to `types/shared.ts`'s `Role` union, `ROLE_LABEL`, and `roleHomePath()`
  (→ `/judge`), and to `Users.tsx`'s `roleBadgeColor` map (a `Record<Role, ...>` — TypeScript's
  exhaustiveness check is what caught this one).
- The judge/student account invite email (`send_set_password_email`,
  `services/lms/ops_integration.py`) was hardcoded to link to `/learn/set-password` for every role —
  harmless for students, wrong for everyone else (a judge or ops-invited instructor would land on
  the LMS-branded page and its "back to login" would send them to `/learn/login`, not the portal).
  `LearnSetPassword.tsx`'s own docstring already documented the intended fix (it's mounted at both
  `/learn/set-password` and `/set-password` for exactly this reason) — the email just never used the
  second mount. Now role-aware: `/learn/set-password` only for `student`, `/set-password` otherwise.

---

## 3. Stage 3 — Registration import + progression (2026-08-24)

Registration/filtering itself stays in Google Forms per the boss thread — the platform's job
starts once ops has a final roster to import, and ends with an explicit, never-automatic action
that moves a team to the next stage.

### Registration import (`services/competitions/registration_import.py`)

Deliberately lighter than `services/sessions/importer.py`'s general bulk sheet importer: one pass,
immediately committed, no dry-run/`ImportBatch` two-phase flow, no contact-merge review queue — a
competition roster is small and already hand-curated by ops before it gets here, so that extra
machinery buys nothing. `parse_registration_sheet()` reads an Excel or CSV export — `.csv` handled
via Python's `csv` module (utf-8-sig, to eat the BOM Excel/Sheets stamp on a CSV export), `.xlsx`
via openpyxl, chosen by the uploaded filename's extension; a genuinely unreadable file 422s with a
clear message instead of the raw `zipfile.BadZipFile` 500 that shipped at first. `_find_header_row`
scans the first 10 rows for one covering every required column (`team_name`/`member_name`/`email`;
optional `phone`/`school`) — same "tolerate a title/banner row above the header" idiom
`services/sessions/importer.py` already uses — since ops's real tracker sheets open with a title
row and a stage-description row before the actual header on row 3. `_HEADER_ALIASES` maps ops's
actual selection-tracker column labels — "Student Name", "School / University" — onto those
canonical names. Both gaps (row offset, then header labels, then CSV support) surfaced only once
testing hit the real exported sheet, added 2026-08-26.
`import_registrations()` reuses the exact same identity/registration/LMS primitives the desk and
the general importer already use per row —`resolve_or_create_contact` → `register()` →
`sync_registration_lms()` (find-or-create the student account, assign the cohort's LMS checklist,
email the set-password link) — then finds-or-creates a same-named `Team` in that cohort and adds
the member. Idempotent on `(contact, cohort)`: re-running the exact same sheet twice reports every
row `matched`, not duplicated, since `resolve_or_create_contact` and the pre-existing-registration
check are themselves idempotent.

`POST /competitions/admin/cohorts/{cohort_id}/registration-import` (multipart file upload) returns
a per-row report (`created|matched|error` + reason) for the ops UI to show — a bad row errors
without failing the rest of the batch.

### Progression (`services/competitions/progression.py`)

Never automatic off a score threshold — exporting the Top 20 for external NSA review and deciding
the real Top 10 happens off platform; `advance_teams()` is the one explicit ops action that moves
anyone, called once ops has that final list. Advancing a team means the same pair advancing an
individual student between cohorts already means elsewhere in this codebase — `register()` +
`assign_lms_program()` per member (idempotent, pre-existing-registration checked first) — plus a
same-named `Team` in the target cohort, since `Team.cohort_id` is fixed at creation and a Qualifier
team can't just be reused for Finalists. Refuses (400) a team that isn't actually in the stated
source cohort — a safety check against advancing the wrong roster. Each advanced member gets a
congrats email (`try_send_email`, same shared primitive every other transactional email in this
codebase uses).

`POST /competitions/admin/cohorts/{cohort_id}/advance-teams` (body: `{team_ids, to_cohort_id}`) —
`cohort_id` in the path is the *source* cohort, validated against each team's actual `cohort_id`.

### Frontend

- **Roster tab** (`CompetitionJudging.tsx`, now the default tab) — file upload, per-row import
  report table.
- **Results tab** — a checkbox column on the leaderboard plus a "Advance to…" cohort picker
  (siblings of the current cohort's own program, via the already-existing `getCohortsApi
  (programId)`) and button, wired to `advance-teams`. This is deliberately the operator's own
  "Confirm Top 10 → move to Finalists" moment — selecting rows off the published leaderboard *is*
  the confirmation, nothing auto-selects the top N for them.

### What's still not built

Nothing tracked as outstanding — all three stages of the original implementation plan (team-scoped
checklists, judging, registration import + progression) are built. Anything past this is a new ask,
not a gap in this plan.

---

## 4. Boss feedback round (2026-08-24)

Three items from the boss after seeing the built domain — the first two below are real code
changes; the third and fourth just confirm existing design decisions with no code needed.

- **"Submitted at [timestamp] by [student X]" needed to actually be visible, not just tracked.**
  Two gaps, both fixed:
  - The judge team-detail view (`team_submission_items()`, `services/lms/program.py`) only
    returned `status`/`submitted_url` — never the `updated_at`/`updated_by_user_id` the team-progress
    table already stores. Added both (plus a batch name lookup, same pattern
    `get_student_checklist` already uses) to `CompetitionSubmissionItemOut`, surfaced on
    `JudgeTeamDetail.tsx`.
  - The bigger one, on the **student/team side**: `LearnChecklist.tsx`'s submission block —
    link input, "last updated by" caption, the works — was gated behind `status !== "done" &&
    status !== "awaiting_confirmation"`. The moment a submission item was marked done, the entire
    block vanished — no link, no submitter, no timestamp, nothing but a bare "Complete" badge. That's
    exactly the operator's stated worry ("teams worry which submission went through") and it wasn't
    a display nitpick, it was a real hole: a team-scoped item is *supposed* to be overridable by any
    teammate at any time (Stage 1's own design), and there was no way to even see what was currently
    submitted once done, let alone replace it. Fixed by decoupling three things that were wrongly
    tied to one status check: the submitted-link summary (now always visible whenever
    `submitted_url` is set, any status), the edit form (now always open, "Replace link" once
    something exists), and the "Mark as done" button (still hidden once done/awaiting — that part
    of the original gating was correct). The "Submitted [time] by [name]" caption itself is
    team-scope-only, matching what's actually tracked — individual items have no equivalent
    timestamp column, and the boss's ask was explicitly about the team view.
- **Judge scoring needed to survive being split across separate sessions.** `JudgeTeamDetail.tsx`
  now autosaves on every score/bonus change (1.2s debounce, restarts on each keystroke) instead of
  only writing on an explicit submit — `submit_score()` already upserts, so autosaving is just
  calling the same endpoint more often. A status line ("Saving…" / "Unsaved changes" / "Saved
  [time]") makes the background writes visible rather than silent; a "Save now" button stays for
  an immediate, non-debounced write. No backend change needed.
- **Pre/mid/post-session quizzes are Google Forms**, added as ordinary `external_link` checklist
  items — no new item type, no new mechanism. Confirmed with the boss, already exactly how the
  checklist model works.
- **The dashboard deliverable has no platform template** — teams build it themselves (vibecoded) and
  submit a link, same as poster/video/circuit/CAD. Ops gives guides, not a builder. Also already
  exactly how `scope="team"` + `submission`/`external_link` items work; no new mechanism needed.

---

## 5. Team analytics — the Analysis tab (2026-09-16)

Ops could list teams but never count them, and nothing showed team progress across a cohort at
all. Per-*student* checklist progress already had a home (`cohort_program_roster` →
`ProgressPanel`, the cohort's LMS > Progress tab, one expandable row per student); what nothing
surfaced was the other axis — how many teams there are, how far each has got, and which single
deliverable the cohort as a whole is stuck on.

Two pieces, both read-only:

- **Teams tab stat strip** — teams, students on teams, average team size, empty teams. Derived
  client-side from the team list `getCohortTeamsApi` already returns, so it costs no request.
  Member ids are deduped rather than summed: a student on two teams in one cohort isn't
  DB-prevented (see `models/team.py`), so summing `member_ids.length` would double-count them.
- **Analysis tab** (`CompetitionAnalysis.tsx`, 7th tab on the Judging page) — one payload from
  `GET /competitions/admin/cohorts/{id}/team-analytics`, backed by
  `services/competitions/analytics.py`. KPI row, a completion-rate bar per checklist item, a
  team-completion distribution, a 30-day activity chart, a sortable/exportable per-team table,
  and a needs-attention list.

### Where a "done" comes from

The one subtle part, and the reason the service has a long module docstring:

- `scope="team"` items (`submission`/`external_link`/`manual`/`team_setup`) —
  `lms_program_team_item_progress.status` is literal truth. Nothing auto-tracks these.
- `scope="individual"` items — the stored `lms_program_item_progress.status`, except `course`
  (reconciled via `batch_course_completion`, same rule `_course_item_done` applies) and `quiz`
  (a submitted `CohortQuizAttempt`, score irrelevant, same rule `_cohort_quiz_item_done`
  applies). Stored status for those two lags until someone opens the checklist; reconciling
  here means a bar never understates them. Both batch, which is why they're the two that get it.
- `mission_run` items (either scope) are **excluded from the completion bars** and reported in
  their own block off each run's shared `MissionAttempt.status`. Their real completion is
  per-design-step, resolved through a Design dashboard that costs a query cascade per attempt
  (`refresh_item_progress` → `_design_dashboard_for_attempt`) — a bar labelled "Build the
  CubeSat" sitting at a stale stored status would be worse than no bar.

`awaiting_confirmation` counts as **not done** everywhere, matching what the checklist shows the
student, but is reported as its own bucket: "everyone submitted and ops hasn't confirmed" and
"nobody submitted" are different problems with different fixes.

Each bar names its own `denominator` (`teams` or `students`) rather than leaving the frontend to
infer it from `scope`. The student denominator is *assigned* students, not registered ones — a
student registered but never assigned the checklist has no progress row for anything, and
counting them against every bar would read as the cohort failing rather than as an assignment
gap (which the KPI row reports separately, as "not on a team" / assigned counts).

### Performance

Set-based throughout — a fixed number of queries regardless of roster size, joined in Python.
Resolving each team on its own would walk straight into the N+1 shape `batch_course_completion`
exists to avoid (B11, then the 7B-1 progress grid); "every team × every checklist item" is
exactly the screen where it bites.

### Chart colours

A **status** encoding (done / awaiting confirmation / not submitted), not a categorical one, and
both themes are *selected* rather than auto-flipped — each pair validated against the surface it
actually renders on: light `#047857`/`#d97706` on white (CVD ΔE 11.0), dark `#199e70`/`#c98500`
on the dark card `#1A0F26` (CVD ΔE 8.4), all four clearing 3:1 contrast. "Not submitted" is a
neutral track, not a third hue — it's the unfilled remainder of the bar, not a series competing
for identity. Every bar carries a legend and a direct percentage label, so meaning never rests
on colour alone. Hex rather than theme tokens because a CSS var in an SVG `fill` doesn't resolve
reliably, same reason `instructors/admin/Overview.tsx` hardcodes its own.

### Not included

Judging/score analytics — the Results tab already owns scores, and duplicating them here would
mean a second place to reason about the blind-until-published gate. Cross-cohort (stage-over-
stage) comparison is likewise out: every progress view in this codebase is cohort-scoped, and a
Qualifier-vs-Finalists view is a different question from "how is this stage going".
