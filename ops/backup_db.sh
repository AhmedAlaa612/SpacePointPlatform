#!/usr/bin/env bash
# Recurring database backup (P0-7, LMS Phase 2 Stage 0, 2026-08-10).
#
# Flagged and deferred three times before this (see PHASE2_EXECUTION_PLAN.md
# P0-7). Non-negotiable before Stage 2 — once the DB holds points it holds
# disputes — and absolutely before Stage S, because Stripe is the system of
# record for the *payment*, but the *entitlement* (who owns what) exists only
# in this Postgres. Lose it and there is no reconstructing it from Stripe.
#
# Custom-format dump (-Fc): compressed already, and restorable with
# pg_restore into a database of any name — see restore_db.sh, and the
# rehearsal precedent in V2_DEPLOY_RUNBOOK.md Phase 1, which this mirrors.
#
# Usage (on the VPS, where Postgres runs on the host and is reached via peer
# auth — matches V2_DEPLOY_RUNBOOK.md's existing pg_dump commands exactly):
#   sudo -u postgres ./backup_db.sh
#
# Cron (add via `sudo crontab -u postgres -e` — this script never ran there
# yet, since there is no SSH access from the session that wrote it):
#   0 3 * * * /path/to/ops/backup_db.sh >> /var/log/spacepoint-backup.log 2>&1
#
# NOT done by this script, and still the operator's call: copying backups
# off this box. A backup that only exists on the server you're protecting
# against is not a backup (V2_DEPLOY_RUNBOOK.md says this explicitly about
# the one-off pre-deploy dump; it's exactly as true for a recurring one).
# rsync/rclone to off-box storage on the same cron cadence is the natural
# next step once a destination exists.

set -euo pipefail

DB_NAME="${SPACEPOINT_DB_NAME:-spacepoint_unified}"
DB_PORT="${SPACEPOINT_DB_PORT:-5432}"
BACKUP_DIR="${SPACEPOINT_BACKUP_DIR:-/var/backups/spacepoint}"
RETENTION_DAYS="${SPACEPOINT_BACKUP_RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%F_%H%M%S)"
DEST="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"

pg_dump -p "$DB_PORT" -Fc "$DB_NAME" > "$DEST"

SIZE="$(du -h "$DEST" | cut -f1)"
echo "$(date -Is)  backed up $DB_NAME -> $DEST ($SIZE)"

# Prune anything older than RETENTION_DAYS. Local retention only — see the
# off-box-copy note above; this is not a substitute for it.
find "$BACKUP_DIR" -name "${DB_NAME}_*.dump" -mtime "+${RETENTION_DAYS}" -print -delete
