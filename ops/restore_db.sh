#!/usr/bin/env bash
# Restore a backup_db.sh dump into a NEW database, for a DR drill or the
# migration-rehearsal pattern V2_DEPLOY_RUNBOOK.md Phase 1 already uses.
# Never restores over an existing database in place — always a fresh
# `createdb` target, so a bad rehearsal can't touch anything real.
#
# Usage:
#   ./restore_db.sh /var/backups/spacepoint/spacepoint_unified_2026-08-10_030000.dump [target_db_name]
#
# target_db_name defaults to spacepoint_restore_test_<timestamp> so repeated
# runs never collide. Drop it yourself when done verifying:
#   dropdb -p 5432 <target_db_name>

set -euo pipefail

DUMP_FILE="${1:?usage: restore_db.sh <dump_file> [target_db_name]}"
DB_PORT="${SPACEPOINT_DB_PORT:-5432}"
TARGET_DB="${2:-spacepoint_restore_test_$(date +%s)}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "error: $DUMP_FILE does not exist" >&2
  exit 1
fi

createdb -p "$DB_PORT" "$TARGET_DB"
# pg_restore may print ownership/permission notices for roles that don't
# exist on the restore target — expected and harmless, same as
# V2_DEPLOY_RUNBOOK.md Phase 1 notes for the identical situation.
pg_restore -p "$DB_PORT" -d "$TARGET_DB" "$DUMP_FILE" || true

echo "$(date -Is)  restored $DUMP_FILE -> $TARGET_DB"
echo "verify, then: dropdb -p $DB_PORT $TARGET_DB"
