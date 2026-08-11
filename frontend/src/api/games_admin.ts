/** Live game facilitator-authoring API (Live Games Phase 2C, 8-3) — thin
 * wrapper over `/games/admin/*`. Types mirror `schemas/games_admin.py`. */
import { api } from "@/api/client";

export type PointsMode = "normal" | "double";

export interface GameQuestionOption {
  text: string;
  is_correct: boolean;
}

export interface GameQuestion {
  id: string;
  position: number;
  prompt: string;
  options: GameQuestionOption[];
  time_limit_seconds: number | null;
  points_mode: PointsMode;
  max_points: number;
}

export interface Game {
  id: string;
  title: string;
  description: string | null;
  created_by: string;
  default_time_limit_seconds: number;
  default_floor_pct: number;
  default_blackout_count: number;
  created_at: string | null;
  question_count: number;
}

export interface GameDetail extends Game {
  questions: GameQuestion[];
}

export interface GameCreateInput {
  title: string;
  description?: string | null;
  default_time_limit_seconds?: number;
  default_floor_pct?: number;
  default_blackout_count?: number;
}

export type GameUpdateInput = Partial<GameCreateInput>;

export interface GameQuestionInput {
  prompt: string;
  options: GameQuestionOption[];
  time_limit_seconds?: number | null;
  points_mode?: PointsMode;
  position?: number;
}

export type GameQuestionUpdateInput = Partial<GameQuestionInput>;

export const listGamesApi = () => api.get<Game[]>("/games/admin").then((r) => r.data);

export const createGameApi = (data: GameCreateInput) =>
  api.post<Game>("/games/admin", data).then((r) => r.data);

export const getGameApi = (gameId: string) =>
  api.get<GameDetail>(`/games/admin/${gameId}`).then((r) => r.data);

export const updateGameApi = (gameId: string, data: GameUpdateInput) =>
  api.patch<Game>(`/games/admin/${gameId}`, data).then((r) => r.data);

export const deleteGameApi = (gameId: string) =>
  api.delete<void>(`/games/admin/${gameId}`).then((r) => r.data);

export const createGameQuestionApi = (gameId: string, data: GameQuestionInput) =>
  api.post<GameQuestion>(`/games/admin/${gameId}/questions`, data).then((r) => r.data);

export const updateGameQuestionApi = (questionId: string, data: GameQuestionUpdateInput) =>
  api.patch<GameQuestion>(`/games/admin/questions/${questionId}`, data).then((r) => r.data);

export const duplicateGameQuestionApi = (questionId: string) =>
  api.post<GameQuestion>(`/games/admin/questions/${questionId}/duplicate`).then((r) => r.data);

export const deleteGameQuestionApi = (questionId: string) =>
  api.delete<void>(`/games/admin/questions/${questionId}`).then((r) => r.data);

export const reorderGameQuestionsApi = (gameId: string, questionIds: string[]) =>
  api.post<GameQuestion[]>(`/games/admin/${gameId}/questions/reorder`, { question_ids: questionIds }).then((r) => r.data);
