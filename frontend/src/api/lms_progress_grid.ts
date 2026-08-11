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
