-- 0018 — application_reviews.submitted_at
--
-- When the applicant submitted their application for review (the
-- in_progress -> under_review transition). Never recorded before — the
-- old app's "Sub Date" was actually just the signup date. Going forward
-- submit_application sets this; below is a one-time best-effort backfill
-- for historical rows.

ALTER TABLE application_reviews ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

-- Backfill: an applicant can't submit until all videos + modules are
-- uploaded, and submission happens right after — so the latest of their
-- video/module upload timestamps is an accurate proxy (to within minutes)
-- for when they actually submitted. Only touches rows that are past
-- in_progress (i.e. actually submitted), not yet backfilled, and for which
-- some upload timestamp exists. Idempotent: the submitted_at IS NULL guard
-- means re-running skips already-populated rows.
UPDATE application_reviews ar
SET submitted_at = GREATEST(
        COALESCE((SELECT MAX(vs.submitted_at) FROM video_submissions vs WHERE vs.user_id = ar.user_id), 'epoch'::timestamptz),
        COALESCE((SELECT MAX(ms.submitted_at) FROM module_submissions ms WHERE ms.user_id = ar.user_id), 'epoch'::timestamptz)
    )
WHERE ar.status::text <> 'in_progress'
  AND ar.submitted_at IS NULL
  AND GREATEST(
        COALESCE((SELECT MAX(vs.submitted_at) FROM video_submissions vs WHERE vs.user_id = ar.user_id), 'epoch'::timestamptz),
        COALESCE((SELECT MAX(ms.submitted_at) FROM module_submissions ms WHERE ms.user_id = ar.user_id), 'epoch'::timestamptz)
      ) > 'epoch'::timestamptz;
