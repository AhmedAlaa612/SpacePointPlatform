# SpacePoint Unified Platform

A role-based platform for managing SpacePoint's interns, ambassadors/teachers, and instructor/facilitator scholarship pipeline, plus admin — one login, one FastAPI backend, one PostgreSQL database. Users can hold multiple roles at once and switch between them from the navbar.

Full platform documentation (stack, repo structure, roles, database, storage, deployment architecture) lives in [`docs/HANDOFF.md`](./docs/HANDOFF.md) and its per-domain deep-dives. This file covers running the project.

## Run locally

**Backend**
```bash
cd backend
python -m venv .venv && .venv\Scripts\activate    # Windows; `source .venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env          # fill in DATABASE_URL, SECRET_KEY, REDIS_URL, storage/SMTP settings
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

**Redis + job worker** — ticket emails and bulk imports run on ARQ, not in the request. The API
starts fine without Redis (it logs a warning and skips enqueues), so this is only needed when
working on anything that sends email or processes an import batch.
```bash
docker run -d --name spacepoint-redis-dev -p 127.0.0.1:6379:6379 redis:7-alpine
cd backend && arq app.workers.main.WorkerSettings     # second terminal
```

**Tests**
```bash
cd backend && pytest
```
Requires a dedicated `spacepoint_test` database — never point it at `spacepoint_dev`; the
fixtures roll back per test but the database is created and torn down wholesale. Tests are
written Redis-free unless they genuinely exercise the queue.

> If a route you just added returns 404, the dev server is serving stale code. Restarting a
> plain `uvicorn` (no `--reload`) is more reliable in this setup than trusting the file watcher.

## Host on a VPS

Production shape: a single Ubuntu VPS running nginx, a Dockerized backend, and PostgreSQL.

- **nginx** terminates TLS (certbot) and serves the built frontend (`npm run build` → static files) directly; it proxies `/api` (stripping the prefix) and `/files` to the backend container.
- **Three containers**, from this repo's published image plus stock Redis:
  ```bash
  # API — runs migrations, then uvicorn
  docker run -d --name spacepoint-api --restart unless-stopped --network host \
    --env-file /etc/spacepoint/env \
    -v /var/lib/spacepoint/storage:/data/storage \
    ghcr.io/ahmedalaa612/spacepoint-api:latest

  # Worker — same image and env, no migrations (the API already ran them)
  docker run -d --name spacepoint-worker --restart unless-stopped --network host \
    --env-file /etc/spacepoint/env \
    -v /var/lib/spacepoint/storage:/data/storage \
    ghcr.io/ahmedalaa612/spacepoint-api:latest arq app.workers.main.WorkerSettings

  # Redis — localhost only
  docker run -d --name spacepoint-redis --restart unless-stopped \
    -p 127.0.0.1:6379:6379 redis:7-alpine
  ```
  The API entrypoint runs `alembic upgrade head` **before binding a port**, so a fresh empty
  database is fully provisioned on first boot (`pgcrypto` must be creatable first) — and
  anything health-checking the API after a deploy must poll rather than sleep.
- **Database**: PostgreSQL 16 on the same host.

> `--env-file` is read **at container creation**. Editing `/etc/spacepoint/env` does nothing
> until the container is recreated. Likewise `VITE_API_URL` is baked into the frontend at build
> time, so a second environment needs its own build.

Concrete host details and credentials are kept in a private `secrets.md`, outside this repo — see [`docs/HANDOFF.md`](./docs/HANDOFF.md) for the full architecture writeup.

## Deploy updates (VPS)

- Frontend-only change → run `deploy-frontend.sh` on the server (downloads the latest `frontend-latest` GitHub Release, swaps it into nginx's dist directory — no downtime).
- Backend-only change → run `deploy-backend.sh` (pulls the latest image, recreates the API container, polls until it answers — migrations run before the port binds — then recreates the **worker**). It must keep recreating the worker: otherwise a deploy leaves stale job code running against a new schema.
- Both changed → backend first, then frontend.
- Always wait for the relevant GitHub Actions workflow (`build-backend.yml` / `build-frontend.yml`) to go green before deploying.

## License

Private — SpacePoint.
