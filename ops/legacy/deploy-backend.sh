#!/usr/bin/env bash
set -euo pipefail

IMAGE="ghcr.io/ahmedalaa612/spacepoint-api:latest"

echo "==> Pulling latest backend image..."
docker pull "$IMAGE"

echo "==> Recreating API container (brief API downtime)..."
docker rm -f spacepoint-api 2>/dev/null || true
docker run -d --name spacepoint-api \
  --restart unless-stopped --network host \
  --env-file /etc/spacepoint/env \
  -v /var/lib/spacepoint/storage:/data/storage \
  "$IMAGE"

# The container runs `alembic upgrade head` before uvicorn binds a port, so
# startup takes as long as the pending migrations do. Poll rather than sleep a
# fixed 4s, which reports a false failure on any deploy carrying real schema
# changes. Bail early if the container actually exited (failed migration).
echo "==> Waiting for API (migrations run first)..."
CODE="000"
for _ in $(seq 1 60); do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/docs || echo "000")
  [ "$CODE" = "200" ] && break
  if ! docker ps --filter name=spacepoint-api --filter status=running | grep -q spacepoint-api; then
    echo "!! Container exited - migration likely failed:" >&2
    docker logs --tail 60 spacepoint-api >&2
    exit 1
  fi
  sleep 2
done

if [ "$CODE" != "200" ]; then
  echo "!! API not healthy after 120s (last HTTP $CODE):" >&2
  docker logs --tail 60 spacepoint-api >&2
  exit 1
fi
echo "==> Backend healthy (HTTP 200)."

# Same image, no alembic - the API already migrated. Recreated here so a
# deploy can never leave a stale worker running old job code.
echo "==> Recreating worker container..."
docker rm -f spacepoint-worker 2>/dev/null || true
docker run -d --name spacepoint-worker \
  --restart unless-stopped --network host \
  --env-file /etc/spacepoint/env \
  -v /var/lib/spacepoint/storage:/data/storage \
  "$IMAGE" \
  arq app.workers.main.WorkerSettings

sleep 3
if docker ps --filter name=spacepoint-worker --filter status=running | grep -q spacepoint-worker; then
  echo "==> Worker running."
else
  echo "!! Worker failed to start:" >&2
  docker logs --tail 40 spacepoint-worker >&2
  exit 1
fi
