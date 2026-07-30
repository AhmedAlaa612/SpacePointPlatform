import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import { ArrowLeft, BookOpen, Calendar, Camera, CheckCircle2, Download, ExternalLink, FileText, MapPin, QrCode, X } from "lucide-react"
import {
  getSessionDeliveryApi, markAttendanceApi, markSessionDoneApi, scanAttendanceApi, startSessionApi,
  uploadSessionReportApi,
} from "@/api/sessions/delivery"
import type { AttendanceStatus, RosterEntry, SessionReport } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { extractQrToken, useQrScanner } from "@/hooks/useQrScanner"
import { cn } from "@/lib/utils"

const STATUS_OPTIONS: { value: AttendanceStatus; label: string; activeClass: string }[] = [
  { value: "present", label: "Present", activeClass: "bg-emerald-600 text-white border-emerald-600" },
  { value: "absent", label: "Absent", activeClass: "bg-red-500 text-white border-red-500" },
]

/** How long a scan result stays on screen. The camera is paused for exactly
 *  this window, so the two can't drift apart. */
const SCAN_FEEDBACK_MS = 2000
/** Ignore the same ticket for this long — covers the ticket still being in
 *  frame when the feedback clears. */
const SAME_TICKET_COOLDOWN_MS = 10000

import { SessionKitsPanel } from "@/pages/instructors/components/SessionKitsPanel"
import { SessionEquipmentPanel } from "@/pages/instructors/components/SessionEquipmentPanel"

export default function SessionDetail() {
  const { sessionId } = useParams({ strict: false }) as { sessionId: string }
  const qc = useQueryClient()
  const [scannerOpen, setScannerOpen] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [scanFeedback, setScanFeedback] = useState<{ kind: "ok" | "info" | "error"; text: string } | null>(null)
  const [rosterSearch, setRosterSearch] = useState("")
  const [reportNotes, setReportNotes] = useState("")
  const [selectedStudent, setSelectedStudent] = useState<RosterEntry | null>(null)
  const [doneError, setDoneError] = useState<string | null>(null)
  const busyRef = useRef(false)
  // The same ticket held in front of the camera is re-detected every frame.
  // Remembering the last one stops a second request firing for it at all,
  // rather than firing it and having the server reject it.
  const lastTokenRef = useRef<{ token: string; at: number } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const delivery = useQuery({
    queryKey: ["session-delivery", sessionId],
    queryFn: () => getSessionDeliveryApi(sessionId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["session-delivery", sessionId] })

  const start = useMutation({ mutationFn: () => startSessionApi(sessionId), onSuccess: invalidate })
  // I2-2: finishing is refused (409) while any assigned kit is uncounted, and
  // the message names them. Without an onError the button would appear to do
  // nothing, which is worse than the refusal itself.
  const done = useMutation({
    mutationFn: () => markSessionDoneApi(sessionId),
    onSuccess: () => { setDoneError(null); invalidate() },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setDoneError(detail ?? "Couldn't mark the session completed")
    },
  })
  const mark = useMutation({
    mutationFn: ({ registrationId, status }: { registrationId: string; status: AttendanceStatus }) =>
      markAttendanceApi(sessionId, registrationId, status),
    onSuccess: invalidate,
  })
  const uploadReport = useMutation({
    mutationFn: (file: File) => uploadSessionReportApi(delivery.data!.cohort_id, { file, sessionId, notes: reportNotes || undefined }),
    onSuccess: () => {
      setReportNotes("")
      if (fileInputRef.current) fileInputRef.current.value = ""
      invalidate()
    },
  })

  // Pause the camera for as long as feedback is on screen, not just while the
  // request is in flight. Releasing it in `finally` (as this used to) reopened
  // the scanner milliseconds after a successful check-in, while the same QR was
  // still in frame — so the next frame re-submitted the same ticket, the server
  // correctly answered "already recorded", and the green success was overwritten
  // by a red error for a student who HAD just been checked in. The ops check-in
  // desk never had this because it derives busy from state the same way.
  useEffect(() => {
    busyRef.current = scanning || scanFeedback !== null
  }, [scanning, scanFeedback])

  useEffect(() => {
    if (!scanFeedback) return
    const timer = window.setTimeout(() => setScanFeedback(null), SCAN_FEEDBACK_MS)
    return () => window.clearTimeout(timer)
  }, [scanFeedback])

  const handleScan = useCallback(
    async (rawValue: string) => {
      if (busyRef.current) return
      const token = extractQrToken(rawValue)
      if (!token) return

      // Second guard, for the case the first can't cover: the ticket is still
      // in frame when the feedback clears and the camera reopens.
      const last = lastTokenRef.current
      if (last && last.token === token && Date.now() - last.at < SAME_TICKET_COOLDOWN_MS) return
      lastTokenRef.current = { token, at: Date.now() }

      setScanning(true)
      try {
        const result = await scanAttendanceApi(sessionId, token)
        setScanFeedback({ kind: "ok", text: `${result.student_name} — checked in` })
        invalidate()
      } catch (err) {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        // Already recorded isn't a failure — a student re-presenting their
        // ticket at a busy door is normal, and flashing red at the instructor
        // makes a working system look broken.
        const alreadyIn = typeof detail === "string" && detail.toLowerCase().includes("already recorded")
        setScanFeedback({
          kind: alreadyIn ? "info" : "error",
          text: alreadyIn ? "Already checked in" : detail ?? "Scan failed — try again",
        })
      } finally {
        setScanning(false)
      }
    },
    [sessionId],
  )

  const { videoRef, scannerMode, cameraError } = useQrScanner({
    enabled: scannerOpen,
    onDetect: handleScan,
    busyRef,
    readerElementId: "session-delivery-qr-reader",
  })

  const s = delivery.data
  const isCompleted = !!s?.completed_at
  const presentCount = s ? s.roster.filter((e) => e.att_status === "present").length : 0

  const filteredRoster = useMemo(
    () => (s ? (rosterSearch ? s.roster.filter((e) => e.student_name.toLowerCase().includes(rosterSearch.toLowerCase())) : s.roster) : []),
    [s, rosterSearch],
  )

  if (delivery.isLoading) return <Spinner />
  if (!s) return <EmptyState title="Session not found" hint="It may have been removed, or you're not assigned to it." />

  return (
    <div className="flex flex-col gap-4">
      <Link to="/instructors/my-sessions" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> My sessions
      </Link>

      <PageHeader
        title={s.title || s.program_name}
        subtitle={s.title ? `${s.program_name} · ${s.cohort_name}` : s.cohort_name}
      />

      <Card>
        <CardContent className="p-4 flex flex-col gap-2">
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Calendar size={14} />
            {new Date(s.meeting_date).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
            {s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
          </span>
          {s.location && (
            <span className="flex items-center gap-1.5 text-sm text-muted-foreground"><MapPin size={14} /> {s.location}</span>
          )}
          {s.material_url && (
            <a
              href={s.material_url} target="_blank" rel="noreferrer"
              className="flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80 transition-colors w-fit"
            >
              <BookOpen size={14} /> Session material <ExternalLink size={12} />
            </a>
          )}
          <div className="flex flex-wrap gap-2 mt-1">
            {s.started_at ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400">
                <CheckCircle2 size={13} /> Started {new Date(s.started_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
              </span>
            ) : (
              <Button size="sm" disabled={start.isPending} onClick={() => start.mutate()}>
                {start.isPending ? "Starting…" : "Start session"}
              </Button>
            )}
            {s.completed_at ? (
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-500/20">
                <CheckCircle2 size={13} /> Completed
              </span>
            ) : (
              <Button size="sm" variant="outline" disabled={done.isPending} onClick={() => done.mutate()}>
                {done.isPending ? "Saving…" : "Mark completed"}
              </Button>
            )}
            <Button size="sm" variant="outline" onClick={() => setScannerOpen((v) => !v)}>
              <QrCode size={14} className="mr-1.5" /> {scannerOpen ? "Close scanner" : "Scan QR"}
            </Button>
          </div>
          {doneError && (
            <p className="text-xs text-amber-700 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-xl px-3 py-2">
              {doneError}
            </p>
          )}
        </CardContent>
      </Card>

      {/* I2-2: renders nothing when no kits are assigned, which is most
          sessions — they must look exactly as they did before. */}
      <SessionKitsPanel sessionId={sessionId} isStarted={!!s.started_at} onChanged={invalidate} />

      {/* I2-7: non-kit equipment. Unlike the kits panel this shows even when
          nothing has been taken — taking something is the action offered. */}
      <SessionEquipmentPanel sessionId={sessionId} notes={s.notes} onChanged={invalidate} />

      {scannerOpen && (
        <Card>
          <CardContent className="p-3 flex flex-col gap-2">
            {cameraError ? (
              <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-red-400/50 bg-red-500/5 p-6 text-center">
                <Camera className="text-red-500" size={28} />
                <p className="text-sm font-medium text-foreground">{cameraError}</p>
              </div>
            ) : (
              <div className="relative aspect-square max-h-80 overflow-hidden rounded-xl border border-border bg-black mx-auto w-full max-w-xs">
                {scannerMode === "native" ? (
                  <video ref={videoRef} className="h-full w-full object-cover" playsInline muted autoPlay />
                ) : (
                  <div id="session-delivery-qr-reader" className="h-full w-full [&_video]:!h-full [&_video]:!w-full [&_video]:object-cover" />
                )}
                <div className="pointer-events-none absolute inset-6 rounded-2xl border-4 border-white/70" />
              </div>
            )}
            {scanFeedback && (
              <p className={cn(
                "text-center text-sm font-semibold",
                scanFeedback.kind === "ok" && "text-emerald-600 dark:text-emerald-400",
                scanFeedback.kind === "info" && "text-amber-600 dark:text-amber-400",
                scanFeedback.kind === "error" && "text-red-500",
              )}>
                {scanFeedback.text}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Student Roster ({presentCount} present / {s.roster.length} registered)
          </p>
          {s.roster.length > 0 && (
            <input
              value={rosterSearch} onChange={(e) => setRosterSearch(e.target.value)}
              placeholder="Search by name…"
              className="ml-auto h-8 w-44 px-2.5 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
            />
          )}
        </div>

        {isCompleted && (
          <div className="mb-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center gap-2">
            <span>🔒 Session completed — attendance is locked. Contact Operations to request changes.</span>
          </div>
        )}

        {s.roster.length === 0 ? (
          <EmptyState title="No students registered" hint="Registrations for this session will show up here." />
        ) : (
          <div className="flex flex-col gap-2">
            {filteredRoster.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">No students match "{rosterSearch}"</p>
            ) : (
              filteredRoster.map((entry) => (
                <RosterRow
                  key={entry.registration_id}
                  entry={entry}
                  isLocked={isCompleted}
                  pending={mark.isPending && mark.variables?.registrationId === entry.registration_id}
                  onMark={(status) => mark.mutate({ registrationId: entry.registration_id, status })}
                  onSelectStudent={() => setSelectedStudent(entry)}
                />
              ))
            )}
          </div>
        )}
      </div>

      <div>
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
          Reports{s.reports.length > 0 ? ` (${s.reports.length})` : ""}
        </p>
        <Card className="mb-2">
          <CardContent className="p-3 flex flex-col gap-2">
            <input
              ref={fileInputRef} type="file"
              onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadReport.mutate(file) }}
              disabled={uploadReport.isPending}
              className="text-xs text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-primary file:px-3 file:py-2 file:text-xs file:font-medium file:text-primary-foreground"
            />
            <input
              value={reportNotes} onChange={(e) => setReportNotes(e.target.value)}
              placeholder="Optional notes about the session…"
              className="h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            {uploadReport.isPending && <p className="text-xs text-muted-foreground">Uploading…</p>}
          </CardContent>
        </Card>
        {s.reports.length > 0 && (
          <div className="flex flex-col gap-1.5">
            {s.reports.map((r) => <ReportRow key={r.id} report={r} />)}
          </div>
        )}
      </div>

      {selectedStudent && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={() => setSelectedStudent(null)}>
          <div className="bg-card border border-border rounded-2xl p-5 max-w-md w-full flex flex-col gap-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <p className="text-base font-bold text-foreground">Student Info — {selectedStudent.student_name}</p>
              <button onClick={() => setSelectedStudent(null)} className="p-1 rounded-lg text-muted-foreground hover:bg-muted">
                <X size={16} />
              </button>
            </div>
            <div className="space-y-2 text-xs">
              <div className="p-3.5 bg-muted/30 border border-border rounded-xl space-y-2">
                <p><span className="font-semibold text-muted-foreground">Full Name:</span> <span className="text-foreground font-medium">{selectedStudent.student_name}</span></p>
                <p><span className="font-semibold text-muted-foreground">Phone:</span> <span className="text-foreground">{selectedStudent.student_phone ?? "Not provided"}</span></p>
                <p><span className="font-semibold text-muted-foreground">Email:</span> <span className="text-foreground">{selectedStudent.student_email ?? "Not provided"}</span></p>
                {selectedStudent.student_grade && <p><span className="font-semibold text-muted-foreground">Grade / Age:</span> <span className="text-foreground">{selectedStudent.student_grade}</span></p>}
                {selectedStudent.student_organization_name && <p><span className="font-semibold text-muted-foreground">School / Org:</span> <span className="text-foreground">{selectedStudent.student_organization_name}</span></p>}
                {selectedStudent.student_date_of_birth && <p><span className="font-semibold text-muted-foreground">DOB:</span> <span className="text-foreground">{selectedStudent.student_date_of_birth}</span></p>}
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-border">
              <Button variant="outline" onClick={() => setSelectedStudent(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}

function ReportRow({ report }: { report: SessionReport }) {
  return (
    <a
      href={report.file_url} target="_blank" rel="noreferrer"
      className="flex items-center gap-2.5 px-3 py-2 bg-background border border-border rounded-xl hover:border-primary/50 transition-colors"
    >
      <FileText size={16} className="text-muted-foreground shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground truncate">{report.filename}</p>
        {report.notes && <p className="text-xs text-muted-foreground truncate">{report.notes}</p>}
      </div>
      <Download size={13} className="text-muted-foreground shrink-0" />
    </a>
  )
}

function RosterRow({ entry, isLocked, pending, onMark, onSelectStudent }: {
  entry: RosterEntry; isLocked?: boolean; pending: boolean; onMark: (status: AttendanceStatus) => void; onSelectStudent: () => void
}) {
  return (
    <Card>
      <CardContent className="p-3 flex flex-col gap-2">
        <div className="min-w-0 flex items-center justify-between">
          <button
            type="button"
            onClick={onSelectStudent}
            className="text-left group/name hover:underline"
          >
            <p className="text-sm font-semibold text-foreground group-hover/name:text-primary transition-colors">{entry.student_name}</p>
            {entry.student_phone && <p className="text-xs text-muted-foreground">{entry.student_phone}</p>}
          </button>
          {entry.att_method === "qr" && (
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"><QrCode size={11} /> via QR scan</span>
          )}
        </div>
        <div className="grid grid-cols-4 gap-1.5">
          {STATUS_OPTIONS.map((opt) => {
            const active = entry.att_status === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                disabled={pending || isLocked}
                onClick={() => onMark(opt.value)}
                className={cn(
                  "min-h-[44px] rounded-xl border text-xs font-semibold transition-colors disabled:opacity-50",
                  active ? opt.activeClass : "bg-background border-border text-foreground hover:border-primary/50",
                )}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
