# SpacePoint Unified Platform

A single role-based platform that unifies three formerly separate apps — **interns**, **ambassadors**, and **instructors** — into one login, one backend, and one database. Users can hold multiple roles at once and switch between them from the navbar.

> The authoritative build plan lives in [`../PLAN.md`](../PLAN.md). Read it before working in this repo.

## Roles

`admin` · `intern` · `leader` · `applicant` · `instructor` · `facilitator` · `ambassador` · `teacher`

A user's `roles` is an array; the active role is a client-side choice only (`localStorage('active_role')`).

## Stack

| Layer | Tech |
|---|---|
| Frontend | React 19 + TypeScript, Vite, TanStack Router + Query, Tailwind (CSS-variable dark mode), Radix UI, CVA |
| Backend | FastAPI (async), SQLAlchemy 2 async + asyncpg, Alembic, python-jose (JWT), passlib (bcrypt) |
| Storage | Supabase (PostgreSQL + Storage) |
| Docs | ReportLab (certificates, letters, contracts), Pillow + qrcode (ID cards), jsPDF (frontend impact reports) |

## Layout

```
spacepoint-unified/
├── frontend/   # Vite SPA — see frontend/src
└── backend/    # FastAPI app + Alembic migrations — see backend/app
```

## Getting started

### Backend
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
cp .env.example .env                              # then fill in DATABASE_URL, SECRET_KEY, Supabase, SMTP
alembic upgrade head                              # once the initial migration exists
python seed.py                                    # seed admin + reference data
uvicorn app.main:app --reload
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env                              # set VITE_API_URL
npm run dev
```

## Build status

Following the phases in `PLAN.md §12`:

- [x] **Phase 0 — Scaffold** (this commit): monorepo structure, build config, design system, auth foundation, unified `users` model, storage service stubs.
- [x] **Phase 1 — Interns domain** — backend + frontend, verified in-browser vs live Supabase
- [ ] Phase 2 — Ambassadors domain
- [ ] Phase 3 — Instructors domain (full rewrite)
- [ ] Phase 4 — Shared document service
- [ ] Phase 5 — Unified admin dashboard
- [ ] Phase 6 — Polish

## License

Private — SpacePoint.
