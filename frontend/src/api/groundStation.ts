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
