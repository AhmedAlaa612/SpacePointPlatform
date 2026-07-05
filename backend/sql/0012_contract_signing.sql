-- Pivot Phase 6: in-app contract signing (mirrors payment-letter signing).
-- Adds the instructor's captured signature + signed timestamp onto
-- instructor_profiles. Signed state is derived from signed_contract_url /
-- contract_signed_at — no separate status enum (unlike payment letters,
-- contracts have no admin "draft"/"publish" step: they auto-generate and are
-- emailed the moment an applicant is approved, so there are only two real
-- states, unsigned and signed).
--
-- Safe to run more than once (every statement is idempotent).

ALTER TABLE instructor_profiles ADD COLUMN IF NOT EXISTS contract_signature_data TEXT;
ALTER TABLE instructor_profiles ADD COLUMN IF NOT EXISTS contract_signed_at TIMESTAMPTZ;
