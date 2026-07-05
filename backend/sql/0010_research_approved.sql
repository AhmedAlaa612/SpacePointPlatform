-- Phase 3 (instructors parity): add the Phase-2 "research approved" stage to the
-- applicant pipeline, matching the live VPS pipeline (portal.spacepoint.ae) whose
-- application_reviews already carries RESEARCH_APPROVED. The unified enum omitted it.
--
-- Safe to run once. ALTER TYPE ... ADD VALUE IF NOT EXISTS is PG12+ and may not be
-- used in the SAME transaction that adds it — this file only adds it.
ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'research_approved' AFTER 'phase_1_approved';
