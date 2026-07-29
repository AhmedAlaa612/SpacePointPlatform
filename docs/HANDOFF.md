# SpacePoint Unified — Handoff

**Entry point for anyone (human or agent) picking up this codebase.** This file is a *map*:
where everything is and what it does. Depth lives in the per-domain files linked below.

**Last verified against the code: 2026-07-28.**

---

## 1. Status in one table

| | |
|---|---|
| **Live at** | `https://portal.spacepoint.ae` |
| **Schema head** | `b3e8a41d0014` — single Alembic head |
| **Branch** | `main` = production. `v2-dev` tracks it |
| **What's live** | Registration, bulk import, check-in, staffing marketplace, instructor delivery, attendance, certificates, calendar, ops dashboard — plus the pre-existing interns / ambassadors / instructors domains |
| **Tests** | ~330, `pytest` from `backend/` |
| **In flight** | Inventory (see `INVENTORY_EXECUTION_PLAN.md` in the planning repo) |

## 2. Read next

**Planning docs live in a separate `spaceCRM` repo the operator maintains — not in this
codebase.** Ask for its location.

| Read | For |
|---|---|
| `HANDOFF_V2_LIVE.md` *(planning repo)* | **What is actually running in production and its known gaps.** Read this before touching anything deployed |
| `MASTER_EXECUTION_PLAN_V2.md` *(planning repo)* | Roadmap, §C decision register, §D status board, §DISCOVERIES (the expensive lessons) |
| `INVENTORY_EXECUTION_PLAN.md` *(planning repo)* | The inventory phase, superseding V2's I7-1…I9-1 |
| [`HANDOFF_SPINE.md`](./HANDOFF_SPINE.md) | Contacts / identity matching / merge review |
| [`HANDOFF_SESSIONS.md`](./HANDOFF_SESSIONS.md) | Programs, cohorts, sessions, registration, staffing, delivery |
| [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md) | Applicant pipeline, contracts, payments, certificates |
| [`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md) | Projects, epics, tasks, kanban, teams |
| [`HANDOFF_AMBASSADORS.md`](./HANDOFF_AMBASSADORS.md) | Leads, points/titles/badges, teacher sessions |
| `HANDOFF_EVERYTHING.md` *(repo root)* | **Historical** — a session log from 2026-07-25, predates the cutover. Not current state |

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
| `/public/*` | registration form, catalog, ticket — **no auth** |
| `/apply/*` · `/files/*` · `/documents/*` · `/notifications/*` | shared |
| `/health`, `/health/worker` | liveness + ARQ heartbeat |

**Frontend** domains — each has its own sidebar in `Sidebar.tsx::getNavItems`:
`/interns` · `/ambassadors` · `/instructors` · `/admin` (platform management) ·
`/operations` (running the business: programs, cohorts, contacts, check-in, calendar).
Public, no auth: `/login`, `/apply/*`, `/t/{ticketToken}`.

---

## 6. Roles

9 roles (`backend/app/models/enums.py::UserRole`): `admin`, `intern`, `leader`, `applicant`,
`instructor`, `facilitator`, `ambassador`, `teacher`, `operations`.

A user holds an **array** of roles (`users.roles`) — there is no single role column. The
"active role" is a client-side choice only (`localStorage`); the backend authorizes purely on
the array.

| Role | Domain | Notes |
|---|---|---|
| `admin` | all | **Passes every `RequireRole` check unconditionally** |
| `operations` | `/operations` | Runs the business — programs, cohorts, registrations, contacts, check-in, calendar |
| `instructor` / `facilitator` | `/instructors` | Delivery: their assigned sessions, attendance, reports |
| `applicant` | `/instructors` | Pre-approval pipeline; gets a minimal shell, no sidebar |
| `intern` / `leader` | `/interns` | |
| `ambassador` / `teacher` | `/ambassadors` | |

---

## 7. Domains and their tables

Alembic is the source of truth for the exact schema — this is orientation, not a column list.

| Domain | Tables |
|---|---|
| **Shared** | `users`, `notifications`, `documents`, `document_requests`, `document_templates`, `certificates`, `applications`, `application_questions`, `id_cards`, `portal_settings` |
| **Spine** | `contacts`, `contact_relationships`, `organizations`, `identity_aliases`, `merge_reviews`, `touchpoints`, `contact_role_events`, `consent_records` *(schema only — nothing writes to it)* |
| **Sessions** | `programs`, `cohorts`, `sessions`, `session_instructors`, `session_call_targets`, `registrations`, `registration_sessions`, `attendance_records`, `instructor_interests`, `session_reports`, `import_batches`, `activities` / `activity_versions` / `activity_assignments` *(quiz — schema only until W13–14)* |
| **Instructors** | `applicant_profiles`, `application_reviews`, `video_submissions`, `checklist_*`, `module_submissions`, `presentation_submissions`, `assessment_submissions`, `invitation_codes`, `instructor_profiles`, `instructor_documents`, `training_*`, `library_*`, `payment_batches`, `payment_letters`, `payment_sessions`, `payment_addons`, `instructor_bank_details` |
| **Interns** | `projects`, `teams`, `epics`, `modules`, `tasks`, `task_submissions`, `proposals`, `mind_map_layouts` + join tables |
| **Ambassadors** | `leads`, `lead_comments`, `points_transactions`, `titles`, `badge_definitions`, `achievements`, `teacher_sessions`, `ambassador_tasks`, `materials`, `system_settings` |

> **`payment_sessions` is not a sessions-domain table.** It's a hand-typed line on a payment
> letter (`session_date` is a `String`), with no FK to `sessions.id`. Delivered sessions and
> payments are **not** connected today.

---

## 8. Conventions that will bite you

Every one of these has already caused a real bug. Fuller accounts in
`MASTER_EXECUTION_PLAN_V2.md` §DISCOVERIES.

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
    shows up in every autogenerate diff. Do not fold it into an unrelated migration.

---

## 9. Migrations

Alembic is the single source of truth. Revisions in `backend/alembic/versions/`; the API
container runs `alembic upgrade head` **before binding a port**, so anything health-checking it
after a deploy must poll, not sleep.

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
a second environment needs its own build. Full production detail in `HANDOFF_V2_LIVE.md`.

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
