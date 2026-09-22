#!/usr/bin/env bash
# ==============================================================================
# Deploy/Update Vector Log Shipper for Axiom
# ==============================================================================
# Ships logs from spacepoint-api, spacepoint-worker, and spacepoint-worker-video
# directly to Axiom over HTTPS with negligible memory footprint (~15-20MB).
#
# Install / Run on VPS:
#   sudo bash ops/deploy-vector.sh
# ==============================================================================

set -euo pipefail

IMAGE="timberio/vector:0.43.0-alpine"
ENV_FILE="/etc/spacepoint/env"
CONFIG_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/vector/vector.toml"
CONFIG_DEST="/etc/spacepoint/vector.toml"

echo "==> Verifying environment and config..."

if [ ! -f "$ENV_FILE" ]; then
  echo "Error: $ENV_FILE does not exist. Please create it first." >&2
  exit 1
fi

if ! grep -q "^AXIOM_TOKEN=" "$ENV_FILE" || ! grep -q "^AXIOM_DATASET=" "$ENV_FILE"; then
  echo "Error: AXIOM_TOKEN or AXIOM_DATASET is missing in $ENV_FILE." >&2
  echo "Add them like:" >&2
  echo "  AXIOM_TOKEN=xaat-..." >&2
  echo "  AXIOM_DATASET=your-dataset-name" >&2
  exit 1
fi

echo "==> Syncing vector.toml to $CONFIG_DEST..."
sudo mkdir -p /etc/spacepoint
sudo cp "$CONFIG_SRC" "$CONFIG_DEST"
sudo chmod 644 "$CONFIG_DEST"

echo "==> Pulling Vector image ($IMAGE)..."
docker pull "$IMAGE"

echo "==> Recreating spacepoint-vector container..."
docker rm -f spacepoint-vector 2>/dev/null || true

docker run -d \
  --name spacepoint-vector \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock:ro \
  -v "$CONFIG_DEST":/etc/vector/vector.toml:ro \
  --env-file "$ENV_FILE" \
  "$IMAGE" \
  --config /etc/vector/vector.toml

echo "==> Waiting 3s for Vector startup..."
sleep 3

if docker ps --filter name=spacepoint-vector --filter status=running | grep -q spacepoint-vector; then
  echo "==> spacepoint-vector is RUNNING."
  echo "==> Tail logs with: docker logs -f spacepoint-vector"
else
  echo "Error: spacepoint-vector failed to start. Container logs:" >&2
  docker logs spacepoint-vector
  exit 1
fi
