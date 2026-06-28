-- 0007 — one-shot cleanup of legacy tables/columns superseded by the unified
-- apply pipeline + on-the-fly ID cards. Safe to run once on the live Supabase
-- project. NOT run automatically (startup migrations are non-destructive).

-- Old teacher-specific application form (replaced by admin-managed apply_questions).
DROP TABLE IF EXISTS application_questions CASCADE;

-- Old ambassador-approved teacher pipeline (replaced by unified `applications`
-- + admin approval; ambassador referral points now awarded on admin approval).
DROP TABLE IF EXISTS teacher_applications CASCADE;

-- ID card images are rendered on-the-fly and never stored; these were always NULL.
ALTER TABLE id_cards DROP COLUMN IF EXISTS front_url;
ALTER TABLE id_cards DROP COLUMN IF EXISTS back_url;
ALTER TABLE id_cards DROP COLUMN IF EXISTS pdf_url;
