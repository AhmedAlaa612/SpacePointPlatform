/** Admin progress grid (7B-1, Missions Phase 2B) — thin wrapper over
 * `/lms/admin/progress-grid`. Types mirror `schemas/lms_progress_grid.py`. */
import { api } from "@/api/client";

export interface ProgressGridCourse {
  course_id: string;
  title: string;
}

export interface ProgressGridMission {
  mission_id: string;
  title: string;
}

export interface CourseCell {
  enrolled: boolean;
  pct: number;
}

export type MissionStatus = "in_progress" | "submitted" | "passed" | "failed" | "abandoned";

export interface MissionCell {
  status: MissionStatus;
  score: number | null;
  attempt_no: number;
  /** Design v2 (7D-9) — per-step entry state for design missions. */
  steps?: Record<string, boolean> | null;
}

export interface ProgressGridRow {
  user_id: string;
  full_name: string;
  courses: Record<string, CourseCell>;
  missions: Record<string, MissionCell>;
}

export interface ProgressGrid {
  cohort_id: string;
  courses: ProgressGridCourse[];
  missions: ProgressGridMission[];
  rows: ProgressGridRow[];
}

export const getProgressGridApi = (cohortId: string) =>
  api.get<ProgressGrid>("/lms/admin/progress-grid", { params: { cohort_id: cohortId } }).then((r) => r.data);

// ── all-students single-item views (2026-08-12) ─────────────────────────────

export interface CourseProgressRow {
  user_id: string;
  full_name: string;
  pct: number;
}

export interface CourseProgressAll {
  course_id: string;
  course_title: string;
  rows: CourseProgressRow[];
}

export interface MissionProgressRow {
  user_id: string;
  full_name: string;
  status: MissionStatus;
  score: number | null;
  attempt_no: number;
}

export interface MissionProgressAll {
  mission_id: string;
  mission_title: string;
  rows: MissionProgressRow[];
}

export const getCourseProgressApi = (courseId: string, cohortId?: string) =>
  api.get<CourseProgressAll>("/lms/admin/progress/courses", {
    params: { course_id: courseId, cohort_id: cohortId || undefined },
  }).then((r) => r.data);

export const getMissionProgressApi = (missionId: string) =>
  api.get<MissionProgressAll>(`/lms/admin/progress/missions/${missionId}`).then((r) => r.data);
