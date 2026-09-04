#!/usr/bin/env bash
set -euo pipefail

REPO="AhmedAlaa612/SpacePointPlatform"
DIST="/var/www/spacepoint-unified/dist"
STAGING="/tmp/frontend-staging"

echo "==> Downloading latest frontend build from GitHub..."
rm -f /tmp/frontend-dist.tar.gz
gh release download frontend-latest --repo "$REPO" --pattern "*.tar.gz" --dir /tmp --clobber

echo "==> Extracting to staging..."
rm -rf "$STAGING" && mkdir -p "$STAGING"
tar xzf /tmp/frontend-dist.tar.gz -C "$STAGING"

# Safety check: refuse to deploy an empty/broken build.
if [ ! -f "$STAGING/index.html" ]; then
  echo "!! ERROR: no index.html in the downloaded build — aborting, live site untouched." >&2
  exit 1
fi

echo "==> Swapping into place..."
rm -rf "$DIST"/*
cp -r "$STAGING"/* "$DIST"/
rm -rf "$STAGING" /tmp/frontend-dist.tar.gz

echo "==> Frontend deployed. Files:"
ls "$DIST"
