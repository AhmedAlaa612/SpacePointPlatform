# `ops/` — recurring backups

*(Relocated from `ops/README.md` — this repo's `.gitignore` excludes stray `README.md` files
except the root one and anything under `docs/`.)*

Built and tested locally 2026-08-10 — mechanism proven. **Whether it's actually been rehearsed
against production and the cron job installed (the two "operator still needs to do" items
below) is not verified as of 2026-08-15** — check `crontab -u postgres -l` on the VPS and
`ls /var/backups/spacepoint` before assuming either happened, rather than trusting this file's
last-known status.

## What's here

- **`backup_db.sh`** — `pg_dump -Fc`, timestamped, prunes anything older than
  `SPACEPOINT_BACKUP_RETENTION_DAYS` (default 14 days).
- **`restore_db.sh`** — restores a dump into a **new** database (never in place), for a DR
  drill or a pre-deploy migration rehearsal — restore into a scratch database, verify, then
  `dropdb` it, never restore in place.

## Verified locally (2026-08-10)

`backup_db.sh` → `restore_db.sh` → row counts (`users`, `courses`) and `alembic_version` compared
between the original and the restored database — identical. Proves the scripts work; does **not**
prove anything about production, which has its own schema drift and scale.

## What the operator still needs to do on the VPS

1. **Run the scripts once, by hand, against the real `spacepoint_unified` DB** — the actual
   rehearsal:
   ```bash
   sudo -u postgres SPACEPOINT_BACKUP_DIR=/var/backups/spacepoint ./backup_db.sh
   sudo -u postgres ./restore_db.sh /var/backups/spacepoint/spacepoint_unified_*.dump
   # then verify row counts / alembic_version the same way, and dropdb the scratch target
   ```
2. **Install the cron job** (`sudo crontab -u postgres -e`):
   ```
   0 3 * * * /path/to/ops/backup_db.sh >> /var/log/spacepoint-backup.log 2>&1
   ```
3. **Decide where backups go besides this box.** Local retention (14 days, pruned
   automatically) is not a real backup on its own — a backup that only exists on the box you're
   protecting against is not a backup. An `rclone`/`rsync` line added to the same cron job, once
   a destination exists, is the natural next step — not built here since it needs a decision
   (where) and credentials this session doesn't have.

**Why this matters more than a routine ops task:** once points/scores are stored (Live Quiz,
missions) they become disputable — a parent or student can ask "why did this change" — and once
any paid entitlement is tracked, this Postgres is the only record of who owns what. There is no
reconstructing either from an external system if this database is lost.
