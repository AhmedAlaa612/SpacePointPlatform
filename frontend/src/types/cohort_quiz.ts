/** Cohort knowledge-quiz domain (2026-09). Mirrors
 *  backend/app/schemas/lms_cohort_quiz.py field-for-field. A separate
 *  domain from `instructor_assessment` (randomized-draw instructor MCQs)
 *  and the in-course module quiz (`ContentQuiz` in `api/lms.ts`) — see
 *  backend/app/models/lms/cohort_quiz.py for why. */

// ── question bank ────────────────────────────────────────────────────────

export type CohortQuizDifficulty = "Easy" | "Medium" | "Hard";

export interface CohortQuizQuestionOption {
  text: string;
  is_correct: boolean;
}

export interface CohortQuizQuestion {
  id: string;
  topic: string;
  subtopic?: string | null;
  difficulty: CohortQuizDifficulty;
  time_limit_seconds: number;
  bloom_level?: string | null;
  question_type?: "mcq" | "multiselect" | "textarea" | string | null;
  is_optional?: boolean;
  prompt: string;
  options: CohortQuizQuestionOption[];
  explanation?: string | null;
  source_url?: string | null;
  is_active: boolean;
  organization_id?: string | null;
}

export interface CohortQuizQuestionImportResult {
  created: number;
  skipped_duplicates: number;
  errors: string[];
  questions: CohortQuizQuestion[];
}

// ── templates (the fixed, hand-picked question set) ─────────────────────

export interface CohortQuizTemplate {
  id: string;
  name: string;
  description?: string | null;
  is_active: boolean;
  created_at?: string | null;
  question_count: number;
  organization_id?: string | null;
}

export interface CohortQuizTemplateQuestionEntry {
  id: string;
  position: number;
  question: CohortQuizQuestion;
}

export interface CohortQuizTemplateDetail extends CohortQuizTemplate {
  questions: CohortQuizTemplateQuestionEntry[];
}

// ── attempts (student-facing) ───────────────────────────────────────────

export interface CohortQuizAttemptQuestion {
  question_id: string;
  topic: string;
  difficulty: CohortQuizDifficulty;
  time_limit_seconds: number;
  prompt: string;
  options: string[];
  question_type?: "mcq" | "multiselect" | "textarea" | string | null;
  is_optional?: boolean;
}

export interface CohortQuizAttempt {
  id: string;
  program_item_id: string;
  status: "in_progress" | "submitted";
  total: number;
  questions: CohortQuizAttemptQuestion[];
}

export interface CohortQuizAnswerInput {
  question_id: string;
  selected_option_index: number | null;
  selected_option_indices?: number[] | null;
  text_answer?: string | null;
  time_taken_seconds?: number | null;
  timed_out?: boolean;
}

export interface CohortQuizQuestionReview {
  question_id: string;
  topic: string;
  prompt: string;
  options: string[];
  selected_index: number | null;
  selected_indices?: number[] | null;
  correct_index: number | null;
  correct_indices?: number[] | null;
  is_correct: boolean | null;
  explanation?: string | null;
  time_taken_seconds?: number | null;
  timed_out?: boolean;
  question_type?: "mcq" | "multiselect" | "textarea" | string | null;
  text_answer?: string | null;
  is_optional?: boolean;
}

export interface CohortQuizResult {
  id: string;
  status: "in_progress" | "submitted";
  score: number | null;
  total: number;
  topic_breakdown: Record<string, { correct: number; total: number }> | null;
  submitted_at: string | null;
  questions: CohortQuizQuestionReview[];
}
