/** Live game student play API (Live Games Phase 2C, 8-8) — thin wrapper
 * over `/games/play/*`. Types mirror `schemas/games_play.py`. */
import { api } from "@/api/client";
import type { GameRun, PublicQuestion, RosterEntry } from "@/api/games_live";

export interface JoinableRun {
  run_id: string;
  assignment_id: string;
  game_title: string;
  status: "lobby" | "live";
  session_title: string | null;
  session_date: string;
}

export interface Participant {
  id: string;
  run_id: string;
  nickname: string;
  avatar: string | null;
  joined_at: string | null;
}

export interface AnswerAck {
  is_correct: boolean;
  points_awarded: number;
  base_points: number;
  speed_bonus: number;
  streak: number;
}

export interface MyScore {
  score: number;
  streak: number;
}

export interface StudentLeaderboardEntry {
  participant_id: string;
  nickname: string;
  avatar: string | null;
  score: number;
  is_me: boolean;
}

export const getJoinableRunsApi = () => api.get<JoinableRun[]>("/games/play/joinable").then((r) => r.data);

export const joinRunApi = (runId: string, avatar?: string | null) =>
  api.post<Participant>(`/games/play/runs/${runId}/join`, { avatar: avatar ?? null }).then((r) => r.data);

export const updateMyProfileApi = (runId: string, nickname: string, avatar: string | null) =>
  api.patch<Participant>(`/games/play/runs/${runId}/me`, { nickname, avatar }).then((r) => r.data);

export const getPlayRosterApi = (runId: string) =>
  api.get<RosterEntry[]>(`/games/play/runs/${runId}/roster`).then((r) => r.data);

export const getPlayRunApi = (runId: string) => api.get<GameRun>(`/games/play/runs/${runId}`).then((r) => r.data);

export const getPlayQuestionApi = (runId: string) =>
  api.get<PublicQuestion>(`/games/play/runs/${runId}/question`).then((r) => r.data);

export const submitAnswerApi = (runId: string, selectedOptionIndex: number | null, elapsedSeconds: number) =>
  api.post<AnswerAck>(`/games/play/runs/${runId}/answer`, {
    selected_option_index: selectedOptionIndex, elapsed_seconds: elapsedSeconds,
  }).then((r) => r.data);

export const getMyScoreApi = (runId: string) => api.get<MyScore>(`/games/play/runs/${runId}/my-score`).then((r) => r.data);

export const getStudentLeaderboardApi = (runId: string) =>
  api.get<StudentLeaderboardEntry[]>(`/games/play/runs/${runId}/leaderboard`).then((r) => r.data);
