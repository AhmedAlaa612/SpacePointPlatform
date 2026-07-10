# SpacePoint Unified Platform

A role-based platform for managing SpacePoint's interns, ambassadors/teachers, and instructor/facilitator scholarship pipeline, plus admin — one login, one FastAPI backend, one PostgreSQL database. Users can hold multiple roles at once and switch between them from the navbar.

Full platform documentation (stack, repo structure, roles, database, storage, deployment architecture) lives in [`docs/HANDOFF.md`](./docs/HANDOFF.md) and its per-domain deep-dives. This file covers running the project.

## Run locally

**Backend**
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows; `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # fill in DATABASE_URL, SECRET_KEY, storage/SMTP settings
alembic upgrade head          # builds the schema on a fresh DB (needs the pgcrypto extension creatable)
python seed.py                # seeds the admin account (ADMIN_EMAIL / ADMIN_PASSWORD)
uvicorn app.main:app --reload
```
Optional reference-data seeders: `python seed_instructors.py` (instructor checklist curriculum), `python app/db/seed_templates.py` (default document templates).

**Frontend**
```bash
cd frontend
npm install
cp .env.example .env          # set VITE_API_URL to the backend's URL
npm run dev
```

## Host on a VPS

Production shape: a single Ubuntu VPS running nginx, a Dockerized backend, and PostgreSQL.

- **nginx** terminates TLS (certbot) and serves the built frontend (`npm run build` → static files) directly; it proxies `/api` and `/files` to the backend container.
- **Backend** runs as a Docker container from this repo's published image, given an env file and a bind-mounted storage directory:
  ```bash
  docker run -d --name spacepoint-api --restart unless-stopped --network host \
    --env-file /etc/spacepoint/env \
    -v /var/lib/spacepoint/storage:/data/storage \
    ghcr.io/ahmedalaa612/spacepoint-api:latest
  ```
  Its entrypoint runs `alembic upgrade head` then starts uvicorn, so a fresh empty database is fully provisioned on first boot (the `pgcrypto` extension must be creatable first).
- **Database**: PostgreSQL 16 on the same host.

Concrete host details and credentials are kept in a private `secrets.md`, outside this repo — see [`docs/HANDOFF.md`](./docs/HANDOFF.md) for the full architecture writeup.

## Deploy updates (VPS)

- Frontend-only change → run `deploy-frontend.sh` on the server (downloads the latest `frontend-latest` GitHub Release, swaps it into nginx's dist directory — no downtime).
- Backend-only change → run `deploy-backend.sh` (pulls the latest image, recreates the container, applies any pending Alembic migrations, health-checks).
- Both changed → backend first, then frontend.
- Always wait for the relevant GitHub Actions workflow (`build-backend.yml` / `build-frontend.yml`) to go green before deploying.

## License

Private — SpacePoint.
