#!/usr/bin/env bash
# Frontend deploy for the VPS. Lives in the repo so it is reviewable and
# versioned; install with:
#   sudo install -m 755 ops/deploy-frontend.sh /usr/local/bin/deploy-frontend.sh
#
#   deploy-frontend.sh            # download the latest build and swap it in
#   deploy-frontend.sh --rollback # restore the most recent backup
#   deploy-frontend.sh --list     # show available backups
#
# One directory serves every domain (portal, lms, any future vanity domain) —
# they all point their nginx `root` at $DIST — so one run updates all of them.

set -euo pipefail

REPO="AhmedAlaa612/SpacePointPlatform"
ROOT="/var/www/spacepoint-unified"
DIST="$ROOT/dist"
BACKUP_ROOT="$ROOT/backups"
KEEP_BACKUPS=5
TARBALL="/tmp/frontend-dist.tar.gz"
STAGING="$ROOT/.dist-staging"     # sibling of $DIST, NOT /tmp — see the swap below

list_backups() {
  if [ -d "$BACKUP_ROOT" ] && [ -n "$(ls -A "$BACKUP_ROOT" 2>/dev/null)" ]; then
    ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null
  else
    echo "(no backups)"
  fi
}

case "${1:-}" in
  --list)
    list_backups; exit 0 ;;
  --rollback)
    LATEST=$(ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | head -1 || true)
    [ -n "$LATEST" ] || { echo "!! No backup to roll back to." >&2; exit 1; }
    echo "==> Rolling back to $LATEST"
    rm -rf "$STAGING" && cp -r "$LATEST" "$STAGING"
    rm -rf "$DIST.old" && mv "$DIST" "$DIST.old" && mv "$STAGING" "$DIST"
    rm -rf "$DIST.old"
    echo "==> Rolled back."; exit 0 ;;
  -h|--help)
    sed -n '2,12p' "$0"; exit 0 ;;
  "") ;;
  *) echo "Unknown argument: $1" >&2; exit 2 ;;
esac

echo "==> Downloading latest frontend build..."
rm -f "$TARBALL"
gh release download frontend-latest --repo "$REPO" --pattern "*.tar.gz" --dir /tmp --clobber

echo "==> Extracting to staging..."
rm -rf "$STAGING" && mkdir -p "$STAGING"
tar xzf "$TARBALL" -C "$STAGING"

# Some builds tar up a `dist/` wrapper directory, some tar its contents.
# Normalise so the swap below always moves the directory that holds index.html.
if [ ! -f "$STAGING/index.html" ] && [ -f "$STAGING/dist/index.html" ]; then
  mv "$STAGING/dist" "$STAGING.inner" && rm -rf "$STAGING" && mv "$STAGING.inner" "$STAGING"
fi

# Refuse to deploy an empty or truncated build. index.html alone is not enough
# — a Vite build with no assets/ directory produces a blank white page that
# looks "deployed" and passes any check that only looks for index.html.
[ -f "$STAGING/index.html" ] || {
  echo "!! No index.html in the downloaded build — aborting, live site untouched." >&2
  rm -rf "$STAGING"; exit 1; }
[ -d "$STAGING/assets" ] && [ -n "$(ls -A "$STAGING/assets" 2>/dev/null)" ] || {
  echo "!! No assets/ in the downloaded build — aborting, live site untouched." >&2
  rm -rf "$STAGING"; exit 1; }
echo "==> Build looks sane ($(find "$STAGING" -type f | wc -l) files)."

# `frontend-latest` is a MUTABLE release tag that CI republishes to every time,
# so once this deploy runs the build we are about to replace may not be
# re-downloadable from GitHub at all. A local copy taken right before the swap
# is the only fast way back from a build that is broken in a way no automated
# check can see (index.html and assets both present, app still white-screens).
BACKUP_DIR=""
if [ -d "$DIST" ] && [ -n "$(ls -A "$DIST" 2>/dev/null)" ]; then
  mkdir -p "$BACKUP_ROOT"
  BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"
  echo "==> Backing up current build to $BACKUP_DIR ..."
  cp -r "$DIST" "$BACKUP_DIR"
  ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -rf
fi

# Two renames, not `rm -rf dist/* && cp`. A copy leaves a window — seconds, on a
# build this size — where nginx is serving a half-populated directory: index.html
# present, assets missing, every visitor in that window gets a broken page.
# `mv` within one filesystem is an atomic rename, so the switch is instant and
# no request ever observes a partial directory. ($STAGING is a sibling of $DIST
# rather than under /tmp precisely so that both renames stay on one filesystem —
# across filesystems `mv` degrades to copy-then-delete and the atomicity is lost.)
echo "==> Swapping into place (atomic)..."
rm -rf "$DIST.old"
if [ -d "$DIST" ]; then mv "$DIST" "$DIST.old"; fi
mv "$STAGING" "$DIST"
rm -rf "$DIST.old" "$TARBALL"

echo "==> Frontend deployed:"
ls "$DIST"
[ -n "$BACKUP_DIR" ] && echo "==> Roll back with: deploy-frontend.sh --rollback   (restores $BACKUP_DIR)"
