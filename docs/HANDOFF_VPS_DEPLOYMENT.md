# VPS & Deployment Handoff

**Audience:** any agent picking up this repo cold who needs to understand what's actually running
in production, how a change gets from a commit to a live server, and the operational gotchas that
aren't obvious from reading the code. Written 2026-08-10 from direct, hands-on observation of a
real deploy + a real bulk content import — not from documentation review. **Updated 2026-09-05**
after the R2/video-compression rollout (PR #44 and follow-ups) actually deployed and all existing
video content migrated — see §2, §6, §7, and the new §9.

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
| `spacepoint-worker` | same image | `arq app.workers.main.WorkerSettings` — every IO-bound job (email, LMS sync, inventory reminders, `heartbeat` cron). **Recreated fresh on every `deploy-backend.sh` run**, not just restarted — see the gotcha in §3. |
| `spacepoint-worker-video` | same image | `arq app.workers.main.VideoWorkerSettings` — `transcode_video` only, on its own queue (`arq:queue:video`), `max_jobs=1`. **Confirmed live** — deployed 2026-09-05, has drained every course's full re-encode/migrate-to-R2 backlog since (130 videos, ~34.6GB source → ~3GB output, see §9). Same bind-mounts/env-file/restart policy as `spacepoint-worker`; recreated the same way, but the swap order is deliberately different (stops the old container before starting the new one, not start-new-then-retire-old) — two containers both enforcing `max_jobs=1` against the same queue at once would let two encodes run concurrently. If this container isn't running, `transcode_video` jobs queue and never run — uploads/re-encodes sit "pending" forever with no visible error. |
| `spacepoint-redis` | `redis:7-alpine` | `127.0.0.1:6379`. **Not** recreated by `deploy-backend.sh` — confirmed by direct observation (uptime survives backend deploys), so the arq queue's state isn't lost on a routine deploy. Also holds the `transcoding:{video_id}` lock keys used by `deploy-backend.sh --check`'s preflight (§3). |

**Not in Docker:**

- **nginx** — TLS via certbot, auto-renewing. One file per domain under
  `/etc/nginx/sites-available/`. `portal.spacepoint.ae`'s file is the canonical, confirmed-live
  example (§4). Also carries a scoped `location ~* \.mjs$ { types { application/javascript mjs; }
  default_type application/javascript; try_files $uri =404; }` block (added 2026-09-05, between the
  `/files/` and `/` blocks) — without it, PDF.js's worker script (`pdf.worker.min.mjs`) is served
  with `application/octet-stream` from the default `mime.types`, which the browser refuses to load
  as an ES module. A regex `location` block always wins over the plain `location /` prefix block
  regardless of file order, which is why this was scoped here instead of editing the shared system
  `mime.types` (would affect every other app on the box).
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
  take effect immediately does nothing — the container needs to actually restart/recreate.

---

## 3. The deploy scripts (`/usr/local/bin/` on the VPS)

**`deploy-backend.sh`** — observed output, in order (steps 1-4 confirmed by direct observation;
step 3b is new with the R2/video-optimization branch, not yet observed on a real deploy):
1. `docker pull` the `:latest` image from GHCR.
2. Recreate `spacepoint-api`; wait for it to report healthy (migrations run first, inside the
   container's own entrypoint, before `uvicorn` binds).
3. Recreate `spacepoint-worker`.
3b. Recreate `spacepoint-worker-video`, waiting on arq's own `--check` health check (not
    `/health/worker`, which only reflects `spacepoint-worker`'s heartbeat key and says nothing
    about the video queue).
4. Fails loudly and doesn't leave a broken container running if the health check doesn't pass —
   confirmed this is a real, working guard, not just a comment for `spacepoint-api`/`spacepoint-worker`;
   the same pattern is now applied to `spacepoint-worker-video` but rehearse it once before trusting it.

Preflight (`deploy-backend.sh --check`) also refuses to proceed if any video is mid-transcode:
a fresh upload/transcode shows as `videos.status='processing'` in Postgres, but a swap-in-place
re-encode (e.g. "Migrate to R2") never changes `status` — the row stays `"ready"` the whole time
by design, so the DB check alone is blind to it. The transcode job holds a `transcoding:{video_id}`
Redis key for that window instead; preflight checks both.

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
**host disk**, bind-mounted into `spacepoint-api`, `spacepoint-worker`, and `spacepoint-worker-video`
at `/data/storage`, Fernet-encrypted at rest and decrypted on every read. This is real, persistent storage — **not**
the ephemeral per-container filesystem from the §3 gotcha; a deploy does not touch it. Buckets in
active use include `lms-video-sources`, `lms-hls`, `lms-attachments`, `internship-letters`
(2026-08-20 — the internship request/letter domain, `HANDOFF_INTERNSHIP.md`), plus the
pre-existing document/certificate buckets.

**As of 2026-09-05, video HLS output is per-video, not per-bucket** — see §9. Every other bucket
above (attachments, letters, documents) is still 100% local disk; only `videos.storage_backend`
rows moved.

---

## 7. R2 video storage (added 2026-09-05, PR #44 + follow-ups)

Every video (LMS module, Library, checklist guideline, facilitator Training) now runs through the
same `video_service` pipeline: compress to 1080p h264/aac, 10s HLS segments, and land on **one of
two backends per row**, tracked by `videos.storage_backend` (`"r2"` or `NULL`/local) — there is no
global on/off switch, and there never will be; it's an incremental, reversible, per-video decision.

- **One R2 bucket for everything.** `storage_r2.py` maps `(app_bucket, path)` → key
  `f"{app_bucket}/{path}"` inside a single real R2 bucket (`R2_BUCKET` in
  `/etc/spacepoint/env`) — app-level "buckets" are just key prefixes, same convention as local
  storage.
- **`source_bucket`/`source_path` always point at local disk, never R2, and are never deleted** —
  deliberate: it's the rollback path. `playlist_path`/`key_path` (the HLS output actually served to
  students) is the only thing that differs per backend.
- **Old local HLS output for already-migrated videos is deliberately kept on disk, not cleaned
  up** — reclaiming that space is explicitly deferred to after the competition, not a bug or an
  oversight if `df -h /var/lib/spacepoint` still looks full post-migration.
- **Migration/status tool**: `python -m scripts.video_migrate_to_r2` (run inside `spacepoint-api`
  or `spacepoint-worker`, per its own docstring) — `--status`, `--sizes` (real object sizes/ratios,
  read-only, no download), `--convert`/`--reencode --course <id>` (enqueues onto
  `arq:queue:video`, drained by `spacepoint-worker-video`, `max_jobs=1` so it's strictly serial —
  batch per course, not all at once), `--move --to vps --video-id <id>` (the actual rollback path).
  **All 130 pre-existing videos were migrated this way as of 2026-09-05** — `--sizes` showed
  ~34.6GB source → ~3GB output (≈9% of original, ~31.6GB saved), ratios in the 6-11% range across
  every course, all confirmed `on=r2`.
- **Known real bug, fixed**: the migration script's `--convert`/`--reencode` originally called
  `redis.enqueue_job()` directly without `_queue_name="arq:queue:video"`, landing jobs on the
  default queue neither worker consumed — they'd sit at `status='pending'` indefinitely with no
  error. Fixed in the same PR that added the script; if a job is ever seen stuck `pending` for more
  than a couple minutes, this is the first thing to check (re-running `--reencode` for that one
  video id re-enqueues it correctly).
- **R2 dashboard "Metrics" tab is not real-time and is not proof of anything being wrong.**
  `Average Storage`/`Data Retrieved` are periodic snapshots that can show `0 B` for up to ~24h
  after a real migration, even while `Class A/B Operations` and `Request Distribution` correctly
  show live non-zero traffic immediately. Trust `--sizes` (reads the actual bucket contents) or the
  dashboard's **Objects** tab (real listing) over the **Metrics** tab if they ever seem to
  disagree.
- **CORS** on the bucket must list the real production domains (`https://portal.spacepoint.ae`,
  `https://lms.spacepoint.ae`), not just `localhost` from local dev — otherwise hls.js fails every
  segment fetch with a generic, misleading error. Set via Cloudflare dashboard → R2 → bucket →
  Settings → CORS Policy.
- See `docs/HANDOFF_VIDEO_R2_EXECUTION.md` for the original design/encode-settings rationale and
  `docs/HANDOFF_COMPETITION_DAY_DEPLOY.md` for the runbook this was actually executed against.

---

## 8. Known state as of 2026-09-05

A point-in-time snapshot — verify against `git log`, `docker ps`, and the actual site before
trusting this section specifically (everything above it is architecture/mechanism and ages much
slower than this list). Supersedes the 2026-08-10 snapshot this section used to hold; the items
below either close out or update items from that list.

- `lms.spacepoint.ae` is live, per §4's pattern.
- LMS Phase 1 is functionally complete and deployed — course content, video pipeline, quizzes,
  PDF attachments, all live. See `HANDOFF_LMS.md` for the current architecture.
- **R2/video-compression rollout (PR #44 + follow-ups) is deployed and all pre-existing content
  migrated** — all 9 courses, 130 videos, confirmed `on=r2` via `--sizes`/`--status`. See §7.
- **Three-way Add-resource UX (Link / File-upload / Video with Upload-or-Embed) now matches
  across Library and Training** — Training used to only support pasting a link before a separate
  upload step existed elsewhere; it's now a single-step dialog identical in structure to
  Library's. Both also got module-title/description edit endpoints and UI (`PATCH
  /library/modules/{id}`, `PATCH /training/modules/{id}`).
- `client_max_body_size` bumped to `4g` on every relevant nginx site file (was `50m`, would `413`
  any video upload through the browser authoring UI) — **done**, no longer outstanding.
- nginx `.mjs` MIME-type fix applied (§2) — was causing a hard PDF.js worker load failure in
  Library's PDF viewer.
- Postgres `max_connections` bumped 100 → 150 (§2) to cover the new second worker container.
- HTTP/2 not confirmed enabled (`listen 443 ssl;` vs `listen 443 ssl http2;` on nginx 1.24) —
  still an open item, not addressed by this round of work.
- **Still outstanding, only this**: the Phase F load test from
  `docs/HANDOFF_COMPETITION_DAY_DEPLOY.md` (synthetic concurrent-request test + a real multi-viewer
  playback test) has not been run yet against the now-fully-migrated content. Everything else on
  that runbook's go/no-go checklist is done.
- Old local HLS output for already-migrated videos is still on disk (`source_bucket`/`source_path`
  are deliberately never deleted, for rollback safety) — reclaiming that space is explicitly
  deferred to after the competition, not an oversight.

---

## 9. Related docs

- **`docs/HANDOFF.md`** (this repo) — general repo orientation; §11 points here for deploy detail.
- **`docs/HANDOFF_LMS.md`** (this repo) — LMS/Missions/Games architecture, including the
  TCP-congestion-control video-latency lesson (§2).
- **`docs/HANDOFF_VIDEO_R2_EXECUTION.md`** (this repo) — original R2 design doc: encode settings,
  segment-length reasoning, bucket-region tradeoffs. §5.3's rollback section is superseded by the
  per-video `storage_backend` design actually shipped — see §7 above.
- **`docs/HANDOFF_COMPETITION_DAY_DEPLOY.md`** (this repo) — the runbook this rollout was actually
  executed against; its go/no-go checklist tracks what's still open (as of 2026-09-05, just the
  Phase F load test).
- **`HANDOFF_PRODUCTION_LIVE.md`, `vps_envs.md`, `secrets.md`** — real credentials and
  point-in-time infra snapshots. **Not in this repo, by design** (§0). If you're an agent without
  access to those files, the architecture in this doc is enough to reason about the system; you
  do not need the actual secret values to understand *how* deployment works.
