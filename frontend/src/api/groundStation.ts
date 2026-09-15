/** Ground Station API — thin wrappers over `/ground-station/*`. Ported from
 * the legacy Madar platform's LoRa-Dashboard-V3, now wired into the
 * missions domain (2026-09-14): a real Mission (solo/team, no scoring —
 * see `completeAttempt`), one rig per attempt, private to its owner +
 * staff (see backend/app/services/ground_station/access.py).
 */
import { api } from "./client";

export interface GroundStationDevice {
  id: string;
  label: string;
  status: "online" | "offline";
  last_seen_at: string | null;
  mission_attempt_id: string | null;
}

export interface AttemptDevice {
  device: GroundStationDevice;
  ingest_base_url: string;
}

export interface AttemptComplete {
  attempt_id: string;
  status: string;
  decided_at: string | null;
}

export interface GroundStationAttemptSummary {
  attempt_id: string;
  owner_label: string;
  team_id: string | null;
  user_id: string | null;
  status: string;
  started_at: string | null;
  device_id: string | null;
  device_status: "online" | "offline" | null;
  device_last_seen_at: string | null;
}

export interface CommandQueued {
  id: string;
  name: string;
  arg: string | null;
  queued_at: string;
}

export interface GroundStationPhoto {
  path: string;
  url: string;
  captured_at: string;
  lat: number | null;
  lon: number | null;
  alt: number | null;
}

export interface TelemetryPoint {
  recorded_at: string;
  temp: number | null;
  voltage: number | null;
  current: number | null;
  power: number | null;
  rssi: number | null;
  snr: number | null;
  lat: number | null;
  lon: number | null;
  alt: number | null;
  pitch: number | null;
  roll: number | null;
  yaw: number | null;
}

export interface HistoryResponse {
  device_id: string;
  minutes: number;
  count: number;
  data: TelemetryPoint[];
}

export interface Thresholds {
  device_id: string;
  temp_max: number;
  temp_min: number;
  voltage_max: number;
  voltage_min: number;
  current_max: number;
  power_max: number;
}

export type ThresholdsInput = Partial<Omit<Thresholds, "device_id">>;

export interface GroundStationAlert {
  id: string;
  device_id: string;
  occurred_at: string;
  alert_type: string;
  threshold: number;
  current_value: number;
  severity: string;
  acknowledged: boolean;
}

export interface DeviceStats {
  device_id: string;
  packets_received: number;
  first_seen: string | null;
  last_seen: string | null;
  active_connections: number;
}

export async function listDevices(): Promise<GroundStationDevice[]> {
  const { data } = await api.get<GroundStationDevice[]>("/ground-station/devices");
  return data;
}

export async function sendCommand(deviceId: string, name: string, arg?: string): Promise<CommandQueued> {
  const { data } = await api.post<CommandQueued>(`/ground-station/devices/${deviceId}/commands`, { name, arg });
  return data;
}

/** Ack a command this browser tab forwarded to the rig over its own open
 * Web Serial connection — the no-auth ingest counterpart to what the
 * on-site agent's ack_command() does after writing to a real serial port.
 * Fire-and-forget by design: `ok` just means the write succeeded, not that
 * the firmware executed it (see cdhs_board.ino's comment on this). */
export async function ackCommand(deviceId: string, commandId: string, ok: boolean, detail?: string): Promise<void> {
  await api.post(`/ground-station/devices/${deviceId}/commands/${commandId}/ack`, { ok, detail: detail ?? "" });
}

export async function listPhotos(deviceId: string): Promise<GroundStationPhoto[]> {
  const { data } = await api.get<GroundStationPhoto[]>(`/ground-station/devices/${deviceId}/photos`);
  return data;
}

export async function getHistory(deviceId: string, minutes: number): Promise<HistoryResponse> {
  const { data } = await api.get<HistoryResponse>(`/ground-station/devices/${deviceId}/history`, { params: { minutes } });
  return data;
}

export async function getThresholds(deviceId: string): Promise<Thresholds> {
  const { data } = await api.get<Thresholds>(`/ground-station/devices/${deviceId}/thresholds`);
  return data;
}

export async function putThresholds(deviceId: string, values: ThresholdsInput): Promise<Thresholds> {
  const { data } = await api.put<Thresholds>(`/ground-station/devices/${deviceId}/thresholds`, values);
  return data;
}

export async function listAlerts(deviceId: string, activeOnly = false): Promise<GroundStationAlert[]> {
  const { data } = await api.get<GroundStationAlert[]>(`/ground-station/devices/${deviceId}/alerts`, { params: { active: activeOnly } });
  return data;
}

export async function acknowledgeAlert(deviceId: string, alertId: string): Promise<GroundStationAlert> {
  const { data } = await api.post<GroundStationAlert>(`/ground-station/devices/${deviceId}/alerts/${alertId}/acknowledge`);
  return data;
}

export async function getDeviceStats(deviceId: string): Promise<DeviceStats> {
  const { data } = await api.get<DeviceStats>(`/ground-station/devices/${deviceId}/stats`);
  return data;
}

export async function sendBrowserTelemetry(deviceId: string, data: Record<string, unknown>): Promise<void> {
  // No auth on ingest (2026-09-14) — Web Serial posts to the same open
  // endpoint the agent/ESP32 use, not a JWT-authenticated variant anymore.
  await api.post(`/ground-station/devices/${deviceId}/telemetry`, { data });
}

export async function registerDevice(label: string): Promise<GroundStationDevice> {
  const { data } = await api.post<GroundStationDevice>("/ground-station/admin/devices", { label });
  return data;
}

export async function getAttemptDevice(attemptId: string): Promise<AttemptDevice> {
  const { data } = await api.get<AttemptDevice>(`/ground-station/attempts/${attemptId}/device`);
  return data;
}

export async function completeAttempt(attemptId: string): Promise<AttemptComplete> {
  const { data } = await api.post<AttemptComplete>(`/ground-station/attempts/${attemptId}/complete`);
  return data;
}

export async function listGroundStationAttempts(): Promise<GroundStationAttemptSummary[]> {
  const { data } = await api.get<GroundStationAttemptSummary[]>("/ground-station/admin/attempts");
  return data;
}
