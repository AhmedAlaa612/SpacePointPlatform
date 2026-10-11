# VPS & Deployment Handoff

**Audience:** any agent picking up this repo cold who needs to understand what's actually running
in production, how a change gets from a commit to a live server, and the operational gotchas that
aren't obvious from reading the code. Written 2026-08-10 from direct, hands-on observation of a
real deploy + a real bulk content import — not from documentation review. **Updated 2026-09-05**
after the R2/video-compression rollout (PR #44 and follow-ups) actually deployed and all existing
video content migrated — see §2, §6, §7, and §9.

**Re-verified 2026-09-17** (routine doc-freshness pass, no VPS access this session — see the note
below). This pass cross-checked every claim below against what's actually checked into this repo
today: `ops/deploy-backend.sh`, `ops/deploy-frontend.sh`, `ops/backup_db.sh`, `ops/restore_db.sh`,
`backend/Dockerfile`, `docker-compose.dev.yml`, and the video/storage code under `backend/app/`.
Both deploy scripts now live in the repo (`ops/`) rather than being VPS-only artifacts — a real
improvement since 2026-09-05, they're reviewable and diffable now, and `ops/legacy/` holds the
simpler pre-rewrite versions for reference. Corrections from this pass are called out inline as
**[2026-09-17]**. Nothing that requires an actual SSH session (current `docker ps` output, nginx
site files, the real Postgres config, whether cron jobs are installed) could be checked this
pass — those claims are left as "documented, not re-verified" rather than guessed at. The detailed
current video architecture (upload, transcode, storage-backend routing, playback token/playlist/
segment/key endpoints) has moved to its own living doc: **[`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md)**
— §7 here is now a short pointer to it plus the VPS-specific operational facts that belong here.

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

**[2026-09-17] Nothing in this section is checked into the repo** (no Terraform/Ansible/inventory
file, no DNS-as-code) — it's operator knowledge, unverifiable from this codebase alone. Carried
forward as documented, not re-confirmed this pass.

---

## 2. What's actually running on the VPS

**Docker (`docker ps`):**

| Container | Image | Notes |
|---|---|---|
| `spacepoint-api` | `ghcr.io/ahmedalaa612/spacepoint-api:latest` | `--network host`, `--env-file /etc/spacepoint/env`, storage volume `/var/lib/spacepoint/storage:/data/storage`. Entrypoint runs `alembic upgrade head` before `uvicorn` — migrations apply once per deploy, not on every boot. |
| `spacepoint-worker` | same image | `arq app.workers.main.WorkerSettings` — every IO-bound job (email, LMS sync, inventory reminders, `heartbeat` cron). **Recreated fresh on every `deploy-backend.sh` run**, not just restarted — see the gotcha in §3. |
| `spacepoint-worker-video` | same image | `arq app.workers.main.VideoWorkerSettings` — `transcode_video` only, on its own queue (`arq:queue:video`), `max_jobs=1`. **Confirmed live** — deployed 2026-09-05, has drained every course's full re-encode/migrate-to-R2 backlog since (130 videos, ~34.6GB source → ~3GB output, see §9). Same bind-mounts/env-file/restart policy as `spacepoint-worker`; recreated the same way, but the swap order is deliberately different (stops the old container before starting the new one, not start-new-then-retire-old) — two containers both enforcing `max_jobs=1` against the same queue at once would let two encodes run concurrently. If this container isn't running, `transcode_video` jobs queue and never run — uploads/re-encodes sit "pending" forever with no visible error. |
| `spacepoint-redis` | `redis:7-alpine` | `127.0.0.1:6379`. **Not** recreated by `deploy-backend.sh` — confirmed by direct observation (uptime survives backend deploys), so the arq queue's state isn't lost on a routine deploy. Also holds the `transcoding:{video_id}` lock keys used by `deploy-backend.sh --check`'s preflight (§3). |

**[2026-09-17]** This table's shape is confirmed against `ops/deploy-backend.sh`, which is now
checked into the repo and recreates exactly these four containers by name (`spacepoint-api`,
`spacepoint-worker`, `spacepoint-worker-video`, plus reads `spacepoint-redis` for the preflight
lock check) — see §3. The actual live `docker ps` output on the VPS itself was **not**
re-observed this pass (no VPS access); this row is "matches what the deploy script would produce",
not a fresh direct observation. Video architecture detail (what `transcode_video` actually does,
the per-video `storage_backend` routing) has moved to [`HANDOFF_VIDEO.md`](./HANDOFF_VIDEO.md).

**Not in Docker:**

- **nginx** — TLS via certbot, auto-renewing. One file per domain under
  `/etc/nginx/sites-available/`. `portal.spacepoint.ae`'s file is the canonical, confirmed-live
  example (§4). Also carries a scoped `location ~* \.mjs$ { types { application/javascript mjs; }
  default_type application/javascript; try_files $uri =404; }` block (added 2026-09-05, between the
  `/files/` and `/` blocks) — without it, PDF.js's worker script (`pdf.worker.min.mjs`) is served
  with `application/octet-stream` from the default `mime.types`, which the browser refuses to load
  as an ES module. A regex `location` block always wins over the plain `location /` prefix block
  regardless of file order, which is why this was scoped here instead of editing the shared system
  `mime.types` (would affect every other app on the box). **[2026-09-17] No nginx config is checked
  into this repo** (no `nginx/` directory, no config-management tooling), so none of this section —
  the `.mjs` fix, `client_max_body_size`, the per-domain file layout — could be re-verified against
  anything in the repo this pass. Documented from the 2026-09-05 hands-on pass, not re-confirmed.
- **PostgreSQL 16**, port 5432 — the real database (`spacepoint_unified`) lives here. A
  *separate* PostgreSQL 17 also exists on this box on port 5433, left over from using its newer
  `pg_restore` during an earlier migration — don't confuse the two; the app only ever talks to
  16/5432. `max_connections` bumped **100 → 150** on 2026-09-05 (`/etc/postgresql/16/main/postgresql.conf`,
  requires a Postgres restart to take effect) to cover the second worker container: 3 uvicorn
  workers × 15 (`pool_size=10`+`max_overflow=5`) + 2 worker containers × 15 = 75 possible app
  connections, and 150 leaves real headroom for manual `psql`/`pg_dump` sessions on top.
  **[2026-09-17]** The pool-sizing arithmetic is confirmed against the repo: `backend/Dockerfile`
  still runs `uvicorn --workers 3`, and `pool_size=10`/`max_overflow=5` is set in
  `backend/app/db/session.py` (checked). The **actual production `max_connections` value** — i.e.
  whether the bump to 150 really happened and is still in effect — lives in
  `/etc/postgresql/16/main/postgresql.conf` on the VPS, which is outside this repo; not
  re-verified this pass, carried forward as documented. Same for "Postgres 16 runs natively (not
  Docker) on port 5432" itself — true as of the 2026-09-05 hands-on pass, consistent with there
  being no Postgres service in `docker-compose.dev.yml` beyond the *dev* container (which
  deliberately binds `5433:5432` so it never collides with a real local Postgres — see that file's
  own comment), but there is no VPS-side infra file in this repo to re-confirm it against.
- **`/etc/spacepoint/env`** (mode `0600`) — the real env file `spacepoint-api`, `spacepoint-worker`,
  and `spacepoint-worker-video` all load via `--env-file`. Real values are outside this repo (§0). One trap:
  **this file is only read at container *creation***, so editing it and expecting the change to
  take effect immediately does nothing — the container needs to actually restart/recreate. Confirmed
  again this pass: every `docker run`/`docker rm -f && docker run` pair in `ops/deploy-backend.sh`
  passes `--env-file "$ENV_FILE"` fresh at creation time, with no in-place env reload path.

---

## 3. The deploy scripts (`/usr/local/bin/` on the VPS)

**[2026-09-17] Both scripts now live in this repo**, at `ops/deploy-backend.sh` and
`ops/deploy-frontend.sh` — reviewable/diffable in git rather than only existing as
hand-installed files on the VPS. Install with `sudo install -m 755 ops/deploy-backend.sh
/usr/local/bin/deploy-backend.sh` (each script's own header says so). `ops/legacy/` holds the
earlier, simpler versions of both (no rollback, no video worker, no frontend backup/rollback) —
kept for reference, not installed anywhere; don't confuse the two when checking what's actually
running on the VPS. Everything below in this section is read directly from the current
`ops/deploy-backend.sh` / `ops/deploy-frontend.sh`, not re-observed from a live deploy this pass.

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

Confirmed **already executed successfully in production** once — the archived
`docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md` records this exact script shipping the
`spacepoint-worker-video` container live on 2026-09-05 and both workers confirmed healthy
afterward — so "not yet observed on a real deploy" (this doc's earlier wording) is now stale;
strike it.

**`deploy-frontend.sh`**
```
deploy-frontend.sh            # download the latest build and swap it in
deploy-frontend.sh --rollback # restore the most recent backup
deploy-frontend.sh --list     # show available backups
```
**[2026-09-17]** More capable than previously documented here — it now keeps its own backup
history, not just "safe against a failed download":
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
   `dist`) — **this one directory is what every domain's nginx `root` points at** (portal, lms,
   any future vanity domain), so one frontend deploy updates all of them simultaneously.
5. Safe against a failed download or a truncated build — won't touch the live site if either
   check fails.

`--rollback` restores the most recent entry under `$ROOT/backups/`; `--list` shows what's
available. Neither existed in the version this doc previously described.

Standard sequence when both sides changed: `deploy-backend.sh && deploy-frontend.sh` (backend
first). Deploy is **manual on purpose** — CI builds the artifact; a human (or an agent, if
explicitly told to) runs the script. Nothing auto-deploys on merge.

**`deploy-website.sh`** (Marketing Website — `https://spacepoint.ae`)
```
deploy-website.sh            # pull AhmedAlaa612/spacepoint-website, build Astro static site, atomic swap into /var/www/spacepoint-website
deploy-website.sh --legacy   # emergency rollback to legacy static site
```
1. Pulls `main` from `https://github.com/AhmedAlaa612/spacepoint-website` into `/var/www/spacepoint-website-repo`.
2. Runs `npm install` and `npm run build` (`astro build`).
3. Backs up the current live build into `/var/www/spacepoint-website/backups/<timestamp>` and atomically swaps the new `dist/` into place, then reloads nginx.

**`deploy-labs.sh`** (SpacePoint Labs — `https://labs.spacepoint.ae`)
```
deploy-labs.sh               # pull AhmedAlaa612/spacepoint-labs into /var/www/spacepoint-labs and reload nginx
```
Pulls `main` from `https://github.com/AhmedAlaa612/spacepoint-labs` into `/var/www/spacepoint-labs` (pure static HTML/WebGL simulation, no build step) and reloads nginx.

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

**[2026-09-17] The nginx pattern itself (the `server { ... }` block above) could not be
re-verified this pass** — no nginx config is checked into this repo, only referenced by these
docs. Carried forward as documented from the 2026-09-05 pass.

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

Two workflows, `.github/workflows/` — **re-confirmed against the actual workflow YAML this pass
[2026-09-17], unchanged from what this doc already said:**

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
active use include `video-sources` (video pre-transcode sources — **[2026-09-17] corrected from
`lms-video-sources`**, which was never the real constant; `backend/app/services/video_service.py::
SOURCE_BUCKET = "video-sources"` is what's actually checked into the repo), `lms-hls` (video HLS
output — kept under its original name even though the video service is no longer LMS-only, see
that file's own comment on why renaming it once already broke playback), `lms-attachments`
(checklist/program PDF attachments — `backend/app/routers/lms/admin.py::ATTACHMENT_BUCKET` /
`backend/app/services/lms/program.py::PROGRAM_ITEM_PDF_BUCKET`), `internship-letters`
(2026-08-20 — the internship request/letter domain, `HANDOFF_INTERNSHIP.md`), plus the
pre-existing document/certificate buckets. All four of those bucket-name constants were
re-confirmed by reading the actual code this pass.

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

## 8. Known state as of 2026-09-05

A point-in-time snapshot — verify against `git log`, `docker ps`, and the actual site before
trusting this section specifically (everything above it is architecture/mechanism and ages much
slower than this list). Supersedes the 2026-08-10 snapshot this section used to hold; the items
below either close out or update items from that list. **[2026-09-17] Left as-is from the
2026-09-05 pass** — it's explicitly a dated snapshot, not a claim about today. The one item worth
flagging: the "Three-way Add-resource UX" and R2-migration bullets below are consistent with the
code read for this pass (§6-§7, `HANDOFF_VIDEO.md`), so nothing here looked wrong, but nobody
re-walked the live site this session to confirm current behavior — that needs a human/agent with
actual portal access, not just a repo read.

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
  `docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md` (synthetic concurrent-request test + a real
  multi-viewer playback test) has not been run yet against the now-fully-migrated content.
  Everything else on that runbook's go/no-go checklist is done. **[2026-09-17] Not re-checked this
  pass** — whether this load test ran at any point since 2026-09-05 needs someone with the actual
  event/production history, not a repo read.
- Old local HLS output for already-migrated videos is still on disk (`source_bucket`/`source_path`
  are deliberately never deleted, for rollback safety) — reclaiming that space is explicitly
  deferred to after the competition, not an oversight.

---

## 9. Related docs

**[2026-09-17] Updated** — the three video/R2 runbooks this section used to point at were moved
to `docs/archive/` on this date (retired, event-specific, superseded by a living doc); links below
reflect their current location.

- **`docs/HANDOFF.md`** (this repo) — general repo orientation; §11 points here for deploy detail.
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
