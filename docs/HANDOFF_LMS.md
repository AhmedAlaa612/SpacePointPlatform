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
`program_curriculum`, `cohort_curriculum`.

- `Course.access_mode` is `open | invite | paid` — governs **self-enrol eligibility only**, and
  self-enrol (`POST /lms/enroll`) is `require_lms_student`: **staff can never self-enrol in
  anything**, regardless of a course's mode. Staff access is always an ops-granted `Enrollment`
  row (`source="ops"`).
- `GET /lms/catalog` (`routers/lms/student.py`) returns every published course to a student
  (self-enrol into `open`, browse the rest as a locked preview) — but for anyone else, it's
  scoped to courses they actually hold an active `Enrollment` in. Otherwise a staff browse
  showed a wall of courses that 403 on click except the handful they'd been enrolled into.
  `admin`/`operations` keep the unscoped full catalog (they need it for oversight).
- Video: encrypted-at-rest sources, HLS transcode pipeline, per-video watch checkpoints
  (`video_checkpoints`). See `HANDOFF_VPS_DEPLOYMENT.md` §6 for where the buckets live on disk
  and the TCP-congestion-control lesson from getting first-segment latency down.
- `program_curriculum` / `cohort_curriculum` are how a course attaches to the Sessions domain's
  Programs/Cohorts (see `HANDOFF_SESSIONS.md`) — a different attachment path than a student's
  own enrollment.

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
`mission_teams`, `mission_team_members`, `mission_managers`, `mission_assignments`,
`mission_proposals`, plus the design-mission-specific `design_component_library`, `designs`,
`design_modes`, `design_components`, `design_component_mode_states`, and one table per budget
(`design_data_budget_entries`, `_power_`, `_mass_`, `_cost_`, `_link_budget_entries`).

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
- **Operate mission** — a real orbital simulation (not a quiz about one), rebuilt 2026-08-13.
  Objectives are graded live against state, not just a final score.
- **`mission_managers`** (7B-7) — staff can assign an intern/other staff as a mission's manager:
  they get its stats, review queue and teaching content, but **cannot edit grading
  config/points once published** — that stays frozen while live, edit the mission back to draft
  first. UI for this (`MissionAuthorsSection.tsx` on `LmsMissionDetail.tsx`) existed in the
  backend since 7B-7 but had no screen until 2026-08-14 — check the actual git log before
  assuming a backend capability is reachable from the UI.
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

frontend/src/pages/lms-authoring/  # staff surface
  LmsCourses.tsx, LmsCourseDetail.tsx, LmsCurriculum.tsx, LmsLearningPaths.tsx
  LmsMissions.tsx, LmsMissionDetail.tsx, LmsDesignLibrary.tsx   # the component library editor
  LmsGames.tsx, LmsGameDetail.tsx
  LmsProgressGrid.tsx, LmsStudents.tsx, LmsStudentDetail.tsx
  LmsInviteCodes.tsx
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
