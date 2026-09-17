# LMS / Missions / Games Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status: LIVE in production** (`portal.spacepoint.ae/learn`, staff-side at `/lms-authoring`).
This domain didn't exist when `HANDOFF.md` was last written top-to-bottom — it's grown into
one of the largest surfaces in the codebase (courses, missions, live quiz games, a real
component catalog, student accounts) with no map of its own until now. If you're here because
`HANDOFF.md` §7 pointed you at a table you don't recognize, this is where it lives.

**2026-09-17 verification pass**: this file was checked line-by-line against the current code
(not rewritten from scratch — most of it still held up). What changed this pass: the
`LearnNav.tsx` references in §1 were stale (deleted 2026-09, replaced by `LearnSidebar.tsx` +
`LearnMobileTabBar.tsx` — see §1); `Mission.kind` picked up a seventh value, `ground_station`
(§4); the staff-can-view-any-attempt-but-not-submit authorization
(`routers/missions/student.py::get_mission_attempt`, PR #86) and the `mission_kind`-gated
"View run"/"Open console" split on the ops Progress tab (`services/lms/program.py::
assignment_item_detail`, PR #87) are both real and confirmed present — both added 2026-09-16;
`services/lms/progress.py::_create_progress_row` picked up the same SAVEPOINT-and-retry-select
race fix `quiz.py` already had (PR #88, 2026-09-16); a whole new sibling domain, the Cohort
Knowledge Quiz (§19), shipped this month and had no mention here at all. **Ground Station**
(hardware/device pairing/websocket telemetry/commands/alerts — `backend/app/{models,routers,
services}/ground_station/`) is now documented separately in
[`HANDOFF_GROUND_STATION.md`](./HANDOFF_GROUND_STATION.md) — this file only covers the
*checklist-item* side of a `ground_station`-kind mission (§18), not the console/rig internals.

---

## 1. Two surfaces, one backend

- **`/learn`** — the student-facing app. Own shell (`LearnShell.tsx`), own login/signup, mounted
  **outside** the portal's `AppShell`/`Sidebar` — same precedent as `ApplicantShell`. Desktop nav
  is a fixed `LearnSidebar.tsx` (2026-09, Roadmap board redesign — replaced the old horizontal
  `LearnNav.tsx`, which is deleted); mobile is unchanged, `pages/learn/nav/LearnMobileTabBar.tsx`,
  a bottom tab bar. Both pull their link list from `pages/learn/nav/navItems.ts` and share the
  "Back to portal" button/profile menu/notifications bell from `pages/learn/nav/LearnNavShared.tsx`
  — hidden for students, since `/learn` already is home for them. **Import discipline**: nothing
  under `frontend/src/pages/learn/**` may import `components/layout/Sidebar` (the portal's own)
  or anything under `pages/operations/**` — `LearnSidebar.tsx` copies the portal sidebar's width/
  spacing/classes by hand rather than reusing it, on purpose (see that file's own docblock).
- **`/lms-authoring`** — staff-facing authoring/admin, reached from the portal's normal
  `AppShell`. Courses, missions, the component library, games, progress, invite codes.
- **`student` is its own role** (`backend/app/models/enums.py::UserRole`), added in the LMS
  phase. A student has no portal home — `roleHomePath()`
  (`frontend/src/lib/roleHome.ts`) sends every other role to their usual portal page and
  students to `/learn`; the `"/"` index route redirect uses the same function so the two can't
  drift apart. Staff browsing `/learn` get a "Back to portal" link (`LearnNav.tsx`) back the
  other way — hidden for students, since `/learn` already is home.
- **Auth guards**: `require_lms_student = RequireRole(["student"])`,
  `require_lms_content = RequireRole(["operations", "facilitator"])`
  (`backend/app/core/dependencies.py`). The design component library has its own per-route
  check, `require_design_library_editor` — staff *or* a mission's assigned manager, not a
  simple role list.

## 2. Courses (`backend/app/models/lms/`, `routers/lms/`, `services/lms/`)

Tables: `courses`, `course_modules`, `module_items`, `module_videos`, `video_checkpoints`,
`enrollments`, `item_progress`, `learning_paths`, `learning_path_steps`, `point_events`,
`purchases`, `lms_programs`, `lms_program_cohort_overrides`, `lms_program_items`,
`lms_program_assignments`, `lms_program_item_progress` (§11 — the checklist-driven Program
redesign, 2026-08-21, which replaced `program_curriculum`/`cohort_curriculum` outright).

- `Course.access_mode` is `open | invite | paid` — governs **self-enrol eligibility only**, and
  self-enrol (`POST /lms/enroll`) is `require_lms_student`: **staff can never self-enrol in
  anything**, regardless of a course's mode. Staff access is always an ops-granted `Enrollment`
  row (`source="ops"`).
- **Stripe Checkout for paid courses** (2026-08-18, August Build Brief Branch 4) — the `paid`
  stage referenced above, now built. One-time payments only, hosted Checkout (not Elements —
  lower PCI surface), webhook-driven fulfilment via `services/lms/checkout.py::fulfill`, which
  both `POST /lms/webhooks/stripe` and the success-page trigger (`POST /lms/checkout/session/
  {id}/fulfill`) call — the redirect is only ever a hint to check, never itself proof of payment.
  New `Purchase` model (`models/lms/purchase.py`) carries a `product_type` discriminator
  (`"lms_course"` today) so a Phase 2 Programs/registration purchase can reuse the table without
  a rebuild — never rename `course_id` for that, add a sibling nullable FK instead.
  Double-payment protection is two-layered: a resume-in-progress check (covers two tabs/back
  button/refresh) plus a partial unique index on `(user_id, course_id)` scoped to
  `status='pending'` (covers the millisecond race) — cheap specifically because the `Purchase`
  row is always inserted *before* the Stripe session is created, so a losing insert fails before
  Stripe is ever contacted and there's no orphaned session to clean up. Webhook handles
  `checkout.session.completed`/`async_payment_succeeded` (fulfil), `expired`/
  `async_payment_failed` (mark failed), `charge.refunded` (revoke on a full refund only — a
  partial refund is a goodwill adjustment, not "give the course back"), and
  `charge.dispute.created`/`closed` (revoke only on a real dispute — `warning_*` states are bank
  inquiries with no funds withdrawn yet, and are deliberately left alone; dispute resolution never
  auto-restores a revoked enrollment, that's a manual ops re-grant). Refunds themselves are fully
  manual via the Stripe Dashboard for v1. `Course.price_cents`/`currency` are integer minor units
  (Stripe's own convention); `EnrollmentSource` gained `"purchase"`. Admin editing lives in
  `LmsCourseDetail.tsx`'s `EditCourseModal` (**not** `LmsMissionDetail.tsx` — that page edits a
  *mission's* access_mode, a different entity a naive grep can confuse this with).
- `GET /lms/catalog` (`routers/lms/student.py`) returns every published course to a student
  (self-enrol into `open`, browse the rest as a locked preview) — but for anyone else, it's
  scoped to courses they actually hold an active `Enrollment` in. Otherwise a staff browse
  showed a wall of courses that 403 on click except the handful they'd been enrolled into.
  `admin`/`operations` keep the unscoped full catalog (they need it for oversight).
- Video: encrypted-at-rest sources, HLS transcode pipeline, per-video watch checkpoints
  (`video_checkpoints`). Buckets (`lms-video-sources`, `lms-hls`) live under
  `/var/lib/spacepoint/storage` on the VPS host disk — see `HANDOFF_VPS_DEPLOYMENT.md` §6 for
  the general storage layout.
- **First-segment video latency was the VPS's default TCP congestion control (Cubic), not the
  app.** Switching to BBR took first-segment load from 11.2s to 1.7s. If HLS playback feels slow
  again, check `sysctl net.ipv4.tcp_congestion_control` on the VPS before assuming the pipeline
  regressed — this exact symptom looks identical to a transcode/CDN problem from the app side.
- **`item_progress` get-or-create race, fixed 2026-09-16**: `services/lms/progress.py::
  _create_progress_row` (called by `_progress_row`, the get-or-create every `POST
  /lms/items/{id}/progress` call goes through) used to be a plain SELECT-then-INSERT — two
  near-simultaneous requests for the same `(user_id, item_id)` (a double-click, a flaky client
  retry) could both miss the SELECT and both INSERT, and the loser 500'd on
  `uq_item_progress_user_item`. Fixed by wrapping the insert in `db.begin_nested()` (a SAVEPOINT)
  and re-`SELECT`ing on `IntegrityError` instead of letting it bubble — a lost race now just
  returns the winner's row. `services/lms/quiz.py::_create_progress_row` already had this exact
  shape (and `certificates.py::issue_course_certificate` has a third copy of the same idiom);
  `progress.py`'s own get-or-create was the one place it hadn't been ported to yet. If you add a
  fourth get-or-create against a uniquely-constrained table anywhere in this domain, use this
  pattern from the start rather than waiting for the 500 to show up in production.
- A course attaches to the Sessions domain's Programs/Cohorts (see `HANDOFF_SESSIONS.md`) as one
  `course`-type item inside an **LMS Program checklist** now — §11 below — a different attachment
  path than a student's own enrollment.

## 3. The unified prerequisite DAG (`backend/app/models/curriculum.py`, `services/curriculum.py`)

Courses and missions are interchangeable **items** in one DAG (`Prerequisite` — edges only),
superseding an earlier mission-only prerequisite table. Two separate concepts, deliberately
not conflated:

- **Readiness** — "has this student earned the right to attempt/enroll in X" — computed, never
  stored. For a mission: a passing attempt (solo, or as a team attempt member). For a course:
  every mandatory item across every module complete.
- **Grant** — "can this student see X at all" — `access_mode` on the item itself.

An item with no incoming edges is vacuously satisfied. No cycle detection beyond blocking
direct self-reference — a human-authored two-node cycle is a code-review problem, not worth a
graph traversal. `curriculum.add_prerequisite()` 409s if the edge already exists, which is what
makes seed scripts idempotent without a second existence query.

## 4. Missions (`backend/app/models/missions/`, `routers/missions/`, `services/missions/`)

Tables: `missions`, `mission_variants`, `mission_attempts`, `mission_attempt_members`,
`mission_managers`, `mission_assignments`, `mission_proposals`, `mission_step_gates`,
`mission_step_selections`, plus the design-mission-specific `design_component_library`,
`designs`, `design_modes`, `design_components`, `design_component_mode_states`, and one table per
budget (`design_data_budget_entries`, `_power_`, `_mass_`, `_cost_`, `_link_budget_entries`).
Team identity (`learner_teams`, `learner_team_members`) is **not** listed here — it moved out to
a top-level, domain-agnostic model since 2026-08-17 (see the Team generalization bullet below).

- **`Mission.kind`** ∈ `design | submission | quiz | checklist | operate | external | ground_station`
  (`schemas/missions_admin.py::MissionKind` — the authoritative list; `Mission.kind`'s own
  docstring/inline comment in `models/missions/mission.py` is stale, still says
  `design|submission|quiz|checklist|external`, missing both `operate` and `ground_station` — a
  code comment bug, not a behavior one). `VERIFIER_KINDS`
  (`services/missions/verifiers/__init__.py`) is a narrower set — `{submission, quiz, checklist,
  design, operate, external}` — one verifier module per kind (`verifiers/design.py`, `operate.py`,
  `quiz.py`, `submission.py`) grades/dispatches an attempt through `decide_attempt`/`submit_*`.
  **`ground_station` is deliberately not in that set**: it has no grading/points path at all — a
  ground_station attempt is flipped straight from `in_progress` to `passed` by the student's own
  `POST /ground-station/attempts/{id}/complete` (`routers/ground_station/attempts.py`, "self-serve
  done for checklist tracking... `score` stays null and nothing runs through `decide_attempt`/
  `award_points`"). See §18 for how that surfaces on the LMS checklist side; hardware/device/
  telemetry/command internals are `HANDOFF_GROUND_STATION.md`'s, not this file's. A `missions` row
  has no `mission_id` per student — **all of a design mission is one `missions` row**,
  `kind='design'`, with up to three `mission_variants` (difficulty levels: Cadet/Engineer/Flight
  Director) a student picks from. Don't create a mission per cohort or per subsystem.
- **Staff can view (never submit) any mission attempt** (`routers/missions/student.py::
  get_mission_attempt`, PR #86, 2026-09-16) — `GET /missions/attempts/{id}` checks
  `is_staff(current)` (`services/missions/authorization.py` — admin/operations/facilitator)
  *before* falling back to the owner-or-team-member check `_own_attempt` does; a staff caller
  skips ownership entirely and can load any attempt by id. Real motivation: Ground Station ops
  watching a student's live run 404'd on this endpoint before the fix (staff isn't the attempt's
  owner and isn't on its team roster). **`POST /missions/attempts/{id}/submit` was deliberately
  left owner-only** — `submit_mission_attempt` still calls the strict `_own_attempt`, no
  `is_staff` bypass — so staff can look but can't grade-by-submitting on a student's behalf
  through this path. Note this generic endpoint returns the generic `MissionAttemptOut`, not a
  kind's full console state — the design (`/missions/design/attempts/{id}`) and operate
  (`/missions/operate/attempts/{id}`) routes each layer their *own*, still strictly owner-only
  `_own_design_attempt`/`_own_operate_attempt` on top of `_own_attempt` and don't carry this
  bypass; staff view a design run's real detail through the separate admin/instructor
  `.../attempts/{id}/design-detail` routes instead (§14), not by pretending to be the owner here.
- **Design mission** — pick components from `design_component_library` (the real Madar catalog
  — see §6), balance six budgets (data/power/mass/cost/link/energy), CONOPS modes. Frozen
  snapshot per design (F2): a finished design keeps the specs it was built with even if the
  library changes under it later; a design still in progress picks up the change.
- **Concurrent named design runs** (2026-08-16) — a student can have several `in_progress`
  Design attempts at once, each its own named/objective'd run (`Design.design_name` etc.,
  collected by a setup step in `DesignBriefingPage.tsx`). `start_attempt()`'s single-flight
  resume is opt-out via `force_new=True`; every other caller (every other kind, and Design's own
  "continue an existing run" path) keeps the original single-flight behavior. `MissionPage.tsx`
  shows a "My Missions" list for `kind === "design"` instead of auto-redirecting into one attempt.
- **`MissionAttempt.cohort_id`** (2026-08-17; auto-resolution removed 2026-08-21, see the LMS
  Program redesign entry below) — every attempt carries a real cohort attribution, resolved at
  `start_attempt()` time, for every mission kind. Supersedes the older `Design.cohort_id`, which
  resolved lazily and solo-only, and now just mirrors this column. **A solo, student-started
  attempt (`POST /missions/{id}/attempts`) is now unconditionally `cohort_id=None`** — the old
  `resolve_student_cohort()` auto-resolution from the student's active `Registration` is gone
  entirely (removed, not deprecated — no function to call). The only ways an attempt gets a real
  `cohort_id` now: the team path (`Team.cohort_id`, unchanged) or an explicit ops action —
  `POST /missions/admin/attempts/assign` (`{user_id, mission_id, cohort_id, variant_id?,
  force_new?}`, `services/missions/attempts.py::assign_mission_run`). This is a real, deliberate
  behavior change (operator call, 2026-08-21): a new run a student starts themselves is always
  independent, never silently scoped to whatever cohort they happen to be registered in.
  **Consequence for anything reading gates/step-selection/poster fields below**: those all key
  off `MissionAttempt.cohort_id`, so they now only apply to ops-assigned attempts — any
  currently-configured cohort (TDRA included) needs its students' attempts (re-)created via the
  assign endpoint, they don't pick this up automatically from registration anymore.
- **Per-cohort step gating — reintroduced, on purpose** (2026-08-17). An identical feature
  (`design_step_gates`) existed once, shipped with no UI to ever use it, and was removed in
  Design v2 (7D-0) with the stated reason "instructors stay out of the mission entirely." The
  operator has since explicitly reversed that call. `MissionStepGate(cohort_id, mission_id,
  step_key, is_unlocked)` — missing row means unlocked (gating is opt-in per cohort). Enforced
  server-side in all 7 design write endpoints (`services/missions/gating.py::
  require_step_unlocked`) and mirrored client-side via `DesignStateOut.step_gates` for the
  wizard's tab-blocking (`DesignMissionPage.tsx`). Design-mission only — the only kind with a
  real multi-step wizard to gate.
- **Per-cohort step *selection* — compositional, not temporal, don't confuse with gating above**
  (2026-08-17). Real driver: the TDRA Summer Camp cohort only needs Components/Power/Mass,
  skipping Data Budget and Communication (Link + Downlink) entirely. `MissionStepSelection
  (cohort_id, mission_id, step_key)` — presence of a row means *included*; no rows for a
  cohort/mission pair means every step is included (permissive default, so a cohort that never
  configures this behaves exactly as before the feature existed). `DESIGN_STEP_PREREQS`
  (`services/lms/admin_progress.py`) is the verified real math dependency graph — narrower than
  `DesignMissionPage.tsx`'s old `DESIGN_TABS.needs` UI hints, which only explain step *order*
  and were never a real dependency check. The one correction that mattered: `calc_power_budget`/
  `calc_data_budget`'s validity never actually reads CONOPS (`modes` default to valid
  zero-duration values regardless), so their only real hard prerequisite is `components`, not
  `conops` — confirmed by the TDRA case, which selects Power without CONOPS. `downlink` is the
  one exception: hidden, not directly selectable, and only counts toward completion when
  `data_budget`+`link_budget`+`conops` are all in the selected subset. Server-side re-expansion
  (`services/missions/step_selection.py::set_selected_steps`) is the real enforcement — the
  frontend picker (`StepsTab` in `CohortMissions.tsx`) pre-expands for UX only. New
  `/missions/instructor/.../steps` GET/PUT/DELETE endpoints, alongside the existing gates ones.
  - **Bug, found live 2026-08-22, fixed same day**: step selection scoped `all_valid`/"Ready"
    correctly (`compute_dashboard()`'s `effective_keys` already existed for that), but the report
    layer (`services/missions/design/report.py`) never consulted it — `build_margins`/
    `build_module_cards`/`build_advice` always built all 9 categories regardless of what the
    cohort selected. A student on a Components/CONOPS/Data-only run (3 steps) saw all 9 module
    cards on the Report tab, including a "Power budget: FAIL" card for a step they never had
    access to. Fixed by threading `effective_keys` (= `dash["included_steps"] |
    ({"downlink"} if dash["downlink_included"] else set())`) through all three `report.py`
    builder functions, each now dropping any row/card/alert whose step isn't in that set; a new
    `report.py::MARGIN_ROW_STEP` constant is the one place that maps a margin row's key back to
    its step (energy and mass each produce two rows). Applied at both read sites: the live
    dashboard endpoint (`routers/missions/design.py`) and the frozen-at-completion review
    (`services/missions/verifiers/design.py::mark_design_complete`) — the latter matters because
    that snapshot is the permanent post-grading record, not just the in-progress view. Covered in
    `tests/services/missions/design/test_design_v2_calculators.py::
    test_module_cards_and_margins_are_filtered_to_the_cohorts_selected_steps`. A run with no
    `MissionStepSelection` configured is unaffected (`included_steps` defaults to "everything").
- **`/missions/instructor/*`** (2026-08-17) — a brand-new access path for the plain `instructor`
  role (it has zero access to `/missions/admin`/`/lms/admin`, which stay
  operations/facilitator/admin-only). Cohort-scoped progress, gates, and a review queue,
  reusing the `SessionInstructor` derivation (`services/missions/cohort_access.py`) exactly as
  `services/sessions/delivery.py` already does — not a new grant table (a `CohortInstructor`
  existed for that purpose once, removed 2026-08-01 as dead weight). Staff bypass the per-cohort
  check entirely, same "layered on top of, not instead of" posture as `mission_managers`.
  Frontend: `pages/lms-authoring/CohortMissions.tsx`, reachable by instructor too (the
  `/lms-authoring` layout guard was widened for this one page — every other page there still
  403s a plain instructor server-side).
- **Poster/Canva link fields** (2026-08-18, August Build Brief Branch 3) — deliberately scoped to
  two plain nullable columns, no new table: `cohorts.poster_template_url` (ops sets once per
  cohort, in the `CohortModal`) and `designs.poster_url` (the team's own working-copy link).
  `DesignStateOut.poster_template_url` is resolved from `attempt.cohort_id` (`None` outside any
  cohort — self-service attempts never see a template). The poster stays editable until the
  cohort's `ends_on` passes; `update_design` 400s a `poster_url` PATCH past that date, checked
  before the generic `setattr` loop, same pattern as everywhere else in this router. Frontend:
  `PosterTab.tsx` reuses `DesignHandbookDrawer`'s slide-over mechanic but anchored to the left
  edge — the handbook already owns the bottom-right corner — mounted alongside it in
  `DesignMissionPage.tsx`. No native poster renderer, no Canva API integration — a real
  drag-and-drop editor was explicitly deferred unless the link-only version proves insufficient.
- **Operate mission** — a real orbital simulation (not a quiz about one), rebuilt 2026-08-13.
  Objectives are graded live against state, not just a final score.
- **`mission_managers`** (7B-7) — staff can assign an intern/other staff as a mission's manager:
  they get its stats, review queue and teaching content, but **cannot edit grading
  config/points once published** — that stays frozen while live, edit the mission back to draft
  first. UI for this (`MissionAuthorsSection.tsx` on `LmsMissionDetail.tsx`) existed in the
  backend since 7B-7 but had no screen until 2026-08-14 — check the actual git log before
  assuming a backend capability is reachable from the UI.
- **Team generalization** (2026-08-17) — `MissionTeam` lifted into a top-level, domain-agnostic
  `Team`/`TeamMember` (`backend/app/models/team.py`, tables `learner_teams`/
  `learner_team_members` — **not** `teams`, which `models/interns/team.py` already owns as a
  fully separate, unrelated internship-program concept). This is the opening move of the
  Competition domain per the August Build Brief: Competition needs teams too, and building its
  logic against a missions-only table would have meant redoing it later. Zero rows in
  `mission_teams` in production made this a rare safe window for a real breaking rename
  (table/column/constraint, migration `a1f0c9b2d4e7`) with no backfill burden — don't expect
  that same freedom for a future rename. `MissionAttempt.mission_team_id` is now `team_id`.
  CRUD/membership primitives moved to `app/services/teams.py`; mission-specific attempt logic
  (XOR handling, per-member point awards) stayed in `services/missions/attempts.py` since that's
  inherently mission-attempt lifecycle, not team identity. New real membership endpoints —
  `POST /teams/{id}/join`, `DELETE /teams/{id}/leave` — wiring up what were previously dead
  `add_member`/`remove_member` primitives (409 on already-a-member, 404 on not-a-member, no
  silent no-ops). **Gotcha if this ever needs touching again**: two unrelated interns-domain
  files (`models/interns/project.py`, `models/interns/epic.py`) use `relationship(Team, ...)` —
  they used to pass a bare `"Team"` string, which broke the moment a second class named `Team`
  existed, since SQLAlchemy resolves string relationship targets registry-wide, not per-module.
  Frontend: `api/teams.ts` (new, generalized out of `missions.ts`'s old `MissionTeam` type),
  join/leave UI in `MissionPage.tsx`'s `TeamPicker`, a new "Teams" card on `LearnProfile.tsx`
  (`/missions/teams/mine` — only shows mission teams for now, labeled generically since
  Competition will add a second domain of teams to the same list later).
- **Proposing a new mission** (intern-submitted prototype → staff port): full process in
  [`MISSIONS_INTERN_SPEC.md`](./MISSIONS_INTERN_SPEC.md). Short version: keep the domain logic
  (calculations, state machine, vocabulary), always rewrite auth/stack/DB against this
  platform's own — never port someone's Express routes or database schema wholesale.

## 5. Games / Live Quiz (`backend/app/models/games/`, `routers/games/`, `services/games/`)

Tables: `games`, `game_questions`, `game_runs`, `game_participants`, `game_answers`,
`game_session_assignments`, `game_session_questions`.

- A `Game` is authored content (questions); a `game_runs` row is one live play-through an
  instructor starts, with realtime state broadcast over `services/games/realtime.py`.
- **Restart-in-place** (2026-08-14): an instructor can restart a run without creating a new one
  and re-sharing a join code mid-class. A run left open in a lobby or mid-question when its
  session is marked done now auto-closes (`close_open_runs_for_session`,
  `routers/sessions/delivery.py`) — otherwise it sat in students' joinable lists indefinitely,
  since nobody goes back to press End on a quiz they moved on from an hour ago.
- Student identity in a run: `nickname` + `avatar` (`AVATAR_PRESETS`,
  `services/games/avatars.py`) — auto-generated at signup, admin-editable
  (`backend/app/routers/admin/users.py`) since a generated nickname occasionally lands
  somewhere unusable in front of a class. `users.avatar` is the account default; a run still
  snapshots its own copy, so changing the default doesn't rewrite history.

## 6. Component library (`design_component_library`, `routers/missions/library.py`)

**The real catalog is 36 components**, transcribed 2026-08-14 straight from Madar's own
production `components` table (pulled over SSH — the handover never included a DB dump, only
the app code and an uploads folder). Real kit parts: DC motors, GPS module, ESP32 variants,
MPU6050, INA219, etc. — not abstract CubeSat-subsystem stand-ins. Seeded via
`backend/scripts/missions_seed_design.py`, matched by `component_code` (not name — two real
components legitimately share a name). Images: either copied byte-for-byte from Madar's
`frontend/uploads/` (matched by the exact `/static/uploads/<uuid>` filename in the pulled data)
or fetched from the component's original external product-photo URL — see that script's
module docstring for the full story and **do not** reintroduce the 15-component placeholder
set that used to be seeded (`Nano Star Tracker`, `MEMS Reaction Wheel`, ...) — that was
dev-seed data from the old repo's `seed.py`, never what Madar's students actually used.

There is deliberately **no manual "pick which of these 16 unlabeled photos matches this
component" picker** in the admin UI — that existed briefly, got removed once the real
image-to-component mapping was recovered from the live DB, and shouldn't come back short of
another from-scratch data-recovery situation like this one. `Upload image` is the only way to
set an image by hand.

**Retire, never delete** (F1, rated Critical) — same rule as everywhere else in this codebase.
Madar's delete cascaded and wiped a component from every student's design along with their
budget entries; this one only hides it from new picks.

## 7. Seed scripts (`backend/scripts/`)

- `missions_seed_design.py [--dry-run] [--update] [--images-dir PATH]` — the ONE `missions` row
  for CubeSat design (`kind='design'`), its variants, and the 36-component library with images.
  Idempotent — re-running skips anything present. `--images-dir` should point at Madar's
  `frontend/uploads/` folder when attaching local-path images; on the VPS that means
  `docker cp`-ing it into the `spacepoint-api` container first (it isn't bind-mounted) — see
  `HANDOFF_VPS_DEPLOYMENT.md` §3's container-recreate gotcha, same pattern.
- `missions_seed_operate.py [--dry-run] [--update]` — the Flight Operations mission + its 3
  variants. No image handling; nothing to point `--images-dir` at.
- Neither script seeds a "design report" follow-on mission any more — one existed briefly
  (`cubesat-design-report`, a `submission`-kind mission gated behind the design one), but it was
  invented during a prior session's own design work, not something Madar shipped, and was
  deleted from production 2026-08-14 (zero attempts existed, so a clean delete rather than an
  archive).

## 8. Frontend map

```
frontend/src/pages/learn/          # student surface
  LearnShell.tsx                    # own shell — see import-discipline note in §1
  LearnSidebar.tsx                  # desktop nav (2026-09, replaces deleted LearnNav.tsx)
  nav/  LearnMobileTabBar.tsx, LearnNavShared.tsx, navItems.ts   # mobile nav + shared nav bits
  LearnLanding.tsx                  # /learn home — hero is <SatkitAssembly>, see §9
  LearnCatalog.tsx, LearnCourse.tsx, LearnMyCourses.tsx, LearnPaths.tsx, LearnPath.tsx,
  LearnProgram.tsx, LearnCheckoutSuccess.tsx
  PlayerLayout.tsx, LearnPlayer.tsx, ItemPane.tsx, VideoPlayer.tsx, Rail.tsx,
  CourseProgress.tsx, CompletionCelebration.tsx     # course-player pieces, split out of LearnPlayer
  LearnChecklists.tsx               # /learn/checklists list — §11
  board/  RoadmapBoard.tsx, TileField.tsx, TraceLayer.tsx, TaskDrawer.tsx, TaskTile.tsx,
          NextTaskCard.tsx, FinalGateBar.tsx, roadmap.ts   # the gated visual board — §17
  MissionCatalog.tsx, MissionPage.tsx, DesignMissionPage.tsx, DesignBriefingPage.tsx
  missions/  MadarPhaseBoard.tsx, MadarPhaseDrawer.tsx   # phase-tile view embedded in DesignMissionPage
  OperateMissionPage.tsx, OperateBriefingPage.tsx, OperateDebriefPanel.tsx
  GroundStationAttemptPage.tsx      # `mission_kind="ground_station"` console — internals in
                                     # HANDOFF_GROUND_STATION.md, not here; see §18
  LearnGames.tsx, GamePlay.tsx, LearnLeaderboard.tsx, CohortQuizPage.tsx   # §19
  LearnLogin.tsx, LearnSignup.tsx, ForgotPassword.tsx, LearnSetPassword.tsx, LearnProfile.tsx

frontend/src/pages/lms-authoring/  # staff surface (+ instructor — role-aware end-to-end, see §14)
  LmsCourses.tsx, LmsCourseDetail.tsx, LmsModuleDetail.tsx, LmsLearningPaths.tsx,
  LmsLearningPathDetail.tsx
  LmsMissions.tsx, LmsMissionDetail.tsx, LmsDesignLibrary.tsx   # the component library editor
  LmsGames.tsx, LmsGameDetail.tsx, LmsCohortQuizAdmin.tsx   # "Quiz Bank" nav item, §19
  LmsProgressGrid.tsx, LmsStudents.tsx, LmsStudentDetail.tsx
  LmsInviteCodes.tsx
  LmsProgramAdmin.tsx   # curriculum route (§11) — checklist authoring + progress/gates/review, see §14
                         # (CohortMissions.tsx, listed here pre-2026-08-22, is deleted — merged into this)
  components/  AssignPanel.tsx, DesignRunDetail.tsx, ItemPicker.tsx, LmsChecklistAuthoring.tsx,
               LmsCohortSection.tsx, LmsComponentConfigPanel.tsx, LmsProgressAndMissions.tsx,
               MissionAuthorsSection.tsx, MissionContentSection.tsx, PrerequisitesSection.tsx
```

Ops-role sidebar nav order (`Sidebar.tsx`'s `LMS_GROUP`, checked 2026-09-17): Courses, Learning
Paths, Programs, Live Quiz, **Quiz Bank** (`/lms-authoring/quiz-bank`, new 2026-09 — §19), Missions,
Students, Invite Codes, Progress, Component library. Says **"LMS"**, not "LMS Courses" — it covers
all of the above now, not just courses. Plain-instructor nav (2026-08-22): Overview, Sessions,
Library Resources, Personal Documents, Instructor ID Card, Payments, **LMS Programs** (renamed from
"Programs"), Learn, SatKit Training, My Kits & Items — a different audience from the ops nav,
deliberately reordered/renamed separately.

## 9. The `/learn` hero (`frontend/src/components/satkit/`)

A pre-rendered PNG frame-sequence player (`<satkit-assembly>`, a dependency-free vanilla custom
element — not React, not three.js) plays the real CubeSat assembly animation. Assets live in
`frontend/public/assets/satkit/` (`manifest.json` + `frames/`, served as-is by Vite).
`SatkitAssembly.tsx` is the typed JSX wrapper.

Two gotchas, both cost real time to find:

1. **React 19's `@types/react` moved the JSX namespace to `React.JSX`.** A bare
   `declare global { namespace JSX { interface IntrinsicElements {...} } } }` augmentation
   silently doesn't merge into what TSX actually resolves against any more — it has to be
   `declare module "react" { namespace JSX {...} } }` instead. `npx tsc --noEmit -p
   tsconfig.json` won't catch this: the root `tsconfig.json` is solution-style (`files: []`,
   only `references`), so without `-b` it type-checks **nothing** and reports success
   regardless. The real build command is `tsc -b && vite build` (`npm run build`) — that's what
   actually failed in CI when this shipped. **Always verify a frontend change with the literal
   `npm run build` command** (with `VITE_API_URL` set, matching `build-frontend.yml`), not a
   substitute typecheck invocation.
2. **`customElements.define()` can't be hot-swapped.** Editing `satkit-assembly.js` and relying
   on Vite HMR to pick it up doesn't work — the already-registered class stays active until a
   full page reload. If a change to that file "isn't taking effect," hard-refresh before
   assuming the code is wrong.

## 10. Deploy note specific to this domain

`gh release download` (inside `deploy-frontend.sh`) has hung on a fully healthy connection at
least once — `gh auth status` and `curl` to `github.com` both fine, plain
`curl -L -o /tmp/frontend-dist.tar.gz <release-asset-url>` completed instantly. If it stalls
again: Ctrl+C, download with plain `curl` to the exact path the script expects
(`/tmp/frontend-dist.tar.gz`), then run the script's extract/verify/swap steps by hand (they're
short — read `/usr/local/bin/deploy-frontend.sh`, it's four commands after the download line).

## 11. LMS Program checklist (2026-08-21)

Replaces `program_curriculum`/`cohort_curriculum` (a flat, course-only list, dropped outright —
confirmed empty in production, no migration needed) with a real checklist. Both backend and
frontend are complete and tested/built: `backend/app/models/lms/program.py`,
`services/lms/program.py`, `routers/lms/{admin,student,instructor}.py`; frontend at
`frontend/src/pages/learn/LearnChecklists.tsx`/`LearnChecklist.tsx` (student, `/learn/checklists`,
nav-labeled "Programs"), `frontend/src/pages/lms-authoring/LmsProgramAdmin.tsx` (ops + instructor
authoring/roster/review, same `/lms-authoring/curriculum` route + Sidebar slot the old curriculum
page used, relabeled "Programs" — replaces `LmsCurriculum.tsx` outright, and as of §14 also absorbs
what used to be the separate `CohortMissions.tsx` page, now deleted).

- **Shape**: `LmsProgram` (a checklist template, attached to a Sessions `Program` via
  `program_id`, nullable+unique — one checklist per program) → `LmsProgramItem` (the steps;
  polymorphic `owner_type`/`owner_id` pointing at either the `LmsProgram` itself or a
  `LmsProgramCohortOverride` — service-layer-enforced, not a DB FK, same discriminator idiom
  `Purchase.product_type` uses) → `LmsProgramAssignment` (one student's instance, created once at
  registration time) → `LmsProgramItemProgress` (per-student per-item status).
- **Cohort override** (`LmsProgramCohortOverride`) replaces its program's checklist outright when
  it has any items of its own — never merged, the exact `CohortCurriculum` idiom carried forward.
  `resolve_cohort_program()` is the one function that applies it; nothing else should read
  `lms_program_items` directly.
- **Item types**: `course` (enrolls immediately on assignment — sequence position governs
  checklist display/certificate-gating only, never actual access), `mission_run` (ops-assigned via
  the endpoint below, never student-started), `external_link`, `submission` (paste-a-link-back,
  same shape as the Poster tab), `article`, `manual`, plus two added since (both
  `AUTO_TRACKED_TYPES` in `services/lms/program.py`, meaning their status is computed, never
  self-checked): `quiz` (2026-09 — a Cohort Knowledge Quiz template, §19; done once submitted,
  score never gates the checklist) and `team_setup` (2026-09-14, Competition team onboarding —
  always `scope="team"`, the one item type where that's enforced rather than optional; see
  `HANDOFF_COMPETITIONS.md`, this isn't an LMS-domain feature). `optional` items don't block the
  certificate; `requires_confirmation` items need an instructor/ops confirm click instead of the
  student's own self-check (self-check is the default everywhere else — operator call: "not
  everything can be trackable"). Only `submission`/`external_link`/`manual`/`mission_run`/
  `team_setup` can be `scope="team"` — `course` and `quiz` are always individual.
- **Assignment is automatic, at registration time** — `sync_registration_lms` calls
  `assign_lms_program()` exactly where it used to call `enroll_in_cohort_curriculum()`. A cohort
  with no attached checklist is a no-op, same as before. Items are materialized once, at
  assignment time; a later checklist edit does not retroactively change an existing assignment
  (no reconciliation fan-out yet — `enroll_in_cohort_curriculum` had one, `P4-2`; add one the same
  way if a real need for it shows up, there's no production data to migrate yet so it wasn't
  built speculatively).
- **Mission-run items and the new general assign endpoint**: `POST /missions/admin/attempts/
  assign` (`services/missions/attempts.py::assign_mission_run`) is the one way a `MissionAttempt`
  gets a `cohort_id` now that solo/student-started attempts never auto-resolve one (see §4's
  `MissionAttempt.cohort_id` entry above for the full detail and its consequence for gates/
  step-selection/poster fields on any *existing* cohort). Not program-exclusive — TDRA-style
  cohort-scoped-missions-with-no-full-checklist use this same endpoint directly.
  - **Bug, found live 2026-08-22, fixed same day**: `start_attempt()`'s "resume the owner's
    in-progress attempt" lookup didn't check `cohort_id` at all, so a student's own independent
    attempt (`cohort_id=None`) got silently handed back to `assign_mission_run()` unchanged — a
    checklist's `mission_run` item ended up pointing at the student's unrelated solo run instead
    of a fresh cohort-scoped one, with no gating applied. Fixed by making the resume lookup match
    on `cohort_id` too (`None` only resumes `None`, a specific cohort only resumes that same
    cohort) — a scope mismatch now mints a fresh attempt in the requested scope and leaves the
    mismatched one untouched, independently resumable. Covered in
    `tests/services/missions/test_missions_attempts.py::
    test_start_attempt_never_resumes_across_a_cohort_scope_mismatch`.
  - **Consequence for anyone who tested this before the fix landed**: `assign_lms_program()` only
    ever runs once per `(user_id, cohort_id)` (idempotent), so an `LmsProgramAssignment` created
    while this bug was live has a `mission_attempt_id` permanently pointing at the wrong attempt —
    the fix doesn't retroactively repair already-created assignments. Delete the affected
    `lms_program_assignments`/`lms_program_item_progress` rows (or just re-test with a fresh
    student account) rather than reusing one that was assigned before this fix.
- **Certificate**: no new certificate type. `LmsProgram.certificate_required` (default true) gates
  the cohort's existing `student_completion` certificate — `services/sessions/delivery.py::
  complete_cohort`'s automatic per-registration issuance now also checks
  `certificate_gate_satisfied()`; `issue_certificate_override` (the existing manual-override
  escape hatch) deliberately still bypasses it, same as it already bypasses the attendance
  completion rule.
- **Endpoints**: ops authoring at `/lms/admin/programs/*` and `/lms/admin/cohorts/{id}/
  program-override/*` (mirrors the course-admin CRUD shape); student read/self-check/submit at
  `/lms/programs*` (distinct from the older, still-live `/lms/my-programs` courses-only cohort
  view); instructor roster + confirm at `/lms/instructor/cohorts/{id}/program-progress*`,
  cohort-scoped via `services/missions/cohort_access.py::require_cohort_access` (reused as-is —
  same instructor/facilitator/operations population an LMS-side view needs).
- **Operational note for whoever deploys this**: any cohort *currently* configured with a
  `MissionStepGate` row, a `poster_template_url`, or relying on `MissionStepSelection` needs its
  students' mission attempts re-created via `POST /missions/admin/attempts/assign` after this
  ships — those features all key off `MissionAttempt.cohort_id`, which a solo attempt no longer
  gets automatically. This is a real, one-time manual step, not automated (no reconciliation
  script) — check with the operator for which cohorts (TDRA at minimum) need it before/soon after
  this deploys.

## 12. Learning path bundle pricing (2026-08-21)

Buy every course in a `LearningPath` at one Stripe Checkout price instead of course-by-course —
the second of the operator's boss's three pricing requests (region/IP pricing and invite-code
discounts are still unscoped, this is the one picked to build). Reuses the Stage S `Purchase`
machinery almost directly, per that model's own docstring anticipating this exact reuse.

- **Pricing**: `LearningPath.price_cents`/`currency` mirror `Course`'s columns — NULL means "not
  sold as a bundle," and the existing free `POST /learning-paths/{id}/start` (self-enrols only
  `open`-access steps) is unchanged either way. Free-form price — no enforced relationship to the
  sum of the individual steps' prices (operator decision: ops is trusted to price it sensibly,
  same posture as course pricing).
- **Checkout**: `POST /lms/learning-paths/{id}/checkout` mirrors `start_course_checkout` almost
  line for line — pending-purchase resume, the partial-unique-index double-payment backstop
  (`uq_purchases_pending_per_path` on `(user_id, learning_path_id)` where `status='pending'`).
  Blocked (200, no Stripe call, no `Purchase` row) only when the caller already has an active
  enrollment in *every* step's course — nothing left to grant. Owning some but not all still buys
  the full bundle at full price; there is no partial/proration logic anywhere in this codebase
  (operator decision).
- **Fulfilment**: `services/lms/checkout.py::fulfill()` now branches on `Purchase.product_type`.
  A `"learning_path"` purchase enrols every current step's course via `enroll(..., source=
  "purchase", purchase_id=purchase.id)` — regardless of each course's own `access_mode`, since the
  whole point of buying the bundle is to unlock steps a free `/start` would have skipped.
  `Purchase.enrollment_id` stays null for a bundle (there's no single row to point at); it's still
  set for a plain `lms_course` purchase, unchanged.
- **Refund/dispute revocation, generalized**: new `Enrollment.purchase_id` (nullable FK) is the
  real join for "which enrollments did this purchase grant" — `enroll()` stamps it on a newly
  created row (and on reactivating an inactive one, mirroring how `granted_by` already behaves),
  but never on its existing-active early return. That's what makes bundle refunds safe: a course
  the student already owned independently before buying the bundle was never stamped with this
  purchase's id, so `routers/lms/checkout.py::_revoke_purchase_enrollments()` (now what both the
  `charge.refunded` and `charge.dispute.created` webhook branches call, replacing the old direct
  `purchase.enrollment_id` lookup) only deactivates enrollments this purchase actually created —
  works identically for the single-course case (exactly one row) and the bundle case (however many
  steps were newly granted).
- **Frontend**: `LearnPath.tsx` shows a "Buy path — $X" button (via `startPathCheckout`) whenever
  `price_cents` is set and `fully_owned` is false, alongside the existing free Start/Continue
  action once the student has already started for free. `LearnCheckoutSuccess.tsx` branches on
  `CheckoutFulfillResult.learning_path_id` vs `course_id` to route back to the right landing page.
  Ops sets the bundle price from the learning-path detail page's Edit modal
  (`LmsLearningPathDetail.tsx`) — not the creation form, matching how publish/image already work.
- **Not built**: region/IP-based pricing and invite-code/promo discounts — both still just
  scoped in conversation, not planned or built. See the operator if picking either up next.

## 13. Invite-code course/path grants, learning-path bulk grant, Stripe promo codes (2026-08-21)

The invite-code discount idea, once interviewed properly, turned out to want three separate
things — none of them a Stripe percentage-off discount:

- **Invite-code grants** (`InvitationCodeGrant`, `models/lms/invite_grant.py`) — ops attaches a
  course or learning path to an `InvitationCode` (kind='student') and every account that's ever
  typed that code — old or new — gets it free, no checkout. The code *is* the batch, same
  `users.invitation_code_used` string-match the invite-codes admin screen already filters students
  by; this is deliberately not a new generic groups/audiences table (`BulkGrantIn`'s own docstring
  rules that out at §3) — it only exists because `InvitationCode` already serves as the batch
  primitive here. `services/lms/invite_grants.py::grant_invite_code_access()` applies retroactively
  the instant ops attaches it; `apply_invite_code_grants_to_new_user()` is called from
  `routers/auth.py::student_signup` right where `invitation.used_count` increments, so a fresh
  signup gets it on the spot too. New `Enrollment.source` value `"invite_code"`. Endpoints:
  `GET/POST /lms/admin/invite-codes/{id}/grants`, `DELETE .../grants/{grant_id}` — deleting a grant
  only stops it applying going forward, it never revokes access already given (same posture as
  deleting a `LearningPath` leaving its enrollments alone). UI: a "Grants" expandable section per
  code card on `LmsInviteCodes.tsx`.
- **Learning-path bulk grant** — the existing one-shot cohort/role course grant
  (`POST /lms/admin/courses/{id}/enrollments/bulk`, §3 "not a live membership rule") now has a path
  sibling: `POST /lms/admin/learning-paths/{id}/enrollments/bulk`, same `BulkGrantIn`/`BulkGrantOut`
  shape, enrols every current step's course per resolved user. `already_enrolled` only counts a
  user once they hold *every* step, matching the bundle purchase's own "block only when fully
  owned" read of ownership. UI: a standalone "Grant every course to a role" panel on
  `LmsLearningPathDetail.tsx` (`BulkGrantPanel`) — deliberately not the full `AssignPanel`
  roster/individual-assign component courses/missions use, since a path bundle has no single roster
  of its own (access lives per-course, one row per step); building that aggregation view wasn't
  asked for here.
- **Stripe promo codes** — `allow_promotion_codes=True` on both Checkout Session calls
  (`routers/lms/checkout.py`, course and path). A code field just appears on Stripe's hosted page;
  Stripe does the discount math. Ops creates/manages codes directly in the Stripe Dashboard —
  nothing stored or tracked on our side (operator decision: no new ops page for this, no
  per-purchase discount tracking).

**Noted for future work, not built now** (operator: "do the minimal, note the redesign so it
doesn't get lost") — the ops course/learning-path pages could use a unified "Access" view per
item showing every channel together (open/invite/paid self-serve, Stripe promo codes in play,
one-shot bulk grants issued, invite-code grants attached) instead of each living in its own corner
of the admin UI. Nobody has scoped what that actually looks like yet.

## 14. Programs / Cohort Missions merge (2026-08-22)

Operator complaint, verbatim: Programs (§11) and Cohort Missions were two separate pages doing
overlapping things — checklist authoring lived on one, cohort-scoped mission progress/gates/review
on the other — and neither showed real submission content, a student profile link, or actual
design-mission detail. `LmsProgramAdmin.tsx` is now the one page; `CohortMissions.tsx` is deleted.

- **One page, scope + sub-tab structure**: `LmsProgramAdmin.tsx`'s existing "Program template" /
  "`{cohort}` override" tab bar is now the page's scope selector — whichever is active governs
  everything below it, not just the checklist editor. Four sub-tabs per scope: **Checklist**
  (existing editor), **Missions** (new — lists the scope's `mission_run` items; a cohort's mission
  expands into Steps/Gates config, ported from the old `CohortMissions.tsx`), **Progress** (roster,
  extended — student name navigates to `/lms-authoring/students/$userId`, row expands to every
  item's status via the new `assignment_item_detail()`, submission items now show the actual
  `submitted_url` instead of a bare title), **Review** (ported from the old page's review queue,
  plus a new "Force pass/fail…" action).
- **Cohort overrides start pre-filled, fork-on-write** (`services/lms/program.py::
  effective_cohort_program_items`/`fork_cohort_override`): reading an unconfigured cohort's
  override now transparently returns the *program's own* items (`is_inherited: true`) instead of
  404/empty, so there's something to edit instead of starting from scratch. The first real write
  (add/update/delete) bulk-copies every current program item into new cohort-owned rows first, then
  applies the edit — including transparently redirecting an "edit this inherited item" call onto
  its freshly-forked copy via an old-id→new-id map. `resolve_cohort_program`'s existing "override
  with ≥1 item wins outright" rule is unchanged; this only changes what the *editor* shows before
  any edit has happened.
- **Manual pass/fail override, any attempt kind/status** (`services/missions/attempts.py::
  override_attempt_outcome`) — distinct from `decide_attempt` (kind-specific self-grading,
  `in_progress`/`submitted` only) and `review_submission_attempt` (human review, submission-kind
  only, `submitted` only). This one works on any attempt regardless of kind or current status,
  requires a `reason` string, and records `{reason, decided_by, decided_at, previous_status}` into
  `attempt.payload["override"]` for an audit trail. **Known, accepted limitation**: flipping an
  already-passed attempt to failed does not claw back points already awarded — operator confirmed
  this is fine for v1. `POST /missions/instructor/attempts/{id}/override` (cohort-scoped, same
  guard as the existing `.../review` endpoint) and `POST /missions/admin/attempts/{id}/override`
  (ops, full catalog).
- **Instructor access widened from one page to the whole `/lms-authoring` space**: instructors were
  previously scoped to `/lms-authoring/cohort-missions` only (a client-side URL-space allowance, see
  `router.tsx`'s `lmsAuthoringLayoutRoute` comment) with a separate, narrower backend dependency
  (`require_instructor_missions`) than the ops-only `require_lms_content`. That dependency shape is
  unchanged, but `LmsProgramAdmin.tsx` and `LmsStudentDetail.tsx` are now both role-aware
  end-to-end: instructors get a program picker pre-filtered to their own cohorts' programs
  (`GET /lms/instructor/programs`, derived from `Cohort.program_id` via `instructor_cohort_ids()`),
  read-only checklist rendering (edit controls hidden, not disabled — "any extra edits need ops"),
  and full edit rights on their own cohorts' mission gates/step-selection/review/override, same as
  before.
- **Student profile now reachable and actually detailed**: clicking a student's name anywhere on
  the roster navigates to `LmsStudentDetail.tsx`. New instructor-side mirrors of the ops-only
  student endpoints (`GET /lms/instructor/students/{user_id}`, `.../enrollments`,
  `.../design-runs`, `.../courses/{course_id}/progress`) scoped to a 404 unless the target student
  holds an active `Registration` in one of the instructor's cohorts — reuses `my_programs()`/
  `student_design_runs()`/`student_course_progress()` as-is, just behind the new scope check.
  Design-mission rows now expand into real detail (`GET /missions/{admin,instructor}/attempts/
  {id}/design-detail`, reusing `design_state_out` — formerly the private `_design_state_out` in
  `routers/missions/design.py`, made public for this reuse) instead of pass/fail dots: component
  choices, CONOPS modes, computed margins/module cards. Margins/module cards deliberately stay
  scoped to whatever step-selection the cohort has configured (same as what the student's own view
  computes) — this is a grading view of *that attempt*, not an unscoped audit; the raw
  component/CONOPS list itself (the actual "what did they select" ask) is never scope-filtered.
- **Frontend syntax landmine, worth flagging for the next person editing this file**: a `/** */`
  JSDoc comment on `LmsStudentDetail.tsx` originally documented an endpoint path containing a
  wildcard segment written as `courses/*/enrollments` — the literal `*/` inside that URL closes a
  block comment early. Everything after silently got swallowed into cascading phantom template
  literals (real code parsed as string content) until the file's *last* stray backtick, at which
  point parsing desynced and threw confusing, far-displaced syntax errors. `tsc --noEmit -p .`
  (root `tsconfig.json`, which has an empty `files` array and only `references`) does **not** catch
  this — it silently checks zero files unless invoked as `tsc -b` or pointed at
  `tsconfig.app.json`/`tsconfig.node.json` directly. Use `npx tsc --noEmit -p tsconfig.app.json` (or
  `npm run build`, which uses `tsc -b`) to actually verify the frontend typechecks — not bare
  `tsc --noEmit -p .`. Fixed by rewording the path to `courses/{id}/enrollments`; more generally,
  never write a literal `*/` sequence inside a `/** */` comment body.

## 15. Post-merge fixes from live testing, and full design-run detail (2026-08-22 → 2026-08-24)

Everything below landed after §14 merged, mostly bugs the operator found live-testing
`LmsProgramAdmin.tsx` on their own machine, plus two follow-on gaps found while answering "how does
an instructor see what a student built."

- **Design-only Steps/Gates, enforced**: `Mission.kind` (`design|submission|quiz|checklist|
  external`) is now checked before serving any Steps/Gates endpoint — previously a non-design
  mission_run item (e.g. an "Operations" mission) rendered collapsible into the same 9-step Design
  build catalog as an unrelated SatKit design mission, because nothing scoped the step-selection UI
  to the item's actual mission. `LmsProgramItemOut.mission_kind` now travels with every item
  (`item_out`/`items_out` in `services/lms/program.py`, populated from a `Mission` lookup), and the
  frontend gates `StepsTab`/`GatesTab` rendering on `item.mission_kind === "design"`, showing an
  explanatory message otherwise. Backend gate: `_require_design_mission()` in
  `routers/missions/instructor.py`, 400 on a non-design mission id.
- **Instructor never lands on Program scope**: a plain instructor opening `/lms-authoring/curriculum`
  used to load the entire authoring surface and 403 across the board. Fixed two ways: (1) an
  effect-driven redirect lands them straight on their own cohort's scope, never "Program"; (2) the
  "Program" scope tab itself is now `{isStaff && (...)}` — not just defaulted away from, actually
  unreachable for a non-staff instructor.
- **Instructor cohort-checklist 403 despite the program default rendering fine**: `CohortOverrideEditor`
  was calling the ops-only `getCohortProgramOverrideApi` regardless of role. Added the instructor
  mirror `GET /lms/instructor/cohorts/{cohort_id}/program-override` (read-only,
  `effective_cohort_program_items` reused as-is) and switched the editor to pick admin vs. instructor
  fetch by role.
- **Missions tab existed as a viewer only**: ops opening a program's Missions tab had no way to add
  or edit `mission_run` items — `ProgramMissionsPanel`/`CohortMissionsPanel` were rewritten with real
  add/edit/delete (shared `AddMissionRunButton`), matching the checklist editor's existing pattern.
  Delete is the `X` next to Edit on each mission run's row (`ItemRow`, `!readOnly` only) — this was
  the answer when the operator later asked whether removing a mistakenly-added mission run was even
  possible; it already was, just easy to miss since the row only shows Edit/Delete when not
  read-only.
- **Student-profile back link 403'd for an instructor**: `LmsStudentDetail.tsx`'s `<ArrowLeft />
  Students` link always pointed at `/lms-authoring/students`, an ops-only route. Made role-aware:
  staff still goes there; instructor goes to `/lms-authoring/curriculum` labeled "Programs" instead.
- **Checklist items were not actually draggable**: an earlier pass removed the decorative
  grip-icon-only affordance but never wired real reordering. `ChecklistItemsEditor`/`ItemRow` now
  implement native HTML5 drag-and-drop (`draggable`/`onDragStart`/`onDragOver`/`onDrop`/`onDragEnd` —
  not `@dnd-kit`, which is already used elsewhere for the interns Kanban board but is overkill for a
  simple vertical list) with optimistic local reordering, backed by new `POST
  /programs/{id}/items/reorder` and `POST /cohorts/{id}/program-override/items/reorder`
  (`services/lms/program.py::reorder_program_items`, negative-offset-then-final-position, same idiom
  as the pre-existing course-module reorder). **Naming-collision gotcha**: this function was
  originally imported as `reorder_items` into `routers/lms/admin.py`, which silently shadowed an
  unrelated, pre-existing local `reorder_items` (course-module item reorder) defined later in the
  same file — no import or type error, just a `TypeError` at call time, caught only by running the
  new tests. Renamed to `reorder_program_items` to avoid the collision outright.
- **Sidebar nav reorders/renames** (`Sidebar.tsx`) — see §8's frontend map for the current order.
  Also added `mk("Role Requests", "/admin/role-requests")` under Applications on the admin sidebar
  (both the `/admin`-path block and the domain-less admin fallback block).
- **Full read-only design-run detail on the student profile** (`LmsStudentDetail.tsx`
  `DesignRunDetail`, 2026-08-24): the roster's design-mission expand only ever showed a components
  table and margin chips. Operator ask, verbatim: "for every student run i should have a way to know
  everything they did there... and most importantly their poster" — followed by their own proposed
  fix, "open the run and see everything there with read only, just like the student view." That
  turned out to be exactly right and needed no backend change: `attemptDesignDetailApi`
  (`/missions/{admin,instructor}/attempts/{id}/design-detail`) already returns the identical
  `DesignState` shape the student's own wizard (`DesignMissionPage.tsx`) consumes. Rebuilt the expand
  as a tabbed read-only replica — **Setup, Components, CONOPS, Budgets (data/power/energy/link/mass/
  cost, per-component entries and totals), Report (alerts/margins/recommendations), Poster** (their
  template + working-copy Canva links) — with zero edit/save controls anywhere; it's a grading
  surface, not a second editor.
- **Program-linked design runs never saw the guided objective/orbit setup**: found while building the
  above. `assign_lms_program` (§14) creates a mission_run item's `MissionAttempt` (and its `Design`
  row) eagerly at cohort-assignment time, server-side — no name/objective/orbit collected. The
  student checklist (`LearnChecklist.tsx`) links straight into `DesignMissionPage.tsx` by that
  attempt id, entirely skipping `DesignBriefingPage.tsx` (the pre-attempt flow that normally gathers
  those via "Name this mission" — 4 guided objective prompts + LEO/SSO/GEO orbit presets, only run
  when a student starts a *catalog* mission on their own). `DesignMissionPage`'s own Setup tab did
  exist as a fallback (it's the wizard's default tab, so a program-linked run does land there first)
  but was just a bare free-text objective box with no orbit presets — no guided format at all.
  Extracted the briefing page's format into shared helpers in `missionsDesign.ts`
  (`OBJECTIVE_PROMPTS`, `joinObjectivePrompts`, `parseObjectivePrompts` — the parse direction
  reconstructs the 4 fields from an already-saved `design_objective` string, so editing a
  briefing-page-started run still round-trips instead of collapsing into one blob) and rebuilt Setup
  around them. Both entry paths now collect and display the same questions in the same format.

## 16. `LmsProgramItem.scope` — see `HANDOFF_COMPETITIONS.md` (2026-08-24)

`LmsProgramItem` gained a `scope` column (`individual|team`, default `individual`) and a sibling
progress table, `lms_program_team_item_progress`, for the new Competition domain. Every item that
existed before this stays `individual` and behaves exactly as documented above — this is additive,
not a change to the checklist model §11 describes. Full detail, including why it's a separate
table rather than a nullable second key on `LmsProgramItemProgress`, is in
[`HANDOFF_COMPETITIONS.md`](./HANDOFF_COMPETITIONS.md).

## 17. Roadmap board — the student checklist becomes a gated visual board (2026-09)

Replaces `LearnChecklist.tsx` (a flat numbered list) outright with a gated visual "board" —
clickable tiles connected by generated circuit-trace wires, a task drawer implementing
guideline → work → submit, individually addressable Madar design phases, and a desktop sidebar
in place of the old horizontal navbar. One student code path: a checklist with no gating/
checkpoints just renders as an ungated board where every unlocked tile reads "live" (there is no
longer a special "flat" mode). Design source: a client-supplied wireframe bundle (circuit-board
motif, "Ru'ya Space Race" reference content) — build from its layout/states/traces faithfully, but
the reference program's own nested six-item Madar checklist screen was explicitly **not** built;
the client's own authoring ask ("I click add mission as a checklist point, it asks me if I want a
specific phase") already described flat per-phase tiles instead, matching decision (2) below.

**Decisions locked with the client:**
1. **Flat Madar tiles, not a nested sub-checklist.** Each referenced design phase is an ordinary
   checklist item/tile in the serpentine, addressed via `LmsProgramItem.mission_step_key`. No
   `parent_item_id`, no second-level checklist screen. One program still has one design mission —
   several phase items on the same checklist share the same `mission_attempt_id` (see §11's
   `start_attempt` single-flight-resume note; this was verified, not assumed, before building).
2. **The board reads Madar automatically.** A phase tile flips to done by reading the design
   dashboard's own `steps[<key>]` validity (or an inferred signal for `setup`/`report`, which
   aren't real `DESIGN_STEP_LABELS` keys) — no student self-check, no instructor confirmation.
   **Superseded 2026-09** (see the "Self-check amendment" note at the end of this section) — every
   step except `report` now also needs the student's own explicit confirmation.
3. **Gating is per item, opt-in.** A `gated` checkbox means "locked until every earlier
   non-optional item on this checklist is done" — never a blanket sequential lock. Authoring has a
   "Gate everything in order" bulk action (client-side loop over the existing PATCH endpoint, no
   new backend route).
4. **Guideline videos are YouTube/Vimeo links, no upload.** The storage layer has no seekable
   streaming path for the `local` backend (Fernet-encrypts whole files, no range requests) and no
   resumable-upload API for `supabase`; building real upload was scoped and explicitly deferred.
   The Week 1 platform tutorial is a `guideline_kind="video"` item with `guideline_url` left empty
   — the drawer renders a "Start here · 3 min — video coming soon" placeholder until the client
   supplies the real link once they've recorded it.

**Backend — five additive columns on `lms_program_items`** (migration `a3f6d18c5b02`, no new
tables): `mission_step_key` (`setup|components|conops|power_budget|energy_budget|mass_budget|
data_budget|link_budget|cost_budget|report`, null = whole mission), `gated` (bool), `guideline_kind`
(`pdf|link|video`, null = no guideline), `guideline_url` (link/video only — a `pdf` guideline
reuses the item's own `pdf_path`/upload, see below), `checkpoint_label` (free text, groups tiles
into the board's row sections and the final-gate-bar summary — purely cosmetic, never a gating
boundary; the tile field is always one continuous serpentine sequence).

- `services/lms/program.py::compute_lock_states(items, statuses)` — pure function, no I/O: an item
  is locked iff `gated` and some *earlier* (by position) non-optional item isn't `done`.
  `awaiting_confirmation` doesn't count as done (a pending submission never unlocks the next tile).
  `checklist_item_locked()` re-derives this for one item and backs the 409 `complete`/`submit` now
  return for a locked item — the client's own lock/no-op is enforced server-side too.
- `refresh_item_progress`/`_mission_run_item_done` are phase-aware: when `mission_step_key` is set,
  status comes from the design dashboard, not `attempt.status`. `_design_dashboard_for_attempt`
  caches one `compute_dashboard()` call per `mission_attempt_id` per request (a `dashboard_cache`
  dict threaded through every caller that loops over a checklist's items) — several phase tiles
  sharing one attempt must not each recompute all six budgets. `setup` reads
  `design.design_objective is not None` (the guided Setup-tab prompts, not `design_name`, which
  always starts pre-filled `"My CubeSat"`); `report` reads `dashboard.all_valid`. **2026-09**: every
  key except `report` also requires `mission_step_key in design.confirmed_steps` — see the
  amendment note below.
- **A `pdf` guideline reuses the item's own `pdf_path` column and the existing
  `POST/DELETE /lms/admin/items/{id}/pdf` + `GET .../pdf-url` endpoints** — no new storage
  plumbing. Those three endpoints (plus the student-side resolver) now gate on
  `item_type == "pdf" OR guideline_kind == "pdf"`, not `item_type == "pdf"` alone, so a `manual`/
  `submission`/`mission_run`/etc. item can carry an uploaded PDF guideline the same way a real
  `pdf`-type item carries its own document.
- No new endpoints otherwise. Authoring's item create/update stayed generic (`**body.model_dump()`
  spread onto the ORM row) so the five new fields needed no router changes at all — only the
  schemas (`LmsProgramItemIn`/`Out`, `LmsProgramChecklistItemOut` += the five fields + derived
  `locked`) and the service layer.

**Frontend** (`frontend/src/pages/learn/board/`):
- `RoadmapBoard.tsx` — the route component (`/learn/checklists/$assignmentId`), replaces
  `LearnChecklist.tsx` (deleted). Order: banner (`<img>` at native ratio — `w-full h-auto`, the
  fix for the old fixed-height `bg-cover` clipping) → header + legend → next-task card → tile
  field → final gate bar.
- `roadmap.ts` — pure helpers shared by every board component: `tileState`, `computeLiveTaskId`
  (first non-optional, not-done, unlocked item — drives the next-task card and which tile pulses),
  `navTargetFor` (course/design/operate/mission/external/drawer/none), `iconForItem`,
  `groupByCheckpoint`, scroll-position save/restore (`sessionStorage`, keyed by assignment id —
  flow rule "back returns to the board at the same scroll position").
- `TileField.tsx` + `TraceLayer.tsx` — the serpentine desktop grid (3-ish rows of 4, `flex-row-
  reverse` on alternate rows, `useMediaQuery` picks desktop vs. the mobile alternating-column
  layout rather than reflowing one DOM tree, since the two are structurally different) and the
  generated SVG wires (measured via `ResizeObserver` inside an effect — reading `ref.current`
  during render, e.g. in a `useMemo`, is now a real lint error under this repo's React Compiler
  rules, not just a style nit). **Gotcha that cost real time to find**: the trace SVG's `-z-[1]`
  needs an ancestor that actually establishes a stacking context (`relative` **and** `isolate`, or
  an explicit `z-index`) — `position:relative` alone doesn't contain a negative-z-index child, so
  without `isolate` the wires silently paint behind the entire page instead of just behind the
  tiles. Caught only by an actual rendered screenshot; the DOM/computed-style inspection alone
  looked completely correct.
- `TaskDrawer.tsx` — every tile click (locked tiles are inert, no handler) opens the drawer rather
  than navigating directly; "direct navigation, no intermediate screen" (flow rule 1) describes
  what the drawer's own "do the work" row does, not the tile click itself. Steps are numbered
  dynamically (guideline is optional; a plain `manual`/`pdf`/`session` item or a submission with no
  reference link has no "do the work" row at all — only guideline + submit/mark-done) rather than
  with fixed indices, to avoid a real bug caught in visual testing: a hardcoded "step 2" rendered a
  dead "Open" row with nothing to open for exactly those item types.
- `LearnSidebar.tsx` (new, `pages/learn/**`-local — cannot import the portal's
  `components/layout/Sidebar`, see `LearnShell.tsx`'s own import-discipline note) replaces the old
  horizontal `LearnNav.tsx` (deleted) on desktop; `pages/learn/nav/LearnMobileTabBar.tsx` is the
  same bottom tab bar unchanged, just extracted into its own file. `BoardProgressContext` lets a
  mounted `RoadmapBoard` publish "N of M traces live" up to the sidebar's own panel without either
  file importing the other.
- `DesignMissionPage.tsx` gained `?phase=` (seeds/write-backs the wizard's active tab) so a phase
  tile can deep-link straight into one step of Madar — `mission_step_key` → tab value is 1:1 except
  `power_budget→power`, `energy_budget→energy`, `mass_budget→mass`, `report→dashboard`.
- `LmsProgramAdmin.tsx`'s `ItemForm` — "Which part of the mission?" phase picker (shown only for a
  `mission_run` item pointing at a `kind="design"` mission; `data_budget`/`link_budget`/
  `cost_budget` are filtered out of the *picker* per the client's "not used for this competition,"
  though the backend vocabulary keeps them — Madar itself still has them), the `gated` checkbox +
  toolbar bulk action, a `guideline_kind` picker that swaps between the existing PDF upload
  affordance and a URL field, and a free-text `checkpoint_label` with a datalist of labels already
  used on this checklist so a run of tiles doesn't drift on a typo.

**Not built**: video upload for guidelines (see decision 4); the reference wireframe's nested
Madar sub-checklist screen (see decision 1 — deliberately not built, not a gap).

**Self-check amendment (2026-09, post-ship)**: decision 2 above shipped a real usability bug —
`is_valid` alone (e.g. "at least one component added") flipped a phase tile straight to done
before the student had actually finished shopping/tuning that step. Fixed by adding an explicit
"Complete this step" click (`DesignMissionPage.tsx`), required in addition to `is_valid`, for
every step except `report` (which stays purely validity-driven — it's a read-only summary of the
other eight, not a step of its own to confirm).
- **`Design.confirmed_steps`** (migration `d4a72fe19b03`, JSONB, default `[]`) — `list[str]` of
  step keys (`setup` plus the 8 selectable `DESIGN_STEP_LABELS` keys minus `downlink`, which isn't
  a tab) the student has explicitly confirmed. Lives on `designs`, not `lms_program_items` —
  self-check is a fact about the design itself, not about any particular checklist tracking it
  (a design mission run outside any LMS checklist is a real case, e.g. from the Missions hub).
- **`POST /missions/design/attempts/{attempt_id}/steps/{step_key}/confirm`**
  (`routers/missions/design.py::confirm_design_step`) — re-validates the step's own requirements
  server-side (setup: `design_objective is not None`; else `dashboard.steps[key].is_valid`) and
  400s if they aren't met, so a client can't force a confirmation through. Idempotent. Rejects any
  key outside `CONFIRMABLE_STEP_KEYS` (`setup` + `DESIGN_STEP_LABELS` minus `downlink`) — `report`
  included, on purpose.
- `_mission_run_item_done` (services/lms/program.py) now requires both the step's own readiness
  AND `mission_step_key in design.confirmed_steps` (piggybacked onto the same cached dashboard
  fetch `_setup_done` already uses) for every key except `report`.
- Frontend: `DesignMissionPage.tsx` reads `state.confirmed_steps` from the server (replacing an
  earlier, briefly-shipped client-only `localStorage` version of this same idea, which only ever
  gated this page's own display and never reached the Roadmap board's checklist-item completion —
  the gap this amendment closes) and calls `confirmDesignStep` on the Complete button, disabled
  until `tabIsDone` says the step's real requirements are met.

## 18. `ground_station`-kind missions on the LMS checklist (2026-09)

**Hardware pairing, device ownership, websocket telemetry, thresholds/alerts and the live
command console are documented in [`HANDOFF_GROUND_STATION.md`](./HANDOFF_GROUND_STATION.md)**
(`backend/app/{models,routers,services}/ground_station/`, `frontend/src/pages/ground-station/`,
`frontend/src/pages/learn/GroundStationAttemptPage.tsx`) — not here. This section covers only how
a `ground_station`-kind mission surfaces as an ordinary `mission_run` checklist item, since that
plumbing is genuinely this file's (`services/lms/program.py`).

- **Attempt lifecycle is generic, not kind-specific**: a `ground_station` mission is created,
  gated by readiness/access_mode, and its `MissionAttempt` started through the exact same
  `start_attempt()`/`assign_mission_run()` paths every other kind uses (§4) — `ground_station` was
  deliberately left out of `VERIFIER_KINDS` (§4) because it never gets *graded*, but it's a normal
  `Mission`/`MissionAttempt` row in every other respect: cohort attribution, prerequisites, ops
  assignment via `POST /missions/admin/attempts/assign`, all unchanged.
- **"Done" on the checklist is `attempt.status == "passed"`, set by the student's own self-serve
  complete call** — `POST /ground-station/attempts/{id}/complete`
  (`routers/ground_station/attempts.py::complete_attempt`), idempotent, no `mission_step_key`
  involved (a ground_station `mission_run` item is always whole-mission, never phase-split the way
  a design item can be). `services/lms/program.py::_mission_run_item_done` reads this the same
  way it reads any other kind's plain "attempt passed" case — the design-specific
  dashboard/confirmed-steps branch (§17) never runs for a `ground_station` attempt. **No points,
  no `decide_attempt`, no verifier runs** — marking a ground_station run done only flips the one
  field the checklist auto-tracking reads; if this domain ever needs to actually grade a
  ground_station run (vs. today's "did the exercise" completion), that's new work, not a flag flip.
- **The ops Progress tab's "View run" vs. "Open console" split** (`components/
  LmsProgressAndMissions.tsx::AssignmentItemRow`, PR #87, 2026-09-16) — `assignment_item_detail()`
  (`services/lms/program.py`) threads `mission_kind` onto every item it returns (a fresh `Mission`
  lookup keyed by `item.mission_id`, batched once per call, not per item). The row picks the button
  by that field: `mission_kind === "design"` → **View run** (`DesignRunDetail`, reads a `Design`
  row via the design-detail endpoints, §14); `mission_kind === "ground_station"` → **Open console**
  (navigates straight to `/learn/missions/ground-station/$attemptId`, the same live console page
  ops can already reach from the Ground Station page). **Before this fix, every `mission_run` item
  got the View-run button unconditionally** — clicking it on a ground_station attempt 500'd,
  because `DesignRunDetail` calls the design-detail endpoint against an attempt with no `Design`
  row at all. **Gotcha for a third mission kind**: `operate`-kind `mission_run` items get *neither*
  button today (`canViewRun`/`canOpenConsole` are both false for `mission_kind === "operate"`) —
  not a bug exactly, just unbuilt; nobody has put an `operate` mission behind an LMS checklist item
  in production yet, so a staff "watch this live" affordance for it was never asked for. If that
  changes, this is the file and the pattern to extend.
- Same staff-can-view-not-submit posture applies here as everywhere else — see §4's `GET
  /missions/attempts/{id}` bullet; a Ground Station device/console permission model of its own
  (who may pair a device, issue a command, etc.) is `HANDOFF_GROUND_STATION.md`'s to document.

## 19. Cohort Knowledge Quiz (2026-09)

A brand-new, LMS-checklist-only quiz domain — not documented at all before this pass. Tables:
`cohort_quiz_questions`, `cohort_quiz_templates`, `cohort_quiz_template_questions`,
`cohort_quiz_attempts`, `cohort_quiz_answers` (`backend/app/models/lms/cohort_quiz.py`). Backend:
`services/lms/cohort_quiz.py` (+ `cohort_quiz_importer.py` for bulk CSV/XLSX question import),
`routers/lms/cohort_quiz_admin.py` (`/lms/admin/cohort-quiz/*`, `require_lms_content`). Frontend:
`LmsCohortQuizAdmin.tsx` (ops authoring, the sidebar's new "Quiz Bank" item — §8), `CohortQuizPage.tsx`
(student play, `/learn/...`).

- **Deliberately a third, separate quiz-shaped domain** — the model's own docstring is explicit
  about why it isn't a fourth copy of an existing shape: `ModuleItem.kind="quiz"`
  (`services/lms/quiz.py`) is in-course practice, random-N sampling from one course's own pool,
  unlimited retries; `instructor_assessment` is a randomized scenario draw for instructor
  applicants. This one is a **per-cohort diagnostic** — every student assigned the same checklist
  item gets the exact same hand-picked, ordered question set (`CohortQuizTemplateQuestion`, not a
  draw-size config), and gets exactly **one attempt, no retries** (`UNIQUE(program_item_id,
  user_id)` on `cohort_quiz_attempts`). `topic` on a question is a free-text tag, not a `Course` FK
  — a cohort quiz is meant to cross-cut topics that don't map 1:1 to a real course.
  `question_order`/`option_order` freeze at attempt-start (`CohortQuizAttempt.question_order`,
  JSONB) so a mid-attempt refresh never reshuffles — same idiom `AssessmentAttempt.question_order`
  already uses for instructor applicants.
  `question_id` is `ondelete="SET NULL"` on the template-question join, on purpose: retiring a bank
  question must not silently shrink a template already handed to a cohort.
- **It's framed as a diagnostic, not a pass/fail gate** — same posture as the whole-course
  completion model. `services/lms/program.py::_cohort_quiz_item_done` only checks the attempt was
  *submitted*; `score`/`topic_breakdown` never factor into whether the checklist tile goes green.
  `topic_breakdown` (`{"<topic>": {"correct", "total"}}`) is per-attempt only — a cross-cohort
  strengths/weaknesses view is computed live by summing every submitted attempt
  (`get_student_topic_breakdown`), never stored as a rollup.
- **Checklist wiring**: `quiz` joined `course`/`mission_run` in `AUTO_TRACKED_TYPES`
  (`services/lms/program.py`) — no student self-check, status is always derived. A checklist
  `quiz` item's `LmsProgramItem.cohort_quiz_template_id` points at the template; student endpoints
  are cohort/assignment-scoped, not global: `POST /lms/programs/{assignment_id}/items/{item_id}/
  quiz/{start,submit}`, `GET .../quiz/result` (`routers/lms/student.py`). Instructor read-only
  result view mirrors this at `routers/lms/instructor.py` (cohort-scoped, same `require_cohort_access`
  posture as everything else instructor-side in this domain).
- **Not built**: retries of any kind (a genuinely locked-in v1 decision, not a gap); per-question
  time limits beyond the existing per-question timer auto-submitting blank on timeout (that part
  is built — see `CohortQuizAnswer`'s own docstring on `selected_option_index=None`).
