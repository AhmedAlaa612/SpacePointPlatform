import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "@tanstack/react-router"
import {
  ArrowLeft, BookOpen, Calendar, Camera, CheckCircle2, ChevronDown,
  Download, ExternalLink, FileText, ImageIcon, Link2, Lock, MapPin, Play, QrCode, Search, Send, UserX, X,
} from "lucide-react"
import {
  getSessionDeliveryApi, markAttendanceApi, markSessionDoneApi, scanAttendanceApi, startSessionApi,
  uploadSessionReportApi,
} from "@/api/sessions/delivery"
import { checkInApi, getDayApi, setChecklistProgressApi, submitDayApi } from "@/api/sessions/day"
import type { AttendanceStatus, ChecklistAttachment, ChecklistLine, RosterEntry, SessionReport } from "@/types/sessions"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"
import { useToast } from "@/components/ui/toast"
import { extractQrToken, useQrScanner } from "@/hooks/useQrScanner"
import { UserProfileModal } from "@/components/UserProfileModal"
import { cn, ensureAbsoluteUrl, getErrorMessage } from "@/lib/utils"

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
/** How long the "start the session first" hint stays on screen after a
 *  disabled attendance control is tapped. */
const LOCK_HINT_MS = 3000

import { SessionKitsPanel } from "@/pages/instructors/components/SessionKitsPanel"
import { SessionEquipmentPanel } from "@/pages/instructors/components/SessionEquipmentPanel"
import { SessionMaterialsPanel } from "@/pages/instructors/components/SessionMaterialsPanel"
import { SessionGamesPanel } from "@/pages/instructors/components/SessionGamesPanel"
import { ProgressPanel } from "@/pages/lms-authoring/components/LmsProgressAndMissions"

export default function SessionDetail() {
  const { sessionId } = useParams({ strict: false }) as { sessionId: string }
  const qc = useQueryClient()
  const [scannerOpen, setScannerOpen] = useState(false)
  const [attendanceOpen, setAttendanceOpen] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [scanFeedback, setScanFeedback] = useState<{ kind: "ok" | "info" | "error"; text: string } | null>(null)
  const [rosterSearch, setRosterSearch] = useState("")
  const [reportNotes, setReportNotes] = useState("")
  const [selectedStudent, setSelectedStudent] = useState<RosterEntry | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [doneError, setDoneError] = useState<string | null>(null)
  const [dayNotes, setDayNotes] = useState("")
  const [dayError, setDayError] = useState("")
  const [checkInError, setCheckInError] = useState("")
  const [askingAbsence, setAskingAbsence] = useState(false)
  const [absenceReason, setAbsenceReason] = useState("")
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
  const day = useQuery({
    queryKey: ["instructor-day", sessionId],
    queryFn: () => getDayApi(sessionId),
  })

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["session-delivery", sessionId] })
    qc.invalidateQueries({ queryKey: ["instructor-day", sessionId] })
  }

  const start = useMutation({
    mutationFn: () => startSessionApi(sessionId),
    onSuccess: invalidate,
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
  const checkIn = useMutation({
    mutationFn: (v: { att: AttendanceStatus; reason?: string }) => checkInApi(sessionId, v.att, v.reason),
    onSuccess: () => { setCheckInError(""); setAskingAbsence(false); invalidate() },
    onError: (e) => setCheckInError(getErrorMessage(e, "Couldn't record that")),
  })
  // Complete session = the one action the instructor sees. Under the hood it
  // closes both concerns that used to be two separate buttons: the session
  // itself (mark_done — idempotent, no real precondition) and this
  // instructor's own day (submit_day — gated on the checklist, which is why
  // the button stays disabled until `day.data.can_submit`).
  const complete = useMutation({
    mutationFn: async () => {
      await markSessionDoneApi(sessionId)
      return submitDayApi(sessionId, dayNotes || undefined)
    },
    onSuccess: () => { setDoneError(""); setDayError(""); invalidate() },
    onError: (e: unknown) => {
      const detail = getErrorMessage(e, "Couldn't complete the session")
      setDoneError(detail)
      setDayError(detail)
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

  const [lockHint, setLockHint] = useState<string | null>(null)
  useEffect(() => {
    if (!lockHint) return
    const timer = window.setTimeout(() => setLockHint(null), LOCK_HINT_MS)
    return () => window.clearTimeout(timer)
  }, [lockHint])

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
  const d = day.data
  const isCompleted = !!s?.completed_at
  const isStarted = !!s?.started_at
  const presentCount = s ? s.roster.filter((e) => e.att_status === "present").length : 0

  const filteredRoster = useMemo(
    () => (s ? (rosterSearch ? s.roster.filter((e) => e.student_name.toLowerCase().includes(rosterSearch.toLowerCase())) : s.roster) : []),
    [s, rosterSearch],
  )

  if (delivery.isLoading || day.isLoading) return <Spinner />
  if (!s) return <EmptyState title="Session not found" hint="It may have been removed, or you're not assigned to it." />

  const statusPill = isCompleted
    ? { text: "Completed", cls: "bg-foreground/10 text-foreground" }
    : isStarted
      ? { text: `In progress · ${new Date(s.started_at!).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`, cls: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400" }
      : { text: "Not started", cls: "bg-muted text-muted-foreground" }

  return (
    <div className="flex flex-col gap-4 pb-24">
      <Link to="/instructors/my-sessions" className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors">
        <ArrowLeft size={14} /> My sessions
      </Link>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <PageHeader
          title={s.title || s.program_name}
          subtitle={s.title ? `${s.program_name} · ${s.cohort_name}` : s.cohort_name}
        />
        <div className="flex items-center gap-3 flex-wrap shrink-0">
          <span className={cn("text-xs font-semibold px-2.5 py-1 rounded-full shrink-0", statusPill.cls)}>{statusPill.text}</span>
          {!isStarted && !isCompleted && (
            <Button
              size="default"
              disabled={start.isPending}
              onClick={() => start.mutate()}
              className="h-11 px-6 text-sm font-bold rounded-xl shadow-lg bg-primary text-black hover:opacity-90 transition-all flex items-center gap-2"
            >
              <Play size={16} fill="currentColor" />
              {start.isPending ? "Starting…" : "Start session"}
            </Button>
          )}
        </div>
      </div>

      {/* ── Combined Session Info & Team Header Card ──────────────────── */}
      <Card>
        <CardContent className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
          {/* Left side: Date, time, location */}
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground flex-wrap">
              <span className="flex items-center gap-1.5">
                <Calendar size={15} className="text-primary shrink-0" />
                {new Date(s.meeting_date).toLocaleDateString(undefined, { weekday: "short", year: "numeric", month: "short", day: "numeric" })}
                {s.starts_at ? ` · ${s.starts_at.slice(0, 5)}` : ""}
              </span>
            </div>
            {s.location && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground flex-wrap mt-0.5">
                <MapPin size={13} className="shrink-0" />
                <span>{s.location}{s.location_address ? ` — ${s.location_address}` : ""}</span>
                {s.location_maps_url && (
                  <a
                    href={s.location_maps_url} target="_blank" rel="noreferrer"
                    className="inline-flex items-center gap-0.5 text-xs font-medium text-primary hover:underline ml-1"
                  >
                    Maps <ExternalLink size={11} />
                  </a>
                )}
              </div>
            )}
          </div>

          {/* Right side: Team Members & Check-in */}
          {s.teammates.length > 0 && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 flex-wrap border-t md:border-t-0 md:border-l border-border pt-3 md:pt-0 md:pl-4 w-full md:w-auto">
              <span className="text-xs font-medium text-muted-foreground mr-1 hidden sm:inline">Team:</span>
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 flex-wrap w-full sm:w-auto">
                {s.teammates.map((t) => (
                  <div
                    key={t.user_id}
                    className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 bg-muted/40 p-2.5 sm:px-2.5 sm:py-1.5 rounded-xl border border-border/60 w-full sm:w-auto"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <div className={cn(
                        "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0",
                        t.att_status === "present" ? "bg-primary text-primary-foreground" : "bg-muted text-foreground",
                      )}>
                        {t.full_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase()}
                      </div>
                      <div className="flex items-center gap-1.5 text-xs min-w-0 flex-wrap">
                        <span className="font-semibold text-foreground truncate">
                          {t.is_me ? "You" : t.full_name}
                        </span>
                        <span className="text-muted-foreground text-[11px] shrink-0">({t.role_name})</span>
                      </div>
                    </div>
                    {t.att_status === "present" ? (
                      <span className="text-[11px] font-bold text-emerald-500 flex items-center gap-1 shrink-0 ml-auto sm:ml-1">
                        <CheckCircle2 size={13} /> Checked in
                      </span>
                    ) : t.att_status === "absent" ? (
                      <span className="text-[11px] font-bold text-amber-500 shrink-0 ml-auto sm:ml-1">Absent</span>
                    ) : t.is_me ? (
                      <div className="grid grid-cols-2 gap-2 w-full sm:w-auto sm:flex sm:items-center sm:gap-1.5 shrink-0 pt-1 sm:pt-0 sm:ml-1">
                        <Button
                          size="sm"
                          disabled={checkIn.isPending}
                          onClick={() => checkIn.mutate({ att: "present" })}
                          className="h-8 sm:h-7 px-3 text-xs font-bold rounded-lg gap-1 w-full sm:w-auto"
                        >
                          <CheckCircle2 size={13} /> Check in
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={checkIn.isPending}
                          onClick={() => setAskingAbsence((v) => !v)}
                          className="h-8 sm:h-7 px-3 text-xs font-bold rounded-lg gap-1 w-full sm:w-auto"
                        >
                          <UserX size={13} /> Can't attend
                        </Button>
                      </div>
                    ) : (
                      <span className="text-[11px] font-medium text-amber-500 shrink-0 ml-auto sm:ml-1">Not checked in</span>
                    )}
                  </div>
                ))}
              </div>
              {askingAbsence && (
                <div className="flex flex-col sm:flex-row gap-2 w-full">
                  <input
                    className="input flex-1 h-9 text-sm"
                    placeholder="Reason (exam, medical appointment…)"
                    value={absenceReason}
                    onChange={(e) => setAbsenceReason(e.target.value)}
                  />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={checkIn.isPending}
                    onClick={() => checkIn.mutate({ att: "absent", reason: absenceReason || undefined })}
                  >
                    Confirm absence
                  </Button>
                </div>
              )}
              {checkInError && <p className="text-xs text-red-600 dark:text-red-400 w-full">{checkInError}</p>}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px] xl:grid-cols-[1fr_400px] gap-5 items-start">
        {/* ── main column — one continuous scroll ─────────────────────── */}
        <div className="flex flex-col gap-4 min-w-0">
          {/* 1. Attendance (collapsible) */}
          <Card>
            <CardContent className="p-4 flex flex-col gap-3">
              <div className="flex items-center justify-between gap-3 flex-wrap">
                <button
                  type="button"
                  onClick={() => setAttendanceOpen((v) => !v)}
                  className="flex items-center gap-2 text-left group select-none"
                >
                  <ChevronDown className={cn("size-4 text-muted-foreground transition-transform duration-200 group-hover:text-foreground", !attendanceOpen && "-rotate-90")} />
                  <p className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                    {isStarted ? `Attendance — ${presentCount} present / ${s.roster.length} registered` : `Students expected (${s.roster.length})`}
                  </p>
                </button>
                {isStarted && attendanceOpen && (
                  <Button
                    variant="outline"
                    onClick={() => setScannerOpen((v) => !v)}
                    className="h-16 w-16 shrink-0 flex-col gap-1 px-1 text-[11px] leading-tight whitespace-normal"
                  >
                    <QrCode size={22} /> {scannerOpen ? "Close" : "Scan QR"}
                  </Button>
                )}
              </div>

              {attendanceOpen && (
                <>
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

                  {isCompleted && (
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-xs text-amber-600 dark:text-amber-400 font-medium flex items-center gap-2">
                      <span>Session completed — attendance is locked. Contact Operations to request changes.</span>
                    </div>
                  )}
                  {lockHint && (
                    <p className="text-xs text-amber-700 dark:text-amber-400">{lockHint}</p>
                  )}

                  {s.roster.length > 0 && (
                    <div className="relative w-full sm:w-64 self-end">
                      <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
                      <input
                        value={rosterSearch}
                        onChange={(e) => setRosterSearch(e.target.value)}
                        placeholder="Search by student name…"
                        className="h-8 w-full pl-8 pr-3 border border-border bg-background text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors"
                      />
                    </div>
                  )}

                  {s.roster.length === 0 ? (
                    <EmptyState title="No students registered" hint="Registrations for this session will show up here." />
                  ) : (
                    <div className="max-h-80 overflow-y-auto pr-1 flex flex-col gap-1.5 border border-border/50 rounded-xl p-1.5 bg-muted/10">
                      {filteredRoster.length === 0 ? (
                        <p className="text-xs text-muted-foreground text-center py-6">No students match "{rosterSearch}"</p>
                      ) : (
                        filteredRoster.map((entry) => (
                          <RosterRow
                            key={entry.registration_id}
                            entry={entry}
                            locked={isCompleted ? "completed" : !isStarted ? "not_started" : undefined}
                            pending={mark.isPending && mark.variables?.registrationId === entry.registration_id}
                            onMark={(status) => {
                              if (!isStarted) { setLockHint("Start the session first."); return }
                              mark.mutate({ registrationId: entry.registration_id, status })
                            }}
                            onSelectStudent={() => entry.student_user_id ? setProfileUserId(entry.student_user_id) : setSelectedStudent(entry)}
                          />
                        ))
                      )}
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>

          {/* 2. Materials (collapsible) */}
          {(s.material_url) && (
            <Card>
              <CardContent className="p-4 flex flex-col gap-2">
                <p className="text-sm font-semibold text-foreground">Before you start</p>
                <a
                  href={ensureAbsoluteUrl(s.material_url)} target="_blank" rel="noreferrer"
                  className="flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80 transition-colors w-fit"
                >
                  <BookOpen size={14} /> Session material <ExternalLink size={12} />
                </a>
              </CardContent>
            </Card>
          )}
          <SessionMaterialsPanel sessionId={sessionId} />

          {/* 3. Live Games */}
          <SessionGamesPanel sessionId={sessionId} />

          {/* 4. Student LMS progress */}
          <Card>
            <CardContent className="p-4 flex flex-col gap-3">
              <p className="text-sm font-semibold text-foreground">Student LMS progress</p>
              <ProgressPanel cohortId={s.cohort_id} scopeLabel={s.cohort_name} />
            </CardContent>
          </Card>

          {/* 5. Uploads */}
          {isStarted && (
            <>
              <SessionKitsPanel sessionId={sessionId} stage="post" locked={isCompleted} onChanged={invalidate} />
              <Card>
                <CardContent className="p-4 flex flex-col gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">
                      File uploads{s.reports.length > 0 ? ` (${s.reports.length})` : ""}
                    </p>
                    <p className="text-xs text-muted-foreground">Submit photos of the day and any relevant documents.</p>
                  </div>
                  <Card>
                    <CardContent className="p-3 flex flex-col gap-2">
                      <input
                        ref={fileInputRef} type="file"
                        onChange={(e) => { const file = e.target.files?.[0]; if (file) uploadReport.mutate(file) }}
                        disabled={uploadReport.isPending}
                        className="text-xs text-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-primary file:px-3 file:py-2 file:text-xs file:font-medium file:text-primary-foreground"
                      />
                      <input
                        value={reportNotes} onChange={(e) => setReportNotes(e.target.value)}
                        placeholder="Notes about the file…"
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
                  <textarea
                    className="input min-h-[4rem] resize-y text-sm"
                    placeholder="How did the session go? Anything ops should know for tomorrow…"
                    value={dayNotes || d?.instructor_notes || ""}
                    onChange={(e) => setDayNotes(e.target.value)}
                    disabled={d?.status === "approved" || d?.status === "submitted"}
                  />
                </CardContent>
              </Card>
            </>
          )}

          {/* 6. Extra Equipment & Notes */}
          <SessionKitsPanel sessionId={sessionId} stage="pre" onChanged={invalidate} />
          <SessionEquipmentPanel sessionId={sessionId} cohortId={s.cohort_id} notes={s.notes} onChanged={invalidate} />
        </div>

        {/* ── sticky right rail — the checklist, visible from the start ─ */}
        <div className="lg:sticky lg:top-4 flex flex-col gap-3">
          <Card>
            <CardContent className="p-4">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                <p className="text-sm font-semibold text-foreground">Daily checklist</p>
                {d && d.checklist.length > 0 && (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {d.checklist.filter((l) => l.is_done).length}/{d.checklist.length}
                  </span>
                )}
              </div>
              {!d || d.checklist.length === 0 ? (
                <p className="text-xs text-muted-foreground">No checklist configured for this session.</p>
              ) : (
                <>
                  <p className="text-xs text-muted-foreground mb-2">
                    Visible now so you know what's ahead — check items off as you go, not all at the end.
                  </p>
                  <div className="divide-y divide-border/60">
                    {d.checklist.map((line) => (
                      <ChecklistRow
                        key={line.item_id} line={line} sessionId={sessionId} cohortId={s.cohort_id}
                        locked={d.status === "approved" || d.status === "submitted"}
                        onChanged={invalidate}
                      />
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* ── sticky finish bar — exactly one completing action ──────────── */}
      {d && d.status !== "approved" && d.status !== "submitted" && (
        <div className="fixed left-0 right-0 bottom-0 z-30 border-t border-border bg-card/95 backdrop-blur-xl">
          <div className="max-w-5xl mx-auto px-4 py-3 flex flex-col items-center gap-1.5">
            {!d.can_submit && d.missing.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {d.missing.length === 1 ? d.missing[0] : `${d.missing.length} things still need attention.`}
              </p>
            )}
            {(doneError || dayError) && <p className="text-xs text-red-600 dark:text-red-400">{doneError || dayError}</p>}
            <Button
              size="lg"
              className="rounded-md px-8"
              disabled={!d.can_submit || complete.isPending}
              onClick={() => { setDoneError(null); setDayError(""); complete.mutate() }}
            >
              <Send size={14} className="mr-1.5" />
              {complete.isPending ? "Completing…" : "Complete session"}
            </Button>
          </div>
        </div>
      )}
      {d && (d.status === "approved" || d.status === "submitted") && (
        <div className="fixed left-0 right-0 bottom-0 z-30 border-t border-border bg-card/95 backdrop-blur-xl">
          <div className="max-w-5xl mx-auto px-4 py-3 flex items-center justify-center">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400 border border-emerald-500/20">
              <CheckCircle2 size={13} /> {d.status === "approved" ? "Completed" : "Submitted — awaiting review"}
            </span>
          </div>
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}

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

function ChecklistRow({
  line, sessionId, cohortId, locked, onChanged,
}: {
  line: ChecklistLine; sessionId: string; cohortId: string; locked: boolean
  onChanged: () => void
}) {
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")

  const tick = useMutation({
    mutationFn: (isDone: boolean) => setChecklistProgressApi(sessionId, line.item_id, { is_done: isDone }),
    onSuccess: onChanged,
    onError: (e) => setError(getErrorMessage(e, "Couldn't save that")),
  })

  const attachments: ChecklistAttachment[] =
    line.attachments && line.attachments.length > 0
      ? line.attachments
      : line.material_url || line.link_url
      ? [
          {
            id: "legacy",
            type: (line.material_url ? "material" : "link") as "material" | "link",
            title: line.material_title || (line.material_url ? "Document" : "Link"),
            url: line.material_url || line.link_url,
            is_file: Boolean(line.material_url),
            is_published: true,
            has_access: true,
            access_denied_message: null,
          },
        ]
      : []

  const handleAttachmentClick = (att: ChecklistAttachment, e: React.MouseEvent) => {
    if (att.has_access === false) {
      e.preventDefault()
      toast.error(
        att.access_denied_message ||
          "You don't have access to this document, please contact the operations team."
      )
    }
  }

  /** Upload through the ordinary session-report path, then point the checklist
   *  row at the row it created. Two steps on purpose — one upload mechanism
   *  for the whole domain. */
  const attach = async (file: File) => {
    setBusy(true)
    setError("")
    try {
      const report = await uploadSessionReportApi(cohortId, { file, sessionId, notes: line.title })
      await setChecklistProgressApi(sessionId, line.item_id, {
        proof_report_id: report.id, is_done: true,
      })
      onChanged()
    } catch (e) {
      setError(getErrorMessage(e, "Couldn't upload that photo"))
    } finally {
      setBusy(false)
    }
  }

  const needsPhoto = line.requires_proof && !line.proof_url

  return (
    <div className="flex items-start gap-2 py-1.5">
      <input
        type="checkbox"
        checked={line.is_done}
        disabled={locked || tick.isPending}
        onChange={(e) => tick.mutate(e.target.checked)}
        className="mt-0.5 shrink-0 rounded text-primary focus:ring-primary border-border bg-background"
      />
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">
          {line.title}
          {!line.is_required && <span className="text-xs text-muted-foreground"> · optional</span>}
        </p>
        {line.description && (
          <p className="text-xs text-muted-foreground">{line.description}</p>
        )}
        {attachments.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap mt-1.5">
            {attachments.map((att, attIdx) => {
              const isRestricted = att.has_access === false
              return (
                <a
                  key={att.id || attIdx}
                  href={att.url ? ensureAbsoluteUrl(att.url) : "#"}
                  target={att.url ? "_blank" : undefined}
                  rel="noreferrer"
                  onClick={(e) => handleAttachmentClick(att, e)}
                  className={cn(
                    "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium border transition-colors cursor-pointer max-w-full",
                    isRestricted
                      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 hover:bg-amber-500/15"
                      : att.is_file
                      ? "bg-primary/10 text-primary hover:bg-primary/15 border-primary/20"
                      : "bg-muted text-foreground hover:bg-muted/80 border-border"
                  )}
                  title={isRestricted ? att.access_denied_message || "Restricted document" : undefined}
                >
                  {isRestricted ? (
                    <Lock size={11} className="shrink-0 text-amber-500" />
                  ) : att.is_file ? (
                    <FileText size={11} className="shrink-0 text-primary" />
                  ) : (
                    <Link2 size={11} className="shrink-0 text-muted-foreground" />
                  )}
                  <span className="truncate max-w-[160px] sm:max-w-xs">{att.title || "Reference"}</span>
                </a>
              )
            })}
          </div>
        )}
        {error && <p className="text-xs text-red-600 dark:text-red-400">{error}</p>}
      </div>
      {line.requires_proof && (
        <div className="shrink-0 flex items-center gap-2">
          {line.proof_url ? (
            <a
              href={line.proof_url} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
            >
              <ImageIcon size={12} /> photo
            </a>
          ) : (
            <span className="text-[10px] font-semibold text-amber-600 dark:text-amber-400">photo needed</span>
          )}
          {!locked && (
            <>
              <input
                ref={fileRef} type="file" accept="image/*" className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void attach(f) }}
              />
              <button
                type="button" disabled={busy}
                onClick={() => fileRef.current?.click()}
                className={`p-1.5 rounded-lg border transition-colors disabled:opacity-50 ${
                  needsPhoto
                    ? "border-amber-500/40 text-amber-600 dark:text-amber-400 hover:bg-amber-500/10"
                    : "border-border text-muted-foreground hover:bg-muted"
                }`}
                aria-label={`Attach a photo for ${line.title}`}
              >
                <Camera size={13} />
              </button>
            </>
          )}
        </div>
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

function RosterRow({ entry, locked, pending, onMark, onSelectStudent }: {
  entry: RosterEntry
  /** "not_started" — soft gate, still clickable to surface a hint.
   *  "completed" — hard lock, same as before. undefined — fully enabled. */
  locked?: "not_started" | "completed"
  pending: boolean
  onMark: (status: AttendanceStatus) => void
  onSelectStudent: () => void
}) {
  return (
    <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-lg border border-border/70 bg-card hover:bg-muted/40 transition-colors shrink-0">
      <div className="min-w-0 flex-1 flex items-center gap-2 flex-wrap sm:flex-nowrap">
        <button
          type="button"
          onClick={onSelectStudent}
          className="text-left group/name hover:underline min-w-0"
        >
          <span className="text-xs font-semibold text-foreground group-hover/name:text-primary transition-colors truncate">
            {entry.student_name}
          </span>
        </button>
        {entry.student_phone && (
          <span className="text-[11px] text-muted-foreground truncate hidden sm:inline">
            · {entry.student_phone}
          </span>
        )}
        {entry.att_method === "qr" && (
          <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground shrink-0 bg-muted px-1.5 py-0.5 rounded">
            <QrCode size={10} /> QR
          </span>
        )}
      </div>

      {locked === "not_started" ? (
        <span className="text-[11px] text-muted-foreground shrink-0 font-medium bg-muted/50 px-2.5 py-1 rounded-md">
          Attendance opens once session starts
        </span>
      ) : (
        <div className="flex items-center gap-1 shrink-0">
          {STATUS_OPTIONS.map((opt) => {
            const active = entry.att_status === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                disabled={pending || locked === "completed"}
                onClick={() => onMark(opt.value)}
                className={cn(
                  "px-2.5 py-1 rounded-md text-[11px] font-semibold transition-colors disabled:opacity-50 border",
                  active ? opt.activeClass : "bg-background border-border text-muted-foreground hover:border-primary/50 hover:text-foreground",
                )}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
