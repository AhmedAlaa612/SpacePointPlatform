import { useEffect, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FileText, Download, UserCheck, Users, Save, AlertCircle, CheckCircle2 } from "lucide-react"
import {
  getStudentExcuseLetterStatusApi,
  updateTeamStudentIdsApi,
  downloadMyExcuseLetterApi,
  type StudentExcuseLetterStatus,
} from "@/api/competitions"
import { updateMeApi } from "@/api/auth"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { useAuth } from "@/context/AuthContext"

interface StudentInvitationLetterModalProps {
  cohortId: string
  open: boolean
  onClose: () => void
}

export function StudentInvitationLetterModal({
  cohortId,
  open,
  onClose,
}: StudentInvitationLetterModalProps) {
  const toast = useToast()
  const queryClient = useQueryClient()
  const { currentUser, setCurrentUser } = useAuth()

  const { data: status, isLoading } = useQuery<StudentExcuseLetterStatus>({
    queryKey: ["student-excuse-letter-status", cohortId],
    queryFn: () => getStudentExcuseLetterStatusApi(cohortId),
    enabled: open && !!cohortId,
  })

  const [myStudentId, setMyStudentId] = useState("")
  const [teammateIds, setTeammateIds] = useState<Record<string, string>>({})
  const [downloadingMode, setDownloadingMode] = useState<"individual" | "team" | null>(null)
  const [isSavingIds, setIsSavingIds] = useState(false)

  useEffect(() => {
    if (status) {
      setMyStudentId(status.my_student_id || currentUser?.student_id || "")
      const initialMap: Record<string, string> = {}
      for (const m of status.members) {
        if (!m.is_me) {
          initialMap[m.user_id] = m.student_id || ""
        }
      }
      setTeammateIds(initialMap)
    }
  }, [status, currentUser])

  const saveIdsMutation = useMutation({
    mutationFn: async () => {
      setIsSavingIds(true)
      try {
        // 1. Update personal student_id in profile
        if (myStudentId.trim() !== (currentUser?.student_id || "")) {
          const updatedUser = await updateMeApi({ student_id: myStudentId.trim() })
          setCurrentUser(updatedUser)
        }

        // 2. Update team members' student IDs
        const payloadMembers = [
          ...(status?.members
            .filter((m) => m.is_me)
            .map((m) => ({ user_id: m.user_id, student_id: myStudentId.trim() })) || []),
          ...Object.entries(teammateIds).map(([user_id, student_id]) => ({
            user_id,
            student_id: student_id.trim(),
          })),
        ]

        if (payloadMembers.length > 0) {
          await updateTeamStudentIdsApi(cohortId, payloadMembers)
        }

        queryClient.invalidateQueries({ queryKey: ["student-excuse-letter-status", cohortId] })
        toast.success("University IDs saved successfully")
      } finally {
        setIsSavingIds(false)
      }
    },
    onError: () => {
      toast.error("Failed to save University IDs")
    },
  })

  const handleDownload = async (mode: "individual" | "team") => {
    if (!myStudentId.trim()) {
      toast.error("Please enter your University ID / Student ID before downloading")
      return
    }

    // Auto-save any modified IDs before downloading
    try {
      await saveIdsMutation.mutateAsync()
    } catch {
      // Continue download even if background save had a hiccup
    }

    setDownloadingMode(mode)
    try {
      const blob = await downloadMyExcuseLetterApi(cohortId, mode)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      const prefix = mode === "individual" ? "My_Individual" : "Team"
      const cleanTeam = (status?.team_name || "Team").replace(/[^a-zA-Z0-9_-]/g, "_")
      a.download = `${cleanTeam}_${prefix}_Excuse_Letter.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      toast.success(`${mode === "individual" ? "Individual" : "Team"} letter downloaded successfully`)
    } catch {
      toast.error("Failed to download invitation letter")
    } finally {
      setDownloadingMode(null)
    }
  }

  if (!open) return null

  const isMissingMyId = !myStudentId.trim()
  const otherMembers = (status?.members || []).filter((m) => !m.is_me)
  const missingTeammateCount = otherMembers.filter((m) => !teammateIds[m.user_id]?.trim()).length

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <FileText className="text-primary" size={20} />
            <span>Official University Invitation & Excuse Letter</span>
          </DialogTitle>
          <p className="text-xs text-muted-foreground">
            {status?.cohort_name ? `${status.cohort_name} • ` : ""}
            {status?.team_name ? `Team: ${status.team_name}` : "Download official letter for academic excuse"}
          </p>
        </DialogHeader>

        {isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground">Loading letter status…</div>
        ) : (
          <div className="space-y-4 pt-2">
            {/* Download Option Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="p-3.5 bg-card border border-border hover:border-primary/50 rounded-xl transition flex flex-col justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <UserCheck size={15} className="text-primary" />
                    <span>Individual Invitation</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Addressed specifically to you with your personal University ID.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDownload("individual")}
                  disabled={downloadingMode !== null || isSavingIds}
                  className="w-full inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition cursor-pointer disabled:opacity-50"
                >
                  <Download size={13} />
                  <span>{downloadingMode === "individual" ? "Generating…" : "Download My Letter"}</span>
                </button>
              </div>

              <div className="p-3.5 bg-card border border-border hover:border-primary/50 rounded-xl transition flex flex-col justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <Users size={15} className="text-primary" />
                    <span>Team Invitation</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground leading-relaxed">
                    Includes all team members and their University IDs in a full roster table.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDownload("team")}
                  disabled={downloadingMode !== null || isSavingIds}
                  className="w-full inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-lg border border-border bg-card hover:bg-muted text-foreground text-xs font-semibold transition cursor-pointer disabled:opacity-50"
                >
                  <Download size={13} />
                  <span>{downloadingMode === "team" ? "Generating…" : "Download Team Letter"}</span>
                </button>
              </div>
            </div>

            {/* University ID Prompt & Editor */}
            <div className="p-3.5 bg-muted/30 border border-border rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                  {isMissingMyId ? (
                    <AlertCircle size={15} className="text-amber-500" />
                  ) : (
                    <CheckCircle2 size={15} className="text-emerald-500" />
                  )}
                  <span>University / Student IDs</span>
                </div>
                <button
                  type="button"
                  onClick={() => saveIdsMutation.mutate()}
                  disabled={isSavingIds}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-medium bg-card hover:bg-muted border border-border text-foreground transition cursor-pointer disabled:opacity-50"
                >
                  <Save size={12} />
                  <span>{isSavingIds ? "Saving…" : "Save IDs"}</span>
                </button>
              </div>

              {isMissingMyId && (
                <p className="text-[11px] text-amber-600 dark:text-amber-400 font-medium">
                  Please add your University ID below. It will appear on your official excuse letter and sync to your profile.
                </p>
              )}

              {/* My ID Input */}
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-muted-foreground block">
                  Your University ID <span className="text-primary font-semibold">(You)</span>
                </label>
                <input
                  type="text"
                  value={myStudentId}
                  onChange={(e) => setMyStudentId(e.target.value)}
                  placeholder="e.g. H00412345 or Student ID Number"
                  className={`w-full h-8 px-2.5 rounded-lg border text-xs bg-card text-foreground focus:outline-none focus:border-primary ${
                    isMissingMyId ? "border-amber-500/60" : "border-border"
                  }`}
                />
              </div>

              {/* Teammates IDs Section */}
              {otherMembers.length > 0 && (
                <div className="pt-2 border-t border-border/60 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-medium text-muted-foreground">
                      Teammates' IDs ({otherMembers.length} members)
                    </span>
                    {missingTeammateCount > 0 && (
                      <span className="text-[10px] text-muted-foreground">
                        {missingTeammateCount} missing
                      </span>
                    )}
                  </div>
                  <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                    {otherMembers.map((m) => (
                      <div key={m.user_id} className="flex items-center gap-2">
                        <span className="text-xs text-foreground font-medium truncate flex-1" title={m.full_name}>
                          {m.full_name}
                        </span>
                        <input
                          type="text"
                          value={teammateIds[m.user_id] ?? ""}
                          onChange={(e) =>
                            setTeammateIds((prev) => ({
                              ...prev,
                              [m.user_id]: e.target.value,
                            }))
                          }
                          placeholder="Student ID"
                          className="w-36 h-7 px-2 rounded-md border border-border bg-card text-foreground text-xs focus:outline-none focus:border-primary"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex justify-end pt-2 border-t border-border">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-1.5 rounded-lg border border-border text-xs font-medium text-muted-foreground hover:text-foreground hover:bg-muted transition cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
