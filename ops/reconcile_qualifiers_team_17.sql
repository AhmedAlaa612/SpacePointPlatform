-- ==============================================================================
-- Migration / Reconciliation Script for Ru'ya Qualifiers Cohort:
-- Cohort ID: d651bca0-394f-4b47-9fa9-ddea274a430f
--
-- Problem:
-- Team 17 and Team MIRAGE-X were duplicated. Judging scores were assigned to
-- Team 17, while student submissions and members are under Team MIRAGE-X.
--
-- Solution:
-- 1. Identify UUIDs of Team 17 (Source) and Team MIRAGE-X (Target).
-- 2. Move competition_scores from Team 17 to Team MIRAGE-X.
-- 3. Move missing learner_team_members from Team 17 to Team MIRAGE-X.
-- 4. Move missing lms_program_team_item_progress from Team 17 to Team MIRAGE-X.
-- 5. Move any mission_attempts from Team 17 to Team MIRAGE-X.
-- 6. Set roster_team_id = '17' on Team MIRAGE-X.
-- 7. Copy qualification, timing adjustments, ops criteria from Team 17 to MIRAGE-X.
-- 8. Delete redundant Team 17.
--
-- To run on the VPS:
-- psql -U spacepoint -d spacepoint_unified -p 5432 -f ops/reconcile_qualifiers_team_17.sql
-- ==============================================================================

BEGIN;

DO $$
DECLARE
    v_cohort_id UUID := 'd651bca0-394f-4b47-9fa9-ddea274a430f';
    v_src_team_id UUID;
    v_src_name TEXT;
    v_tgt_team_id UUID;
    v_tgt_name TEXT;
    v_scores_moved INT := 0;
    v_members_moved INT := 0;
BEGIN
    -- 1. Find Source Team ('17')
    SELECT id, name INTO v_src_team_id, v_src_name
    FROM learner_teams
    WHERE cohort_id = v_cohort_id
      AND (trim(lower(name)) IN ('17', 'team 17') OR (roster_team_id = '17' AND lower(name) NOT LIKE '%mirage%'))
    ORDER BY created_at ASC
    LIMIT 1;

    -- 2. Find Target Team ('MIRAGE-X')
    SELECT id, name INTO v_tgt_team_id, v_tgt_name
    FROM learner_teams
    WHERE cohort_id = v_cohort_id
      AND lower(name) LIKE '%mirage%'
    ORDER BY created_at ASC
    LIMIT 1;

    IF v_src_team_id IS NULL THEN
        RAISE EXCEPTION 'Source Team (17) not found in cohort %', v_cohort_id;
    END IF;

    IF v_tgt_team_id IS NULL THEN
        RAISE EXCEPTION 'Target Team (MIRAGE-X) not found in cohort %', v_cohort_id;
    END IF;

    IF v_src_team_id = v_tgt_team_id THEN
        RAISE EXCEPTION 'Source and Target teams are the same UUID: %', v_src_team_id;
    END IF;

    RAISE NOTICE 'Found Source Team: "%" (ID: %)', v_src_name, v_src_team_id;
    RAISE NOTICE 'Found Target Team: "%" (ID: %)', v_tgt_name, v_tgt_team_id;

    -- 3. Move competition_scores
    -- First, update scores where target does not have a score from that judge/rubric
    UPDATE competition_scores
    SET team_id = v_tgt_team_id
    WHERE team_id = v_src_team_id
      AND (rubric_id, judge_user_id, cohort_id) NOT IN (
          SELECT rubric_id, judge_user_id, cohort_id
          FROM competition_scores
          WHERE team_id = v_tgt_team_id
      );
    GET DIAGNOSTICS v_scores_moved = ROW_COUNT;
    RAISE NOTICE 'Moved % competition score(s) to target team.', v_scores_moved;

    -- Delete any remaining duplicate scores on source
    DELETE FROM competition_scores WHERE team_id = v_src_team_id;

    -- 4. Move team members
    UPDATE learner_team_members
    SET team_id = v_tgt_team_id
    WHERE team_id = v_src_team_id
      AND user_id NOT IN (
          SELECT user_id FROM learner_team_members WHERE team_id = v_tgt_team_id
      );
    GET DIAGNOSTICS v_members_moved = ROW_COUNT;
    RAISE NOTICE 'Moved % team member(s) to target team.', v_members_moved;

    -- Delete any remaining duplicate membership rows on source
    DELETE FROM learner_team_members WHERE team_id = v_src_team_id;

    -- 5. Move deliverables/progress (keeping target submissions intact)
    UPDATE lms_program_team_item_progress
    SET team_id = v_tgt_team_id
    WHERE team_id = v_src_team_id
      AND item_id NOT IN (
          SELECT item_id FROM lms_program_team_item_progress WHERE team_id = v_tgt_team_id
      );

    DELETE FROM lms_program_team_item_progress WHERE team_id = v_src_team_id;

    -- 6. Move mission attempts
    UPDATE mission_attempts
    SET team_id = v_tgt_team_id
    WHERE team_id = v_src_team_id;

    -- 7. Copy metadata from source to target
    UPDATE learner_teams tgt
    SET 
        qualification = COALESCE(tgt.qualification, src.qualification),
        timing_adjustment_override = COALESCE(tgt.timing_adjustment_override, src.timing_adjustment_override),
        timing_adjustment_notes = COALESCE(tgt.timing_adjustment_notes, src.timing_adjustment_notes),
        ops_criterion_scores = CASE 
            WHEN tgt.ops_criterion_scores = '{}'::jsonb AND src.ops_criterion_scores != '{}'::jsonb 
            THEN src.ops_criterion_scores 
            ELSE tgt.ops_criterion_scores 
        END,
        ops_criterion_notes = COALESCE(tgt.ops_criterion_notes, src.ops_criterion_notes),
        ops_scored_by = COALESCE(tgt.ops_scored_by, src.ops_scored_by),
        ops_scored_at = COALESCE(tgt.ops_scored_at, src.ops_scored_at),
        final_locked_at = COALESCE(tgt.final_locked_at, src.final_locked_at),
        final_locked_by = COALESCE(tgt.final_locked_by, src.final_locked_by),
        first_locked_at = LEAST(tgt.first_locked_at, src.first_locked_at)
    FROM learner_teams src
    WHERE tgt.id = v_tgt_team_id AND src.id = v_src_team_id;

    -- 8. Clear roster_team_id on source, then set it to '17' on target
    UPDATE learner_teams SET roster_team_id = NULL WHERE id = v_src_team_id;
    UPDATE learner_teams SET roster_team_id = '17' WHERE id = v_tgt_team_id;

    -- 9. Delete Source Team
    DELETE FROM learner_teams WHERE id = v_src_team_id;
    RAISE NOTICE 'Deleted duplicate source team (ID: %).', v_src_team_id;
    RAISE NOTICE 'Reconciliation complete! MIRAGE-X now has roster_team_id "17" and all scores/submissions.';
END $$;

COMMIT;
