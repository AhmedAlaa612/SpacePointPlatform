/** Live game per-session assignment API (Live Games Phase 2C, 8-4) — thin
 * wrapper over `/games/sessions/*`. Types mirror `schemas/games_admin.py`'s
 * GameSessionAssignment* schemas; question shape reuses GameQuestion as-is
 * (identical fields on both the template and its snapshot copy). */
import { api } from "@/api/client";
import type { GameQuestion, GameQuestionInput, GameQuestionUpdateInput } from "@/api/games_admin";

export interface GameSessionAssignment {
  id: string;
  session_id: string;
  game_id: string;
  game_title: string;
  instructor_note: string | null;
  time_limit_seconds: number;
  floor_pct: number;
  blackout_count: number;
  assigned_by: string;
  created_at: string | null;
  question_count: number;
}

export interface GameSessionAssignmentDetail extends GameSessionAssignment {
  questions: GameQuestion[];
}

export interface GameSessionAssignmentCreateInput {
  game_id: string;
  instructor_note?: string | null;
}

export interface GameSessionAssignmentUpdateInput {
  instructor_note?: string | null;
  time_limit_seconds?: number;
  floor_pct?: number;
  blackout_count?: number;
}

export const listSessionAssignmentsApi = (sessionId: string) =>
  api.get<GameSessionAssignment[]>(`/games/sessions/${sessionId}/assignments`).then((r) => r.data);

export const createSessionAssignmentApi = (sessionId: string, data: GameSessionAssignmentCreateInput) =>
  api.post<GameSessionAssignmentDetail>(`/games/sessions/${sessionId}/assignments`, data).then((r) => r.data);

export const getSessionAssignmentApi = (assignmentId: string) =>
  api.get<GameSessionAssignmentDetail>(`/games/sessions/assignments/${assignmentId}`).then((r) => r.data);

export const updateSessionAssignmentApi = (assignmentId: string, data: GameSessionAssignmentUpdateInput) =>
  api.patch<GameSessionAssignment>(`/games/sessions/assignments/${assignmentId}`, data).then((r) => r.data);

export const deleteSessionAssignmentApi = (assignmentId: string) =>
  api.delete<void>(`/games/sessions/assignments/${assignmentId}`).then((r) => r.data);

export const createAssignmentQuestionApi = (assignmentId: string, data: GameQuestionInput) =>
  api.post<GameQuestion>(`/games/sessions/assignments/${assignmentId}/questions`, data).then((r) => r.data);

export const updateAssignmentQuestionApi = (questionId: string, data: GameQuestionUpdateInput) =>
  api.patch<GameQuestion>(`/games/sessions/questions/${questionId}`, data).then((r) => r.data);

export const duplicateAssignmentQuestionApi = (questionId: string) =>
  api.post<GameQuestion>(`/games/sessions/questions/${questionId}/duplicate`).then((r) => r.data);

export const deleteAssignmentQuestionApi = (questionId: string) =>
  api.delete<void>(`/games/sessions/questions/${questionId}`).then((r) => r.data);

export const reorderAssignmentQuestionsApi = (assignmentId: string, questionIds: string[]) =>
  api.post<GameQuestion[]>(`/games/sessions/assignments/${assignmentId}/questions/reorder`, { question_ids: questionIds }).then((r) => r.data);
