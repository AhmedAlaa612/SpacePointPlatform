#!/usr/bin/env bash
# Backend deploy for the VPS. Lives in the repo so it is reviewable and
# versioned; install with:
#   sudo install -m 755 ops/deploy-backend.sh /usr/local/bin/deploy-backend.sh
#
# Recreates spacepoint-api (brief downtime — the container is --network host,
# so only one can hold :8000 at a time) then swaps spacepoint-worker with no
# downtime at all. Migrations run inside the API container's own entrypoint,
# before uvicorn binds, so "waiting for healthy" and "waiting for migrations"
# are the same wait.
#
# Two worker containers, not one: spacepoint-worker runs
# `arq app.workers.main.WorkerSettings` (IO-bound jobs — email, LMS sync,
# default concurrency); spacepoint-worker-video runs
# `arq app.workers.main.VideoWorkerSettings` (transcode_video only, max_jobs=1,
# its own queue) so an hour-long re-encode can't back up every other job
# behind it. Both must be running or nothing consumes the video queue at all —
# uploads and re-encodes would sit "pending" forever, silently.
#
# spacepoint-worker-video's swap has a brief GAP, not zero downtime: the old
# container is stopped before the new one starts (queued jobs just wait — a
# transcode is fine to be seconds late, never fine to run twice at once).
# Two workers briefly both dequeuing the same job is exactly what max_jobs=1
# exists to prevent, so this queue does not get the same start-new-first
# treatment as spacepoint-worker/spacepoint-api.
#
#   deploy-backend.sh                 # normal deploy, auto-rollback armed
#   deploy-backend.sh --no-rollback   # REQUIRED for destructive migrations
#   deploy-backend.sh --check         # preflight only, changes nothing
#
# ── When to pass --no-rollback ──────────────────────────────────────────────
# The rollback swaps the API back to the previous IMAGE. It cannot roll back
# the DATABASE, and migrations have already committed by the time a health
# check can fail. For an additive migration that is fine: old code simply
# ignores the new column. For a DESTRUCTIVE one it is actively harmful —
# e.g. the unify_video_service migration drops `module_videos`, so rolling the
# image back gives you new schema + old code, a site that looks up but 500s on
# every LMS video page. That is worse than being down, because it is not
# obviously broken.
#
# Rule: if the deploy carries a migration with drop_table/drop_column/a
# not-null backfill, pass --no-rollback and recover by restoring the dump
# (ops/restore_db.sh) and redeploying, not by swapping the image back.
#
# ── Do not deploy mid-transcode ─────────────────────────────────────────────
# `docker rm -f` is SIGKILL. It bypasses run_encrypted_transcode's
# CancelledError handler (which only catches arq's own job cancellation), so an
# in-flight video transcode dies with its row stuck at "processing" forever,
# with nothing to retry it. Check first — the preflight below does.
#
# A swap-in-place re-encode (re-encoding an already-`ready` video onto a
# DIFFERENT backend, e.g. "Migrate to R2") never sets status='processing' —
# it deliberately keeps serving the old copy the whole time, so the DB alone
# can't tell idle from mid-transcode for those. The transcode job holds a
# `transcoding:{video_id}` Redis key for that exact window; the preflight
# checks that too.
#
# ── One-time hazard: the FIRST deploy that ships arq:queue:video ───────────
# transcode_video moved off the default arq queue and onto its own
# (backend/app/workers/main.py — WorkerSettings no longer registers it,
# VideoWorkerSettings does). A job enqueued moments before THIS SPECIFIC
# deploy sits on the OLD default queue with status='pending' and no
# transcoding:* lock yet (the lock is only set once a job starts running) —
# neither preflight check above sees it, and after this deploy nothing
# consumes that queue for transcode_video anymore, so it is stuck 'pending'
# forever with no error anywhere. Not an ongoing risk (every deploy after
# this one enqueues straight onto arq:queue:video), just this one: deploy
# during a quiet window with no video upload/migration in flight, and
# spot-check `SELECT id FROM videos WHERE status='pending'` right after —
# any hit needs enqueue_transcode() called again manually for that video.

set -euo pipefail

IMAGE="ghcr.io/ahmedalaa612/spacepoint-api:latest"
ENV_FILE="/etc/spacepoint/env"
STORAGE_MOUNT="/var/lib/spacepoint/storage:/data/storage"
HEALTH_URL="http://127.0.0.1:8000/health"
WORKER_HEALTH_URL="http://127.0.0.1:8000/health/worker"
HEALTH_TIMEOUT_SECONDS=180

ALLOW_ROLLBACK=1
CHECK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-rollback) ALLOW_ROLLBACK=0 ;;
    --check)       CHECK_ONLY=1 ;;
    -h|--help)     sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

API_ROLLBACK_ARMED=0

# ── Preflight ───────────────────────────────────────────────────────────────
# The `docker run` lines below are this script's ASSUMPTION about how the
# containers are configured. If the live container carries anything else — an
# extra volume, a log driver, a different restart policy — recreating it from
# these flags silently drops that. Catch it here rather than discovering it in
# production.
preflight() {
  local drift=0

  if docker inspect spacepoint-api >/dev/null 2>&1; then
    local binds network restart
    binds=$(docker inspect spacepoint-api --format '{{json .HostConfig.Binds}}')
    network=$(docker inspect spacepoint-api --format '{{.HostConfig.NetworkMode}}')
    restart=$(docker inspect spacepoint-api --format '{{.HostConfig.RestartPolicy.Name}}')
    [ "$network" = "host" ] || { echo "!! api NetworkMode is '$network', script assumes 'host'" >&2; drift=1; }
    [ "$restart" = "unless-stopped" ] || { echo "!! api RestartPolicy is '$restart', script assumes 'unless-stopped'" >&2; drift=1; }
    case "$binds" in
      *"$STORAGE_MOUNT"*) ;;
      *) echo "!! api Binds are $binds — script only recreates $STORAGE_MOUNT" >&2; drift=1 ;;
    esac
  fi

  # An in-flight transcode would be SIGKILLed by the recreate below and left
  # stuck at "processing" with nothing to retry it.
  local processing
  processing=$(sudo -u postgres psql -d spacepoint_unified -tAc \
    "SELECT count(*) FROM videos WHERE status='processing'" 2>/dev/null || echo "?")
  if [ "$processing" != "0" ] && [ "$processing" != "?" ]; then
    echo "!! $processing video(s) are mid-transcode (fresh upload). Recreating the worker" >&2
    echo "!! SIGKILLs them and leaves their rows stuck at 'processing'. Wait, or reset" >&2
    echo "!! those rows after." >&2
    drift=1
  fi

  # A swap-in-place re-encode (e.g. "Migrate to R2") never touches `status` —
  # the row still reads "ready" the whole time it's re-encoding, by design, so
  # the query above is blind to it. The transcode job holds an explicit
  # `transcoding:{video_id}` Redis key for that exact window instead. Queried
  # via `docker exec` into the (never-recreated) redis container rather than
  # requiring redis-cli + REDIS_URL parsing on the host itself.
  local transcoding_locks scan_output
  # Split into two steps rather than piping straight into `wc -l || echo "?"`:
  # under `set -o pipefail`, a failing left-hand command still lets `wc -l`
  # emit "0" for its empty input, so the `||` ALSO fires and the two outputs
  # concatenate into a garbled "0\n?" that matches neither branch below.
  if scan_output=$(docker exec spacepoint-redis redis-cli --scan --pattern 'transcoding:*' 2>/dev/null); then
    transcoding_locks=$(echo "$scan_output" | grep -c . || true)
  else
    transcoding_locks="?"
  fi
  if [ "$transcoding_locks" != "0" ] && [ "$transcoding_locks" != "?" ]; then
    echo "!! $transcoding_locks video(s) are mid-swap-in-place-reencode (e.g. a Migrate-to-R2" >&2
    echo "!! job). Their DB status still reads 'ready' — this Redis lock is the only signal." >&2
    echo "!! Recreating the video worker SIGKILLs them mid-encode. Wait for it to clear." >&2
    drift=1
  fi

  return $drift
}

echo "==> Preflight..."
if preflight; then
  echo "==> Preflight clean."
else
  echo "" >&2
  echo "!! Preflight found drift (above). Re-run with --check to inspect, or fix first." >&2
  [ "$CHECK_ONLY" -eq 1 ] || exit 1
fi
[ "$CHECK_ONLY" -eq 1 ] && { echo "==> --check only; nothing changed."; exit 0; }

# ── Ensure spacepoint-mailpit is running ────────────────────────────────────
if ! docker ps --filter name=spacepoint-mailpit --filter status=running | grep -q spacepoint-mailpit; then
  echo "==> Starting spacepoint-mailpit..."
  docker start spacepoint-mailpit 2>/dev/null || \
    docker run -d --name spacepoint-mailpit \
      --restart unless-stopped \
      -p 127.0.0.1:1025:1025 \
      -p 127.0.0.1:8025:8025 \
      --env-file "$ENV_FILE" \
      -e MP_DATABASE=/data/mailpit.db \
      -v /var/lib/spacepoint/mailpit:/data \
      axllent/mailpit:latest
fi

# ── Pull ────────────────────────────────────────────────────────────────────
echo "==> Pulling $IMAGE ..."
docker pull "$IMAGE"

# Snapshot the running image BY ID before anything changes. Docker keeps it
# locally (merely untagged once :latest moves on), so `docker run "$ID"` still
# works. Empty on a first-ever deploy.
OLD_API_IMAGE_ID=""
if docker inspect spacepoint-api >/dev/null 2>&1; then
  OLD_API_IMAGE_ID=$(docker inspect --format='{{.Image}}' spacepoint-api 2>/dev/null || echo "")
  echo "==> Rollback target: ${OLD_API_IMAGE_ID:-<none>}"
fi

# Record the schema revision we are deploying FROM, so the recovery
# instructions below can name it instead of saying "restore something".
DB_REVISION_BEFORE=$(sudo -u postgres psql -d spacepoint_unified -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || echo "unknown")
echo "==> Schema before deploy: $DB_REVISION_BEFORE"

rollback_api() {
  echo "" >&2
  local revision_now
  revision_now=$(sudo -u postgres psql -d spacepoint_unified -tAc \
    "SELECT version_num FROM alembic_version" 2>/dev/null || echo "unknown")

  if [ "$revision_now" != "$DB_REVISION_BEFORE" ]; then
    # Migrations committed before the failure. Swapping the image back now
    # produces new-schema-plus-old-code, which is a subtler and harder-to-spot
    # breakage than an outage. Refuse, and say what to do instead.
    echo "!! DEPLOY FAILED, and migrations already committed:" >&2
    echo "!!     $DB_REVISION_BEFORE -> $revision_now" >&2
    echo "!! NOT rolling the image back — old code against the new schema would" >&2
    echo "!! come up looking healthy while failing on whatever the migration changed." >&2
    echo "!! Recover by restoring the pre-deploy dump and redeploying:" >&2
    echo "!!     ops/restore_db.sh <dump taken before this deploy>" >&2
    echo "!!     deploy-backend.sh" >&2
    echo "!! The API is DOWN until you do. That is deliberate." >&2
    return
  fi

  if [ "$ALLOW_ROLLBACK" -eq 0 ]; then
    echo "!! DEPLOY FAILED. --no-rollback was passed, so the API is left DOWN." >&2
    echo "!! Schema is unchanged at $DB_REVISION_BEFORE, so a plain redeploy of a" >&2
    echo "!! fixed image is safe." >&2
    return
  fi

  echo "!! DEPLOY FAILED before any migration committed — rolling the image back." >&2
  docker rm -f spacepoint-api >/dev/null 2>&1 || true
  if [ -z "$OLD_API_IMAGE_ID" ]; then
    echo "!! No previous image on record (first-ever deploy?) — spacepoint-api is DOWN." >&2
    return
  fi
  docker run -d --name spacepoint-api \
    --restart unless-stopped --network host \
    --log-opt max-size=10m --log-opt max-file=3 \
    --env-file "$ENV_FILE" \
    -v "$STORAGE_MOUNT" \
    "$OLD_API_IMAGE_ID"
  echo "!! Rolled back to $OLD_API_IMAGE_ID (schema untouched at $DB_REVISION_BEFORE)." >&2
}

# Fires on ANY nonzero exit while armed — not just the explicit checks — so an
# unexpected error mid-recreate still lands in the handler above rather than
# leaving nothing running.
on_exit() {
  local code=$?
  if [ "$code" -ne 0 ] && [ "$API_ROLLBACK_ARMED" -eq 1 ]; then
    rollback_api
  fi
  exit "$code"
}
trap on_exit EXIT

# ── API ─────────────────────────────────────────────────────────────────────
echo "==> Recreating spacepoint-api (brief downtime; migrations run first)..."
API_ROLLBACK_ARMED=1
docker rm -f spacepoint-api 2>/dev/null || true
docker run -d --name spacepoint-api \
  --restart unless-stopped --network host \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file "$ENV_FILE" \
  -v "$STORAGE_MOUNT" \
  "$IMAGE"

# Poll rather than sleep a fixed interval: startup takes as long as the pending
# migrations do, and a fixed wait reports a false failure on any deploy
# carrying real schema changes. /health rather than /docs — it is the endpoint
# that exists to answer this question, and it survives docs_url being disabled.
echo "==> Waiting for API (up to ${HEALTH_TIMEOUT_SECONDS}s)..."
CODE="000"
for _ in $(seq 1 $((HEALTH_TIMEOUT_SECONDS / 2))); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$HEALTH_URL" || echo "000")
  [ "$CODE" = "200" ] && break
  # Bail immediately if the container actually exited — that is a failed
  # migration, and there is no point waiting out the remaining timeout.
  if ! docker ps --filter name=spacepoint-api --filter status=running | grep -q spacepoint-api; then
    echo "!! Container exited — migration likely failed:" >&2
    docker logs --tail 80 spacepoint-api >&2
    exit 1
  fi
  sleep 2
done

if [ "$CODE" != "200" ]; then
  echo "!! API not healthy after ${HEALTH_TIMEOUT_SECONDS}s (last HTTP $CODE):" >&2
  docker logs --tail 80 spacepoint-api >&2
  exit 1
fi
echo "==> API healthy."
API_ROLLBACK_ARMED=0   # new image confirmed good — nothing left to roll back

DB_REVISION_AFTER=$(sudo -u postgres psql -d spacepoint_unified -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || echo "unknown")
[ "$DB_REVISION_AFTER" = "$DB_REVISION_BEFORE" ] \
  && echo "==> Schema unchanged ($DB_REVISION_AFTER)." \
  || echo "==> Schema migrated: $DB_REVISION_BEFORE -> $DB_REVISION_AFTER"

# ── Worker ──────────────────────────────────────────────────────────────────
# Same image, no alembic — the API already migrated. Start the NEW worker
# before retiring the old one: two workers briefly consuming one arq queue is
# harmless (that is exactly how horizontal scaling works), which buys a genuine
# zero-downtime swap here, unlike the port-bound API above.
echo "==> Starting new worker..."
OLD_WORKER_EXISTS=0
docker inspect spacepoint-worker >/dev/null 2>&1 && OLD_WORKER_EXISTS=1

docker rm -f spacepoint-worker-new 2>/dev/null || true
docker run -d --name spacepoint-worker-new \
  --restart unless-stopped --network host \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file "$ENV_FILE" \
  -v "$STORAGE_MOUNT" \
  "$IMAGE" \
  arq app.workers.main.WorkerSettings

# `docker ps` only proves a process exists. /health/worker reads the heartbeat
# the worker itself writes to Redis, so it proves the thing we actually care
# about: that it is connected and consuming.
echo "==> Waiting for worker heartbeat..."
WORKER_OK=0
for _ in $(seq 1 20); do
  if [ "$(curl -s "$WORKER_HEALTH_URL" | grep -c '"status":"ok"' || true)" -ge 1 ]; then
    WORKER_OK=1; break
  fi
  if ! docker ps --filter name=spacepoint-worker-new --filter status=running | grep -q spacepoint-worker-new; then
    break
  fi
  sleep 2
done

if [ "$WORKER_OK" -ne 1 ]; then
  echo "!! New worker never reported a heartbeat:" >&2
  docker logs --tail 60 spacepoint-worker-new >&2
  docker rm -f spacepoint-worker-new 2>/dev/null || true
  [ "$OLD_WORKER_EXISTS" -eq 1 ] \
    && echo "!! Old worker was left untouched and is still running." >&2 \
    || echo "!! There was no old worker to fall back to — no worker is running." >&2
  # The API is already confirmed healthy on the new image, so a worker-only
  # failure deliberately does NOT take it back down.
  exit 1
fi

echo "==> New worker healthy — retiring the old one."
docker rm -f spacepoint-worker 2>/dev/null || true
docker rename spacepoint-worker-new spacepoint-worker

# ── Video worker ────────────────────────────────────────────────────────────
# Separate container, separate queue (arq:queue:video) — transcode_video jobs
# never reach the main worker above, so if this one isn't running nothing
# consumes them at all: uploads and re-encodes sit "pending" forever with no
# error anywhere. Health is arq's own built-in `--check` (not /health/worker,
# which only reflects the main worker's heartbeat key and says nothing about
# this queue).
#
# NOT the same start-new-before-stop-old pattern as the main worker above.
# That pattern is safe there because IO-bound jobs tolerate two workers
# briefly both dequeuing from the same queue. It is NOT safe here:
# VideoWorkerSettings.max_jobs=1 exists specifically so at most one ffmpeg
# encode ever runs at a time on this 4-vCPU box, and two containers each
# independently enforcing "1 at a time" against the same queue can still add
# up to 2 concurrent encodes for the brief window both are up — exactly the
# "melt the box" outcome that setting exists to prevent, and exactly the
# scenario a queued bulk re-encode (the 400-student competition's actual use
# case) would hit. So: stop (not remove) the old container first, accepting a
# brief gap where nothing drains arq:queue:video — queued jobs simply wait,
# nothing is lost — then start the new one. If the new one fails its health
# check, restart the old one rather than leaving video transcoding dark.
echo "==> Stopping old video worker (if any) before starting new — avoids two"
echo "    containers both enforcing max_jobs=1 against the same queue at once."
OLD_VIDEO_WORKER_EXISTS=0
if docker inspect spacepoint-worker-video >/dev/null 2>&1; then
  OLD_VIDEO_WORKER_EXISTS=1
  docker stop spacepoint-worker-video >/dev/null 2>&1 || true
fi

docker rm -f spacepoint-worker-video-new 2>/dev/null || true
docker run -d --name spacepoint-worker-video-new \
  --restart unless-stopped --network host \
  --log-opt max-size=10m --log-opt max-file=3 \
  --env-file "$ENV_FILE" \
  -v "$STORAGE_MOUNT" \
  "$IMAGE" \
  arq app.workers.main.VideoWorkerSettings

echo "==> Waiting for video worker health check..."
VIDEO_WORKER_OK=0
for _ in $(seq 1 20); do
  if docker exec spacepoint-worker-video-new arq app.workers.main.VideoWorkerSettings --check >/dev/null 2>&1; then
    VIDEO_WORKER_OK=1; break
  fi
  if ! docker ps --filter name=spacepoint-worker-video-new --filter status=running | grep -q spacepoint-worker-video-new; then
    break
  fi
  sleep 2
done

if [ "$VIDEO_WORKER_OK" -ne 1 ]; then
  echo "!! New video worker never passed its health check:" >&2
  docker logs --tail 60 spacepoint-worker-video-new >&2
  docker rm -f spacepoint-worker-video-new 2>/dev/null || true
  if [ "$OLD_VIDEO_WORKER_EXISTS" -eq 1 ]; then
    echo "!! Restarting the old video worker (it was only stopped, not removed)." >&2
    docker start spacepoint-worker-video >/dev/null 2>&1 \
      && echo "!! Old video worker is back up." >&2 \
      || echo "!! Old video worker failed to restart too — no video transcode jobs will run." >&2
  else
    echo "!! There was no old video worker to fall back to — no video transcode jobs will run." >&2
  fi
  # Same posture as the main worker above: API and main worker are already
  # confirmed healthy, so this failure alone does not take them back down.
  exit 1
fi

echo "==> New video worker healthy — retiring the old one."
docker rm -f spacepoint-worker-video 2>/dev/null || true
docker rename spacepoint-worker-video-new spacepoint-worker-video

echo "==> Done. API, worker, and video worker all healthy on $IMAGE."
