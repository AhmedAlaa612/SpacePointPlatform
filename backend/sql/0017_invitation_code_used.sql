-- 0017 — users.invitation_code_used
--
-- The legacy instructors portal stores the exact code a user typed at
-- signup on their own row (users.invitation_code_used). The unified
-- schema's users.invite_code is a DIFFERENT concept (an ambassador's own
-- sharable referral code, only ever set for ambassadors) and was
-- incorrectly assumed to be the same thing, so this was dropped entirely
-- during the legacy ETL — a real, closable gap, not unrecoverable data.

ALTER TABLE users ADD COLUMN IF NOT EXISTS invitation_code_used VARCHAR(100);
