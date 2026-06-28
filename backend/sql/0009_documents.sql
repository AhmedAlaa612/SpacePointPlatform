-- 0009 — unified `documents` table (generated letters). Replaces recommendation_letters
-- + intern_letters; certificates keep their own first-class table. Run once on live Supabase.

CREATE TABLE IF NOT EXISTS documents (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_id   UUID REFERENCES document_templates(id) ON DELETE SET NULL,
    label         VARCHAR(255) NOT NULL,
    file_url      TEXT NOT NULL,
    generated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    data          JSONB NOT NULL DEFAULT '{}',
    generated_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);

-- Backfill existing recommendation letters → documents (keeps their old file URLs).
INSERT INTO documents (id, user_id, label, file_url, generated_by, data, generated_at)
SELECT id, user_id, 'Letter of Recommendation', file_url, generated_by,
       jsonb_build_object('signatory_name', signatory_name, 'signatory_title', signatory_title,
                          'recommendation_text', recommendation_text),
       generated_at
FROM recommendation_letters
ON CONFLICT (id) DO NOTHING;

-- Backfill existing intern letters (confirmation / completion) → documents.
INSERT INTO documents (id, user_id, label, file_url, generated_by, data, generated_at)
SELECT id, user_id,
       CASE WHEN type = 'confirmation' THEN 'Program Confirmation Letter' ELSE 'Program Completion Letter' END,
       file_url, NULL, '{}'::jsonb, generated_at
FROM intern_letters
ON CONFLICT (id) DO NOTHING;

-- After confirming the rows migrated, drop the legacy tables:
-- DROP TABLE IF EXISTS recommendation_letters;
-- DROP TABLE IF EXISTS intern_letters;

-- Duplicated foreign key removed: the referring ambassador is now tracked solely on
-- users.invited_by_id (applicant_profiles.referred_by_ambassador_id was a copy that drifted).
ALTER TABLE applicant_profiles DROP COLUMN IF EXISTS referred_by_ambassador_id;
