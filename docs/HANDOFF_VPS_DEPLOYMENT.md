# VPS & Deployment Handoff

**Audience:** any agent picking up this repo cold who needs to understand what's actually running
in production, how a change gets from a commit to a live server, and the operational gotchas that
aren't obvious from reading the code. Written 2026-08-10 from direct, hands-on observation of a
real deploy + a real bulk content import — not from documentation review.

**This file deliberately contains no real secrets.** See §0.

---

## 0. Where the real secrets live (not here)

Real credentials — DB password, `SECRET_KEY`, `STORAGE_ENCRYPTION_KEY`, SMTP, the admin
password — live in `HANDOFF_PRODUCTION_LIVE.md`, `vps_envs.md`, and `secrets.md`, all outside
this repo (`Downloads/spacepoint/` on the operator's machine at time of writing), **deliberately
never committed to git**. That discipline predates this file and this file doesn't break it —
if you find yourself about to paste a real password/key into a git-tracked file, stop; it belongs
in one of those files instead, not here.

---

## 1. Servers

- **Current VPS:** `187.127.191.138` (hostname `srv1804722`) — runs everything in this doc.
- **Old VPS:** `31.97.186.59` (hostname `srv906464`) — legacy instructors portal, kept only as a
  rollback. Status of its own service should be reconfirmed stopped before assuming it's inert.
- **DNS:** Hostinger, `spacepoint.ae` zone. Every subdomain in use (`portal`, `inventory`,
  `madar`, `selfie`, `lms`, ...) is a plain A record pointing at the current VPS IP above — one
  box serves all of them.

---

## 2. What's actually running on the VPS

**Docker (`docker ps`):**

| Container | Image | Notes |
|---|---|---|
| `spacepoint-api` | `ghcr.io/ahmedalaa612/spacepoint-api:latest` | `--network host`, `--env-file /etc/spacepoint/env`, storage volume `/var/lib/spacepoint/storage:/data/storage`. Entrypoint runs `alembic upgrade head` before `uvicorn` — migrations apply once per deploy, not on every boot. |
| `spacepoint-worker` | same image | `arq app.workers.main.WorkerSettings`. **Recreated fresh on every `deploy-backend.sh` run**, not just restarted — see the gotcha in §3. |
| `spacepoint-redis` | `redis:7-alpine` | `127.0.0.1:6379`. **Not** recreated by `deploy-backend.sh` — confirmed by direct observation (uptime survives backend deploys), so the arq queue's state isn't lost on a routine deploy. |

**Not in Docker:**

- **nginx** — TLS via certbot, auto-renewing. One file per domain under
  `/etc/nginx/sites-available/`. `portal.spacepoint.ae`'s file is the canonical, confirmed-live
  example (§4).
- **PostgreSQL 16**, port 5432 — the real database (`spacepoint_unified`) lives here. A
  *separate* PostgreSQL 17 also exists on this box on port 5433, left over from using its newer
  `pg_restore` during an earlier migration — don't confuse the two; the app only ever talks to
  16/5432.
- **`/etc/spacepoint/env`** (mode `0600`) — the real env file both `spacepoint-api` and
  `spacepoint-worker` load via `--env-file`. Real values are outside this repo (§0). One trap:
  **this file is only read at container *creation***, so editing it and expecting the change to
  take effect immediately does nothing — the container needs to actually restart/recreate.

---

## 3. The deploy scripts (`/usr/local/bin/` on the VPS)

**`deploy-backend.sh`** — observed output, in order:
1. `docker pull` the `:latest` image from GHCR.
2. Recreate `spacepoint-api`; wait for it to report healthy (migrations run first, inside the
   container's own entrypoint, before `uvicorn` binds).
3. Recreate `spacepoint-worker`.
4. Fails loudly and doesn't leave a broken container running if the health check doesn't pass —
   confirmed this is a real, working guard, not just a comment.

**`deploy-frontend.sh`** — observed output, in order:
1. `gh release download frontend-latest` — the one stable release tag CI republishes to every
   time (§5), so this script never needs to know a specific version/run ID.
2. Extract to a staging directory, verify `index.html` exists.
3. Swap into `/var/www/spacepoint-unified/dist` — **this one directory is what every domain's
   nginx `root` points at** (portal, lms, any future vanity domain), so one frontend deploy
   updates all of them simultaneously.
4. Safe against a failed download — won't wipe the live site if the download itself fails.

Standard sequence when both sides changed: `deploy-backend.sh && deploy-frontend.sh` (backend
first). Deploy is **manual on purpose** — CI builds the artifact; a human (or an agent, if
explicitly told to) runs the script. Nothing auto-deploys on merge.

### The recurring gotcha, worth internalizing

`deploy-backend.sh` recreates `spacepoint-api`/`spacepoint-worker` **fresh** — any file that
exists only inside one of those containers' own filesystem (a `docker cp`'d staging directory, a
copied OAuth token, anything under `/app` that isn't the bind-mounted storage volume) is gone
after the next deploy. Hit this for real running a bulk Drive-content import mid-session: had to
either (a) finish the whole multi-step process before deploying anything else, or (b) `docker cp`
the working directory OUT to the VPS host disk first, deploy, then `docker cp` it back in
(confirmed working — the host disk itself is unaffected by a container recreate). If you're an
agent mid-way through anything that stages files inside `spacepoint-api`, check with whoever's
driving before running `deploy-backend.sh`.

---

## 4. nginx pattern for a new subdomain

Real, confirmed-working example — `lms.spacepoint.ae`, added 2026-08-10 as a vanity domain
serving the *same* app as `portal.spacepoint.ae`, not a separate deployment:

```nginx
server {
    listen 80;
    server_name lms.spacepoint.ae;
    root /var/www/spacepoint-unified/dist;
    index index.html;
    location / {
        try_files $uri /index.html;
    }
}
```

Then `sudo certbot --nginx -d <domain>` rewrites this into the standard `listen 443 ssl` +
`http→https` redirect shape, same as every other domain on this box.

**Non-obvious fact this depends on, confirmed against the real CI config:** the frontend's API
base URL is baked in at **build time**
(`VITE_API_URL=https://portal.spacepoint.ae/api`, set in `.github/workflows/build-frontend.yml`),
not resolved relative to whichever domain actually served the page. Consequences:

- A new vanity subdomain only needs to serve **static files** — no `/api` or `/files` proxy
  block of its own. `portal.spacepoint.ae`'s file is the one that proxies those
  (`location /api/ { proxy_pass http://127.0.0.1:8000/; }` etc.), because it's the literal
  target the built bundle's JS calls, regardless of which domain loaded that JS.
- Any domain whose page should be able to *call* the API — which is every domain running this
  same bundle — must be added to the backend's `CORS_ORIGINS` env var (comma-separated). This
  isn't theoretical: confirmed necessary in practice, since `fetch()`/PDF.js calls made by a page
  loaded from `lms.spacepoint.ae` are genuine cross-origin requests to `portal.spacepoint.ae`.

---

## 5. CI/CD (GitHub Actions)

Two workflows, `.github/workflows/`:

- **`build-backend.yml`** — triggers on push to `main` touching `backend/**` (or manual
  `workflow_dispatch`). Builds and pushes `ghcr.io/ahmedalaa612/spacepoint-api:latest`.
- **`build-frontend.yml`** — triggers on push to `main` touching `frontend/**`. `npm ci && npm
  run build` with `VITE_API_URL=https://portal.spacepoint.ae/api` baked in, packages `dist/` as
  `frontend-dist.tar.gz`, publishes to the **same** `frontend-latest` GitHub Release every time
  (not a new release per push) — that stable tag is what lets `deploy-frontend.sh` always pull
  from one predictable URL without knowing a commit SHA or run ID.

**Check before assuming local work is live:** this clone has, more than once, sat dozens of
commits ahead of `origin/main` without ever being pushed — active work happening entirely
locally while production ran old code. Before touching deploy, run:
```bash
git log --oneline origin/main..HEAD | wc -l
```
If that's non-zero, `git push origin main` is very likely the actual first step, not "already
deployed."

---

## 6. Storage

`STORAGE_BACKEND=local` — files live at `/var/lib/spacepoint/storage/{bucket}/{path}` on the VPS
**host disk**, bind-mounted into both `spacepoint-api` and `spacepoint-worker` at `/data/storage`,
Fernet-encrypted at rest and decrypted on every read. This is real, persistent storage — **not**
the ephemeral per-container filesystem from the §3 gotcha; a deploy does not touch it. Buckets in
active use include `lms-video-sources`, `lms-hls`, `lms-attachments`, `internship-letters`
(2026-08-20 — the internship request/letter domain, `HANDOFF_INTERNSHIP.md`), plus the
pre-existing document/certificate buckets.

---

## 7. Known state as of 2026-08-10

A point-in-time snapshot — verify against `git log`, `docker ps`, and the actual site before
trusting this section specifically (everything above it is architecture/mechanism and ages much
slower than this list):

- `lms.spacepoint.ae` is live, per §4's pattern.
- LMS Phase 1 is functionally complete and deployed — course content, video pipeline, quizzes,
  PDF attachments, all live. See `HANDOFF_LMS.md` for the current architecture.
- Introduction course: imported, transcoded, published.
- 8 more courses (~110 videos, ~20.7GB) imported via a combined Drive folder from the boss;
  transcoding/publish status not tracked here — check `/lms-authoring/courses` directly.
- `client_max_body_size 50m` in nginx will `413` a video upload attempted through the browser
  authoring UI (the bulk-import scripts are unaffected — they default to
  `http://localhost:8000`, bypassing nginx entirely when run on the VPS itself). Flagged, not yet
  raised — worth bumping to `2G`.
- HTTP/2 not confirmed enabled (`listen 443 ssl;` vs `listen 443 ssl http2;` on nginx 1.24).

---

## 8. Related docs

- **`docs/HANDOFF.md`** (this repo) — general repo orientation; §11 points here for deploy detail.
- **`docs/HANDOFF_LMS.md`** (this repo) — LMS/Missions/Games architecture, including the
  TCP-congestion-control video-latency lesson (§2).
- **`HANDOFF_PRODUCTION_LIVE.md`, `vps_envs.md`, `secrets.md`** — real credentials and
  point-in-time infra snapshots. **Not in this repo, by design** (§0). If you're an agent without
  access to those files, the architecture in this doc is enough to reason about the system; you
  do not need the actual secret values to understand *how* deployment works.
