/** Ground Station API — thin wrappers over `/ground-station/*`. Ported from
 * the legacy Madar platform's LoRa-Dashboard-V3, minus the mission/scoring
 * wrapper: no attempts, no points, just live telemetry/commands/photos
 * gated by normal login (see backend/app/routers/ground_station/).
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

export async function listGroundStationAttempts(): Promise<GroundStationAttemptSummary[]> {
  const { data } = await api.get<GroundStationAttemptSummary[]>("/ground-station/admin/attempts");
  return data;
}
