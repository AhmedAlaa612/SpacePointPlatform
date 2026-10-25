# SpacePoint Unified — Handoff

**Entry point for anyone (human or agent) picking up this codebase.** This file is a *map*:
where everything is and what it does. Depth lives in the per-domain files linked below.

**Last verified against the code: 2026-10-11**, covering the Website CMS, E-Commerce Store, SpacePoint Labs integration (`spacepoint.ae` & `labs.spacepoint.ae`), Observer Mode, the unified Student & Observer Operations Hub, Invite Code Grants, and Judging toolbar fixes.

---

## 1. Status in one table

| | |
|---|---|
| **Live at** | `https://portal.spacepoint.ae` · Marketing site: `https://spacepoint.ae` · Labs: `https://labs.spacepoint.ae` |
| **Schema head** | `a8c4e2f91b05` — single Alembic head (SpacePoint Mission Arcade games & program item links). Production follows `main` deploys; the API container runs `alembic upgrade head` before binding its port |
| **Branch** | `main` = production. `v2-dev` tracks it |
| **What's live** | Registration, bulk import, check-in, staffing marketplace, attendance, certificates, calendar, ops dashboard, **inventory end to end**, interns/ambassadors/instructors/internship letters, **Mentorship Domain** (satellite & space mentors, ops tags, Option A Meet links, attendance gateway), **Public Website CMS & E-Commerce Store** (`/admin/website`, `/operations/inventory/website`, `/admin/shop`, `/operations/inventory/shop` powering `spacepoint.ae` and `labs.spacepoint.ae`) — **LMS/Missions/Games domain**: student and observer accounts, courses + encrypted-HLS video, learning paths, CubeSat design + Flight Operations missions, Live Quiz games, **SpacePoint Mission Arcade** (`/learn/arcade` — 51 interactive engineering/science simulations across 8 subsystems with Explorer/Engineer tracks, guideline briefings, and program checklist auto-pass verification), cohort-scoped instructor progress/gating/review, **LMS Program checklists**, **Invite-Code Grants** (instant course/path/cohort provisioning for student & observer batches), **Student & Observer Operations Hub** (`/lms-authoring/students` with live checklist trees, team progress cards, direct course/path assignment, and unenroll), and **Competition Judging with Observer Partitioning** (`JudgeTeams.tsx` with top toolbar toggling `Students | Observers | All`, blind scoring, rubric builder, timing windows, and analysis dashboard). See [`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md), [`HANDOFF_LMS.md`](./HANDOFF_LMS.md) & [`HANDOFF_COMPETITIONS.md`](./HANDOFF_COMPETITIONS.md) |
| **Tests** | Collected via `pytest` from `backend/`. Requires live Redis for worker tasks |

## 2. Read next

| Read | For |
|---|---|
| [`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md) | **Marketing Website (`spacepoint.ae`), SpacePoint Labs (`labs.spacepoint.ae`), & E-Commerce Store** — 12-tab Portal CMS (`WebsiteManagement.tsx`), Stripe store (`Shop.tsx`), public hydration APIs, lead email forwarding, `deploy-website.sh` & `deploy-labs.sh` |
| [`HANDOFF_LMS.md`](./HANDOFF_LMS.md) | Student & Observer accounts, courses, learning paths, missions, live quiz games, **SpacePoint Mission Arcade (`/learn/arcade`)**, checklist programs, **Student Operations Hub (`/lms-authoring/students`)**, **Invite-Code Grants**, and **Observer Mode Architecture** (§21–25) |
| [`HANDOFF_COMPETITIONS.md`](./HANDOFF_COMPETITIONS.md) | Competitions, team-scoped checklists, rubric scoring, judging surface (`JudgeTeams.tsx`), team analytics (`CompetitionAnalysis.tsx`), and **Observer Sandbox Teams Partitioning** (§6) |
| [`HANDOFF_GROUND_STATION.md`](./HANDOFF_GROUND_STATION.md) | Live CubeSat telemetry/command console, device provisioning, Redis pub/sub websocket flow, alerts/thresholds |
| [`HANDOFF_SPINE.md`](./HANDOFF_SPINE.md) | Contacts / identity matching / merge review / `replace_user_email` synchronization |
| [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md) | Programs, cohorts, sessions, registration, staffing, delivery |
| [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md) | Applicant pipeline, contracts, payments, certificates, assessments |
| [`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md) | Projects, epics, tasks, kanban, teams |
| [`HANDOFF_INTERNSHIP.md`](./HANDOFF_INTERNSHIP.md) | HR-side intern pipeline: role request -> admin approval -> in-app-signed internship letter |
| [`HANDOFF_AMBASSADORS.md`](./HANDOFF_AMBASSADORS.md) | Leads, points/titles/badges, teacher sessions, the task approval state machine |
| [`HANDOFF_VPS_DEPLOYMENT.md`](./HANDOFF_VPS_DEPLOYMENT.md) | VPS environment, deploy scripts (`deploy-backend.sh`, `deploy-frontend.sh`, `deploy-website.sh`, `deploy-labs.sh`), auto-rollback logic, storage layout |
| [`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md) | Cloudflare R2 video storage, transcode pipeline, playback tokens, HLS mechanics |
| [`HANDOFF_TUTORIALS.md`](./HANDOFF_TUTORIALS.md) | **Interactive Onboarding & Live Action Guides (`react-joyride` v3)** — `TourContext.tsx`, `lib/tours/index.ts`, `SpacePointTourCard.tsx`, dynamic hidden-tab filtering, per-step spotlight memory, and multi-page live action walkthroughs across Portal & LMS |
| [`OPS_BACKUPS.md`](./OPS_BACKUPS.md) | Database backup script — usage, cron, restore |

---

## 2.5 Fast Navigation Map (Zero-Effort Code Exploration)

*Use this cheat sheet to jump directly to the right files without grepping across the codebase.*

| Feature / Domain | Frontend UI | Backend Router | Backend Service / Model |
|---|---|---|---|
| **SpacePoint Mission Arcade** | `pages/learn/LearnArcade.tsx`<br/>`pages/learn/LearnArcadeGame.tsx` | `routers/lms/arcade.py` | `services/lms/arcade.py`<br/>`models/lms/arcade_game.py` |
| **Website & Labs CMS (12 Tabs)** | `pages/admin/WebsiteManagement.tsx` | `routers/admin/website.py`<br/>`routers/admin/website_config.py`<br/>`routers/admin/website_people.py`<br/>`routers/public_content.py`<br/>`routers/public_website.py` | `models/website_cms.py`<br/>`models/website_config.py`<br/>`models/website_people.py` |
| **Store & Merchandise (Stripe)** | `pages/admin/Shop.tsx` | `routers/admin/store.py`<br/>`routers/public_store.py` | `models/store.py` |
| **Student & Observer Roster** | `pages/lms-authoring/LmsStudents.tsx` | `routers/lms/admin.py::search_students` | `services/lms/students.py::search_students` |
| **Student & Observer Detail** (Manage Page) | `pages/lms-authoring/LmsStudentDetail.tsx` | `routers/lms/admin.py::get_student_detail` | `services/lms/students.py::get_student_detail`<br/>`models/user.py`, `models/lms/program.py` |
| **Invite Codes & Grants** | `pages/lms-authoring/LmsInviteCodes.tsx` | `routers/lms/admin.py::/invite-codes/*` | `services/lms/invite_grants.py`<br/>`models/instructors/invitation_code.py`<br/>`models/lms/invite_grant.py` |
| **Judge Teams Portal** | `pages/judge/JudgeTeams.tsx` | `routers/competitions/judge.py::list_my_teams` | `services/competitions/judges.py`<br/>`models/team.py` |
| **Judge Team Scoring & Runs** | `pages/judge/JudgeTeamDetail.tsx`<br/>`pages/lms-authoring/components/DesignRunDetail.tsx` | `routers/competitions/judge.py::put_my_team_score` | `services/competitions/judging.py`<br/>`models/competitions.py` |
| **Admin Judging Management** | `pages/admin/CompetitionJudging.tsx`<br/>`pages/admin/components/CompetitionAnalysis.tsx` | `routers/competitions/admin.py` | `services/competitions/analytics.py`<br/>`services/competitions/judging.py` |
| **Course & Path Enrollments** | `pages/lms-authoring/LmsStudentDetail.tsx` | `routers/lms/admin.py::assign_student_courses` | `services/lms/enrollment.py::enroll` |
| **User & Contact Email Sync** | `pages/admin/Users.tsx`<br/>`pages/lms-authoring/LmsStudentDetail.tsx` | `routers/admin/users.py`<br/>`routers/lms/admin.py` | `services/spine/identity.py::replace_user_email` *(Mandatory helper)* |
| **Student App Shell (`/learn`)** | `pages/learn/LearnShell.tsx`<br/>`pages/learn/nav/LearnSidebar.tsx` | `routers/lms/student.py` | `services/lms/progress.py` |
| **Tutorials & Live Action Guides (`react-joyride` v3)** | `context/TourContext.tsx`<br/>`lib/tours/index.ts`<br/>`components/ui/SpacePointTourCard.tsx` | *(Frontend-managed via `localStorage` per-step IDs)* | — |

### Critical Codebase Invariants (Avoid Pitfalls)
1. **Never Nest Control Bars Inside Conditional Empty States**: Filter/search toolbars (such as `Students | Observers | All`) must **always** sit above `{isLoading ? <Spinner/> : items.length === 0 ? <EmptyState/> : <List/>}` so users are never trapped when an active filter is empty.
2. **Keyed React Fragments in Lists**: When returning multiple elements (like sibling `<tr>`s) inside `.map()`, always use `<Fragment key={id}>`, never `<>`.
3. **Email Updates Require Spine Sync**: Updating a user's email address must always invoke `replace_user_email(db, user, new_email)` so that `users.email`, `contacts.email`, and `identity_aliases` remain consistent.
4. **Invite Code Pool Checks**: Invite code validation and grants endpoints must check `kind.in_(["student", "observer"])`, not `kind == "student"`.

---

## 3. Stack

**Frontend** — React 19, Vite, TanStack Router + Query, Tailwind, Radix, TypeScript.
**Backend** — FastAPI (async), SQLAlchemy 2 (`asyncpg`), Alembic, Pydantic v2, Python 3.11.
**Jobs** — ARQ + Redis (`backend/app/workers/`).
**Docs/PDFs** — `docxtpl` + headless LibreOffice, ReportLab, Pillow, `qrcode`, `cairosvg`.
**Auth** — JWT (`python-jose`) + bcrypt. **Storage encryption** — Fernet.

---

## 4. Where things live

```
backend/
  app/
    main.py            # app, router mounting, CORS, lifespan (ARQ pool), /health
    core/              # config.py · dependencies.py (auth + role guards) · security.py · rate_limit.py
    db/                # session.py · base.py
    models/            # SQLAlchemy — top-level = shared; subdirs = per domain
    routers/           # HTTP layer — mirrors models/ layout
    schemas/           # Pydantic in/out — mirrors routers/ layout
    services/          # business logic; documents/ holds PDF+DOCX generation
    workers/           # ARQ: settings.py (safe_enqueue) · main.py · tasks/
    static/            # fonts, DOCX/PNG templates, branding
  alembic/versions/    # migrations — SOURCE OF TRUTH for the schema
  tests/               # mirrors routers/ + services/
  seed.py              # creates the admin account from ADMIN_EMAIL/ADMIN_PASSWORD
frontend/src/
  router.tsx           # route tree + client-side guards
  context/AuthContext.tsx   # user, roles, active-role switch
  api/<domain>/        # thin fetch wrappers, one file per router group
  pages/<domain>/      # UI
  components/          # ui/ primitives · layout/ (Sidebar owns all nav)
```

| Task | Go to |
|---|---|
| Add an endpoint | `backend/app/routers/<domain>/` |
| Business rules | `backend/app/services/<domain>/` |
| DB model | `backend/app/models/<domain>/` |
| Schema change | edit model → `alembic revision --autogenerate` → **review it** |
| Role gating | `backend/app/core/dependencies.py` |
| A page | `frontend/src/pages/<domain>/` + route in `router.tsx` + nav in `components/layout/Sidebar.tsx` |
| Background job | `backend/app/workers/tasks/` + register in `WorkerSettings.functions` |
| File upload/download | `services/storage.py` (facade — never import the backends directly) |

---

## 5. URL map

**Backend** (mounted in `main.py`). **There is no `/api` prefix** — nginx strips it before the
app sees the request.

| Path | Router |
|---|---|
| `/auth/*` | login, refresh, instructor apply |
| `/admin/users/*` | generic user management (admin only) |
| `/interns/*` · `/ambassadors/*` · `/instructors/*` | the three original domains |
| `/sessions/*` | programs, cohorts, registrations, staffing, delivery, check-in, calendar, dashboard, imports |
| `/spine/*` | contacts, merge reviews |
| `/inventory/*` | locations, warehouses, item catalogue (+ categories, variant grouping), kit templates, kits, stock, movements, `/my-kits`, the session loop (`/sessions/{id}/kits`, checks, receipt/return reporting), equipment pickup (`/sessions/{id}/equipment`) and the storekeeper queue (`/fulfilment`) |
| `/lms/*` | student catalog + enrollment, course outline/player, video, curriculum, learning paths, points/leaderboard, admin course/module CRUD, progress grid. See `HANDOFF_LMS.md` |
| `/missions/*` | design mission (state, budgets, component library), operate mission, proposals, teams, manager dashboards, cohort-scoped instructor dashboards (progress/gating/review), admin CRUD. See `HANDOFF_LMS.md` |
| `/games/*` | Live Quiz authoring, live run control + realtime, student play. See `HANDOFF_LMS.md` |
| `/admin/website/*` · `/admin/store/*` | Website CMS (12 tabs: leads, newsletter, articles, press, programs, missions, labs, team, ambassadors, alumni, sponsors, FAQs/config) + Store & Merchandise CRUD (`require_operations`). See [`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md) |
| `/public/*` | registration form, catalog, ticket, **plus public Website CMS, Labs projects, Store checkout, Lead submission (`POST /public/leads`), and Newsletter subscription** — **no auth** |
| `/apply/*` · `/files/*` · `/documents/*` · `/notifications/*` | shared |
| `/health`, `/health/worker` | liveness + ARQ heartbeat |

**Frontend** domains — each has its own sidebar in `Sidebar.tsx::getNavItems`:
`/interns` · `/ambassadors` · `/instructors` · `/admin` (platform management, including `/admin/website` and `/admin/shop`) ·
`/operations` (running the business: programs, cohorts, contacts, check-in, calendar, and
`/operations/inventory/*` for kits, stock, fulfilment, the catalogue, `/operations/inventory/website`, and `/operations/inventory/shop`).
**`/learn`** is a separate surface for the `student` role — own shell, not part of `Sidebar.tsx`
at all (see `HANDOFF_LMS.md` §1) — with staff-facing authoring at `/lms-authoring` living inside
the normal `AppShell` like everything else.
Public, no auth: `/login`, `/apply/*`, `/t/{ticketToken}`.

---

## 6. Roles

13 roles (`backend/app/models/enums.py::UserRole`): `admin`, `intern`, `leader`, `applicant`,
`instructor`, `facilitator`, `ambassador`, `teacher`, `operations`, `coo`, `storekeeper`,
`student`, `judge`.

A user holds an **array** of roles (`users.roles`) — there is no single role column. The
"active role" is a client-side choice only (`localStorage`); the backend authorizes purely on
the array.

| Role | Domain | Notes |
|---|---|---|
| `admin` | all | **Passes every `RequireRole` check unconditionally** |
| `operations` | `/operations` | Runs the business — programs, cohorts, registrations, contacts, check-in, calendar |
| `coo` | `/operations/inventory` | Approves inventory purchases and cross-border transfers. **Not** an ops account: `require_operations` rejects it |
| `storekeeper` | `/operations/inventory/stock` · `/fulfilment` | Restocks kits, receives goods, records stock movements, works the fulfilment queue. **Deliberately narrow** — no session assignments, no kit create/edit/delete, no catalogue, no full ledger. Enforced by `require_operations` not listing it. Its sidebar is three items because everything else would 403 — but the reads those three pages need (`/inventory/stock`, `/overdue`, `/locations`, `/fulfilment`) are `require_storekeeper`. Getting that wrong made the role unusable for two days without erroring |
| `instructor` / `facilitator` | `/instructors` | Delivery: their assigned sessions, attendance, reports |
| `applicant` | `/instructors` | Pre-approval pipeline; gets a minimal shell, no sidebar |
| `intern` / `leader` | `/interns` | |
| `ambassador` / `teacher` | `/ambassadors` | |
| `student` | `/learn` | **Not a portal role.** A separate learner surface, own shell/auth, no sidebar, no role switcher. Has no portal home — `roleHomePath()` sends it to `/learn`, same function the `"/"` index redirect uses. See `HANDOFF_LMS.md` §1 |
| `judge` | `/judge` | Temporary, cohort-scoped Competition domain account (2026-08-24), zero ops access — invited by ops per cohort, not self-applied. Uses the ordinary portal shell (unlike `student`), but only one page. See `HANDOFF_COMPETITIONS.md` §2 |

---

## 7. Domains and their tables

Alembic is the source of truth for the exact schema — this is orientation, not a column list.

| Domain | Tables |
|---|---|
| **Shared** | `users`, `notifications`, `documents`, `document_requests`, `document_templates` (now with `student_completion` and `workshop_delivery` system templates seeded — `d8a2c94e0035` / `e1b3d05f0036`), `certificates`, `applications`, `application_questions`, `id_cards`, `portal_settings` |
| **Website, Store & Labs** | `website_leads`, `newsletter_subscribers`, `website_articles`, `press_mentions`, `sponsors_partners`, `website_faqs`, `website_settings` (`WebsiteConfig`), `website_programs`, `website_resources`, `labs_projects`, `team_members`, `website_ambassadors`, `alumni_members`, `student_missions`; `store_products`, `store_orders`, `store_order_items`, `discount_codes`. Full detail in [`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md) |
| **Spine** | `contacts`, `contact_relationships`, `organizations`, `identity_aliases`, `merge_reviews`, `touchpoints`, `contact_role_events`, `consent_records` *(schema only — nothing writes to it)* |
| **Sessions** | `programs`, `cohorts`, `sessions`, `session_instructors` (`role_id` → `delivery_roles`, not a `lead\|co` string since I5-3), `delivery_roles`, `session_openings`, `session_addons`, `session_materials`, `session_call_targets`, `session_calls` (multiple concurrent calls per session — `c4e7a39f0028`), `cohort_openings` (cohort-level opening defaults — `b3d6f28e0027`), `cohort_calls` (grouped cohort-wide staffing campaigns — `e7c4a92d0036`), `cohort_instructor_assignments` + `cohort_call_interests` (**cohort-level staffing**, 2026-08-24 — see below), `delivery_checklist_items` / `instructor_session_days` / `instructor_checklist_progress` (the **instructor daily loop**), `payment_session_coverage` (which sessions one payment line covers), `registrations`, `registration_sessions`, `attendance_records`, `instructor_interests`, `session_reports`, `import_batches`, `activities` / `activity_versions` / `activity_assignments` *(quiz — schema only until the LMS games phase)*. Cohorts and sessions now have `location_id` → `locations` (`a2c5e17d0026`; `locations.address`/`maps_url` live on the entity); `locations.city_id` → `cities` (8 seeded UAE cities) is the anchor — `locations.country` is legacy/derived-only and nullable, never entered directly (see §8) |
| **Inventory** | `locations`, `items`, `kit_templates`, `kit_template_items`, `kits`, `kit_items`, `stock_levels`, `movements`, plus `session_kits` / `kit_checks` (I2-1/I2-2) — and, since 2026-08-01: `item_categories` (`d2e6f81a0029`), `warehouses` (`f8d9e21a0033`, `c4f1a83b0034` — **stock and kits now key on `warehouse_id`; a location is the union of its warehouses**), `cohort_kits` (cohort-level kit defaults, `a3c7f95e0037`), and `items.variant_group`/`variant_label` (T-shirt-style size grouping, `d1e4c73f0038`). **`items.is_consumable` is gone** (`a7c9e15f0032` — everything now counts toward kit completeness). **Kit custody legs were replaced** (`e3f8b04c0030`): there is no issue/collected/return movement flow; `session_kits` carries `received_at` / `return_status` / `returned_at` / `ops_confirmed_at` instead, and moving a kit to a shelf is an ordinary `movements` row. Equipment pickup (I2-7) adds no tables — it is a form over `items` + `stock_levels` + `movements` with a persisted "returning later" flag (`f4a1c65d0031`). `movements` is the single ledger every physical thing passes through — issue, return, transfer, refill, receive, write-off, adjust — and either side of it can be a location, a person or a kit. Custody keys on `users`, so nothing here touches `MERGE_FK_REGISTRY`. `POST /inventory/stock/adjust-bulk` writes one item across every warehouse in one transaction (`StockCountModal.tsx`); `POST /inventory/kits/{kit_id}/count` (`require_storekeeper`, a deliberate narrow exception to this router's usual `require_operations`) lets a storekeeper count a kit's contents directly instead of going through individual stock rows |
| **LMS / Missions / Games** | `courses`, `course_modules`, `module_items`, `module_videos`, `video_checkpoints`, `enrollments`, `item_progress`, `learning_paths`, `learning_path_steps`, `point_events`, `program_curriculum`, `cohort_curriculum`; `missions`, `mission_variants`, `mission_attempts` (now with `cohort_id`, resolved eagerly at attempt-start for every kind), `mission_attempt_members`, `mission_teams`, `mission_team_members`, `mission_managers`, `mission_assignments`, `mission_proposals`, `mission_step_gates` (per-cohort Design-mission step gating), `design_component_library` + the design-mission budget tables; `arcade_games`, `arcade_game_attempts` (SpacePoint Mission Arcade simulator); `games`, `game_questions`, `game_runs`, `game_participants`, `game_answers`, `game_session_assignments`, `game_session_questions`; plus the shared `curriculum.prerequisites` DAG (courses and missions as interchangeable items). Full detail in `HANDOFF_LMS.md` |
| **Competitions** | A competition is a `Program` with `program_type="competition"` — no new column there. `lms_program_items.scope` is a new column on the existing LMS Program tables; `lms_program_team_item_progress` is the team-scoped twin of `lms_program_item_progress`. Judging adds `competition_rubrics`/`competition_rubric_criteria`/`competition_scores`/`competition_result_publications`/`competition_judges`, plus a `judge` role. Registration import + progression reuse existing Session/LMS tables, no schema of their own. Full detail in `HANDOFF_COMPETITIONS.md` |
| **Instructors** | `applicant_profiles`, `application_reviews`, `video_submissions`, `checklist_*`, `module_submissions`, `presentation_submissions`, `assessment_submissions`, `invitation_codes`, `instructor_profiles`, `instructor_documents`, `training_*`, `library_*`, `payment_batches`, `payment_letters`, `payment_sessions`, `payment_addons`, `instructor_bank_details` |
| **Interns** | `projects`, `teams`, `epics`, `modules`, `tasks`, `task_submissions`, `proposals`, `mind_map_layouts` + join tables |
| **Ambassadors** | `leads`, `lead_comments`, `points_transactions`, `titles`, `badge_definitions`, `achievements`, `teacher_sessions`, `ambassador_tasks`, `materials`, `system_settings` |

> **`payment_sessions` is not a sessions-domain table**, but it is no longer disconnected from
> delivery. `session_date` is still a `String` (it holds a *range* like `10/10/2026 - 14/10/2026`
> on a cohort line), and `session_id` is still a nullable FK used by single-session and manual
> lines — but since 2026-08-24 a line normally stands for a whole cohort, and which sessions it
> covers lives in `payment_session_coverage`. That table is the anti-double-billing key: a session
> is billed iff `payment_sessions.session_id` names it **or** a coverage row under that
> instructor's own letters covers it. `compensation_aed` is now pre-computed from the rate agreed
> at staffing time × the days ops approved, and stays editable until the letter is published.

---

## 8. Conventions that will bite you

Every one of these has already caused a real bug.

1. **No `/api` prefix anywhere.** Spec text that writes `/api/...` is wrong about this codebase.
2. **`admin` passes every role guard.** Never add a per-route admin bypass.
3. **Any new FK to `contacts.id` must be added to `MERGE_FK_REGISTRY`** in
   `services/spine/identity.py`, in the same migration that creates it — or a contact merge
   silently orphans those rows.
4. **Services raise `HTTPException` directly.** There is no domain-exception layer. Simple CRUD
   lives in the router; anything with rules gets a service module.
5. **Identity matching never uses name** — email + phone only. Email-exact auto-merges; any
   phone match queues a human review. Permanent product decision.
6. **`@layer base` input rules in `frontend/src/index.css` outrank Tailwind utilities.** If a
   utility "doesn't work" on an input, check specificity before anything else.
7. **QR scanners must derive their busy flag from state**, covering the whole time feedback is
   on screen — see `CheckIn.tsx`. Releasing it in a `finally` makes the camera resubmit the
   code still in front of it.
8. **Client-side route guards are cosmetic** — they read `localStorage` directly. The backend
   guard is the real one. Never rely on the router for authorization.
9. **Tests are Redis-free.** `tests/conftest.py` gives you two HTTP clients: **`client`**
   (default — `get_arq_redis` pinned to `None`, exactly as the app behaves when Redis is
   unreachable) and **`arq_client`** (real ARQ pool, needs a running broker). Use `client`.
   Only take `arq_client` + `arq_redis` if you are asserting a job actually landed on
   `arq:queue` — seven tests do. The whole suite runs with no broker except those seven.
   **Do not write a local `client` fixture**; five files used to and it bound every role-guard
   and 404 test in them to a live Redis.
10. **Never `alembic downgrade`.** Two revisions fail exactly when the system has been used, and
    downgrading drops ~20 tables. Roll back the image, leave the database migrated.
11. **Circular FKs need hand-splitting** after autogenerate (`contacts`↔`touchpoints`,
    `organizations`↔`contacts`) — autogenerate emits them in an order that fails at runtime.
12. **`baseline_schema.sql` has known drift** from the models (TEXT↔String, index naming). It
    shows up in every autogenerate diff — measured at **~100 unrelated changes**, including two
    tables with no models at all. Never commit an autogenerated revision wholesale. **Hand-write
    migrations**, then verify they match the models: generate a throwaway revision, grep it for
    your table names, and delete it. *"It applies"* is not *"it matches"* — that check caught six
    indexes declared in a migration but not on the models.
13. **`db.expire_all()` + re-select raises `MissingGreenlet` under asyncpg.** Hits whenever you
    test a DB-side `ON DELETE SET NULL`: Postgres nulls the FK, not the ORM, so the cached object
    is stale — but reading an expired attribute triggers a sync lazy-load outside the greenlet.
    Use `await db.refresh(obj)` to re-read after the database has changed a row underneath you.
14. **Test-file basenames must be unique across the whole suite.** `tests/` has no
    `__init__.py`, so two files called `test_equipment.py` in different directories abort
    collection with "import file mismatch" — not one failure, the *entire run*. Name the
    router-level one `test_<thing>_routes.py` (precedent: `test_custody_and_public.py`).
15. **`DialogContent` defaults to `sm:max-w-sm`.** Anything wider than a short form — a table,
    a multi-column editor — needs an explicit `className="sm:max-w-4xl"` or it renders in a
    box the content cannot fit. Pair it with an `overflow-x-auto` wrapper on the table itself.
16. **`session_instructors.role` no longer exists.** Roles are rows in `delivery_roles`
    (I5-3) and the column is `role_id`. "The lead" is the lowest `sort_order`, **never** a name
    match — renaming or inserting a role must not change who is in charge. `payment_sessions.role`
    is deliberately the opposite: a plain string snapshotting the name, so a signed letter keeps
    saying what it said.
17. **Walk a role's pages *as that role*, never as admin.** `admin` passes every `RequireRole`
    check, so an admin walkthrough proves a page renders — not that its owner can reach it.
    The `storekeeper` role shipped with all three of its landing page's API calls returning
    403; the page showed an ordinary empty state, so nothing looked broken. Caught only by
    logging in as one.
18. **`create_notification` takes `type=`, not `notif_type=`.** Easy to get wrong from memory,
    and in a cron job the resulting `TypeError` is invisible for weeks. Check service signatures
    rather than assuming them.
19. **A `Location`'s `country` is derived from its `city_id`, never entered directly.** Free-typed
    country was the recurring bug — a venue with a city but no address/maps link, forms that let
    you set a country not matched by any city picker. `City` is the anchor; `country` is
    read-only display, resolved by one canonical function
    (`services/sessions/staffing.py::resolve_session_location_display`) for every consumer.
    Countries with no seeded SpacePoint city get an explicit "Other (type it)" free-text
    fallback rather than a silently-empty field.
20. **`npx tsc --noEmit -p tsconfig.json` is a no-op in this frontend and reports success
    regardless of real errors.** The root `tsconfig.json` is solution-style (`files: []`, only
    `references`) — without `-b` it type-checks nothing. The actual build is `tsc -b && vite
    build` (`npm run build`, with `VITE_API_URL` set same as `build-frontend.yml`). **Verify a
    frontend change with the literal CI build command**, not a substitute — this shipped a real
    build failure to `main` once already (see `HANDOFF_LMS.md` §9 for the specific bug it hid).
21. **`customElements.define()` can't be hot-swapped by Vite HMR.** If a vanilla custom element's
    own script changes and the change "isn't taking effect" in the browser, hard-refresh before
    concluding the code is wrong — the already-registered class instance stays active across HMR.
22. **`gh release download` can hang on a fully healthy connection** (auth fine, `curl` to
    `github.com` fine) while the actual release-asset host stalls. If `deploy-frontend.sh` hangs
    on the download step: Ctrl+C, `curl -L -o /tmp/frontend-dist.tar.gz <asset-url>` directly,
    then run the script's extract/verify/swap steps by hand — see `HANDOFF_LMS.md` §10.

---

## 9. Migrations

Alembic is the single source of truth. Revisions in `backend/alembic/versions/`; the API
container runs `alembic upgrade head` **before binding a port**, so anything health-checking it
after a deploy must poll, not sleep. Current head: **`c7d3e1f9a2b5`**.

Edit the model → `alembic revision --autogenerate -m "…"` → **review the generated file**
(enum columns use `create_type=False` and produce spurious diffs) → commit → deploy. Never
hand-write schema SQL. New enum values use the `autocommit_block()` + `ADD VALUE IF NOT EXISTS`
pattern (`b2d8a91c0002` is the precedent).

Rehearse anything risky against a restored copy of production first — and create it the way
production is owned: `createdb -O spacepoint_app`, `pgcrypto` as superuser,
`pg_restore --no-owner --role=spacepoint_app`.

## 10. File storage

Pluggable via `STORAGE_BACKEND`. In production files sit on disk under
`/var/lib/spacepoint/storage/{bucket}/{path}`, **Fernet-encrypted at rest**. The DB stores only
`bucket` + `path`; URLs are minted per request as HMAC-signed `/files/{bucket}/{path}?exp=…&sig=…`
(except `website-assets`, which is in `PUBLIC_BUCKETS` in `routers/files.py` so public website and store images can be embedded on `spacepoint.ae` and `labs.spacepoint.ae` without expiring signatures).

Buckets: `documents`, `certificates`, `instructor-documents`, `applicant-submissions`,
`contracts`, `payment-letters`, `profile_pictures`, `library-resources`, `cvs`,
`session-reports`, `website-assets`.

Always import `services/storage.py`, never the backend modules directly.

## 11. Deployment

nginx terminates TLS, serves the built frontend from `/var/www/spacepoint-unified/dist`, and
proxies `/api` (stripped) and `/files` to `127.0.0.1:8000`.

**Three containers**, not one: `spacepoint-api`, `spacepoint-worker`
(`arq app.workers.main.WorkerSettings`, same image, no alembic), `spacepoint-redis`
(bound to localhost only).

CI: `build-backend.yml` on `backend/**`, `build-frontend.yml` on `frontend/**` (publishes a
`frontend-latest` release). Deploys are manual on the server:
`deploy-backend.sh && deploy-frontend.sh`. Backend first when both change; wait for CI green.

Two traps: **`--env-file` is read at container creation**, so editing `/etc/spacepoint/env`
does nothing until the container is recreated; and **`VITE_API_URL` is baked at build time**, so
a second environment needs its own build. Full production detail, including the deploy scripts'
actual observed behavior, the recurring "deploy wipes the worker container's own filesystem"
gotcha, and the nginx pattern for adding a new vanity subdomain, is in
**`docs/HANDOFF_VPS_DEPLOYMENT.md`** (this repo, no secrets) — real credentials are still only in
`vps_envs.md` / `secrets.md`, outside this repo, never committed.

## 12. Running it locally

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # DATABASE_URL, SECRET_KEY, REDIS_URL, storage + SMTP
alembic upgrade head          # needs the pgcrypto extension to be creatable
python seed.py                # admin account from ADMIN_EMAIL / ADMIN_PASSWORD
uvicorn app.main:app --reload
```

```bash
cd frontend && npm install && cp .env.example .env && npm run dev
```

**Redis** (for the job queue — the API starts without it and logs a warning, but jobs are
skipped):

```bash
docker run -d --name spacepoint-redis-dev -p 127.0.0.1:6379:6379 redis:7-alpine
arq app.workers.main.WorkerSettings     # from backend/, in a second terminal
```

**Tests** — `pytest` from `backend/`. Needs a dedicated `spacepoint_test` database (never
`spacepoint_dev`). Optional seeders: `seed_instructors.py`, `app/db/seed_templates.py`.

> If newly added routes 404, the dev server is serving stale code. A plain `uvicorn` restart is
> more reliable here than trusting `--reload` — this has cost hours more than once.
