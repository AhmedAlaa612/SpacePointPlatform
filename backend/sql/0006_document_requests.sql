-- Phase 5 Add-on - Document requests system where users request certificates and letters.
-- Safe to run on a fresh Supabase project after 0001-0005.

CREATE TABLE IF NOT EXISTS document_requests (
    id              UUID PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            VARCHAR(50) NOT NULL, -- 'recommendation_letter' | 'confirmation_letter' | 'completion_letter' | 'certificate'
    status          VARCHAR(50) NOT NULL DEFAULT 'pending', -- 'pending' | 'approved' | 'rejected'
    notes           TEXT,
    admin_notes     TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_document_requests_user_id ON document_requests(user_id);
