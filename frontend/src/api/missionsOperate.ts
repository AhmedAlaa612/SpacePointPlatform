/** Operate mission API (Phase 2B, Stage 7B-3/4) — thin wrappers over
 * `/missions/operate/*`. Types mirror `schemas/missions_operate.py`.
 */
import { api } from "./client";

export interface Telemetry {
  pitch: number;
  roll: number;
  yaw: number;
  battery_voltage: number;
  battery_current: number;
  battery_percentage: number;
  panel_temp: number;
  system_temp: number;
  solar_current: number;
  imu_x: number;
  imu_y: number;
  imu_z: number;
  reaction_wheel_speed: number;
  signal_strength: number;
  humidity: number;
  light: number;
}

export interface CommandEvent {
  seq: number;
  command: string;
  issued_by: string;
  success: boolean;
  message: string;
  at: string;
}

export interface AnomalyState {
  index: number;
  subsystem: string;
  triggered: boolean;
  resolved: boolean;
}

export interface CrewMember {
  user_id: string;
  name: string;
  role: string | null;
}

export const CREW_ROLES = ["commander", "eps", "adcs", "comms", "payload"] as const;
export type CrewRole = (typeof CREW_ROLES)[number];

export const CREW_ROLE_LABELS: Record<CrewRole, string> = {
  commander: "Commander",
  eps: "Power Engineer",
  adcs: "Flight Dynamics Officer",
  comms: "Comms Officer",
  payload: "Payload/Science Officer",
};

export interface OperateState {
  attempt_id: string;
  mission_id: string;
  variant_id: string;
  variant_label: string;
  attempt_status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";
  elapsed_seconds: number;
  telemetry: Telemetry;
  events: CommandEvent[];
  anomalies: AnomalyState[];
  score: number;
  triggered_count: number;
  resolved_count: number;
  pass_threshold: number;
  is_team: boolean;
  crew: Record<string, string>;
  roster: CrewMember[];
}

export async function fetchOperateState(attemptId: string): Promise<OperateState> {
  const { data } = await api.get<OperateState>(`/missions/operate/attempts/${attemptId}`);
  return data;
}

export async function sendCommand(attemptId: string, command: string): Promise<{ event: CommandEvent; state: OperateState }> {
  const { data } = await api.post(`/missions/operate/attempts/${attemptId}/command`, { command });
  return data;
}

export async function finishOperation(attemptId: string): Promise<{ passed: boolean; score: number; state: OperateState }> {
  const { data } = await api.post(`/missions/operate/attempts/${attemptId}/finish`);
  return data;
}

export async function setCrewRole(attemptId: string, role: CrewRole | null): Promise<OperateState> {
  const { data } = await api.post<OperateState>(`/missions/operate/attempts/${attemptId}/crew`, { role });
  return data;
}
