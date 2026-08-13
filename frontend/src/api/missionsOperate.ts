/** Operate mission API (Operate v2, Stage 7C) — thin wrappers over
 * `/missions/operate/*`. Types mirror `schemas/missions_operate.py`.
 *
 * `telemetry` is a loose record on purpose: the channel list is authored
 * server-side in `services/missions/operate/telemetry.py:CHANNELS` next to
 * its nominal ranges, and re-declaring every channel here would mean a new
 * readout could only ship by editing two files that must agree. The v1
 * port had exactly that drift — its `Telemetry` interface declared
 * `solar_current`, which the simulator never actually set.
 */
import { api } from "./client";

export interface CommandEvent {
  seq: number;
  command: string;
  arg: string;
  sim_t: number;
  issued_by: string;
  success: boolean;
  message: string;
  at: string;
}

/** An event the spacecraft reported on its own — AOS, eclipse entry, a
 * fault detection firing. Distinct from the command transcript, and the
 * student's primary alert channel. */
export interface SpacecraftLogEntry {
  t: number;
  level: "INFO" | "WARNING" | "ERROR";
  message: string;
}

export interface OrbitPhase {
  orbit_number: number;
  orbit_fraction: number;
  label: string;
  sunlit: boolean;
  in_pass: boolean;
  in_saa: boolean;
  elevation_deg: number;
  seconds_to_next_aos: number;
  seconds_to_los: number;
  seconds_to_eclipse: number;
  seconds_to_sunrise: number;
}

export interface OrbitSummary {
  altitude_km: number;
  period_minutes: number;
  velocity_km_s: number;
  inclination_deg: number;
  eclipse_fraction: number;
  eclipse_minutes: number;
  pass_minutes: number;
  orbits: number;
  session_minutes: number;
  real_minutes: number;
  time_compression: number;
  ground_station: string;
}

export type ChannelStatus = "nominal" | "warn" | "alarm";

export interface SubsystemRow {
  key: string;
  label: string;
  value: string | number;
  unit: string;
  status: ChannelStatus;
}

export interface SubsystemCard {
  subsystem: string;
  title: string;
  status: "nominal" | "warning" | "critical" | "off";
  rows: SubsystemRow[];
}

export interface AnomalyState {
  key: string;
  title: string;
  subsystem: string;
  origin: "injected" | "emergent";
  raised_t: number;
  cleared_t: number | null;
  outcome: "resolved" | "late" | "unresolved";
}

export interface Objective {
  key: string;
  label: string;
  detail: string;
  target: number;
  actual: number;
  fraction: number;
  met: boolean;
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

export type Telemetry = Record<string, number | string | boolean>;

export interface OperateState {
  attempt_id: string;
  mission_id: string;
  variant_id: string;
  variant_label: string;
  attempt_status: "in_progress" | "submitted" | "passed" | "failed" | "abandoned";

  sim_t: number;
  session_seconds: number;
  time_compression: number;
  expired: boolean;
  phase: OrbitPhase;
  orbit: OrbitSummary;

  telemetry: Telemetry;
  subsystems: SubsystemCard[];
  events: CommandEvent[];
  spacecraft_log: SpacecraftLogEntry[];
  anomalies: AnomalyState[];

  objectives: Objective[];
  score: number;
  objectives_score: number;
  performance_score: number;
  penalty_points: number;
  pass_threshold: number;

  is_team: boolean;
  crew: Record<string, string>;
  roster: CrewMember[];
  /** Non-empty when this flight's vehicle came from the student's own
   * passed design attempt (Stage 7C-9). */
  spacecraft_source: string[];
}

export interface HandbookEntry {
  key: string;
  title: string;
  subsystem: string;
  origin: "injected" | "emergent";
  symptom_channels: string[];
  symptom: string;
  meaning?: string;
  action?: string;
  if_ignored?: string;
  commands?: string[];
}

export interface CommandRef {
  name: string;
  subsystem: string;
  summary: string;
  usage: string;
  role: string | null;
}

export interface FlightRule {
  channel: string;
  label: string;
  unit: string;
  subsystem: string;
  low: number | null;
  high: number | null;
}

export interface CrewRoleBrief {
  role: string;
  label: string;
  subsystem: string;
  commands: string[];
}

export interface Handbook {
  disclosure: "full" | "symptoms" | "reference";
  entries: HandbookEntry[];
  commands: CommandRef[];
  flight_rules: FlightRule[];
  crew_roles: CrewRoleBrief[];
  assumptions: string[];
}

export interface Briefing {
  mission_id: string;
  mission_title: string;
  mission_summary: string | null;
  variant_id: string;
  variant_label: string;
  points: number;
  pass_threshold: number;
  orbit: OrbitSummary;
  spacecraft: Record<string, number>;
  objectives: { key: string; label: string; detail: string }[];
  flight_rules: FlightRule[];
  commands: CommandRef[];
  handbook: HandbookEntry[];
  crew_roles: CrewRoleBrief[];
  assumptions: string[];
}

export interface TracePoint {
  t: number;
  soc: number;
  wheel_rpm: number;
  payload_temp: number;
  panel_temp: number;
  signal: number;
  storage: number;
  downlinked: number;
  sunlit: boolean;
  in_pass: boolean;
}

export interface AnomalyWindow {
  key: string;
  title: string;
  subsystem: string;
  origin: "injected" | "emergent";
  start_t: number;
  end_t: number;
  outcome: "resolved" | "late" | "unresolved";
  cleared_by: string | null;
  response_seconds: number | null;
  response_window_s: number;
  teaching: {
    title?: string;
    symptom?: string;
    meaning?: string;
    action?: string;
    if_ignored?: string;
    commands?: string[];
  };
}

export interface FlightReport {
  summary: Record<string, number | string>;
  anomaly_tally: { total: number; resolved: number; late: number; unresolved: number };
  notes: { tone: "good" | "warn" | "bad"; text: string }[];
}

export interface Debrief {
  attempt_id: string;
  mission_id: string;
  variant_label: string;
  attempt_status: string;
  passed: boolean;
  score: number;
  pass_threshold: number;
  objectives_score: number;
  performance_score: number;
  penalty_points: number;
  objectives: Objective[];
  penalties: { key: string; label: string; note: string; count: number; points: number }[];
  timeline: {
    session_seconds: number;
    period_seconds: number;
    orbits: number;
    passes: { orbit: number; start_t: number; end_t: number; station: string }[];
    eclipses: { orbit: number; start_t: number; end_t: number }[];
    saa: { orbit: number; start_t: number; end_t: number }[];
  };
  trace: TracePoint[];
  command_markers: { t: number; command: string; success: boolean; issued_by: string }[];
  anomaly_windows: AnomalyWindow[];
  report: FlightReport;
  events: CommandEvent[];
  spacecraft_log: SpacecraftLogEntry[];
}

export async function fetchBriefing(missionId: string, variantId?: string): Promise<Briefing> {
  const { data } = await api.get<Briefing>(`/missions/operate/briefing/${missionId}`, {
    params: variantId ? { variant_id: variantId } : undefined,
  });
  return data;
}

export async function fetchOperateState(attemptId: string): Promise<OperateState> {
  const { data } = await api.get<OperateState>(`/missions/operate/attempts/${attemptId}`);
  return data;
}

export async function fetchHandbook(attemptId: string): Promise<Handbook> {
  const { data } = await api.get<Handbook>(`/missions/operate/attempts/${attemptId}/handbook`);
  return data;
}

export async function fetchDebrief(attemptId: string): Promise<Debrief> {
  const { data } = await api.get<Debrief>(`/missions/operate/attempts/${attemptId}/debrief`);
  return data;
}

export async function sendCommand(
  attemptId: string,
  command: string,
): Promise<{ event: CommandEvent; state: OperateState }> {
  const { data } = await api.post(`/missions/operate/attempts/${attemptId}/command`, { command });
  return data;
}

export async function finishOperation(
  attemptId: string,
): Promise<{ passed: boolean; score: number; state: OperateState }> {
  const { data } = await api.post(`/missions/operate/attempts/${attemptId}/finish`);
  return data;
}

export async function setCrewRole(attemptId: string, role: CrewRole | null): Promise<OperateState> {
  const { data } = await api.post<OperateState>(`/missions/operate/attempts/${attemptId}/crew`, { role });
  return data;
}

/** `T+01:23:45` on the flight clock. Sim time, not wall time — the whole
 * console reasons in orbit seconds. */
export function flightClock(simSeconds: number): string {
  const t = Math.max(0, Math.floor(simSeconds));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  return `T+${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

/** `8m 12s` — for countdowns, where hours are noise. */
export function countdown(seconds: number): string {
  const t = Math.max(0, Math.floor(seconds));
  const m = Math.floor(t / 60);
  const s = t % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}
