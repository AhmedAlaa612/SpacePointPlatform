-- 0014 — Path-based storage (Phase 7 / GO_LIVE §3.A2)
--
-- Every table that used to store a full Supabase signed URL gains a storage
-- path (and, where the bucket can vary per row, a bucket column). The path
-- columns become the source of truth; readers generate signed URLs at query
-- time via services/storage.resolve_url(). The legacy *_url columns are KEPT
-- as a non-destructive fallback — never dropped, never nulled.
--
-- NOTE (PIVOT_HANDOFF §1.5.9): the REAL migration mechanism is the idempotent
-- startup DDL in app/main.py::_run_startup_migrations — this file is the
-- historical snapshot. The startup hook additionally URL-decodes paths
-- (module-submission paths embed original filenames, which may be
-- percent-encoded in the signed URL); the SQL backfill below does not.
--
-- Fixed-bucket columns (no bucket column added — the bucket is implicit):
--   applications.cv_path                    → bucket "cvs"
--   users.photo_path                        → bucket "profile_pictures"
--   instructor_profiles.contract_path,
--   instructor_profiles.signed_contract_path→ bucket "contracts"
--   payment_letters.pdf_path,
--   payment_letters.signed_pdf_path         → bucket "payment-letters"
--   document_templates.template_file_path   → bucket "library-resources"

-- ── Columns ──────────────────────────────────────────────────────────────────
ALTER TABLE documents              ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE documents              ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE certificates           ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE certificates           ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE document_requests      ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE document_requests      ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE instructor_documents   ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE instructor_documents   ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE module_submissions     ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE module_submissions     ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE assessment_submissions ADD COLUMN IF NOT EXISTS bucket VARCHAR(100);
ALTER TABLE assessment_submissions ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE applications           ADD COLUMN IF NOT EXISTS cv_path TEXT;
ALTER TABLE users                  ADD COLUMN IF NOT EXISTS photo_path TEXT;
ALTER TABLE instructor_profiles    ADD COLUMN IF NOT EXISTS contract_path TEXT;
ALTER TABLE instructor_profiles    ADD COLUMN IF NOT EXISTS signed_contract_path TEXT;
ALTER TABLE payment_letters        ADD COLUMN IF NOT EXISTS pdf_path TEXT;
ALTER TABLE payment_letters        ADD COLUMN IF NOT EXISTS signed_pdf_path TEXT;
ALTER TABLE document_templates     ADD COLUMN IF NOT EXISTS template_file_path VARCHAR(512);

-- ── Backfill from stored Supabase URLs ───────────────────────────────────────
-- URL shape: https://<proj>.supabase.co/storage/v1/object/{sign|public}/{bucket}/{path}?token=…
-- Idempotent: only rows whose path column is still NULL are touched. This only
-- needs to cover the current dev DB — production is populated fresh by the
-- legacy ETL (GO_LIVE §3.A4), which writes bucket+path natively.

UPDATE documents SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE certificates SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE document_requests SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE instructor_documents SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE module_submissions SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE assessment_submissions SET
    bucket    = substring(file_url from '/storage/v1/object/(?:sign|public)/([^/]+)/'),
    file_path = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_path IS NULL AND file_url LIKE '%/storage/v1/object/%';

UPDATE applications SET
    cv_path = substring(cv_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE cv_path IS NULL AND cv_url LIKE '%/storage/v1/object/%';

-- Photos: the path is reused even when the stored URL references a renamed
-- legacy bucket (instructor-photos → profile_pictures kept the same paths).
UPDATE users SET
    photo_path = substring(photo_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE photo_path IS NULL AND photo_url LIKE '%/storage/v1/object/%';

UPDATE instructor_profiles SET
    contract_path = substring(contract_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE contract_path IS NULL AND contract_url LIKE '%/storage/v1/object/%';

UPDATE instructor_profiles SET
    signed_contract_path = substring(signed_contract_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE signed_contract_path IS NULL AND signed_contract_url LIKE '%/storage/v1/object/%';

UPDATE payment_letters SET
    pdf_path = substring(pdf_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE pdf_path IS NULL AND pdf_url LIKE '%/storage/v1/object/%';

UPDATE payment_letters SET
    signed_pdf_path = substring(signed_pdf_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE signed_pdf_path IS NULL AND signed_pdf_url LIKE '%/storage/v1/object/%';

UPDATE document_templates SET
    template_file_path = substring(template_file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE template_file_path IS NULL AND template_file_url LIKE '%/storage/v1/object/%';

-- library_resources.file_url already stores a bare path for uploaded files and
-- an external URL for links — normalize legacy rows still holding a full
-- Supabase storage URL down to the bare path (in place, same column).
UPDATE library_resources SET
    file_url = substring(file_url from '/storage/v1/object/(?:sign|public)/[^/]+/([^?]+)')
WHERE file_url LIKE '%/storage/v1/object/%';
