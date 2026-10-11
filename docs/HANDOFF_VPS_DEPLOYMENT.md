# VPS & Deployment Handoff

**Audience:** any agent picking up this repo cold who needs to understand what's actually running
in production, how a change gets from a commit to a live server, and the operational gotchas that
aren't obvious from reading the code. Written 2026-08-10 from direct, hands-on observation of a
real deploy + a real bulk content import — not from documentation review. **Updated 2026-09-05**
after the R2/video-compression rollout (PR #44 and follow-ups) actually deployed and all existing
video content migrated — see §2, §6, §7, and §9.

**Updated 2026-10-11** after rolling out the dynamic Marketing Website (`https://spacepoint.ae`), SpacePoint Labs (`https://labs.spacepoint.ae`), and the E-Commerce Store & 12-tab Website CMS in the Portal (`https://portal.spacepoint.ae`) at Alembic head `c7d3e1f9a2b5` — see §2, §3, §4, §5, §6, §8, and [`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md).

**Re-verified 2026-09-17 & 2026-10-11**. This pass cross-checked every claim below against what's actually checked into this repo and observed live on `srv1804722` (`187.127.191.138`): `ops/deploy-backend.sh`, `ops/deploy-frontend.sh`, `ops/backup_db.sh`, `ops/restore_db.sh`, `backend/Dockerfile`, `docker-compose.dev.yml`, the video/storage code under `backend/app/`, and the VPS scripts `/usr/local/bin/deploy-website.sh` and `/usr/local/bin/deploy-labs.sh`. The detailed current video architecture (upload, transcode, storage-backend routing, playback token/playlist/segment/key endpoints) lives in **[`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md)**, and the Website/Store/Labs architecture lives in **[`HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md)**.

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
- **DNS:** Hostinger, `spacepoint.ae` zone. The apex domain (`spacepoint.ae`) and every subdomain in use (`portal`, `labs`, `inventory`,
  `madar`, `selfie`, `lms`, ...) point at the current VPS IP above — one
  box serves all of them.

---

## 2. What's actually running on the VPS

**Docker (`docker ps`):**

| Container | Image | Notes |
|---|---|---|
| `spacepoint-api` | `ghcr.io/ahmedalaa612/spacepoint-api:latest` | `--network host`, `--env-file /etc/spacepoint/env`, storage volume `/var/lib/spacepoint/storage:/data/storage`. Entrypoint runs `alembic upgrade head` before `uvicorn` — migrations apply once per deploy, not on every boot. |
| `spacepoint-worker` | same image | `arq app.workers.main.WorkerSettings` — every IO-bound job (email, LMS sync, inventory reminders, `heartbeat` cron). **Recreated fresh on every `deploy-backend.sh` run**, not just restarted — see the gotcha in §3. |
| `spacepoint-worker-video` | same image | `arq app.workers.main.VideoWorkerSettings` — `transcode_video` only, on its own queue (`arq:queue:video`), `max_jobs=1`. **Confirmed live** — deployed 2026-09-05, has drained every course's full re-encode/migrate-to-R2 backlog since (130 videos, ~34.6GB source → ~3GB output, see §9). Same bind-mounts/env-file/restart policy as `spacepoint-worker`; recreated the same way, but the swap order is deliberately different (stops the old container before starting the new one, not start-new-then-retire-old) — two containers both enforcing `max_jobs=1` against the same queue at once would let two encodes run concurrently. If this container isn't running, `transcode_video` jobs queue and never run — uploads/re-encodes sit "pending" forever with no visible error. |
| `spacepoint-redis` | `redis:7-alpine` | `127.0.0.1:6379`. **Not** recreated by `deploy-backend.sh` — confirmed by direct observation (uptime survives backend deploys), so the arq queue's state isn't lost on a routine deploy. Also holds the `transcoding:{video_id}` lock keys used by `deploy-backend.sh --check`'s preflight (§3). |

**[2026-09-17 / 2026-10-11]** Confirmed against `ops/deploy-backend.sh` and live deploy output on `srv1804722` (2026-10-11). Video architecture detail has moved to [`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md).

**Not in Docker:**

- **nginx** — TLS via certbot, auto-renewing. One file per domain under
  `/etc/nginx/sites-available/`:
  - `portal.spacepoint.ae` & `lms.spacepoint.ae` → serve `/var/www/spacepoint-unified/dist` (`portal.spacepoint.ae` also proxies `/api/` and `/files/` to `127.0.0.1:8000`). Also carries a scoped `location ~* \.mjs$ { types { application/javascript mjs; } default_type application/javascript; try_files $uri =404; }` block (added 2026-09-05, between the `/files/` and `/` blocks) — without it, PDF.js's worker script (`pdf.worker.min.mjs`) is served with `application/octet-stream` from the default `mime.types`, which the browser refuses to load as an ES module.
  - `spacepoint.ae` (`www.spacepoint.ae`) → serves `/var/www/spacepoint-website/dist` (built by `deploy-website.sh` from `/var/www/spacepoint-website-repo`).
  - `labs.spacepoint.ae` → serves `/var/www/spacepoint-labs` (updated by `deploy-labs.sh`).
- **PostgreSQL 16**, port 5432 — the real database (`spacepoint_unified`) lives here. A
  *separate* PostgreSQL 17 also exists on this box on port 5433, left over from using its newer
  `pg_restore` during an earlier migration — don't confuse the two; the app only ever talks to
  16/5432. `max_connections` bumped **100 → 150** on 2026-09-05 (`/etc/postgresql/16/main/postgresql.conf`,
  requires a Postgres restart to take effect) to cover the second worker container: 3 uvicorn
  workers × 15 (`pool_size=10`+`max_overflow=5`) + 2 worker containers × 15 = 75 possible app
  connections, and 150 leaves real headroom for manual `psql`/`pg_dump` sessions on top.
- **`/etc/spacepoint/env`** (mode `0600`) — the real env file `spacepoint-api`, `spacepoint-worker`,
  and `spacepoint-worker-video` all load via `--env-file`. Real values are outside this repo (§0). One trap:
  **this file is only read at container *creation***, so editing it and expecting the change to
  take effect immediately does nothing — the container needs to actually restart/recreate. Confirmed
  again this pass: every `docker run`/`docker rm -f && docker run` pair in `ops/deploy-backend.sh`
  passes `--env-file "$ENV_FILE"` fresh at creation time, with no in-place env reload path.
- **`/var/www/spacepoint-website-repo/.env`** — contains `PUBLIC_API_URL=https://portal.spacepoint.ae/api` for the Astro static site build on the VPS. (In addition, `spacepoint-website` code ignores any `localhost` / `127.0.0.1` value in `PUBLIC_API_URL` during `astro build` and on non-localhost hostnames).

---

## 3. The deploy scripts (`/usr/local/bin/` on the VPS)

**[2026-09-17]** `ops/deploy-backend.sh` and `ops/deploy-frontend.sh` live in this repo — reviewable/diffable in git rather than only existing as hand-installed files on the VPS. Install with `sudo install -m 755 ops/deploy-backend.sh /usr/local/bin/deploy-backend.sh` (each script's own header says so). `ops/legacy/` holds the earlier, simpler versions of both (no rollback, no video worker, no frontend backup/rollback) — kept for reference, not installed anywhere; don't confuse the two when checking what's actually running on the VPS.

**`deploy-backend.sh`**
```
deploy-backend.sh                 # normal deploy, auto-rollback armed
deploy-backend.sh --no-rollback   # REQUIRED for destructive migrations
deploy-backend.sh --check         # preflight only, changes nothing
```
In order:
1. **Preflight** (`preflight()`): checks the live `spacepoint-api` container's config hasn't
   drifted from what this script assumes (network mode, restart policy, storage bind-mount), that
   no video is `status='processing'` (a fresh transcode mid-flight — recreating the worker
   SIGKILLs it), and that no `transcoding:{video_id}` Redis key exists (a swap-in-place re-encode
   mid-flight, e.g. "Migrate to R2" — its DB `status` never changes, so this lock is the only
   signal; see [`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md)). Any drift blocks the deploy unless
   `--check` (report-only) was passed.
2. `docker pull` the `:latest` image from GHCR; snapshot the running `spacepoint-api` image ID
   (for rollback) and the current `alembic_version` (to detect whether a migration commits).
3. Recreate `spacepoint-api` (`docker rm -f` + `docker run`); poll `/health` until it answers 200
   or the container exits (migrations run first, inside the entrypoint, before `uvicorn` binds).
   **On failure here, the script auto-rolls-back the API image** — but only if migrations have
   *not* committed yet (`alembic_version` unchanged); if they have, it refuses to roll the image
   back (new schema + old code is worse than being down) and tells you to restore the pre-deploy
   dump instead. `--no-rollback` disables the auto-rollback outright — required whenever the
   deploy carries a migration with `drop_table`/`drop_column`/a not-null backfill, per the script's
   own comment block.
4. Start a **new** `spacepoint-worker` container, wait for `/health/worker`'s heartbeat, then
   retire the old one — zero-downtime (briefly two workers dequeue the same IO-bound queue, which
   is harmless). A worker-only failure here does **not** take the already-healthy API back down.
5. **Video worker**: the opposite swap order on purpose — **stop** the old
   `spacepoint-worker-video` first, *then* start the new one and wait for arq's own `--check`
   health check (not `/health/worker`, which only reflects the main worker's heartbeat key and
   says nothing about the video queue). Two containers both enforcing `max_jobs=1` against
   `arq:queue:video` at once would let two ffmpeg encodes run concurrently — exactly what that
   setting exists to prevent — so this queue accepts a brief gap (queued jobs just wait) instead
   of the zero-downtime pattern used for the main worker. If the new one fails health, the old one
   (only stopped, not removed) is restarted rather than leaving video transcoding dark.

**`deploy-frontend.sh`**
```
deploy-frontend.sh            # download the latest build and swap it in
deploy-frontend.sh --rollback # restore the most recent backup
deploy-frontend.sh --list     # show available backups
```
1. `gh release download frontend-latest` — the one stable release tag CI republishes to every
   time (§5), so this script never needs to know a specific version/run ID.
2. Extract to a staging directory (`$ROOT/.dist-staging`, a *sibling* of the live `dist/`, not
   `/tmp` — deliberately, so the final swap stays on one filesystem and can be a true atomic
   `mv` rather than a cross-filesystem copy). Refuses to proceed unless both `index.html` **and**
   a non-empty `assets/` directory are present — a build with only `index.html` produces a blank
   white page that would otherwise pass the old check.
3. Before swapping, copies the *current* live `dist/` into `$ROOT/backups/<timestamp>/` (keeps
   the last 5, older ones pruned) — this is what makes `--rollback` possible, and it exists
   because `frontend-latest` is a mutable tag: once a new build republishes to it, the build being
   replaced may not be re-downloadable from GitHub at all.
4. Swaps into `/var/www/spacepoint-unified/dist` via two renames (`dist` → `dist.old`, staging →
   `dist`) — **this one directory is what every portal/LMS domain's nginx `root` points at** (`portal.spacepoint.ae`, `lms.spacepoint.ae`), so one frontend deploy updates all of them simultaneously.
5. Safe against a failed download or a truncated build — won't touch the live site if either
   check fails.

**`deploy-website.sh`** (Marketing Website — `https://spacepoint.ae`)
```
deploy-website.sh            # pull AhmedAlaa612/spacepoint-website, build Astro static site, atomic swap into /var/www/spacepoint-website/dist
deploy-website.sh --legacy   # emergency rollback to legacy static site
```
1. Pulls `main` from `https://github.com/AhmedAlaa612/spacepoint-website` into `/var/www/spacepoint-website-repo`.
2. Runs `npm install` and `npm run build` (`astro build` — reads `/var/www/spacepoint-website-repo/.env` where `PUBLIC_API_URL=https://portal.spacepoint.ae/api` is set, pre-rendering all 26 static routes with current API data).
3. Backs up the current live build into `/var/www/spacepoint-website/backups/<timestamp>` and atomically swaps the new `dist/` into `/var/www/spacepoint-website/dist`, then tests and reloads nginx.
*(Note: Live counter, marquee, program, resource, and store updates also hydrate client-side on page load without requiring `deploy-website.sh`, whereas new blog posts with new `/blog/[slug]` URLs or Astro template changes require `deploy-website.sh`.)*

**`deploy-labs.sh`** (SpacePoint Labs — `https://labs.spacepoint.ae`)
```
deploy-labs.sh               # pull AhmedAlaa612/spacepoint-labs into /var/www/spacepoint-labs and reload nginx
```
Pulls `main` from `https://github.com/AhmedAlaa612/spacepoint-labs` into `/var/www/spacepoint-labs` (pure static HTML/Three.js showcase, no build step) and reloads nginx. Project cards on `labs.spacepoint.ae` are fetched live in the browser from `GET https://portal.spacepoint.ae/api/public/labs/projects`.

Standard sequence when deploying across all surfaces:
```bash
deploy-backend.sh && deploy-frontend.sh && deploy-website.sh && deploy-labs.sh
```

### The recurring gotcha, worth internalizing

`deploy-backend.sh` recreates `spacepoint-api`/`spacepoint-worker`/`spacepoint-worker-video`
**fresh** — any file that exists only inside one of those containers' own filesystem (a `docker cp`'d staging directory, a
copied OAuth token, anything under `/app` that isn't the bind-mounted storage volume) is gone
after the next deploy. Hit this for real running a bulk Drive-content import mid-session: had to
either (a) finish the whole multi-step process before deploying anything else, or (b) `docker cp`
the working directory OUT to the VPS host disk first, deploy, then `docker cp` it back in
(confirmed working — the host disk itself is unaffected by a container recreate). If you're an
agent mid-way through anything that stages files inside `spacepoint-api`, check with whoever's
driving before running `deploy-backend.sh`.

---

## 4. nginx pattern for a new subdomain & CORS rules

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
(`VITE_API_URL=https://portal.spacepoint.ae/api` and `VITE_WEBSITE_URL=https://spacepoint.ae`, set in `.github/workflows/build-frontend.yml`),
not resolved relative to whichever domain actually served the page. Consequences:

- A new vanity subdomain only needs to serve **static files** — no `/api` or `/files` proxy
  block of its own. `portal.spacepoint.ae`'s file is the one that proxies those
  (`location /api/ { proxy_pass http://127.0.0.1:8000/; }` etc.), because it's the literal
  target the built bundle's JS calls, regardless of which domain loaded that JS.
- **CORS (`backend/app/main.py`):** As of **2026-10-11** (`895a9d6`), `CORSMiddleware` includes
  `allow_origin_regex=r"^https?://([a-z0-9-]+\.)?spacepoint\.ae$"` in addition to `settings.cors_origins_list`.
  This automatically allows cross-origin requests from `https://spacepoint.ae`, `https://www.spacepoint.ae`,
  `https://labs.spacepoint.ae`, `https://portal.spacepoint.ae`, `https://lms.spacepoint.ae`, and any future
  `*.spacepoint.ae` subdomain without requiring `/etc/spacepoint/env` edits + container recreates.

---

## 5. CI/CD (GitHub Actions)

Two workflows in `spacepoint-stripe-test/.github/workflows/`:

- **`build-backend.yml`** — triggers on push to `main` touching `backend/**` (or manual
  `workflow_dispatch`). Builds and pushes `ghcr.io/ahmedalaa612/spacepoint-api:latest`.
- **`build-frontend.yml`** — triggers on push to `main` touching `frontend/**`. `npm ci && npm
  run build` with `VITE_API_URL=https://portal.spacepoint.ae/api` and `VITE_WEBSITE_URL=https://spacepoint.ae` baked in, packages `dist/` as
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
**host disk**, bind-mounted into `spacepoint-api`, `spacepoint-worker`, and `spacepoint-worker-video`
at `/data/storage`, Fernet-encrypted at rest and decrypted on every read. This is real, persistent storage — **not**
the ephemeral per-container filesystem from the §3 gotcha; a deploy does not touch it. Buckets in
active use include `video-sources` (video pre-transcode sources — `backend/app/services/video_service.py::
SOURCE_BUCKET = "video-sources"`), `lms-hls` (video HLS
output — kept under its original name even though the video service is no longer LMS-only, see
that file's own comment on why renaming it once already broke playback), `lms-attachments`
(checklist/program PDF attachments — `backend/app/routers/lms/admin.py::ATTACHMENT_BUCKET` /
`backend/app/services/lms/program.py::PROGRAM_ITEM_PDF_BUCKET`), `internship-letters`
(2026-08-20 — the internship request/letter domain, `HANDOFF_INTERNSHIP.md`), **`website-assets`**
(2026-10-11 — public bucket for Website CMS & Store image uploads, listed in `PUBLIC_BUCKETS = {"website-assets"}` in `backend/app/routers/files.py` so `/files/website-assets/{path}` is served without an expiring HMAC signature), plus the
pre-existing document/certificate buckets.

**As of 2026-09-05, video HLS output is per-video, not per-bucket.** Every other bucket
above (attachments, letters, documents) is still 100% local disk; only some `videos` rows'
`storage_backend` moved to R2 — and, per code now checked into the repo, **every genuinely new
video upload lands on R2 unconditionally** (`video_service.py::_NEW_UPLOAD_BACKEND = "r2"`, not a
setting — see [`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md) §"Storage backend routing" for the full
current picture, which is more specific than this doc needs to restate).

---

## 7. R2 video storage (added 2026-09-05, PR #44 + follow-ups)

**[2026-09-17] Full current architecture has moved to its own living doc:
[`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md).** This was previously the only place any of this was
written down (plus two now-archived event runbooks); it no longer needs to be, so this section is
now just the operational facts a person deploying to the VPS specifically needs, cross-checked
against the code this pass. For the full picture — upload/transcode pipeline, the per-video
storage-backend column, playback token/playlist/segment/key endpoints, encode settings and why —
go to `HANDOFF_VIDEO.md`.

**What still belongs here, VPS-side:**

- **R2 credentials must be in `/etc/spacepoint/env` *before* any container carrying this code is
  (re)created** — confirmed in code: `video_service.py::_NEW_UPLOAD_BACKEND = "r2"` means every
  fresh video upload targets R2 unconditionally (not opt-in, not gated by a setting), so a
  container started without working `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY`/
  `R2_BUCKET` fails every video upload outright the moment someone tries one (`storage_r2.py`
  raises `RuntimeError` from `_client()`/`_endpoint()` if any are missing). Remember §2's trap:
  the env file is only read at container creation.
- **R2 bucket CORS** must list the real production domains (`https://portal.spacepoint.ae`,
  `https://lms.spacepoint.ae`), not just `localhost` from local dev — otherwise hls.js fails every
  segment fetch with a generic, misleading error. Set via Cloudflare dashboard → R2 → bucket →
  Settings → CORS Policy. (This is a Cloudflare-dashboard fact, not something checked into the
  repo — not re-verified this pass.)
- **Migration/status tool**: `python -m scripts.video_migrate_to_r2`, run inside `spacepoint-api`
  or `spacepoint-worker` (confirmed present at `backend/scripts/video_migrate_to_r2.py` this
  pass — flags are `--status`, `--sizes`, `--link-legacy-library`, `--move --to r2|vps`,
  `--convert`, `--reencode`; see `HANDOFF_VIDEO.md` for what each does).
- **R2 dashboard "Metrics" tab is not real-time and is not proof of anything being wrong.**
  `Average Storage`/`Data Retrieved` are periodic snapshots that can show `0 B` for up to ~24h
  after a real migration, even while `Class A/B Operations` and `Request Distribution` correctly
  show live non-zero traffic immediately. Trust `--sizes` (reads the actual bucket contents) or the
  dashboard's **Objects** tab (real listing) over the **Metrics** tab if they ever seem to
  disagree.
- **As of 2026-09-05, 130 pre-existing videos across all 9 courses were migrated this way** —
  `--sizes` showed ~34.6GB source → ~3GB output (≈9% of original, ~31.6GB saved). This is a
  point-in-time fact, not re-measured this pass (no VPS/R2 access) — current real counts need a
  fresh `--status`/`--sizes` run on the VPS.
- The original design rationale (why 10s segments, why the remux-gate fix, encode settings) and
  the runbook this was executed against are now in `docs/archive/HANDOFF_VIDEO_R2_EXECUTION.md`
  and `docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md` — retired, historical, not living docs
  (see `docs/archive/README.md`). `HANDOFF_VIDEO.md` is what carries forward from them.

---

## 8. Known state as of 2026-10-11

A point-in-time snapshot — verify against `git log`, `docker ps`, and the actual site before
trusting this section specifically.

- **Marketing Website (`https://spacepoint.ae`), SpacePoint Labs (`https://labs.spacepoint.ae`), and Portal Website CMS & Store (`https://portal.spacepoint.ae`) are live** as of **2026-10-11** on Alembic head `c7d3e1f9a2b5`:
  - All 12 Website CMS tabs (`/admin/website`, `/operations/inventory/website`) and Store & Merchandise (`/admin/shop`, `/operations/inventory/shop`) are live and seeded with production defaults.
  - `POST /public/leads` stores inquiries/bookings in `website_leads` and forwards an HTML notification email to `WebsiteConfig.contact_email` (`info@spacepoint.ae`).
  - `CORSMiddleware` allows `https://spacepoint.ae` and `https://*.spacepoint.ae` via `allow_origin_regex`.
  - `/var/www/spacepoint-website-repo/.env` on the VPS has `PUBLIC_API_URL=https://portal.spacepoint.ae/api`.
- `lms.spacepoint.ae` is live, per §4's pattern.
- LMS Phase 1 + Observer Mode + Student & Observer Operations Hub (`/lms-authoring/students`) + Competition Judging with Observer Partitioning are deployed and live. See `HANDOFF_LMS.md` and `HANDOFF_COMPETITIONS.md`.
- **R2/video-compression rollout (PR #44 + follow-ups) is deployed and all pre-existing content
  migrated** — all 9 courses, 130 videos, confirmed `on=r2` via `--sizes`/`--status`. See §7.
- **Three-way Add-resource UX (Link / File-upload / Video with Upload-or-Embed) now matches
  across Library and Training**.
- `client_max_body_size` bumped to `4g` on every relevant nginx site file — **done**.
- nginx `.mjs` MIME-type fix applied (§2).
- Postgres `max_connections` bumped 100 → 150 (§2) to cover the second worker container.

---

## 9. Related docs

- **`docs/HANDOFF.md`** (this repo) — general repo orientation; §11 points here for deploy detail.
- **[`docs/HANDOFF_WEBSITE.md`](./HANDOFF_WEBSITE.md)** (this repo) — **the living doc** for the Marketing Website (`spacepoint.ae`), SpacePoint Labs (`labs.spacepoint.ae`), Portal 12-tab Website CMS (`WebsiteManagement.tsx`), and E-Commerce Store (`Shop.tsx`).
- **`docs/HANDOFF_LMS.md`** (this repo) — LMS/Missions/Games architecture, including the
  TCP-congestion-control video-latency lesson (§2).
- **[`docs/HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md)** (this repo) — **the current living doc** for
  video storage/delivery architecture: upload, transcode pipeline, the per-video storage-backend
  column, playback token/playlist/segment/key endpoints, encode settings. Start here for anything
  video-related instead of §6/§7 above, which are now just the VPS-operational subset.
- **`docs/archive/HANDOFF_VIDEO_R2_EXECUTION.md`** (moved from `docs/`, 2026-09-17) — the original
  R2 design doc: encode-settings rationale, segment-length reasoning, bucket-region tradeoffs.
  Historical — executed, and superseded as a living reference by `HANDOFF_VIDEO.md`. Its §5.3
  rollback section was already superseded in-repo by the per-video `storage_backend` design
  actually shipped (see §7 above) before the archive move.
- **`docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md`** (moved from `docs/`, 2026-09-17) — the
  runbook the 2026-09-05 rollout was actually executed against. That deploy happened; this is now
  history, not a live checklist.
- **`docs/archive/README.md`** — index of what's archived and why, written the same day these two
  moved.
- **`HANDOFF_PRODUCTION_LIVE.md`, `vps_envs.md`, `secrets.md`** — real credentials and
  point-in-time infra snapshots. **Not in this repo, by design** (§0). If you're an agent without
  access to those files, the architecture in this doc is enough to reason about the system; you
  do not need the actual secret values to understand *how* deployment works.
