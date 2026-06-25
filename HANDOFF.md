# SpacePoint Unified — Handoff

> **Audience:** any agent/developer picking this up cold.
> **Authoritative spec:** [`../PLAN.md`](../PLAN.md) — read it first. This file is the *current state* on top of that plan.
> **Last updated:** 2026-06-25

---

## 1. What this is

A single role-based platform replacing three separate apps (`interns`, `ambassadorsV1`, `instructors`). One login, one backend, one database. Users hold multiple roles at once (`roles[]`) and switch between them in the navbar. Full rationale + target architecture is in `PLAN.md`.

Source apps (siblings of this repo, used as the port source — do not deploy them):
- `../interns/` — React 19 + async FastAPI. Roles: admin, leader, intern. **Feature-complete.**
- `../ambassadorsV1/` — React 19 + async FastAPI. Roles: admin, ambassador, teacher. **Feature-complete.**
- `../instructors/` — Jinja2 + **sync** FastAPI. Roles: ADMIN, APPLICANT, INSTRUCTOR, FACILITATOR. Rewrite is **done** (Phase 3) — kept as historical reference only; see `../instructors/HANDOFF.md` for the source-app inventory it was rewritten from.
- `../ambassadors/` (no V1) — an **older, flat-structured** version of the ambassador app. **Ignore it.** The source of truth is `ambassadorsV1`.

---

## 2. Status at a glance

| Phase | State |
|---|---|
| **Phase 0 — Scaffold** | ✅ Done, verified, committed (`956013d`) |
| **Phase 1 — Interns: backend** | ✅ Done, verified vs live Supabase, committed (`a3f56b2`) |
| **Phase 1 — Interns: frontend** | ✅ Done, verified in-browser vs live Supabase, committed (`6ddf3fd`, `5ffbe9f`) |
| **Phase 2 — Ambassadors** | ✅ Done, verified, committed (`9cbb914`) |
| **Phase 3 — Instructors (rewrite)** | ✅ Done, verified, committed (`e3eec31`…`e35af11`, see §14) |
| Phase 4 — Shared documents (ID cards, certs, letters) | ✅ Done — `id_cards`/`certificates` pulled forward into Phase 3; `recommendation_letters`/`intern_letters` (tables + services + shared `/documents` router) and the completion-cert triggers shipped now. Intern ID cards intentionally out of scope (no `intern` card artwork exists yet — see §12). |
| Phase 5 — Unified admin dashboard | ✅ Done as a hub (`/admin` cards with live counts → domain-specific admin pages) instead of PLAN §9.4's single tabbed page, per explicit user direction. Instructors admin (3.6) + **Ambassadors admin (Phase 2 gap, now closed — `ce2566c`)** both done. Multi-role user management across domains still generic-only (`/interns/admin/users` — not domain-scoped). |
| Phase 6 — Polish | ⬜ Not started |

**All commits are on `main`.** The repo is its own git repo (`git init`'d here); it is NOT the same repo as the parent `spacepoint/` folder.

---

## 3. Tech stack (as built)

**Frontend** — React 19.2 + TypeScript, Vite 8, TanStack Router v1 + Query v5, Tailwind 3.4 (CSS-variable dark mode), Radix UI, CVA, `@xyflow/react` (mind maps), `@dnd-kit` (kanban), jsPDF, lucide-react, axios. Versions pinned to match the source apps (see `frontend/package.json`).

**Backend** — Python 3.11+ target (dev venv is 3.10.7), FastAPI (async), SQLAlchemy 2 async + asyncpg, Alembic, python-jose (JWT), passlib[bcrypt], ReportLab/Pillow/qrcode (docs, later phases), supabase-py (storage), aiosmtplib (email).

**Infra** — Supabase (Postgres + Storage). Frontend → Vercel, backend → Railway/Render (not deployed yet).

---

## 4. Repo structure (actual)

```
spacepoint-unified/
├── HANDOFF.md                 ← this file
├── README.md
├── .gitignore / .gitattributes
├── frontend/                  # Vite SPA (Phase 0 scaffold; interns & ambassadors integrated)
│   └── src/
│       ├── api/{client.ts, auth.ts, documents.ts, admin/users.ts, interns/, instructors/, ambassadors/}
│       ├── components/{ui/, layout/Navbar.tsx}
│       ├── context/AuthContext.tsx     # user, roles[], activeRole, setActiveRole
│       ├── lib/{utils.ts, logos.ts}
│       ├── pages/{auth/Login.tsx, Home.tsx, interns/, ambassadors/, instructors/,
│       │         admin/{Dashboard.tsx, Users.tsx, components/common.tsx}}
│       ├── types/shared.ts             # Role, User (roles[]), ROLE_DOMAIN, ROLE_LABEL
│       ├── router.tsx                  # auth-gated shell; with global auth loading guard
│       └── main.tsx
└── backend/
    ├── .env                   # REAL secrets, gitignored (see §6)
    ├── .env.example
    ├── requirements.txt
    ├── seed.py                # creates admin from ADMIN_EMAIL/PASSWORD
    ├── seed_instructors.py    # loads spacepoint/instructors/seed_data.json (checklist curriculum)
    ├── sql/                   # SQL-first provisioning artifacts (see §5)
    │   ├── 0001_initial_users.sql
    │   ├── 0002_interns.sql
    │   ├── 0003_ambassadors.sql
    │   ├── 0004_instructors.sql
    │   └── 0005_phase4_documents.sql
    ├── alembic/               # async env + 0001 migration (kept for "later")
    └── app/
        ├── main.py            # mounts auth, notifications, documents, admin, /interns/*, /ambassadors/*, /instructors/*
        ├── core/{config.py, security.py, dependencies.py}   # roles[] JWT + RequireRole
        ├── db/{base.py, session.py}                          # async engine (Supabase SSL)
        ├── models/{user.py, notification.py, enums.py, id_card.py, certificate.py,
        │           recommendation_letter.py, intern_letter.py, interns/, ambassadors/, instructors/}
        ├── schemas/{auth.py, user.py, notification.py, documents.py, interns/, ambassadors/, instructors/}
        ├── services/{user.py, notification.py, storage.py, email.py, points.py, interns/, ambassadors/,
        │             documents/{id_card,certificate,contract,payment_letter,recommendation,intern_letters}.py}
        ├── static/{fonts/ (Times New Roman x4), templates/{certificate_template.png, id_cards/instructor_{front,back}.png},
        │           spacepoint_logo.png}
        └── routers/{auth.py, notifications.py, documents.py, admin/users.py (package — generic user mgmt, not
                     domain-specific), interns/{admin,leader,intern,shared}.py, ambassadors/,
                     instructors/{applicant,admin,instructor,training,library,payments,facilitator,payments_admin}.py}
```

> **Convention note (deviation from PLAN §3):** we use `app/db/base.py` + `app/db/session.py` (matches both source backends → clean ports), not the plan's illustrative `core/database.py`. Domain code lives in `*/interns/` subpackages to avoid name collisions across domains.

---

## 5. Database (Supabase — LIVE)

A **fresh** Supabase project is provisioned and in use. Schema was created **SQL-first** (the user's chosen workflow); Alembic is kept for later.

**Tables that exist now (51 total):** `users` (Phase 0) + 13 interns/shared tables (Phase 1) + 11 ambassadors tables (Phase 2) + 25 instructors + shared-doc tables (Phase 3): `invitation_codes, applicant_profiles, application_reviews, video_submissions, presentation_submissions, checklist_modules, module_sections, checklist_items, user_checklist_progress, module_submissions, instructor_profiles, instructor_documents, training_modules, training_videos, user_training_progress, library_modules, library_resources, payment_batches, payment_letters, payment_sessions, payment_addons, instructor_bank_details, portal_settings, id_cards, certificates`.
**Enums:** `user_role` (8 roles), `work_status`, `submission_status`, `application_status`, `instructor_video_status`, `module_submission_status`, `payment_letter_status`, `payment_session_role`, `certificate_type`.

**How the schema is provisioned / reproduced:**
- `backend/sql/0001_initial_users.sql` — run in Supabase SQL editor (already done).
- `backend/sql/0002_interns.sql` — generated from the SQLAlchemy models; the actual tables were created by running `Base.metadata.create_all` against Supabase. Re-runnable on a fresh DB.
- `backend/sql/0003_ambassadors.sql` — generated from SQLAlchemy models for the ambassadors domain (tables created via SQL/Supabase).
- `backend/sql/0004_instructors.sql` — same pattern; enum types created first (raw `CREATE TYPE`), then `create_all` for the tables.
- Each future phase should ship a matching `backend/sql/000N_*.sql`.

**Supabase Storage buckets (all 11 from PLAN §10, created in Phase 3):** `id-cards, certificates, recommendation-letters, intern-letters, instructor-documents, library-resources (public), training-videos, applicant-submissions, contracts, payment-letters, instructor-photos`. None existed before Phase 3 — created via the `supabase-py` storage admin client, not the dashboard.

**⚠️ Alembic catch-up:** because tables were created via SQL/`create_all` (not `alembic upgrade`), before ever using Alembic you must `alembic stamp head` so it doesn't try to recreate existing tables. There is currently only the `0001` migration; **no `0002` or `0003` alembic migrations were written** (the SQL scripts + models are the source of truth). Writing matching Alembic migrations is a deferred clean-up task.

**Admin account (created + bcrypt-verified in DB):**
- Login: **`admin@space.com` / `admin123`** (dev credential — rotate before any real use)
- `roles = {admin}`, `status = active`

---

## 6. Environment & how to run

Secrets live in **`backend/.env`** and **`frontend/.env`** — both **gitignored** (only `.env.example` is committed). The Supabase URL, DB password, and service key are in `backend/.env`; do not commit them. The user said these will be rotated.

> ⚠️ The system `python` on this machine is msys2 (no pip). Use a real CPython:
> `C:\Users\ahmed\AppData\Local\Programs\Python\Python310\python.exe` (a venv is already set up at `backend/.venv`, Python 3.10.7). `py -3.13` / `py -3.10` also work. `psql` 17 is installed at `C:\Program Files\PostgreSQL\17\bin`.

**Backend:**
```bash
cd backend
.venv\Scripts\activate            # venv already created + deps installed
uvicorn app.main:app --reload     # serves on :8000
python seed.py                    # (idempotent) ensure admin exists
```

**Frontend:**
```bash
cd frontend
npm install                       # already done once; node_modules present
npm run dev                       # Vite on :5173
npm run build                     # tsc -b && vite build (must stay clean)
```

---

## 7. What's verified

**Phase 0** — `frontend` `tsc -b` + `vite build` clean; backend auth endpoints pass end-to-end vs live Supabase (`/auth/login`, `/auth/me`, `/auth/refresh`, 401 cases).

**Phase 1 backend** — verified vs live Supabase using an in-process `httpx.AsyncClient(ASGITransport)` smoke test:
- `POST /auth/login` (admin) → 200
- `GET /interns/admin/{users,projects,teams,epics}` → 200
- `POST` + `DELETE` `/interns/admin/projects` → 200/200 (write path)
- `GET /notifications/me` → 200
- unauthenticated → 401

**Phase 1 frontend** — verified in a real browser against the running stack: login as admin → redirect to `/interns` → AdminDashboard board renders + fetches → nav → `/interns/admin` users page renders with the correct role badge, dark mode. **No console errors.** `tsc -b` + `vite build` clean.

**Phase 2 (Ambassadors)** — verified backend compilation, frontend build, and a live httpx smoke test (login + ambassadors/interns/notifications endpoints, 200/401 as expected) against Supabase.

**Phase 3 (Instructors)** — verified per sub-phase, each with a live httpx `ASGITransport` smoke test against Supabase *and* (3.4 onward) real in-browser passes via the Claude Preview MCP tools, not just API checks:
- 3.0 schema: all 51 tables present live, backend imports clean.
- 3.1 applicant pipeline backend: full apply → videos → modules → submit → admin phase1-approve → phase2 → admin final-approve chain, including contract PDF generation + upload to Storage.
- 3.3 instructor portal backend: ID card generation (visually inspected the rendered PNGs/PDF, not just "didn't crash"), training/library/vault, payment letter sign (signature embed → PDF regen → certificate generation → email/notify) — also visually inspected the generated certificate PDF.
- 3.4 instructor portal frontend: full in-browser walkthrough as a real instructor account, zero console errors. **Caught and fixed a real bug this way** — an unhandled Storage 404 that left the video player spinning forever.
- 3.5 facilitator portal: role enforcement confirmed (instructor correctly 403's on facilitator-only endpoints), in-browser module creation through the real dialog UI.
- 3.6 admin instructors page + hub: backend smoke test (invitations/facilitators/directory/settings/batches/letters/sessions/addons/bulk-import-with-a-real-xlsx-round-trip/certificates) + full in-browser admin pass. **Caught and fixed a recurring CSS bug** (see §9.7) in 3 places, including one left over from Phase 3.2 that had never been visually exercised until now.
- 3.7 end-to-end: one continuous run with a brand-new account through the *entire* chain (apply → both admin approval gates → fresh login as the newly-promoted instructor → full instructor portal → facilitator cross-visibility → admin directory), proving no step depends on state left over from manual testing.

**Phase 4 (shared documents)** — backend import clean; both new tables confirmed live; httpx smoke test covering all 3 new interns endpoints, the recommendation-letter flow (including the returned signed URL resolving with a real HTTP 200), `/documents/me`, and the instructor completion-cert auto-trigger firing on approval; `npm run build` clean; in-browser pass generating a confirmation letter, a completion certificate, and a recommendation letter (deliberately including `&`/`>` in the admin-authored text to exercise the XML-escaping fix) via the real Users-panel modal, against a genuinely multi-role account (`admin@space.com` carries `intern` among its roles) to confirm the modal's role-gating reads the actual `roles[]` array — then confirmed both new self-service sections (`interns/Profile.tsx`, `instructors/Documents.tsx`) render the generated documents with zero console errors.

---

## 8. Key decisions & adaptations (interns & ambassadors backend ports)

- **`role` → `roles[]`:** the unified `users` table has a `roles user_role[]` array; JWT carries `roles`. `app/core/dependencies.py` exposes the same names the source used (`require_admin/require_leader/require_intern`, `get_current_user`) so interns routers imported them **unchanged**. Admin always passes `RequireRole`.
- **Shared `UserOut`** (`app/schemas/user.py`) uses `roles: list[UserRole]` (not a single `role`). The interns frontend will need the matching `User.role` → `roles[]` change.
- **Notifications are shared**, not interns-specific: model `app/models/notification.py`, schema `app/schemas/notification.py`, service `app/services/notification.py`, router mounted at top-level **`/notifications`** (ambassadors will reuse it). The model is a superset (adds an optional `type` column).
- **User service is shared** (`app/services/user.py`, top-level) — admin user CRUD; `create_user` now takes `roles`.
- Routers mounted under **`/interns`** (so `/interns/admin/*`, `/interns/leader/*`, `/interns/intern/*`, `/interns/users/me`, `/interns/teams/{id}/members`).
- Ported via copy + import-repath script (`app.models.X` → `app.models.interns.X`, etc.), leaving `user/notification/enums/auth/security/db` shared. No `current_user.role` comparisons existed in any router (all role-gating is via deps), which made the port clean.
- **Admin Bypasses for Ambassadors**: Added checks in `network.py` allowing users with the `admin` role to bypass the owner/inviter controls. This enables admins to view and approve teacher applications and manage sessions without throwing 403 Forbidden errors.
- **Global Auth Guarding**: Wrapped the routing layout shell in `router.tsx` to handle context `isLoading` explicitly. Before child components (like `TeacherPortal`) can render, the app displays a loading `Spinner` to prevent `null` references when resolving asynchronous profiles on page reloads.
- **Form Controls & Tailwind Specificity**: Base inputs (`input`, `select`, `textarea`) and `.input` declarations were moved into Tailwind's `@layer base` and `@layer components` in `index.css`. This prevents high-specificity attributes (e.g. `input[type="text"]` with `!important` padding) from overriding Tailwind utility classes, resolving the overlapping search icon problem.

---

## 9. Gotchas learned (this environment)

1. **`fastapi 0.138` + `starlette 1.3.1` nest included routers under a `Mount`** → `len(app.routes)` UNDERCOUNTS (it showed `5` with everything mounted). **Routes still work.** Verify functionally (httpx ASGITransport), never by counting `app.routes`.
2. **Windows coarse mtime → stale `__pycache__`** gave inconsistent import results mid-session. When diagnosing imports, clear `__pycache__` and run `python -B`.
3. **TS 6** flags `baseUrl` as deprecated → we removed `baseUrl` and kept `paths` (works in TS 6; Vite resolves `@` via its own alias). Also needed `declare module "@fontsource-variable/inter"` for the side-effect import under `noUncheckedSideEffectImports`.
4. **asyncpg + Supabase pooler:** `statement_cache_size=0` + permissive SSL context (already in `app/db/session.py`); session pooler **port 5432**; DB password is URL-encoded in `DATABASE_URL`.
5. **PowerShell sandbox** blocked a `Remove-Item` that was embedded inside a big regex-heavy script — run destructive ops as small standalone commands.
6. From the interns source: `model_validator(mode="before")` reads `_sa_instance_state.dict` for async-safe relationship reads; mind-map uses `useParams({ strict: false })`; admin board has two separate `DndContext`s — don't merge them.
7. **`<input className="input w-X">` / `"input flex-1"` — the `.input` class's own `width: 100%` competes with a sizing utility on the *same* element.** Confirmed via direct DOM measurement: the input meant to be wide rendered at 25px, the one meant to be narrow stretched to 596px. Fix: put the sizing class (`flex-1`, `w-24`, etc.) on a wrapping `<div>`, leave `.input` alone on the `<input>`. Hit this in 3 places across Phase 3 (two in `pages/instructors/Admin.tsx`, one in `pages/instructors/Status.tsx` left over from Phase 3.2 and never caught until a Phase 3.6 browser pass happened to exercise that exact form). **Grep for `className="input \(flex-\|w-\)` before trusting any form layout that wasn't visually checked.**
8. **SQLAlchemy `ENUM(SomePyEnum, ...)` sends the Python member *name* to Postgres by default, not `.value`.** Only matters when they differ (e.g. `PaymentSessionRole.facilitator = "Facilitator"` — name≠value). Fix with `values_callable=lambda e: [x.value for x in e]` on that column. Every other Phase 3 enum is snake_case-name-equals-value and unaffected.
9. **FastAPI: a plain scalar param (`str | None = None`) alongside an `UploadFile` param is read as a query param, not a form field** — confirmed empirically with a throwaway `TestClient` script, not obvious from the FastAPI docs at a glance. Every `UploadFile`-handling endpoint in Phase 3 sends its other fields via the query string for this reason; the frontend `api/*.ts` functions append them to the URL, not the `FormData` body.
10. **`preview_eval`'s plain `element.click()` did not reliably trigger React's onClick** in this session (root cause unclear). `element.dispatchEvent(new MouseEvent('click', {bubbles:true, cancelable:true, view:window}))` worked every time — prefer it when driving the UI via `preview_eval`.
11. **The source instructors app's `id_card_service.py` hardcoded a `venv/lib/python3.12/...` path** to find a fallback font — breaks on any other Python version or OS layout. The unified `services/documents/id_card.py` resolves the same fallback (`reportlab`'s bundled Vera font) via `os.path.dirname(reportlab.__file__)` instead — works regardless of Python version/venv layout since it walks the installed package, not a hardcoded path.

---

## 10. Phase 1 frontend (interns) — DONE ✅

Ported and verified in-browser. Pages/components/api live under `frontend/src/pages/interns`, `frontend/src/api/interns`; the interns UI kit (`button`/`card`/`dialog`) is now the shared `components/ui`. The plan below records *how* it was done — reuse the same recipe for ambassadors/instructors. Source: `../interns/frontend/Spacepoint-interns/src/`.

**Plan:**
1. **Types** — replace interns `types.ts` usage with the unified `@/types/shared` `User` (which is `roles[]`). Add interns-specific types (Epic, Module, Task, TaskBrief, Submission, Proposal, BoardCard) under `frontend/src/types/interns.ts`. Map `WorkStatus`/`SubmissionStatus`.
2. **API** — copy `api/{epics,tasks,modules,proposals,tracker,mindmap}.ts` into `frontend/src/api/interns/`, repoint base paths to the **`/interns/*`** prefix, and use the unified `api` client (`@/api/client`) + `/notifications/*`. (Source api used `VITE_API_URL`; unified client already does.)
3. **Auth** — delete the interns `AuthContext`; use the unified one (`@/context/AuthContext`). Replace `user.role === 'admin'` checks with `activeRole` / `hasRole('admin')`. Interns users self-register? No — admin-created only (see interns HANDOFF).
4. **Pages** — port `Dashboard.tsx` (admin epic-drilldown board), `Tracker.tsx`, `MindMap.tsx`, plus Calendar/Leaderboard/Profile, into `frontend/src/pages/interns/`. Board has admin/leader/intern variants.
5. **Components** — port `components/kanban/*` (`KanbanBoard`, `TaskModal`, `TaskCard`, `CreateSubtaskModal`) into `frontend/src/pages/interns/components/` (or `components/`). Keep the **two separate DndContexts** on admin.
6. **Routes** — add the interns subtree under `/interns/*` in `frontend/src/router.tsx` (board, tracker, mind-map/$epicId, calendar, leaderboard, profile), guarded by `roles ∩ {intern,leader,admin}`. Wire the navbar role-switcher to land on `/interns`.
7. **Convert classes to semantic tokens** where shared (dark mode), per PLAN §5. Domain-only pages may keep raw grays.
8. **Verify:** `npm run build` clean; manually exercise admin → create project/epic/task → intern submit → leader review; tracker; mind map. Then commit `Phase 1 (frontend): interns`.

**Backend endpoints available to the frontend now:**
`/auth/*` · `/interns/admin/*` · `/interns/leader/*` · `/interns/intern/*` · `/interns/users/me` · `/interns/teams/{id}/members` · `/notifications/*`. (Open `http://localhost:8000/docs` with the backend running for the full list.)

---

## 11. Phase 2 frontend & backend (Ambassadors) — DONE ✅

Ported, integrated, and verified in-browser. Pages and components live under `frontend/src/pages/ambassadors`, APIs under `frontend/src/api/ambassadors/`, and backend models/routers/schemas under `backend/app/*/ambassadors/`. 

**Adaptation Summary:**
1. **Types** — Shared typescript types consolidated under `frontend/src/types/ambassadors.ts` with explicit type safety.
2. **API Clients** — Migrated legacy endpoints under `/ambassadors` prefix, configured type-safe API requests, and integrated shared notifications system.
3. **Database Schema** — Applied `0003_ambassadors.sql` containing all schema updates to the Supabase database.
4. **Auth Switcher integration** — Allowed administrative roles to access both the Interns board and Ambassador features seamlessly. Integrated dynamic redirect matching based on `activeRole`.
5. **Theme-Aware Styling** — Rewrote cards (LeadCard, TaskCard), modal overlays (Leads, Tasks), and tables (Leaderboard) to support the unified dark mode token system. Cleaned up color overlaps on the network node and search filters.
6. **Bypasses & Guards** — Implemented admin bypasses for session creation and approvals in `network.py`. Integrated the routing auth spinner to prevent asynchronous auth crashes.

---

## 11.5 Phase 3 — Instructors (full rewrite) — DONE ✅

Full rewrite, not a port: source was sync FastAPI + Jinja2 + Integer PKs + local disk + cookie JWT; target is async + React + UUID PKs + Supabase Storage + Bearer JWT. See `../instructors/HANDOFF.md` (written before this phase started) for the complete source-app inventory this rewrite was based on, and `C:\Users\ahmed\.claude\plans\magical-forging-gray.md` for the sub-phase plan (3.-1 through 3.7) this was executed against.

**Key decisions (deviations from PLAN.md's literal text, made deliberately):**
- `id_cards`/`certificates` tables + `id_card.py`/`certificate.py` services pulled forward from Phase 4 into Phase 3 — the instructor Profile Card page needed them now. Both are genuinely role/type-generic (not instructor-specific) per explicit user direction — only the *artwork* (`static/templates/id_cards/instructor_{front,back}.png`) is instructor-only today; the code resolves per-role templates and falls back to the instructor one only because no other role's artwork exists yet.
- `certificates` unified with a `type` discriminator (`workshop_delivery` now; `instructor_completion`/`internship_completion` reserved for Phase 4) instead of two same-named concepts colliding.
- `checklist_modules` (not bare `modules`, which already belongs to the interns domain in this shared schema).
- `research_submissions` (source table) dropped — dead in source, no router referenced it.
- The stub `/auth/instructor-apply` endpoint (ported as-is from ambassadorsV1 *before* this phase, bypassing the whole applicant pipeline) was stripped and rebuilt properly as part of 3.1 — same route, real semantics this time (applicant_profiles → application_reviews pipeline, ambassador-referral detection against both `invitation_codes` and `users.invite_code`).
- **Admin dashboard reframed as a hub-and-spoke model** (`/admin` → summary cards with live counts → click into a domain's own admin page) instead of PLAN §9.4's single tabbed page, per explicit user direction. This also surfaced that **ambassadors admin (network tree, approvals, titles/badges, questions — documented in `ambassadorsV1/HANDOFF.md`) was never built in Phase 2** — shown as a disabled hub card, flagged as a separate task, not backfilled here.

**Sub-phases (each its own commit, see §14):** 3.0 schema (25 tables) → 3.1 applicant pipeline backend → 3.2 applicant pipeline frontend → 3.3 instructor portal backend (ID cards, training, library, vault, payments+e-signature) → 3.4 instructor portal frontend → 3.5 facilitator portal → 3.6 admin instructors page + hub → 3.7 end-to-end verification.

---

## 12. NEXT — Phase 6 (per PLAN §12)

- **Phase 4 is done.** `recommendation.py` (admin-triggered, any role) and `intern_letters.py` (confirmation/completion) shipped, alongside `generate_completion_certificate_pdf` in the existing `certificate.py`. New shared router `routers/documents.py` (`/documents/me` self-service, `/documents/recommendation-letters` admin) mirrors the `/notifications` top-level pattern. Completion-cert trigger is **automatic** for instructors (fires inside `review_applicant`'s `approved` branch — a real existing event) and **manual** for interns (3 new `/interns/admin/users/{id}/{confirmation-letter,completion-letter,certificate}` endpoints, since there's no equivalent "internship done" event to hook — PLAN §8.2's "auto on intern status=completed" was aspirational; `users.status` never actually gained a `completed` value). New tables `recommendation_letters`/`intern_letters` per `sql/0005_phase4_documents.sql`. Frontend: a "Documents" action per row on `pages/admin/Users.tsx` (recommendation letter form, always; the 3 intern-only actions, gated on the real `roles[]` array) plus self-service "My documents" sections on `interns/Profile.tsx` and `instructors/Documents.tsx`.
- **Intern ID cards remain out of scope** — PLAN §9.1 lists an admin-triggered `.../id-card` endpoint, but `static/templates/id_cards/` only has `instructor_{front,back}.png`; wiring it would silently hand an intern an instructor-branded card. Needs real `intern_front.png`/`intern_back.png` artwork first — `id_card.py`'s per-role template resolution already supports dropping it in with zero code changes once it exists.
- **Phase 5's one remaining gap is now closed too.** Generic user management relocated out of the interns domain to `/admin/users` (`pages/admin/Users.tsx`, backend `routers/admin/users.py` — a package, since `routers/admin/` already existed as an empty Phase-0 scaffold dir reserved for exactly this per PLAN §3) per explicit user direction: user management isn't domain-specific, but team management stays owned by interns (`/interns/admin`, Teams-only now — the Users tab was removed entirely, not left in parallel). The create-user form now supports real multi-role assignment (checkbox group over all 8 roles — `UserCreate`/`UserUpdate` already accepted `roles: list[UserRole]`, only the frontend was single-role) and shows a team picker whenever `intern` is checked, which calls the existing `/interns/admin/teams/{id}/members` endpoint right after creation — no new backend endpoint needed, just a cross-domain call from the new page (same precedent as ambassadors' admin-bypass code calling across domains). This also fixed a latent display bug for free: the per-row role badge now renders the real `roles[]` array instead of going through the old single-role `userRole()` helper, which collapsed every non-admin/leader/intern user to an "intern" badge.
- **Bug found while testing the above, not fixed (flagged as `task_e822a830`):** `DELETE /admin/users/{id}` 500s if the user is still a team member — `team_members.user_id`'s FK has no cascade/cleanup behavior, and `services/user.py`'s `delete_user` doesn't remove memberships first. Pre-existing gap (unrelated to this session's changes), just newly likely to get hit now that creating a user and assigning them to a team in one step is easy.
- **Phase 6 — Polish:** dark-mode pass, CORS tighten, RLS review, `tsc --noEmit` clean, secrets check. Also: the `xlsx` npm package (interns Tracker export) has an unfixed high-severity vulnerability — flagged as a separate task, swap it out.

---

## 13. Source reference

| What | Where |
|---|---|
| Authoritative plan | `../PLAN.md` |
| Interns backend (ported from) | `../interns/backend/app/` |
| Interns frontend (port next) | `../interns/frontend/Spacepoint-interns/src/` |
| Interns handoff | `../interns/HANDOFF.md` |
| Ambassadors backend/frontend | `../ambassadorsV1/backend/app/`, `../ambassadorsV1/frontend/src/` |
| Ambassadors handoff | `../ambassadorsV1/HANDOFF.md` |
| Instructors business logic | `../instructors/backend/app/` |
| ID-card service (Pillow) + templates | `../instructors/backend/app/services/id_card_service.py`, `../instructors/backend/app/static/templates/newID_*.png` |
| Logos in use | `frontend/src/assets/logos/` (ambassador.svg, intern.svg, logo.png plain) |

## 14. Commits

- `956013d` — Phase 0: scaffold unified platform (monorepo, auth, design system)
- `a3f56b2` — Phase 1 (backend): port interns domain
- `97a2035` — docs: add HANDOFF.md
- `6ddf3fd` — Phase 1 (frontend): port interns SPA
- `5ffbe9f` — fix(interns): show interns nav links for admin
- `c96a2e56` — docs: mark Phase 1 complete and add domain-port recipe
- `e29947ee` — feat(interns): responsive navbar + fix port encoding
- `ed0339a6` — fix(interns/backend): correct UTF-8 encoding of ported files
- `6a59aefe` — docs: note UTF-8 encoding gotcha in port recipe
- `9cbb914` — Phase 2: port ambassadors domain (backend + frontend)
- `e3eec31` — Phase 3.0: instructors domain schema & models
- `383bbd6` — Phase 3.1: instructors applicant pipeline backend
- `feeadb4` — Phase 3.2: instructors applicant pipeline frontend
- `74786c5` — Phase 3.3: instructor portal backend (id cards, training, library, documents vault, payments with e-signature)
- `ea442c3` — Phase 3.4: instructor portal frontend
- `f21726b` — Phase 3.5: facilitator portal
- `e35af11` — Phase 3.6: instructors admin page + super-admin hub
- `f23f67f` — Phase 3.7: end-to-end verification + HANDOFF.md update
- `ce2566c` — Port ambassadors admin dashboard (closes the Phase 2 gap; also fixes the `invited_by_id` instructor-referral stats bug — see commit message)

### Recipe for porting a domain frontend (used for interns; reuse for §11)
> ⚠️ **Encoding:** read source with `[System.IO.File]::ReadAllText($p)` and write with `New-Object System.Text.UTF8Encoding($false)`. **Do NOT use `Get-Content -Raw`** (PS 5.1 reads UTF-8 as Windows-1252 → mojibake on `·`, em-dashes, smart quotes). And don't name a PS function `R` (collides with the `r`=Invoke-History alias). Both bit the interns port.

1. Copy `api/*` → `frontend/src/api/<domain>/`; repath `./client` → `@/api/client` (named `api` import), `@/types` → `@/types/<domain>`, prefix API paths with `/<domain>` (leave `/auth`, `/notifications`).
2. Copy pages/components → `frontend/src/pages/<domain>/`; repath `@/types`→`@/types/<domain>`, `@/api/X`→`@/api/<domain>/X`, `@/components/X`(≠ui)→`@/pages/<domain>/components/X`. Drop the domain's own `AuthContext`/`client`/`Layout`/`Navbar`.
3. `types/<domain>.ts`: re-export shared `User`; keep domain types. Patch other-user `u.role` → `u.roles` (a `userRole()`-style helper).
4. Add routes under `/<domain>` in `router.tsx`; fix in-page `to:` strings (typed router flags them).
5. Add domain nav links to the shared `Navbar`. Then `npm run build` and fix iteratively; finish with an in-browser check.
