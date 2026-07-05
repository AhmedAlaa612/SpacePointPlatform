-- Pivot Phase 4: ID cards get ONE number per PERSON (SP-XXXX-UAE), not one
-- number per role. Previously each role had its own Postgres sequence
-- (card_seq_instructor, card_seq_ambassador, ...), so a multi-role person saw
-- a different card_id on every role's card. Now the number lives on
-- users.card_number, allocated once on first-ever card generation and reused
-- by every role's id_cards row for that person. The `role` column on
-- id_cards is unchanged and still drives only the printed role label.
--
-- Safe to run more than once (every statement is idempotent).

CREATE SEQUENCE IF NOT EXISTS card_seq_person START 1 INCREMENT 1;

ALTER TABLE users ADD COLUMN IF NOT EXISTS card_number INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_card_number
    ON users(card_number) WHERE card_number IS NOT NULL;

-- Backfill: give any user with pre-existing per-role id_cards but no
-- card_number yet a fresh sequential number. Old per-role numbers came from 8
-- independent sequences, so e.g. "instructor #1" and "facilitator #1" are
-- different people — reusing those numbers as-is would collide. Order by
-- earliest card generation so longtime users keep lower numbers.
WITH distinct_users AS (
    SELECT user_id, MIN(generated_at) AS first_gen
    FROM id_cards
    WHERE card_id IS NOT NULL
    GROUP BY user_id
),
ranked AS (
    SELECT user_id, ROW_NUMBER() OVER (ORDER BY first_gen) AS rn
    FROM distinct_users
)
UPDATE users u
SET card_number = ranked.rn
FROM ranked
WHERE u.id = ranked.user_id AND u.card_number IS NULL;

-- Rewrite every existing id_cards row to the person's shared number/format.
UPDATE id_cards ic
SET card_id = 'SP-' || lpad(u.card_number::text, 4, '0') || '-UAE'
FROM users u
WHERE ic.user_id = u.id AND u.card_number IS NOT NULL
  AND ic.card_id IS DISTINCT FROM ('SP-' || lpad(u.card_number::text, 4, '0') || '-UAE');

-- Keep the sequence ahead of any backfilled number.
DO $$
DECLARE
    max_num INTEGER;
    cur_val BIGINT;
BEGIN
    SELECT COALESCE(MAX(card_number), 0) INTO max_num FROM users;
    SELECT last_value INTO cur_val FROM card_seq_person;
    IF max_num > cur_val THEN
        PERFORM setval('card_seq_person', max_num);
    END IF;
END $$;

-- Legacy per-role sequences (card_seq_admin, card_seq_intern, ...) are left in
-- place — harmless and unused now, not worth a destructive DROP.
