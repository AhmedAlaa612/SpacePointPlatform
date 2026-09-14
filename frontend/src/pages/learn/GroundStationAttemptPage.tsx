/** Ground Station mission console — `/learn/missions/ground-station/$attemptId`.
 * One rig, owned by this attempt (solo or team), auto-provisioned on first
 * visit (`GET /ground-station/attempts/{id}/device`). No scoring, no
 * pass/fail — just the live console, private to the attempt's owner(s)
 * and staff (see backend/app/services/ground_station/access.py). */
import { useEffect, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import { getAttemptDevice, type AttemptDevice } from "@/api/groundStation";
import { DeviceConsole } from "@/pages/ground-station/GroundStationPage";

export default function GroundStationAttemptPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const [attemptDevice, setAttemptDevice] = useState<AttemptDevice | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getAttemptDevice(attemptId)
      .then((d) => { setAttemptDevice(d); setError(""); })
      .catch(() => setError("Couldn't load your rig for this mission."));
  }, [attemptId]);

  if (error) return <div className="p-6 text-sm text-destructive">{error}</div>;
  if (!attemptDevice) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Ground Station</span>
      </div>
      <div>
        <h1 className="text-lg font-semibold">Ground Station</h1>
        <p className="text-xs text-muted-foreground">
          Post your ESP32's telemetry straight to this device — no auth needed:
          <code className="ml-1 bg-muted px-1.5 py-0.5 rounded font-mono text-[11px]">
            POST {attemptDevice.ingest_base_url}/ground-station/devices/{attemptDevice.device.id}/telemetry
          </code>
        </p>
      </div>
      <DeviceConsole deviceId={attemptDevice.device.id} device={attemptDevice.device} />
    </div>
  );
}
