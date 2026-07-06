-- Phase 3 (instructors parity): Phase-2 "10 Questions Assessment" submission,
-- unlocked when application_reviews.status = 'research_approved'. Mirrors
-- presentation_submissions (0004_instructors.sql) but supports either a PDF
-- upload or a Google Drive link, plus optional comments.
CREATE TABLE IF NOT EXISTS assessment_submissions (
    id                 UUID PRIMARY KEY,
    user_id            UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    file_url           TEXT,
    google_drive_link  TEXT,
    comments           TEXT,
    submitted_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_assessment_submissions_user ON assessment_submissions(user_id);
