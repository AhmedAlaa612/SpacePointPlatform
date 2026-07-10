# SpacePoint Unified — Handoff

Entry point for anyone (human or agent) picking up work on this codebase. Domain deep-dives:

- [`HANDOFF_INSTRUCTORS.md`](./HANDOFF_INSTRUCTORS.md) — applicant pipeline, contracts, payments, certificates.
- [`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md) — projects/epics/tasks, kanban board, teams, submissions.
- [`HANDOFF_AMBASSADORS.md`](./HANDOFF_AMBASSADORS.md) — leads, points/titles/badges, teacher sessions.

Credentials and the production env are in `secrets.md`, kept out of version control (it lives one directory above this repo). The live env file is at `/etc/spacepoint/env` on the server.

---

## What this is

A single role-based web platform (one login, one FastAPI backend, one PostgreSQL database) for managing SpacePoint's interns, ambassadors/teachers, and the instructor/facilitator scholarship pipeline, plus an admin layer that spans all three.

## Tech stack

**Frontend** — React 19, Vite, TanStack Router + TanStack Query, Tailwind CSS, Radix UI, recharts, lucide-react, TypeScript.

**Backend** — FastAPI (async), SQLAlchemy 2 (async, `asyncpg`), Alembic, Pydantic v2, Python 3.11.

**Document generation** — `docxtpl` + LibreOffice headless (DOCX → PDF, for contracts/payment letters), ReportLab (PDF letters/certificates), Pillow, `pypdf`, `cairosvg`, `qrcode`.

**Auth** — JWT (`python-jose`) + bcrypt (`passlib`).

**Storage encryption** — Fernet (`cryptography`), used when the local storage backend is active.

## Repo structure

```
backend/
  app/
    main.py              # FastAPI app, router mounting, CORS
    core/                # config.py (env settings), dependencies.py (auth/role guards), security.py
    db/                  # session.py, base.py
    models/               # SQLAlchemy models
      user.py, notification.py, document.py, document_request.py,
      document_template.py, certificate.py, application*.py, id_card.py, enums.py   # shared/top-level
      interns/           # project, team, epic, module, task, submission, proposal, mind_map
      ambassadors/       # lead, lead_comment, points_transaction, title, badge_definition,
                          #   achievement, teacher_session, task, material, system_setting
      instructors/       # applicant_profile, application_review, checklist, module_submission,
                          #   video_submission, presentation_submission, assessment_submission,
                          #   instructor_profile, instructor_document, invitation_code, payment,
                          #   library, training
    routers/
      auth.py, documents.py, notifications.py, apply.py, files.py     # shared, top-level
      admin/             # generic user management + applications + settings
      interns/           # admin.py, leader.py, intern.py, shared.py
      ambassadors/       # leads, points, titles, badges, achievements, network, teacher, tasks, materials, admin, dashboard, public
      instructors/       # applicant, instructor, facilitator, admin, payments, payments_admin, library, training
    services/
      storage.py, storage_local.py, storage_supabase.py    # storage facade + backends
      documents/         # letters.py, letterhead.py, contract.py, payment_letter.py, certificate.py, id_card.py, dossier.py
      email.py, notification.py, points.py, settings.py, user.py
      interns/, ambassadors/    # per-domain business logic
    schemas/             # Pydantic request/response models, mirrors routers/ layout
  alembic/
    versions/            # migration revisions — source of truth for the DB schema
  static/                # fonts, DOCX templates, branding assets, ID card templates
frontend/
  src/
    pages/
      admin/, interns/, ambassadors/, instructors/, apply/, auth/, public/, shared/
    api/                 # one file per router group, thin fetch wrappers
    components/          # ui/ (primitives), layout/, documents/, shared cross-domain components
    context/AuthContext.tsx   # user, roles, active-role switch, login/logout
    router.tsx            # route tree + role guards
```

## Where things live

| Task | Location |
|---|---|
| Add an API endpoint | `backend/app/routers/<domain>/` |
| A role's UI pages | `frontend/src/pages/<domain>/` |
| DB model | `backend/app/models/<domain>/` (or top-level for shared models) |
| Request/response validation | `backend/app/schemas/<domain>/` |
| File storage | `backend/app/services/storage.py` (facade) + `storage_local.py` / `storage_supabase.py` |
| Document templates/generation | `backend/app/services/documents/` |
| Auth / role gating | `backend/app/core/dependencies.py` (backend) + `frontend/src/context/AuthContext.tsx` (frontend) |
| Frontend API calls | `frontend/src/api/<domain>/` |
| Route guards / role-based routing | `frontend/src/router.tsx` |
| Schema change | edit the model → `alembic revision --autogenerate` (see Migrations below) |

## Roles

8 roles total (`backend/app/models/enums.py`, `UserRole`): `admin`, `intern`, `leader`, `applicant`, `instructor`, `facilitator`, `ambassador`, `teacher`.

A user holds an array of roles (`users.roles`); there is no single "role" column. The **active role** is a client-side-only choice (`localStorage`), not a server concept — the backend authorizes every request purely on which roles are in the array, regardless of what's "active" in the UI.

| Role | Domain |
|---|---|
| `admin` | All three domains — full oversight everywhere |
| `intern` | Interns |
| `leader` | Interns (team lead) |
| `applicant` | Instructors (pre-approval) |
| `instructor` | Instructors |
| `facilitator` | Instructors (content management) |
| `ambassador` | Ambassadors |
| `teacher` | Ambassadors (recruited by an ambassador) |

See the role files linked at the top for what each role can actually do.

## Database

PostgreSQL 16, ~57 tables, UUID primary keys everywhere. `users` is the shared identity table across all domains (one row per person, roles as an array). `notifications` and the document tables (`documents`, `document_requests`, `document_templates`, `certificates`) are shared/top-level — used across domains, not owned by one.

Per-domain table groups (see each role file for details, or the model files for exact columns):
- **Interns**: `projects`, `teams`, `epics`, `modules`, `tasks`, `task_submissions`, `proposals`, `mind_map_layouts`, plus join tables (`project_teams`, `team_members`, `task_assignees`).
- **Ambassadors**: `leads`, `lead_comments`, `points_transactions`, `titles`, `badge_definitions`, `achievements`, `teacher_sessions`, `ambassador_tasks`, `materials`, `system_settings`.
- **Instructors**: `applicant_profiles`, `application_reviews`, `video_submissions`, `checklist_modules`/`module_sections`/`checklist_items`, `module_submissions`, `presentation_submissions`, `assessment_submissions`, `invitation_codes`, `instructor_profiles`, `instructor_documents`, `training_modules`/`training_videos`, `library_modules`/`library_resources`, `payment_batches`, `payment_letters`, `payment_sessions`, `payment_addons`, `instructor_bank_details`.

## Migrations

Alembic is the single source of truth for the schema. Revisions live in `backend/alembic/versions/`; the backend container runs `alembic upgrade head` on every start (see `backend/Dockerfile`).

To make a schema change:
1. Edit the SQLAlchemy model.
2. Run `alembic revision --autogenerate -m "…"` and **review the generated file** — autogenerate is reliable for straightforward add-column/add-table changes, but this app's enum columns (`create_type=False`) can produce spurious diffs, so don't commit it unreviewed.
3. Commit the revision file.
4. Deploy (`deploy-backend.sh` applies it — see Deployment below).

Never hand-write SQL for schema changes.

## File storage

Storage backend is pluggable via the `STORAGE_BACKEND` env var. In production, files live on the server disk under `/var/lib/spacepoint/storage/{bucket}/{path}`, each **Fernet-encrypted at rest**. The database stores only `bucket` + `path` (never a raw file); URLs are minted at request time as HMAC-signed `/files/{bucket}/{path}?exp=…&sig=…` links, which the app validates, decrypts, and streams on the fly.

Buckets: `documents`, `certificates`, `instructor-documents`, `applicant-submissions`, `contracts`, `payment-letters`, `profile_pictures`, `library-resources`, `cvs`.

Code: `backend/app/services/storage.py` (facade — always import this, never the backend modules directly) + `storage_local.py` (the encrypted-disk implementation) + `backend/app/routers/files.py` (the signed-URL serving route).

## Deployment & infrastructure

Live at `https://portal.spacepoint.ae`. nginx terminates TLS (certbot, auto-renewing), serves the static frontend from `/var/www/spacepoint-unified/dist`, and proxies `/api` and `/files` to a Dockerized FastAPI backend on `127.0.0.1:8000`.

The backend runs as a Docker container (`spacepoint-api`) built from this repo's GitHub Container Registry image, with the env file mounted and the storage directory bind-mounted. Its entrypoint runs `alembic upgrade head`, then starts uvicorn.

Database: PostgreSQL 16, database `spacepoint_unified`.

**CI/CD** — GitHub repo `AhmedAlaa612/SpacePointPlatform`, branch `main` = production.
- `.github/workflows/build-backend.yml` builds and pushes the backend image on `backend/**` changes.
- `.github/workflows/build-frontend.yml` builds and publishes to a stable `frontend-latest` GitHub Release on `frontend/**` changes.
- Deploys are manual via server-side scripts: `deploy-backend.sh` (pull image + recreate container + health check — also applies any pending Alembic migrations) and `deploy-frontend.sh` (download the `frontend-latest` release, swap into the dist directory).

**Deploy rule of thumb**: frontend-only change → `deploy-frontend.sh`. Backend-only change → `deploy-backend.sh`. Both → backend first, then frontend. Always wait for the relevant CI workflow to go green before deploying.

Concrete host, image name, env-file path, and all credentials are in `secrets.md` (not in version control).
