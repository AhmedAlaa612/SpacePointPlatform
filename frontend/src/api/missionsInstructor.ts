/** Cohort-scoped instructor Missions surface (2026-08-17) — thin wrapper
 * over `/missions/instructor/*`. Progress reuses the same `ProgressGrid`
 * shape as the staff-only cohort grid (`api/lms_progress_grid.ts`).
 * Review reuses the same `ManagedAttempt` shape as the mission-manager
 * queue (`api/missions_manager.ts`). */
import { api } from "@/api/client";
import type { ProgressGrid } from "@/api/lms_progress_grid";
import type { ManagedAttempt } from "@/api/missions_manager";

export interface InstructorCohort {
  id: string;
  name: string;
  program_name: string | null;
  status: string;
}

export interface MissionStepGate {
  step_key: string;
  label: string;
  is_unlocked: boolean;
  updated_at: string | null;
  updated_by_name: string | null;
}

export const myInstructorCohortsApi = () =>
  api.get<InstructorCohort[]>("/missions/instructor/cohorts").then((r) => r.data);

export const instructorCohortProgressApi = (cohortId: string) =>
  api.get<ProgressGrid>(`/missions/instructor/cohorts/${cohortId}/progress`).then((r) => r.data);

export const instructorStepGatesApi = (cohortId: string, missionId: string) =>
  api.get<MissionStepGate[]>(`/missions/instructor/cohorts/${cohortId}/missions/${missionId}/gates`).then((r) => r.data);

export const setInstructorStepGateApi = (cohortId: string, missionId: string, stepKey: string, isUnlocked: boolean) =>
  api.put<MissionStepGate>(
    `/missions/instructor/cohorts/${cohortId}/missions/${missionId}/gates/${stepKey}`,
    { is_unlocked: isUnlocked },
  ).then((r) => r.data);

export interface DesignStepSelection {
  step_key: string;
  label: string;
  included: boolean;
  prereqs: string[];
}

export interface DesignStepSelections {
  is_default: boolean;
  steps: DesignStepSelection[];
  downlink_deps: string[];
  downlink_included: boolean;
}

export const instructorStepSelectionApi = (cohortId: string, missionId: string) =>
  api.get<DesignStepSelections>(`/missions/instructor/cohorts/${cohortId}/missions/${missionId}/steps`).then((r) => r.data);

export const setInstructorStepSelectionApi = (cohortId: string, missionId: string, stepKeys: string[]) =>
  api.put<DesignStepSelections>(
    `/missions/instructor/cohorts/${cohortId}/missions/${missionId}/steps`,
    { step_keys: stepKeys },
  ).then((r) => r.data);

export const clearInstructorStepSelectionApi = (cohortId: string, missionId: string) =>
  api.delete<DesignStepSelections>(`/missions/instructor/cohorts/${cohortId}/missions/${missionId}/steps`).then((r) => r.data);

export const instructorReviewQueueApi = (cohortId: string, missionId: string) =>
  api.get<ManagedAttempt[]>(`/missions/instructor/cohorts/${cohortId}/missions/${missionId}/queue`).then((r) => r.data);

export const instructorReviewAttemptApi = (
  attemptId: string, data: { passed: boolean; score?: number | null; review_comment?: string | null },
) => api.post<ManagedAttempt>(`/missions/instructor/attempts/${attemptId}/review`, data).then((r) => r.data);
