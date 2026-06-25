-- Phase 4 (remainder) - shared documents: recommendation letters + intern letters.
-- Safe to run on a fresh Supabase project after 0001-0004.
-- No new enum needed: certificate_type already has internship_completion /
-- instructor_completion (added in 0004) - the completion-cert auto-triggers
-- just insert into the existing `certificates` table.

CREATE TABLE IF NOT EXISTS recommendation_letters (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    generated_by    UUID NOT NULL REFERENCES users(id),
    signatory_name  VARCHAR(255) NOT NULL,
    signatory_title VARCHAR(255) NOT NULL,
    file_url        TEXT NOT NULL,
    generated_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_recommendation_letters_user_id ON recommendation_letters(user_id);

CREATE TABLE IF NOT EXISTS intern_letters (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type         VARCHAR(50) NOT NULL,  -- 'confirmation' | 'completion'
    file_url     TEXT NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_intern_letters_user_id ON intern_letters(user_id);
