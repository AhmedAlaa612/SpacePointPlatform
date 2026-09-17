# `ops/` — recurring backups

*(Relocated from `ops/README.md` — this repo's `.gitignore` excludes stray `README.md` files
except the root one and anything under `docs/`.)*

Built and tested locally 2026-08-10 — mechanism proven. **Whether it's actually been rehearsed
against production and the cron job installed (the two "operator still needs to do" items
below) is not verified as of 2026-08-15** — check `crontab -u postgres -l` on the VPS and
`ls /var/backups/spacepoint` before assuming either happened, rather than trusting this file's
last-known status.

**Re-verified 2026-09-17** (routine doc-freshness pass): `ops/backup_db.sh` and `ops/restore_db.sh`
were re-read line-by-line against this file's description below — both still exist, unchanged in
shape from what this doc already said, and both still work exactly as described (custom-format
`pg_dump -Fc`, retention pruning, restore-into-a-new-database-only). **The cron-installed and
real-rehearsal-against-production questions remain exactly as unresolved as they were on
2026-08-15** — this pass had no VPS/SSH access, so there was no way to check
`crontab -u postgres -l` or `ls /var/backups/spacepoint` this time either. Deliberately **not**
resolving that uncertainty with a guess; see `HANDOFF_VPS_DEPLOYMENT.md` §0 for why nothing in
this repo can answer it (real infra state lives outside this repo, and this session had no way to
reach the actual VPS).

Also note: `docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md` (moved to `docs/archive/` on this same
pass — see that directory's `README.md`) records that its Phase B backup step
(`sudo -u postgres /path/to/ops/backup_db.sh`, then a restore rehearsal into a throwaway DB) was
checked off as done ahead of the 2026-09-05 R2/video deploy — so at least one real, on-VPS
run-and-rehearse of these exact scripts against `spacepoint_unified` has almost certainly
happened since 2026-08-15's "not verified" note. That is a one-off deploy-gated rehearsal though,
**not** the same thing as "the recurring cron job is installed" — the two "operator still needs to
do" items below are still tracked separately, and the cron item specifically is still unconfirmed.

## What's here

- **`backup_db.sh`** — `pg_dump -Fc`, timestamped, prunes anything older than
  `SPACEPOINT_BACKUP_RETENTION_DAYS` (default 14 days). Re-read 2026-09-17: matches this
  description exactly — `DB_NAME`/`DB_PORT`/`BACKUP_DIR`/`RETENTION_DAYS` are all env-var
  overridable with the same defaults (`spacepoint_unified`, `5432`, `/var/backups/spacepoint`,
  `14`), and pruning is a plain `find ... -mtime "+${RETENTION_DAYS}" -delete` over
  `${DB_NAME}_*.dump`.
- **`restore_db.sh`** — restores a dump into a **new** database (never in place), for a DR
  drill or a pre-deploy migration rehearsal — restore into a scratch database, verify, then
  `dropdb` it, never restore in place. Re-read 2026-09-17: matches — `createdb` a fresh target
  (defaults to `spacepoint_restore_test_<unix timestamp>` if no name is given, so repeated runs
  never collide) then `pg_restore`, tolerating (not failing on) the ownership/permission notices
  `pg_restore` prints for roles that don't exist on the restore target.

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
   **[2026-09-17] Likely done at least once since 2026-08-15**, but still not directly confirmed
   by this pass: the archived `docs/archive/HANDOFF_COMPETITION_DAY_DEPLOY.md` (Phase B) checks
   off taking exactly this backup, copying it off the VPS, and rehearsing the restore into a
   throwaway DB, ahead of the 2026-09-05 R2/video deploy. That's real evidence the mechanism has
   been exercised on production data at least once — but it's a one-off, deploy-gated run, not a
   standing guarantee, and this session had no VPS access to independently confirm it happened or
   check for a more recent one. Treat this item as "probably exercised once, not as an ongoing
   practice" rather than fully closed.
2. **Install the cron job** (`sudo crontab -u postgres -e`):
   ```
   0 3 * * * /path/to/ops/backup_db.sh >> /var/log/spacepoint-backup.log 2>&1
   ```
   **[2026-09-17] Still genuinely unverified** — nothing in this repo or in any archived doc
   confirms this cron line was ever actually installed on the VPS (the Phase B backup above was a
   manual pre-deploy run, not evidence of a standing cron job). Keep checking
   `crontab -u postgres -l` before assuming recurring backups are happening; do not treat the
   Phase B rehearsal above as covering this item too — they're different claims.
3. **Decide where backups go besides this box.** Local retention (14 days, pruned
   automatically) is not a real backup on its own — a backup that only exists on the box you're
   protecting against is not a backup. An `rclone`/`rsync` line added to the same cron job, once
   a destination exists, is the natural next step — not built here since it needs a decision
   (where) and credentials this session doesn't have. **[2026-09-17] Also still unverified** — no
   sign anywhere in this repo of an off-box copy destination having been decided or set up.

**Why this matters more than a routine ops task:** once points/scores are stored (Live Quiz,
missions) they become disputable — a parent or student can ask "why did this change" — and once
any paid entitlement is tracked, this Postgres is the only record of who owns what. There is no
reconstructing either from an external system if this database is lost.
