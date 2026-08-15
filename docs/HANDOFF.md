# SpacePoint Unified — Handoff

**Entry point for anyone (human or agent) picking up this codebase.** This file is a *map*:
where everything is and what it does. Depth lives in the per-domain files linked below.

**Last verified against the code: 2026-08-15.**

---

## 1. Status in one table

| | |
|---|---|
| **Live at** | `https://portal.spacepoint.ae` |
| **Schema head** | `e2f7a93d0040` — single Alembic head (the merge revision `b88f272265ef` joins two branches of the same chain, not a second head). Production follows `main` deploys; the API container runs `alembic upgrade head` before binding its port |
| **Branch** | `main` = production. `v2-dev` tracks it |
| **What's live** | Registration, bulk import, check-in, staffing marketplace (multiple calls per session + cohort-level campaigns), instructor delivery + payment letters, attendance, certificates, calendar, ops dashboard, **inventory end to end** (kits, warehouses, stock, custody, equipment, fulfilment, public QR scan), plus the pre-existing interns / ambassadors / instructors domains — **and the LMS/Missions/Games domain**: student accounts, courses + encrypted-HLS video, learning paths, the CubeSat design + Flight Operations missions with a real 36-part component library, Live Quiz games. See [`HANDOFF_LMS.md`](./HANDOFF_LMS.md) |
| **Tests** | ~567 collected, `pytest` from `backend/`. Five need a live Redis and error without one — everything else is broker-free |

## 2. Read next

This file plus the per-domain docs below are the complete, self-contained map — everything you
need to navigate this codebase lives in this repo's `docs/` folder. (The operator separately
keeps week-to-week sprint planning/status boards outside this repo; those are working documents
for active development, not architecture references, and get deleted once a phase wraps — don't
expect them to exist, and nothing here depends on them.)

| Read | For |
|---|---|
| [`HANDOFF_LMS.md`](./HANDOFF_LMS.md) | Student accounts, courses, learning paths, the CubeSat design + Flight Operations missions, the component library, Live Quiz games — the whole `/learn` + `/lms-authoring` surface |
| [`HANDOFF_SPINE.md`](./HANDOFF_SPINE.md) | Contacts / identity matching / merge review |
| [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md) | Programs, cohorts, sessions, registration, staffing, delivery |
| [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md) | Applicant pipeline, contracts, payments, certificates |
| [`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md) | Projects, epics, tasks, kanban, teams |
| [`MISSIONS_INTERN_SPEC.md`](./MISSIONS_INTERN_SPEC.md) | Intern-facing: how to propose a mission, what gets ported vs. rebuilt, lessons from the first real port (SatKit → Operate Your Satellite, Phase 2B) |
| [`HANDOFF_AMBASSADORS.md`](./HANDOFF_AMBASSADORS.md) | Leads, points/titles/badges, teacher sessions |
| [`HANDOFF_VPS_DEPLOYMENT.md`](./HANDOFF_VPS_DEPLOYMENT.md) | What's actually running on the VPS, the deploy scripts' real behavior, storage layout |
| [`OPS_BACKUPS.md`](./OPS_BACKUPS.md) | Database backup script — usage, cron, restore |

Credentials are in `secrets.md` / `vps_envs.md`, kept out of version control (one directory
above this repo). Production env file: `/etc/spacepoint/env`.

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
| `/missions/*` | design mission (state, budgets, component library), operate mission, proposals, teams, manager dashboards, admin CRUD. See `HANDOFF_LMS.md` |
| `/games/*` | Live Quiz authoring, live run control + realtime, student play. See `HANDOFF_LMS.md` |
| `/public/*` | registration form, catalog, ticket — **no auth** |
| `/apply/*` · `/files/*` · `/documents/*` · `/notifications/*` | shared |
| `/health`, `/health/worker` | liveness + ARQ heartbeat |

**Frontend** domains — each has its own sidebar in `Sidebar.tsx::getNavItems`:
`/interns` · `/ambassadors` · `/instructors` · `/admin` (platform management) ·
`/operations` (running the business: programs, cohorts, contacts, check-in, calendar, and
`/operations/inventory/*` for kits, stock, fulfilment and the catalogue).
**`/learn`** is a separate surface for the `student` role — own shell, not part of `Sidebar.tsx`
at all (see `HANDOFF_LMS.md` §1) — with staff-facing authoring at `/lms-authoring` living inside
the normal `AppShell` like everything else.
Public, no auth: `/login`, `/apply/*`, `/t/{ticketToken}`.

---

## 6. Roles

12 roles (`backend/app/models/enums.py::UserRole`): `admin`, `intern`, `leader`, `applicant`,
`instructor`, `facilitator`, `ambassador`, `teacher`, `operations`, `coo`, `storekeeper`,
`student`.

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

---

## 7. Domains and their tables

Alembic is the source of truth for the exact schema — this is orientation, not a column list.

| Domain | Tables |
|---|---|
| **Shared** | `users`, `notifications`, `documents`, `document_requests`, `document_templates` (now with `student_completion` and `workshop_delivery` system templates seeded — `d8a2c94e0035` / `e1b3d05f0036`), `certificates`, `applications`, `application_questions`, `id_cards`, `portal_settings` |
| **Spine** | `contacts`, `contact_relationships`, `organizations`, `identity_aliases`, `merge_reviews`, `touchpoints`, `contact_role_events`, `consent_records` *(schema only — nothing writes to it)* |
| **Sessions** | `programs`, `cohorts`, `sessions`, `session_instructors` (`role_id` → `delivery_roles`, not a `lead\|co` string since I5-3), `delivery_roles`, `session_openings`, `session_addons`, `session_materials`, `session_call_targets`, `session_calls` (multiple concurrent calls per session — `c4e7a39f0028`), `cohort_openings` (cohort-level opening defaults — `b3d6f28e0027`), `cohort_calls` (grouped cohort-wide staffing campaigns — `e7c4a92d0036`), `registrations`, `registration_sessions`, `attendance_records`, `instructor_interests`, `session_reports`, `import_batches`, `activities` / `activity_versions` / `activity_assignments` *(quiz — schema only until the LMS games phase)*. Cohorts and sessions now have `location_id` → `locations` (`a2c5e17d0026`; `locations.address`/`maps_url` live on the entity); `locations.city_id` → `cities` (8 seeded UAE cities) is the anchor — `locations.country` is legacy/derived-only and nullable, never entered directly (see §8) |
| **Inventory** | `locations`, `items`, `kit_templates`, `kit_template_items`, `kits`, `kit_items`, `stock_levels`, `movements`, plus `session_kits` / `kit_checks` (I2-1/I2-2) — and, since 2026-08-01: `item_categories` (`d2e6f81a0029`), `warehouses` (`f8d9e21a0033`, `c4f1a83b0034` — **stock and kits now key on `warehouse_id`; a location is the union of its warehouses**), `cohort_kits` (cohort-level kit defaults, `a3c7f95e0037`), and `items.variant_group`/`variant_label` (T-shirt-style size grouping, `d1e4c73f0038`). **`items.is_consumable` is gone** (`a7c9e15f0032` — everything now counts toward kit completeness). **Kit custody legs were replaced** (`e3f8b04c0030`): there is no issue/collected/return movement flow; `session_kits` carries `received_at` / `return_status` / `returned_at` / `ops_confirmed_at` instead, and moving a kit to a shelf is an ordinary `movements` row. Equipment pickup (I2-7) adds no tables — it is a form over `items` + `stock_levels` + `movements` with a persisted "returning later" flag (`f4a1c65d0031`). `movements` is the single ledger every physical thing passes through — issue, return, transfer, refill, receive, write-off, adjust — and either side of it can be a location, a person or a kit. Custody keys on `users`, so nothing here touches `MERGE_FK_REGISTRY`. `POST /inventory/stock/adjust-bulk` writes one item across every warehouse in one transaction (`StockCountModal.tsx`); `POST /inventory/kits/{kit_id}/count` (`require_storekeeper`, a deliberate narrow exception to this router's usual `require_operations`) lets a storekeeper count a kit's contents directly instead of going through individual stock rows |
| **LMS / Missions / Games** | `courses`, `course_modules`, `module_items`, `module_videos`, `video_checkpoints`, `enrollments`, `item_progress`, `learning_paths`, `learning_path_steps`, `point_events`, `program_curriculum`, `cohort_curriculum`; `missions`, `mission_variants`, `mission_attempts`, `mission_attempt_members`, `mission_teams`, `mission_team_members`, `mission_managers`, `mission_assignments`, `mission_proposals`, `design_component_library` + the design-mission budget tables; `games`, `game_questions`, `game_runs`, `game_participants`, `game_answers`, `game_session_assignments`, `game_session_questions`; plus the shared `curriculum.prerequisites` DAG (courses and missions as interchangeable items). Full detail in `HANDOFF_LMS.md` |
| **Instructors** | `applicant_profiles`, `application_reviews`, `video_submissions`, `checklist_*`, `module_submissions`, `presentation_submissions`, `assessment_submissions`, `invitation_codes`, `instructor_profiles`, `instructor_documents`, `training_*`, `library_*`, `payment_batches`, `payment_letters`, `payment_sessions`, `payment_addons`, `instructor_bank_details` |
| **Interns** | `projects`, `teams`, `epics`, `modules`, `tasks`, `task_submissions`, `proposals`, `mind_map_layouts` + join tables |
| **Ambassadors** | `leads`, `lead_comments`, `points_transactions`, `titles`, `badge_definitions`, `achievements`, `teacher_sessions`, `ambassador_tasks`, `materials`, `system_settings` |

> **`payment_sessions` is not a sessions-domain table.** It's a hand-typed line on a payment
> letter (`session_date` is a `String`), with no FK to `sessions.id`. Delivered sessions and
> payments are **not** connected today.

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
   `arq:queue` — five tests do. The whole suite runs with no broker except those five.
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
after a deploy must poll, not sleep. Current head: **`e2f7a93d0040`**.

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
`bucket` + `path`; URLs are minted per request as HMAC-signed `/files/{bucket}/{path}?exp=…&sig=…`.

Buckets: `documents`, `certificates`, `instructor-documents`, `applicant-submissions`,
`contracts`, `payment-letters`, `profile_pictures`, `library-resources`, `cvs`,
`session-reports`.

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
