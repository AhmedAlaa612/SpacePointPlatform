/** Live game instructor live-play API (Live Games Phase 2C, 8-7) — thin
 * wrapper over `/games/live/*`. Types mirror `schemas/games_live.py`. */
import { api } from "@/api/client";

export interface PublicQuestion {
  id: string;
  position: number;
  prompt: string;
  options: { text: string }[];
  time_limit_seconds: number;
  max_points: number;
}

export interface LiveQuestion {
  id: string;
  position: number;
  prompt: string;
  options: { text: string; is_correct: boolean }[];
  time_limit_seconds: number;
  max_points: number;
}

export interface GameRun {
  id: string;
  assignment_id: string;
  run_no: number;
  status: "lobby" | "live" | "ended";
  current_question_position: number | null;
  total_questions: number;
  blackout_active: boolean;
  started_at: string | null;
  ended_at: string | null;
}

export interface RosterEntry {
  participant_id: string;
  nickname: string;
  avatar: string | null;
  has_answered_current: boolean;
}

export interface LeaderboardEntry {
  participant_id: string;
  nickname: string;
  avatar: string | null;
  score: number;
}

export interface QuestionResult {
  index: number;
  text: string;
  is_correct: boolean;
  count: number;
  pct: number;
}

export const openRunApi = (assignmentId: string) =>
  api.post<GameRun>(`/games/live/assignments/${assignmentId}/runs`).then((r) => r.data);

export const getRunApi = (runId: string) =>
  api.get<GameRun>(`/games/live/runs/${runId}`).then((r) => r.data);

export const getCurrentQuestionApi = (runId: string) =>
  api.get<LiveQuestion>(`/games/live/runs/${runId}/question`).then((r) => r.data);

export const startRunApi = (runId: string) =>
  api.post<GameRun>(`/games/live/runs/${runId}/start`).then((r) => r.data);

export const revealRunApi = (runId: string) =>
  api.post<QuestionResult[]>(`/games/live/runs/${runId}/reveal`).then((r) => r.data);

export const nextQuestionApi = (runId: string) =>
  api.post<GameRun>(`/games/live/runs/${runId}/next`).then((r) => r.data);

export const restartRunApi = (runId: string) =>
  api.post<GameRun>(`/games/live/runs/${runId}/restart`).then((r) => r.data);

export const endRunApi = (runId: string) =>
  api.post<GameRun>(`/games/live/runs/${runId}/end`).then((r) => r.data);

export const getRosterApi = (runId: string) =>
  api.get<RosterEntry[]>(`/games/live/runs/${runId}/roster`).then((r) => r.data);

export const getLeaderboardApi = (runId: string) =>
  api.get<LeaderboardEntry[]>(`/games/live/runs/${runId}/leaderboard`).then((r) => r.data);

export const revealParticipantNameApi = (runId: string, participantId: string) =>
  api.get<{ participant_id: string; real_name: string }>(`/games/live/runs/${runId}/participants/${participantId}/reveal`).then((r) => r.data);

export const revealAllNamesApi = (runId: string) =>
  api.get<{ participant_id: string; real_name: string }[]>(`/games/live/runs/${runId}/reveal-all`).then((r) => r.data);
