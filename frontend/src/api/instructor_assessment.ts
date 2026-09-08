/** Instructor assessment & performance ranking endpoints (2026-09), mirroring
 *  backend/app/routers/instructor_assessment/. */

import { api } from "@/api/client";
import type {
  AssessmentCohortAssignment,
  AssessmentConfig,
  AssessmentConfigDetail,
  AssessmentQuestion,
  AssessmentQuestionImportResult,
  Attempt,
  AttemptResult,
  CertificationTag,
  InstructorPerformance,
  InstructorProgramRating,
  RankingWeightProfile,
} from "@/types/instructor_assessment";

// ── admin: question bank ────────────────────────────────────────────────

export const listAssessmentConfigsApi = () =>
  api.get<AssessmentConfig[]>("/instructor-assessment/admin/configs").then((r) => r.data);

export const createAssessmentConfigApi = (
  data: { name: string; description?: string | null; draw_size?: number; critical_floor?: number },
) => api.post<AssessmentConfig>("/instructor-assessment/admin/configs", data).then((r) => r.data);

export const getAssessmentConfigApi = (configId: string) =>
  api.get<AssessmentConfigDetail>(`/instructor-assessment/admin/configs/${configId}`).then((r) => r.data);

export const updateAssessmentConfigApi = (
  configId: string,
  data: Partial<{ name: string; description: string | null; is_active: boolean; draw_size: number; critical_floor: number }>,
) => api.patch<AssessmentConfig>(`/instructor-assessment/admin/configs/${configId}`, data).then((r) => r.data);

export interface AssessmentQuestionInput {
  category: string;
  prompt: string;
  options: { text: string; is_correct: boolean }[];
  critical: boolean;
  rationale?: string | null;
}

export const createAssessmentQuestionApi = (configId: string, data: AssessmentQuestionInput) =>
  api.post<AssessmentQuestion>(`/instructor-assessment/admin/configs/${configId}/questions`, data).then((r) => r.data);

export const updateAssessmentQuestionApi = (questionId: string, data: Partial<AssessmentQuestionInput & { is_active: boolean }>) =>
  api.patch<AssessmentQuestion>(`/instructor-assessment/admin/questions/${questionId}`, data).then((r) => r.data);

export const deleteAssessmentQuestionApi = (questionId: string) =>
  api.delete<void>(`/instructor-assessment/admin/questions/${questionId}`).then((r) => r.data);

export const importAssessmentQuestionsApi = (configId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<AssessmentQuestionImportResult>(
    `/instructor-assessment/admin/configs/${configId}/questions/import`, form,
  ).then((r) => r.data);
};

export const downloadAssessmentQuestionsTemplateApi = async () => {
  const res = await api.get("/instructor-assessment/admin/questions/import/template", { responseType: "blob" });
  const url = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "instructor_assessment_questions_template.xlsx";
  a.click();
  URL.revokeObjectURL(url);
};

// ── cohort assignment (the on/off switch) ───────────────────────────────

export const getCohortAssessmentAssignmentApi = (cohortId: string) =>
  api.get<AssessmentCohortAssignment | null>(`/instructor-assessment/cohorts/${cohortId}/config`).then((r) => r.data);

export const setCohortAssessmentAssignmentApi = (cohortId: string, configId: string) =>
  api.put<AssessmentCohortAssignment>(`/instructor-assessment/cohorts/${cohortId}/config`, { config_id: configId }).then((r) => r.data);

export const clearCohortAssessmentAssignmentApi = (cohortId: string) =>
  api.delete<void>(`/instructor-assessment/cohorts/${cohortId}/config`).then((r) => r.data);

// ── attempts (instructor-facing) ────────────────────────────────────────

export const startAssessmentAttemptApi = (cohortCallId: string) =>
  api.post<Attempt>(`/instructor-assessment/attempts/${cohortCallId}/start`).then((r) => r.data);

export const getMyAssessmentAttemptApi = (cohortCallId: string) =>
  api.get<Attempt | null>(`/instructor-assessment/attempts/${cohortCallId}`).then((r) => r.data);

export const submitAssessmentAttemptApi = (attemptId: string, answers: Record<string, number | null>) =>
  api.post<AttemptResult>(`/instructor-assessment/attempts/${attemptId}/submit`, { answers }).then((r) => r.data);

// ── post-program rating ─────────────────────────────────────────────────

export const getInstructorRatingApi = (cohortId: string, instructorUserId: string) =>
  api.get<InstructorProgramRating | null>(`/instructor-assessment/ratings/${cohortId}/${instructorUserId}`).then((r) => r.data);

export interface RatingInput {
  dimension_scores: Record<string, number>;
  strengths?: string | null;
  areas_for_improvement?: string | null;
  recommended?: boolean | null;
  flag: "none" | "exceptional" | "concern";
  submit: boolean;
}

export const upsertInstructorRatingApi = (cohortId: string, instructorUserId: string, data: RatingInput) =>
  api.put<InstructorProgramRating>(`/instructor-assessment/ratings/${cohortId}/${instructorUserId}`, data).then((r) => r.data);

// ── performance profile ──────────────────────────────────────────────────

export const getInstructorPerformanceApi = (userId: string) =>
  api.get<InstructorPerformance>(`/instructor-assessment/performance/${userId}`).then((r) => r.data);

export const addCertificationTagApi = (userId: string, label: string) =>
  api.post<CertificationTag>(`/instructor-assessment/performance/${userId}/certifications`, { label }).then((r) => r.data);

export const deleteCertificationTagApi = (tagId: string) =>
  api.delete<void>(`/instructor-assessment/performance/certifications/${tagId}`).then((r) => r.data);

// ── ranking weights ──────────────────────────────────────────────────────

export const getActiveRankingWeightsApi = () =>
  api.get<RankingWeightProfile>("/instructor-assessment/ranking/weights").then((r) => r.data);

export const updateRankingWeightsApi = (data: { name: string; factor_weights: Record<string, number> }) =>
  api.put<RankingWeightProfile>("/instructor-assessment/ranking/weights", data).then((r) => r.data);
