import { api } from "./client";

export interface ArcadeDebriefNote {
  ok: boolean;
  t: string;
}

export interface ArcadeModeBest {
  best_score: number;
  passed: boolean;
  attempts_count: number;
}

export interface ArcadeGameCatalogItem {
  id: string;
  game_key: string;
  position: number;
  module_key: string;
  module_no: string;
  module_name: string;
  kind: string;
  is_3d: boolean;
  title: string;
  blurb: string | null;
  lesson_explorer: string | null;
  lesson_engineer: string | null;
  time_explorer_seconds: number;
  time_engineer_seconds: number;
  points_explorer: number;
  points_engineer: number;
  explorer: ArcadeModeBest;
  engineer: ArcadeModeBest;
}

export interface ArcadeAttemptSubmitInput {
  mode: "explorer" | "engineer";
  score: number;
  accuracy: number;
  passed: boolean;
  elapsed_seconds: number;
  notes: ArcadeDebriefNote[];
  assignment_id?: string | null;
  program_item_id?: string | null;
}

export interface ArcadeAttemptOut {
  id: string;
  game_id: string;
  game_key: string;
  game_title: string;
  mode: string;
  score: number;
  accuracy: number;
  passed: boolean;
  elapsed_seconds: number;
  attempt_no: number;
  points_awarded: number;
  notes: ArcadeDebriefNote[];
  completed_at: string | null;
}

export const fetchArcadeGamesApi = () =>
  api.get<ArcadeGameCatalogItem[]>("/lms/arcade/games").then((r) => r.data);

export const submitArcadeAttemptApi = (gameKey: string, body: ArcadeAttemptSubmitInput) =>
  api.post<ArcadeAttemptOut>(`/lms/arcade/games/${gameKey}/attempts`, body).then((r) => r.data);

export const getStudentArcadeBestAttemptApi = (cohortId: string, assignmentId: string, itemId: string) =>
  api
    .get<ArcadeAttemptOut>(`/lms/arcade/cohorts/${cohortId}/assignments/${assignmentId}/items/${itemId}/best-attempt`)
    .then((r) => r.data);
