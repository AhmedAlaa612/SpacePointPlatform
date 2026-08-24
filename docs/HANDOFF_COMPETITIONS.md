# Competition Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status: in progress.** First case is Ru'ya Space Race: SatKit Edition (September 2026). Built
in stages, each landing as its own PR — this doc grows with each one rather than describing a
finished domain up front. If a section below says "not yet built," that's accurate, not a typo.

A competition is deliberately **not** a new top-level entity — it's the existing `Program`/
`Cohort`/`LmsProgram` machinery (see [`HANDOFF_LMS.md`](./HANDOFF_LMS.md)) with a flag and two
extensions layered on top: a competition Program has `is_competition=true`, its checklist items
can be team-scoped instead of per-student, and (in a later stage) it gains judging. Everything
else — courses, guides, cohort-scoped access, certificates — is unchanged, reused as-is.

---

## 1. Stage 1 — `Program.is_competition` + team-scoped checklist items (2026-08-24)

### The shape

- **`programs.is_competition`** (`Boolean`, default `false`) — a competition is a normal
  `Program`, just flagged. Deliberately a new column rather than overloading the existing
  `program_type` (`workshop|course|session`, a *format* axis): a competition isn't a 4th format,
  it's a behavioral flag layered on top of one.
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

- Judging: rubric, blind per-judge scores, publish/unpublish gate, `judge` role.
- Registration import (Excel/CSV → bulk `User`/`Registration`/`Team` creation).
- Progression: the ops "confirm Top 10 → move to Finalists" action + congrats email.
- Ops UI for any of the above (Rubric/Judges/Results tabs on `LmsProgramAdmin.tsx`).

A wireframe set for the ops/judge/student/team views (all four, including stages not yet built)
exists as a Claude Design canvas from the planning pass — ask whoever ran that session for the
link if you need it; it isn't checked into the repo.
