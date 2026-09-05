# Competition-day VPS deploy runbook

**Status:** ready to execute. Written 2026-09-05, once PR #44 (video R2/compression work,
`claude/competition-video-optimization-cm8b21`) is merging to `main`.

**Supersedes** `HANDOFF_VIDEO_R2_EXECUTION.md`'s §5.3 rollback section specifically — that section
describes a single `VIDEO_STORAGE_BACKEND` env-var flip as "the" rollback. The design changed mid-project
to a **per-video `storage_backend` column** (see PR #44) — R2 is opt-in per row, not a global switch,
so there is no single env var that rolls everything back anymore. Rollback is now
`video_migrate_to_r2.py --move --to vps --video-id <id>`, one video at a time. Everything else in
that doc (§0–§4, the encode settings, the segment-length reasoning) still holds.

Everything below assumes you have SSH access to the VPS (`187.127.191.138`, per
`HANDOFF_VPS_DEPLOYMENT.md` §1) and `sudo`.

---

## Phase A — Before you touch the VPS (do these first, in this order)

### A1. R2 credentials must already be in `/etc/spacepoint/env` — CRITICAL, blocks everything

New video uploads stamp `storage_backend="r2"` **unconditionally** the moment this deploy lands
(`_NEW_UPLOAD_BACKEND` in `video_service.py` — every LMS/Library/guideline/training upload, not
opt-in). If R2 credentials aren't already in the env file, **every video upload starts failing
the instant you deploy** — not gracefully, an actual error to whoever's uploading.

Check now, before anything else:
```bash
grep -E '^R2_(ACCOUNT_ID|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)=' /etc/spacepoint/env
```
All four must have real values (`R2_ENDPOINT_URL` is optional — defaults to
`https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com`). If any are missing, add them now — this file
is only read at container *creation*, so this has to happen before you recreate anything, not
after.

### A2. R2 bucket CORS — for the production domains, not localhost

If the CORS policy on the bucket only lists `http://localhost:5173` (from local testing), add the
real domains or hls.js will fail every segment fetch with a generic, misleading error:
```json
[{
  "AllowedOrigins": ["https://portal.spacepoint.ae", "https://lms.spacepoint.ae"],
  "AllowedMethods": ["GET", "HEAD"],
  "AllowedHeaders": ["range", "content-type"],
  "ExposeHeaders": ["content-length", "content-range", "etag"],
  "MaxAgeSeconds": 3600
}]
```
Set via the Cloudflare dashboard (R2 → your bucket → Settings → CORS Policy).

### A3. nginx — the one manual VPS-side config change this PR doesn't ship

`client_max_body_size` is still `50m` on the VPS per `HANDOFF_VPS_DEPLOYMENT.md` §7 — every
app-level upload limit was already raised to 4GB in code, so nginx is the only thing still
blocking a large upload with a `413`. On the VPS:
```bash
sudo grep -n client_max_body_size /etc/nginx/sites-available/*
```
Bump every site file that's missing it (or has the old `50m`) to `client_max_body_size 4g;`, then:
```bash
sudo nginx -t && sudo systemctl reload nginx
```

### A4. Confirm BBR is still on

```bash
sysctl net.ipv4.tcp_congestion_control
```
Should read `bbr`. This took first-segment load from 11.2s to 1.7s per `HANDOFF_LMS.md` §2 — a
kernel update can silently revert it. Less critical now that segments serve from R2 instead of the
VPS directly, but the API still serves the SPA bundle, PDFs, and every JSON call through the same
stack.

### A5. Disk headroom

```bash
df -h /var/lib/spacepoint
```
Old local HLS output is kept in place (not migrated, not deleted — see Phase F), so this deploy
itself doesn't free anything. Just confirm there's room before a bulk re-encode potentially adds
new local-disk output too (any video whose `storage_backend` stays unset re-encodes onto local
disk, same as always).

### A6. Postgres `max_connections` — recheck the math, it changed

This PR adds a **second** worker container (`spacepoint-worker-video`), which also opens its own
DB pool. With the pool sizing already in code (`pool_size=10, max_overflow=5` —
`backend/app/db/session.py`) and `uvicorn --workers 3` (`backend/Dockerfile`):

| Process | Max connections |
|---|---|
| `spacepoint-api` (×3 uvicorn workers) | 3 × 15 = 45 |
| `spacepoint-worker` | 15 |
| `spacepoint-worker-video` | 15 |
| **Total** | **75** |

```bash
sudo -u postgres psql -tAc "SHOW max_connections;"
```
Needs comfortable headroom above 75 (your own `psql` sessions, `pg_dump`, anything else). If it's
still the Postgres default of 100, that's cutting it close — bump it in `postgresql.conf` to 150+
and restart Postgres if so, **before** deploying (a restart here is unrelated to and independent of
the backend deploy).

---

## Phase B — Database backup (mandatory, before touching anything)

```bash
sudo -u postgres /path/to/ops/backup_db.sh
```
Produces a compressed `pg_dump -Fc` at `/var/backups/spacepoint/spacepoint_unified_<timestamp>.dump`.
This PR's migration (`f2c8a916e731_unify_video_service`, if not already applied — check
`sudo -u postgres psql -d spacepoint_unified -tAc "SELECT version_num FROM alembic_version;"`
against the migration's revision id) does a real backfill + `DROP TABLE module_videos`, so this
backup is your only way back if something goes wrong mid-migration. **Copy it off the VPS** —
`ops/backup_db.sh`'s own header is explicit that a backup living only on the box it protects
against isn't a backup (rsync/scp it somewhere else now, don't defer this).

Optional but recommended given the stakes: rehearse the restore once, into a throwaway DB name,
so you're not reading `ops/restore_db.sh --help` for the first time under pressure:
```bash
./ops/restore_db.sh /var/backups/spacepoint/spacepoint_unified_<timestamp>.dump spacepoint_rehearsal
# verify it, then:
dropdb -p 5432 spacepoint_rehearsal
```

---

## Phase C — Deploy

### C1. Wait for the image build

Merging the PR to `main` triggers `.github/workflows/build-backend.yml` (any push to `main`
touching `backend/**`), which rebuilds and pushes `ghcr.io/ahmedalaa612/spacepoint-api:latest`.
**Check the Action is green before pulling** — `deploy-backend.sh` pulls whatever `:latest`
currently points to, so pulling too early gets you the pre-merge image.

### C2. Preflight only — changes nothing

```bash
sudo deploy-backend.sh --check
```
This now checks (per PR #44): container config drift, any video `status='processing'` (fresh
transcode in flight), and any `transcoding:*` Redis lock (swap-in-place re-encode in flight — the
DB status alone can't see this case). Clear it before proceeding, don't override past a warning.

### C3. The real deploy

```bash
sudo deploy-backend.sh
```
This is the FIRST deploy that ships the `spacepoint-worker-video` container and the
`arq:queue:video` queue rename. Read the "One-time hazard" comment block at the top of
`ops/deploy-backend.sh` before running this specifically: **any `transcode_video` job enqueued in
the seconds right before this deploy** sits on the OLD default queue and is never picked up by
either worker afterward (a one-time transition gap, not an ongoing risk — every deploy after this
one is fine). Practically: deploy during a quiet window with nobody uploading or migrating a video
at that exact moment, and do the spot-check in C4 right after.

Then frontend:
```bash
sudo deploy-frontend.sh
```

### C4. Immediately after — spot-check for the one-time hazard

```bash
sudo -u postgres psql -d spacepoint_unified -tAc \
  "SELECT id, owner_type, created_at FROM videos WHERE status='pending' AND upload_mode='hls_encrypted';"
```
Anything here that's been `pending` for more than a minute or two is a casualty of C3's hazard —
call `enqueue_transcode()` for it again manually (or just re-run `--convert`/`--reencode` for that
one video id from the migration script, which re-enqueues it onto the new queue).

---

## Phase D — Verify both workers are actually up

```bash
docker ps --filter name=spacepoint
```
Expect `spacepoint-api`, `spacepoint-worker`, `spacepoint-worker-video`, `spacepoint-redis`, all
`Up`. Then:
```bash
curl -s http://127.0.0.1:8000/health/worker      # main worker heartbeat
docker exec spacepoint-worker-video arq app.workers.main.VideoWorkerSettings --check; echo $?   # 0 = healthy
```

Then a real functional smoke test — one upload through the browser UI, in each of the four
features, confirming it compresses and plays:
- LMS course module video
- Checklist guideline video (and try the new admin "Preview" button — PR #44's last commit)
- Instructor Library video
- Facilitator training video

---

## Phase E — Roll out the actual video migration (separate from the deploy itself)

Do this deliberately, not all at once, and not during active student traffic. Every command below
runs inside the `spacepoint-api` or `spacepoint-worker` container (`docker exec -it spacepoint-api
bash`, then the `python -m scripts...` commands), per `video_migrate_to_r2.py`'s own docstring.

1. `python -m scripts.video_migrate_to_r2 --status` — baseline, know what you're starting from.
2. `python -m scripts.video_migrate_to_r2 --link-legacy-library --dry-run`, then for real — fixes
   the pre-migration Library videos that were serving `video_info: null`.
3. `python -m scripts.video_migrate_to_r2 --convert --owner-type library_resource --limit 1` first,
   confirm it plays, then the rest without `--limit`.
4. `python -m scripts.video_migrate_to_r2 --reencode --course <id> --limit 1 --dry-run`, then for
   real, one course at a time — **not** all 8+ courses in one bulk enqueue. `max_jobs=1` on the
   video worker drains these strictly serially; batching by course lets you watch each batch land
   before starting the next, and stop between courses if the competition schedule needs the box
   free.
5. Watch it drain: `docker logs -f spacepoint-worker-video`.
6. `python -m scripts.video_migrate_to_r2 --sizes` — confirm real compression happened (this was
   the whole point of §0.1's audit in the original plan — a source that was already H.264 and
   in-spec gets `-c copy`'d near-instantly; anything 4K/high-bitrate is what actually takes
   encode time).

---

## Phase F — Load test before trusting it with 400 people

- **Synthetic**: hit the token-issuance endpoint concurrently (the heaviest of the three
  per-playback calls — enrollment check + JWT sign):
  ```bash
  hey -n 4000 -c 400 -H "Authorization: Bearer <a real student JWT>" \
      https://portal.spacepoint.ae/api/lms/items/<id>/video/token
  ```
  Watch `docker stats spacepoint-api` and `pg_stat_activity` count during it. p99 should stay well
  under a second; connection count must stay under the `max_connections` figure from A6.
- **Real**: get 5-10 people on real, different connections playing different videos at once.
  A synthetic test won't catch a CORS misconfiguration or a bad codec profile — a browser will.
- Confirm a fresh browser tab, incognito, as a real enrolled student: Network tab shows exactly 3
  requests to `portal.spacepoint.ae` (token, playlist, key) and everything else goes to
  `*.r2.cloudflarestorage.com`.

---

## Go/no-go checklist

- [ ] A1 — R2 credentials confirmed in `/etc/spacepoint/env`
- [ ] A2 — R2 CORS covers `portal.spacepoint.ae` and `lms.spacepoint.ae`
- [ ] A3 — nginx `client_max_body_size 4g` on every relevant site file, reloaded
- [ ] A4 — BBR confirmed on
- [ ] A5 — disk headroom checked
- [ ] A6 — Postgres `max_connections` covers 75 + headroom
- [ ] B — DB backup taken AND copied off the VPS; restore rehearsed at least once
- [ ] C1 — GHCR image build green on the actual merge commit
- [ ] C2 — `deploy-backend.sh --check` clean
- [ ] C3/C4 — deployed during a quiet window; no stuck `pending` rows after
- [ ] D — both worker containers confirmed healthy; one real upload verified per feature
- [ ] E — migration rolled out course-by-course, `--sizes` confirms real compression
- [ ] F — synthetic + real concurrent playback test done, before the actual event
