/** Ground Station mission console — `/learn/missions/ground-station/$attemptId`.
 * One rig, owned by this attempt (solo or team), auto-provisioned on first
 * visit (`GET /ground-station/attempts/{id}/device`). No scoring, no
 * pass/fail — just the live console, private to the attempt's owner(s)
 * and staff (see backend/app/services/ground_station/access.py). */
import { useEffect, useState } from "react";
import { useParams, Link } from "@tanstack/react-router";
import { ChevronRight, CheckCircle2 } from "lucide-react";
import { completeAttempt, getAttemptDevice, type AttemptDevice } from "@/api/groundStation";
import { fetchMissionAttempt } from "@/api/missions";
import { DeviceConsole } from "@/pages/ground-station/GroundStationPage";

export default function GroundStationAttemptPage() {
  const { attemptId } = useParams({ strict: false }) as { attemptId: string };
  const [attemptDevice, setAttemptDevice] = useState<AttemptDevice | null>(null);
  const [done, setDone] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getAttemptDevice(attemptId), fetchMissionAttempt(attemptId)])
      .then(([d, attempt]) => { setAttemptDevice(d); setDone(attempt.status === "passed"); setError(""); })
      .catch(() => setError("Couldn't load your rig for this mission."));
  }, [attemptId]);

  async function markComplete() {
    setCompleting(true);
    try {
      await completeAttempt(attemptId);
      setDone(true);
    } finally {
      setCompleting(false);
    }
  }

  if (error) return <div className="p-6 text-sm text-destructive">{error}</div>;
  if (!attemptDevice) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="p-4 sm:p-6 max-w-6xl mx-auto space-y-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Link to="/learn/missions" className="text-primary hover:opacity-80">Missions</Link>
        <ChevronRight className="size-3" />
        <span className="text-foreground">Ground Station</span>
      </div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold">Ground Station</h1>
          <p className="text-xs text-muted-foreground">
            Post your ESP32's telemetry straight to this device — no auth needed:
            <code className="ml-1 bg-muted px-1.5 py-0.5 rounded font-mono text-[11px]">
              POST {attemptDevice.ingest_base_url}/ground-station/devices/{attemptDevice.device.id}/telemetry
            </code>
          </p>
        </div>
        {done ? (
          <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-500 shrink-0">
            <CheckCircle2 size={14} /> Marked complete
          </span>
        ) : (
          <button
            type="button"
            onClick={() => void markComplete()}
            disabled={completing}
            className="text-xs rounded-lg ring-1 ring-border px-3 py-1.5 hover:bg-muted disabled:opacity-50 shrink-0"
          >
            {completing ? "Marking…" : "Mark as complete"}
          </button>
        )}
      </div>
      <DeviceConsole deviceId={attemptDevice.device.id} device={attemptDevice.device} />
    </div>
  );
}
