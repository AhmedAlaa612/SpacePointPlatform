import { useCallback, useEffect, useRef, useState } from "react"
import type { FormEvent } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft,
  Camera,
  CheckCircle2,
  Keyboard,
  Loader2,
  WifiOff,
  XCircle,
} from "lucide-react"
import { checkInApi, getTodaysSessionsApi } from "@/api/sessions/checkin"
import type { TodaySession } from "@/api/sessions/checkin"
import { extractQrToken, useQrScanner } from "@/hooks/useQrScanner"
import { cn } from "@/lib/utils"

/**
 * Check-in scanner (V2 R2-5) — a door-queue tool: pick today's session, then
 * scan tickets one after another with no taps required between people.
 * Camera lifecycle lives in the shared useQrScanner hook (also used by the
 * W5 S5-1 instructor session-delivery scan) — this file owns session
 * selection, the check-in API call, and the result overlay.
 */

const RESULT_DISPLAY_MS = 2000

type ResultKind =
  | "success"
  | "already_checked_in"
  | "wrong_session"
  | "unknown_ticket"
  | "network_error"
  | "generic_error"

interface ScanOutcome {
  kind: ResultKind
  title: string
  detail?: string
}

function interpretError(err: unknown): ScanOutcome {
  const axiosErr = err as {
    response?: { status?: number; data?: { detail?: string } }
  }
  if (!axiosErr?.response) {
    return {
      kind: "network_error",
      title: "No connection",
      detail: "Couldn't reach the server — check your network and try again.",
    }
  }
  const status = axiosErr.response.status
  const detail = axiosErr.response.data?.detail ?? ""

  if (status === 404) {
    return { kind: "unknown_ticket", title: "Unknown ticket", detail: "This QR code isn't a valid ticket." }
  }
  if (status === 409) {
    if (detail.toLowerCase().includes("already")) {
      return {
        kind: "already_checked_in",
        title: "Already checked in",
        detail: "This ticket was already scanned for this session.",
      }
    }
    return {
      kind: "wrong_session",
      title: "Wrong session",
      detail: detail || "This ticket isn't for this session.",
    }
  }
  if (status === 401 || status === 403) {
    return {
      kind: "generic_error",
      title: "Not authorized",
      detail: "Your session may have expired — please log in again.",
    }
  }
  return { kind: "generic_error", title: "Something went wrong", detail: detail || "Please try again." }
}

export default function CheckIn() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [manualSessionId, setManualSessionId] = useState("")
  const [manualToken, setManualToken] = useState("")
  const [outcome, setOutcome] = useState<ScanOutcome | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [isOnline, setIsOnline] = useState(() => (typeof navigator !== "undefined" ? navigator.onLine : true))

  // True while a submit is in flight or a result card is showing — scans
  // detected during this window are ignored so one QR can't fire twice.
  const busyRef = useRef(false)

  const { data: todaysSessions = [], isLoading: sessionsLoading, isError: sessionsFailed } = useQuery<TodaySession[]>({
    queryKey: ["sessions-todays-sessions"],
    queryFn: getTodaysSessionsApi,
  })

  const selectedSession = todaysSessions.find((m) => m.id === sessionId)

  useEffect(() => {
    busyRef.current = submitting || outcome !== null
  }, [submitting, outcome])

  // Auto-resume: the result card clears itself ~2s after showing, no tap needed.
  useEffect(() => {
    if (!outcome) return
    const timer = window.setTimeout(() => setOutcome(null), RESULT_DISPLAY_MS)
    return () => window.clearTimeout(timer)
  }, [outcome])

  useEffect(() => {
    const goOnline = () => setIsOnline(true)
    const goOffline = () => setIsOnline(false)
    window.addEventListener("online", goOnline)
    window.addEventListener("offline", goOffline)
    return () => {
      window.removeEventListener("online", goOnline)
      window.removeEventListener("offline", goOffline)
    }
  }, [])

  const handleScan = useCallback(
    async (rawValue: string) => {
      if (busyRef.current || !sessionId) return
      const token = extractQrToken(rawValue)
      if (!token) return
      busyRef.current = true
      setSubmitting(true)
      try {
        const result = await checkInApi({ token, session_id: sessionId })
        setOutcome({
          kind: "success",
          title: result.student_name,
          detail: [result.program_name, result.cohort_name].filter(Boolean).join(" · ") || "Checked in",
        })
      } catch (err) {
        setOutcome(interpretError(err))
      } finally {
        setSubmitting(false)
      }
    },
    [sessionId],
  )

  const { videoRef, scannerMode, cameraError } = useQrScanner({
    enabled: !!sessionId,
    onDetect: handleScan,
    busyRef,
    readerElementId: "checkin-qr-reader",
  })

  const handleManualSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (!manualToken.trim() || busyRef.current) return
    void handleScan(manualToken.trim())
    setManualToken("")
  }

  const changeSession = () => {
    setSessionId(null)
    setOutcome(null)
  }

  // ── Step 1: pick today's meeting ──────────────────────────────────────────
  if (!sessionId) {
    return (
      <div className="mx-auto flex w-full max-w-md flex-col gap-5">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Check-in scanner</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Pick today's session to start scanning tickets at the door.
          </p>
        </div>

        {sessionsLoading && (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="animate-spin text-muted-foreground" size={28} />
          </div>
        )}

        {!sessionsLoading && !sessionsFailed && todaysSessions.length > 0 && (
          <div className="flex flex-col gap-2">
            {todaysSessions.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => setSessionId(m.id)}
                className="flex min-h-[44px] flex-col items-start gap-0.5 rounded-2xl border border-border bg-card p-4 text-left transition-colors hover:border-primary/50 hover:bg-primary/5"
              >
                <span className="text-base font-semibold text-foreground">{m.cohort_name}</span>
                <span className="text-sm text-muted-foreground">{m.program_name}</span>
                {(m.starts_at || m.title) && (
                  <span className="mt-1 text-xs text-muted-foreground">
                    {m.starts_at ? `Starts ${m.starts_at.slice(0, 5)}` : ""}
                    {m.starts_at && m.title ? " · " : ""}
                    {m.title ?? ""}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {!sessionsLoading && (sessionsFailed || todaysSessions.length === 0) && (
          <div className="rounded-2xl border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
            {sessionsFailed ? "Couldn't load today's sessions." : "No sessions are scheduled for today."}
          </div>
        )}

        <div className="mt-2 flex flex-col gap-2 rounded-2xl border border-border bg-card p-4">
          <label htmlFor="manual-session-id" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Or enter a session ID manually
          </label>
          <div className="flex gap-2">
            <input
              id="manual-session-id"
              value={manualSessionId}
              onChange={(e) => setManualSessionId(e.target.value)}
              placeholder="Session ID"
              className="h-11 flex-1 rounded-xl border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => manualSessionId.trim() && setSessionId(manualSessionId.trim())}
              disabled={!manualSessionId.trim()}
              className="h-11 min-w-[44px] rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              Use
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Step 2: scan ───────────────────────────────────────────────────────────
  return (
    <div className="mx-auto flex w-full max-w-md flex-col gap-4">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={changeSession}
          className="-ml-2 flex min-h-[44px] items-center gap-1 px-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft size={16} /> Change session
        </button>
      </div>

      <div className="rounded-2xl border border-border bg-card p-3 text-center">
        <p className="text-base font-semibold text-foreground">{selectedSession?.cohort_name ?? "Manual session"}</p>
        {selectedSession?.program_name && <p className="text-sm text-muted-foreground">{selectedSession.program_name}</p>}
      </div>

      {!isOnline && (
        <div className="flex items-center gap-2 rounded-xl bg-amber-500/15 px-3 py-2 text-sm font-medium text-amber-600">
          <WifiOff size={16} /> You're offline — scans won't go through until you reconnect.
        </div>
      )}

      {cameraError ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-red-400/50 bg-red-500/5 p-6 text-center">
          <Camera className="text-red-500" size={32} />
          <p className="text-sm font-medium text-foreground">{cameraError}</p>
        </div>
      ) : (
        <div className="relative aspect-square overflow-hidden rounded-2xl border border-border bg-black">
          {scannerMode === "native" ? (
            <video ref={videoRef} className="h-full w-full object-cover" playsInline muted autoPlay />
          ) : (
            <div id="checkin-qr-reader" className="h-full w-full [&_video]:!h-full [&_video]:!w-full [&_video]:object-cover" />
          )}
          <div className="pointer-events-none absolute inset-6 rounded-2xl border-4 border-white/70" />
        </div>
      )}

      <form onSubmit={handleManualSubmit} className="flex flex-col gap-2 rounded-2xl border border-border bg-card p-4">
        <label htmlFor="manual-token" className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          <Keyboard size={13} /> Manual entry
        </label>
        <div className="flex gap-2">
          <input
            id="manual-token"
            value={manualToken}
            onChange={(e) => setManualToken(e.target.value)}
            placeholder="Paste ticket link or token"
            className="h-11 flex-1 rounded-xl border border-border bg-background px-3 text-sm text-foreground focus:outline-none focus:border-primary"
          />
          <button
            type="submit"
            disabled={!manualToken.trim() || submitting}
            className="h-11 min-w-[44px] rounded-xl bg-primary px-4 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
          >
            Check in
          </button>
        </div>
      </form>

      {outcome && <ResultOverlay outcome={outcome} onDismiss={() => setOutcome(null)} />}
    </div>
  )
}

function ResultOverlay({ outcome, onDismiss }: { outcome: ScanOutcome; onDismiss: () => void }) {
  const isSuccess = outcome.kind === "success"
  const Icon = isSuccess ? CheckCircle2 : outcome.kind === "network_error" ? WifiOff : XCircle

  return (
    <div
      role="status"
      aria-live="assertive"
      onClick={onDismiss}
      className={cn(
        "fixed inset-0 z-50 flex cursor-pointer flex-col items-center justify-center gap-4 px-6 text-center",
        isSuccess ? "bg-emerald-600" : "bg-red-600",
      )}
    >
      <Icon className="text-white" size={96} strokeWidth={1.5} />
      <p className="max-w-full break-words text-3xl font-bold leading-tight text-white">{outcome.title}</p>
      {outcome.detail && <p className="max-w-full text-lg text-white/90">{outcome.detail}</p>}
      <p className="mt-2 text-xs font-medium uppercase tracking-widest text-white/60">Tap anywhere to continue</p>
    </div>
  )
}
