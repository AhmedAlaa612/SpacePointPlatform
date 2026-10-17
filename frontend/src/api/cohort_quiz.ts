/** Cohort knowledge-quiz endpoints (2026-09), mirroring
 *  backend/app/routers/lms/cohort_quiz_admin.py (authoring) and the
 *  quiz/start/submit/result endpoints added to backend/app/routers/lms/
 *  student.py. See api/instructor_assessment.ts for the closest sibling
 *  pattern this follows. */

import { api } from "@/api/client";
import type {
  CohortQuizAnswerInput,
  CohortQuizAttempt,
  CohortQuizDifficulty,
  CohortQuizQuestion,
  CohortQuizQuestionImportResult,
  CohortQuizResult,
  CohortQuizTemplate,
  CohortQuizTemplateDetail,
} from "@/types/cohort_quiz";

// ── admin: question bank ────────────────────────────────────────────────

export const listCohortQuizQuestionsApi = (params?: { topic?: string; is_active?: boolean }) =>
  api.get<CohortQuizQuestion[]>("/lms/admin/cohort-quiz/questions", { params }).then((r) => r.data);

export interface CohortQuizQuestionInput {
  topic: string;
  subtopic?: string | null;
  difficulty: CohortQuizDifficulty;
  time_limit_seconds: number;
  bloom_level?: string | null;
  question_type?: "mcq" | "textarea" | string | null;
  prompt: string;
  options?: { text: string; is_correct: boolean }[];
  explanation?: string | null;
  source_url?: string | null;
}

export const createCohortQuizQuestionApi = (data: CohortQuizQuestionInput) =>
  api.post<CohortQuizQuestion>("/lms/admin/cohort-quiz/questions", data).then((r) => r.data);

export const updateCohortQuizQuestionApi = (
  questionId: string, data: Partial<CohortQuizQuestionInput & { is_active: boolean }>,
) => api.patch<CohortQuizQuestion>(`/lms/admin/cohort-quiz/questions/${questionId}`, data).then((r) => r.data);

export const retireCohortQuizQuestionApi = (questionId: string) =>
  api.delete<void>(`/lms/admin/cohort-quiz/questions/${questionId}`).then((r) => r.data);

export const importCohortQuizQuestionsApi = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<CohortQuizQuestionImportResult>("/lms/admin/cohort-quiz/questions/import", form).then((r) => r.data);
};

export const downloadCohortQuizQuestionTemplateApi = async () => {
  const res = await api.get("/lms/admin/cohort-quiz/questions/import/template", { responseType: "blob" });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "cohort_quiz_question_template.xlsx";
  a.click();
  URL.revokeObjectURL(url);
};

// ── admin: templates ─────────────────────────────────────────────────────

export const listCohortQuizTemplatesApi = () =>
  api.get<CohortQuizTemplate[]>("/lms/admin/cohort-quiz/templates").then((r) => r.data);

export const createCohortQuizTemplateApi = (data: { name: string; description?: string | null }) =>
  api.post<CohortQuizTemplate>("/lms/admin/cohort-quiz/templates", data).then((r) => r.data);

export const getCohortQuizTemplateApi = (templateId: string) =>
  api.get<CohortQuizTemplateDetail>(`/lms/admin/cohort-quiz/templates/${templateId}`).then((r) => r.data);

export const updateCohortQuizTemplateApi = (
  templateId: string, data: Partial<{ name: string; description: string | null; is_active: boolean }>,
) => api.patch<CohortQuizTemplate>(`/lms/admin/cohort-quiz/templates/${templateId}`, data).then((r) => r.data);

/** Hard delete — only succeeds for a template no checklist item points at
 *  and no student has attempted; the server 409s (with a sentence) otherwise
 *  and suggests `updateCohortQuizTemplateApi(id, { is_active: false })`
 *  (retire) instead. */
export const deleteCohortQuizTemplateApi = (templateId: string) =>
  api.delete<void>(`/lms/admin/cohort-quiz/templates/${templateId}`).then((r) => r.data);

export const addCohortQuizTemplateQuestionApi = (templateId: string, questionId: string) =>
  api.post<CohortQuizTemplateDetail>(
    `/lms/admin/cohort-quiz/templates/${templateId}/questions`, { question_id: questionId },
  ).then((r) => r.data);

export const removeCohortQuizTemplateQuestionApi = (templateId: string, templateQuestionId: string) =>
  api.delete<CohortQuizTemplateDetail>(
    `/lms/admin/cohort-quiz/templates/${templateId}/questions/${templateQuestionId}`,
  ).then((r) => r.data);

export const reorderCohortQuizTemplateQuestionsApi = (templateId: string, templateQuestionIds: string[]) =>
  api.post<CohortQuizTemplateDetail>(
    `/lms/admin/cohort-quiz/templates/${templateId}/questions/reorder`,
    { template_question_ids: templateQuestionIds },
  ).then((r) => r.data);

/** Auto-populates the template's fixed question set (replacing whatever's
 *  currently on it) with a round-robin spread across topics. "Regenerate"
 *  in the UI is just calling this again for a different random pick. */
export const generateCohortQuizTemplateQuestionsApi = (
  templateId: string, data: { count: number; topics?: string[] | null },
) => api.post<CohortQuizTemplateDetail>(`/lms/admin/cohort-quiz/templates/${templateId}/generate`, data).then((r) => r.data);

// ── student: taking the quiz ─────────────────────────────────────────────

export const startCohortQuizApi = (assignmentId: string, itemId: string) =>
  api.post<CohortQuizAttempt>(`/lms/programs/${assignmentId}/items/${itemId}/quiz/start`).then((r) => r.data);

export const submitCohortQuizApi = (assignmentId: string, itemId: string, answers: CohortQuizAnswerInput[]) =>
  api.post<CohortQuizResult>(
    `/lms/programs/${assignmentId}/items/${itemId}/quiz/submit`, { answers },
  ).then((r) => r.data);

export const getCohortQuizResultApi = (assignmentId: string, itemId: string) =>
  api.get<CohortQuizResult>(`/lms/programs/${assignmentId}/items/${itemId}/quiz/result`).then((r) => r.data);

// ── ops/instructor: reviewing + resetting a student's attempt ───────────

/** Per-question answers, response time, and what was left unanswered —
 * the ops/instructor drill-in from the Progress panel. 404s until the
 * student has actually submitted. */
export const getInstructorCohortQuizReviewApi = (cohortId: string, assignmentId: string, itemId: string) =>
  api.get<CohortQuizResult>(
    `/lms/instructor/cohorts/${cohortId}/program-progress/${assignmentId}/items/${itemId}/quiz/review`,
  ).then((r) => r.data);

/** Deletes the student's attempt (in-progress or submitted) so their next
 * visit starts a brand-new one — "let them retake". Returns every item on
 * the assignment (same shape as `getAssignmentItemsApi`) so the caller can
 * refresh the row without a second round-trip. */
export const resetCohortQuizAttemptApi = (cohortId: string, assignmentId: string, itemId: string) =>
  api.post(
    `/lms/instructor/cohorts/${cohortId}/program-progress/${assignmentId}/items/${itemId}/quiz/reset`,
  ).then((r) => r.data);
