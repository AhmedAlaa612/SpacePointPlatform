# LMS / Missions / Games Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

**Status: LIVE in production** (`portal.spacepoint.ae/learn`, staff-side at `/lms-authoring`).
This domain didn't exist when `HANDOFF.md` was last written top-to-bottom — it's grown into
one of the largest surfaces in the codebase (courses, missions, live quiz games, a real
component catalog, student accounts) with no map of its own until now. If you're here because
`HANDOFF.md` §7 pointed you at a table you don't recognize, this is where it lives.

---

## 1. Two surfaces, one backend

- **`/learn`** — the student-facing app. Own shell (`LearnShell.tsx` + `LearnNav.tsx`), own
  login/signup, mounted **outside** the portal's `AppShell`/`Sidebar` — same precedent as
  `ApplicantShell`. Mobile-first: content is full-bleed, a bottom tab bar on phones. **Import
  discipline**: nothing under `frontend/src/pages/learn/**` may import
  `components/layout/Sidebar` or anything under `pages/operations/**`.
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

- **`Mission.kind`** ∈ `design | submission | quiz | checklist | operate | external`
  (`VERIFIER_KINDS`, `services/missions/verifiers/__init__.py`) — one verifier module per kind
  (`verifiers/design.py`, `operate.py`, `quiz.py`, `submission.py`) grades/dispatches an
  attempt. A `missions` row has no `mission_id` per student — **all of a design mission is one
  `missions` row**, `kind='design'`, with up to three `mission_variants` (difficulty levels:
  Cadet/Engineer/Flight Director) a student picks from. Don't create a mission per cohort or
  per subsystem.
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
  LearnShell.tsx, LearnNav.tsx     # own shell/nav — see import-discipline note in §1
  LearnLanding.tsx                 # /learn home — hero is <SatkitAssembly>, see §9
  LearnCatalog.tsx, LearnCourse.tsx, LearnPlayer.tsx, LearnPaths.tsx, LearnProgram.tsx
  MissionCatalog.tsx, MissionPage.tsx, DesignMissionPage.tsx, DesignBriefingPage.tsx
  OperateMissionPage.tsx, OperateBriefingPage.tsx, OperateDebriefPanel.tsx
  LearnGames.tsx, GamePlay.tsx, LearnLeaderboard.tsx

frontend/src/pages/lms-authoring/  # staff surface (+ instructor, cohort-missions only — see §4)
  LmsCourses.tsx, LmsCourseDetail.tsx, LmsCurriculum.tsx, LmsLearningPaths.tsx
  LmsMissions.tsx, LmsMissionDetail.tsx, LmsDesignLibrary.tsx   # the component library editor
  LmsGames.tsx, LmsGameDetail.tsx
  LmsProgressGrid.tsx, LmsStudents.tsx, LmsStudentDetail.tsx
  LmsInviteCodes.tsx
  CohortMissions.tsx    # instructor/facilitator/operations: progress, gates, review (§4)
```

Ops-role sidebar nav says **"LMS"**, not "LMS Courses" — it covers all of the above now, not
just courses. Facilitator/instructor nav still says "LMS Courses" (different audience,
deliberately unchanged).

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
nav-labeled "Programs"), `frontend/src/pages/lms-authoring/LmsProgramAdmin.tsx` (ops authoring,
same `/lms-authoring/curriculum` route + Sidebar slot the old curriculum page used, relabeled
"Programs" — replaces `LmsCurriculum.tsx` outright), and a new "Program" tab in
`frontend/src/pages/lms-authoring/CohortMissions.tsx` (instructor roster + confirm, cohort-scoped
like its Steps/Gates/Review siblings but not mission-scoped).

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
  same shape as the Poster tab), `article`, `manual`. `optional` items don't block the
  certificate; `requires_confirmation` items need an instructor/ops confirm click instead of the
  student's own self-check (self-check is the default everywhere else — operator call: "not
  everything can be trackable").
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
