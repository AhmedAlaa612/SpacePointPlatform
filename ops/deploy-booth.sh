#!/usr/bin/env bash
# SpacePoint CubeSat Booth Kiosk Deployment Script
# Usage:
#   deploy-booth.sh
# Install with:
#   sudo install -m 755 ops/deploy-booth.sh /usr/local/bin/deploy-booth.sh

set -euo pipefail

REPO_DIR="/var/www/cubesat-photobooth"
GITHUB_REPO="https://github.com/AhmedAlaa612/spacepoint-booth.git"

echo "==> Deploying SpacePoint Booth Kiosk (selfie.spacepoint.ae)..."

if [ ! -d "$REPO_DIR" ]; then
  echo "Creating $REPO_DIR..."
  git clone "$GITHUB_REPO" "$REPO_DIR"
fi

cd "$REPO_DIR"

# Ensure origin points to AhmedAlaa612/spacepoint-booth.git
CURRENT_REMOTE=$(git remote get-url origin 2>/dev/null || true)
if [ "$CURRENT_REMOTE" != "$GITHUB_REPO" ]; then
  echo "==> Updating git remote to $GITHUB_REPO..."
  git remote set-url origin "$GITHUB_REPO" || git remote add origin "$GITHUB_REPO"
fi

echo "==> Pulling latest changes from main..."
git fetch origin main
git checkout main
git reset --hard origin/main

# Ensure .env exists with portal API URL
if [ ! -f "$REPO_DIR/.env" ]; then
  cat <<'EOF' > "$REPO_DIR/.env"
VITE_API_URL=https://selfie.spacepoint.ae
VITE_PORTAL_API_URL=https://portal.spacepoint.ae/api
VITE_DEFAULT_EVENT_SLUG=sef-2026
EOF
else
  # Ensure VITE_PORTAL_API_URL is set
  if ! grep -q "VITE_PORTAL_API_URL" "$REPO_DIR/.env"; then
    echo "VITE_PORTAL_API_URL=https://portal.spacepoint.ae/api" >> "$REPO_DIR/.env"
  fi
fi

echo "==> Building frontend bundle..."
npm install --no-audit --no-fund
npm run build

echo "==> Updating and restarting CubeSat backend (PM2)..."
if [ -d "$REPO_DIR/backend" ]; then
  (cd "$REPO_DIR/backend" && npm install --no-audit --no-fund)
  pm2 restart cubesat-backend || pm2 start "$REPO_DIR/backend/server.js" --name cubesat-backend
  pm2 save
fi

echo "==> Testing and reloading Nginx..."
nginx -t && systemctl reload nginx

echo "==> CubeSat Booth Kiosk is updated and live at https://selfie.spacepoint.ae!"
