/** Instructor assessment & performance ranking domain (2026-09). Mirrors
 *  backend/app/schemas/instructor_assessment.py field-for-field. */

// ── question bank ────────────────────────────────────────────────────────

export interface AssessmentQuestionOption {
  text: string;
  is_correct: boolean;
}

export interface AssessmentQuestion {
  id: string;
  category: string;
  prompt: string;
  options: AssessmentQuestionOption[];
  critical: boolean;
  rationale?: string | null;
  is_active: boolean;
}

export interface AssessmentQuestionImportResult {
  created: number;
  errors: string[];
  questions: AssessmentQuestion[];
}

export interface AssessmentConfig {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at?: string | null;
  draw_size: number;
  critical_floor: number;
  question_count: number;
  category_counts: Record<string, number>;
  critical_count: number;
}

export interface AssessmentConfigDetail extends AssessmentConfig {
  questions: AssessmentQuestion[];
}

// ── cohort assignment (the on/off switch) ───────────────────────────────

export interface AssessmentCohortAssignment {
  cohort_id: string;
  config_id: string;
  config_name: string;
  assigned_by?: string | null;
  created_at?: string | null;
}

// ── attempts (instructor-facing) ────────────────────────────────────────

export interface AttemptQuestion {
  question_id: string;
  category: string;
  prompt: string;
  options: string[];
  critical: boolean;
}

export interface Attempt {
  id: string;
  cohort_call_id: string;
  status: "in_progress" | "submitted";
  total: number;
  questions: AttemptQuestion[];
}

// Revealed only after the whole attempt is submitted — see the backend's
// get_attempt_review docstring for why this never shows up mid-quiz.
export interface AttemptQuestionReview {
  question_id: string;
  category: string;
  prompt: string;
  options: string[];
  selected_index: number | null;
  correct_index: number;
  is_correct: boolean;
  critical: boolean;
  rationale?: string | null;
}

export interface AttemptResult {
  id: string;
  status: "in_progress" | "submitted";
  score: number | null;
  total: number;
  critical_correct: number | null;
  critical_total: number | null;
  category_breakdown: Record<string, { correct: number; total: number }> | null;
  submitted_at?: string | null;
  questions: AttemptQuestionReview[];
}

// ── post-program rating ─────────────────────────────────────────────────

export const RATING_DIMENSIONS = [
  { key: "punctuality", label: "Punctuality" },
  { key: "technical_knowledge", label: "Technical Knowledge" },
  { key: "teaching_facilitation", label: "Teaching / Facilitation Skills" },
  { key: "student_engagement", label: "Student Engagement" },
  { key: "communication", label: "Communication" },
  { key: "commitment_reliability", label: "Commitment & Reliability" },
  { key: "teamwork_collaboration", label: "Teamwork & Collaboration" },
  { key: "safety_procedure_compliance", label: "Safety & Procedure Compliance" },
  { key: "problem_solving_adaptability", label: "Problem Solving & Adaptability" },
  { key: "documentation_operational_discipline", label: "Documentation & Operational Discipline" },
] as const;

export type RatingDimensionKey = (typeof RATING_DIMENSIONS)[number]["key"];

export type RatingFlag = "none" | "exceptional" | "concern";

export interface InstructorProgramRating {
  id: string;
  cohort_id: string;
  instructor_user_id: string;
  rater_user_id?: string | null;
  dimension_scores: Partial<Record<RatingDimensionKey, number>>;
  overall_rating: number;
  strengths?: string | null;
  areas_for_improvement?: string | null;
  recommended?: boolean | null;
  flag: RatingFlag;
  submitted: boolean;
  created_at?: string | null;
  submitted_at?: string | null;
}

// ── certifications ───────────────────────────────────────────────────────

export interface CertificationTag {
  id: string;
  label: string;
  created_at?: string | null;
}

// ── performance aggregation ──────────────────────────────────────────────

export interface QuizHistoryEntry {
  attempt_id: string;
  cohort_id: string;
  program_name: string;
  score: number | null;
  total: number;
  critical_correct: number | null;
  critical_total: number | null;
  submitted_at?: string | null;
}

export interface RatingHistoryEntry {
  rating_id: string;
  cohort_id: string;
  program_name: string;
  rater_name?: string | null;
  overall_rating: number;
  recommended?: boolean | null;
  flag: RatingFlag;
  strengths?: string | null;
  areas_for_improvement?: string | null;
  submitted_at?: string | null;
}

export interface InstructorPerformance {
  user_id: string;
  total_sessions_delivered: number;
  total_hours_delivered: number;
  programs_participated_in: number;
  average_rating: number | null;
  recent_rating_trend: number[];
  reliability_ratio: number | null;
  certifications: CertificationTag[];
  quiz_history: QuizHistoryEntry[];
  rating_history: RatingHistoryEntry[];
}

// ── ranking weights ──────────────────────────────────────────────────────

export const RANKING_FACTORS = [
  { key: "assessment_score", label: "Assessment Score" },
  { key: "previous_rating", label: "Previous Performance Rating" },
  { key: "relevant_experience", label: "Relevant Experience" },
  { key: "sessions_hours", label: "Total Sessions / Hours Delivered" },
  { key: "reliability", label: "Reliability & Commitment" },
  { key: "recent_performance", label: "Recent Performance" },
] as const;

export type RankingFactorKey = (typeof RANKING_FACTORS)[number]["key"];

export interface RankingWeightProfile {
  id: string;
  name: string;
  factor_weights: Record<RankingFactorKey, number>;
  is_active: boolean;
  updated_at?: string | null;
}
