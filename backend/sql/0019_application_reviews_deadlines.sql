-- 0019 — application_reviews deadlines & extension tracking
--
-- Tracks per-phase deadlines, one-time extensions (+1 day), application start time (created_at),
-- and latest status transition timestamp (last_status_change_at).

ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS phase_deadline TIMESTAMPTZ;
ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS extension_used BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS last_status_change_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Best-effort backfill for created_at on existing rows from users.created_at
UPDATE application_reviews ar
SET created_at = u.created_at,
    last_status_change_at = COALESCE(ar.reviewed_at, ar.submitted_at, u.created_at)
FROM users u
WHERE ar.user_id = u.id;
