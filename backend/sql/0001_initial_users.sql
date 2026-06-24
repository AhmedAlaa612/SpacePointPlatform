-- ============================================================================
-- SpacePoint Unified — Phase 0 schema
-- Run this in the Supabase SQL editor on a FRESH project.
-- This mirrors Alembic migration 0001_initial_users.py exactly.
--
-- IMPORTANT (so Alembic still works later): after running this, when you wire
-- up the backend, tell Alembic these tables already exist by running ONCE:
--     alembic stamp 0001
-- Then future `alembic upgrade head` runs apply only the NEW migrations.
--
-- Supabase has pgcrypto enabled, so gen_random_uuid() is available out of the box.
-- ============================================================================

-- 1) The eight platform roles (PLAN §1)
DO $$
BEGIN
  CREATE TYPE user_role AS ENUM (
    'admin', 'intern', 'leader',
    'applicant', 'instructor', 'facilitator',
    'ambassador', 'teacher'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

-- 2) Unified users table — one account, many roles
CREATE TABLE IF NOT EXISTS users (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name             VARCHAR(255) NOT NULL,
  email                 VARCHAR(255) NOT NULL,
  password_hash         VARCHAR(255) NOT NULL,
  roles                 user_role[]  NOT NULL DEFAULT '{}',
  status                VARCHAR(50)  NOT NULL DEFAULT 'active',  -- 'active' | 'pending' | 'inactive'
  invite_code           VARCHAR(100),                            -- ambassador's sharable code
  invited_by_id         UUID REFERENCES users(id) ON DELETE SET NULL,
  must_change_password  BOOLEAN NOT NULL DEFAULT FALSE,          -- set TRUE for admin-created accounts
  phone                 VARCHAR(50),
  country               VARCHAR(100),
  created_at            TIMESTAMPTZ DEFAULT now(),
  last_login_at         TIMESTAMPTZ
);

CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email        ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_invite_code  ON users (invite_code);

-- ----------------------------------------------------------------------------
-- 3) Admin account
-- The password must be a bcrypt hash (the API hashes with passlib[bcrypt]).
-- You CANNOT type a plain password here. Two options:
--   (a) Skip this block, and later run `python seed.py` (reads ADMIN_EMAIL /
--       ADMIN_PASSWORD from .env and inserts a correctly-hashed admin), or
--   (b) Ask me to generate a ready-to-paste INSERT with a real bcrypt hash for
--       your chosen email + password.
--
-- Example shape (DO NOT use this fake hash — it will not log in):
-- INSERT INTO users (full_name, email, password_hash, roles, status)
-- VALUES ('SpacePoint Admin', 'admin@spacepoint.local',
--         '$2b$12$REPLACE_WITH_REAL_BCRYPT_HASH', ARRAY['admin']::user_role[], 'active');
-- ----------------------------------------------------------------------------
