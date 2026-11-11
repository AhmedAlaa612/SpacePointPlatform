import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Check, GraduationCap, Upload } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { tokens } from "@/api/client"
import { applyAsStudentApi } from "@/api/instructors/applicant"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

const DEGREES = ["Currently Pursuing Bachelors Degree", "Bachelors", "Masters", "PhD", "Other"]
const BACKGROUNDS = ["Engineering", "Science", "Education", "Other"]

interface ApplyAsInstructorModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function ApplyAsInstructorModal({ open, onOpenChange }: ApplyAsInstructorModalProps) {
  const { currentUser, setCurrentUser, setActiveRole } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const [university, setUniversity] = useState(currentUser?.organization_name || "")
  const [highestDegree, setHighestDegree] = useState(DEGREES[0])
  const [highestDegreeOther, setHighestDegreeOther] = useState("")
  const [backgroundAreas, setBackgroundAreas] = useState<string[]>(["Engineering"])
  const [backgroundOther, setBackgroundOther] = useState("")
  const [hasTransportation, setHasTransportation] = useState<boolean>(false)
  const [inviteCode, setInviteCode] = useState("")
  const [cvFile, setCvFile] = useState<File | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggleBackground = (bg: string) => {
    setBackgroundAreas((prev) =>
      prev.includes(bg) ? prev.filter((b) => b !== bg) : [...prev, bg]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!cvFile) {
      setError("Please upload your CV / resume (PDF format).")
      return
    }
    if (backgroundAreas.length === 0) {
      setError("Please select at least one background discipline.")
      return
    }

    setLoading(true)
    setError(null)

    try {
      const payload = {
        university: university.trim() || undefined,
        highest_degree: highestDegree,
        highest_degree_other: highestDegree === "Other" ? highestDegreeOther.trim() : undefined,
        background_areas: backgroundAreas,
        background_other: backgroundAreas.includes("Other") ? backgroundOther.trim() : undefined,
        has_own_transportation: hasTransportation,
        invite_code: inviteCode.trim() ? inviteCode.trim().toUpperCase() : undefined,
      }

      const res = await applyAsStudentApi(payload, cvFile)

      // Store fresh tokens and update state
      tokens.set({
        access_token: res.access_token,
        refresh_token: res.refresh_token,
      })
      setCurrentUser(res.user)
      setActiveRole("applicant")

      void queryClient.invalidateQueries({ queryKey: ["me"] })
      void queryClient.invalidateQueries({ queryKey: ["instructor-status"] })

      onOpenChange(false)
      void navigate({ to: "/instructors/status" })
    } catch (err: unknown) {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setError(err.response.data.detail)
      } else {
        setError("Failed to submit application. Please check your connection.")
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2 text-primary font-semibold text-xs uppercase tracking-wider mb-1">
            <GraduationCap className="size-4" />
            Instructor Intake
          </div>
          <DialogTitle className="text-lg font-bold">Apply as an Instructor</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Complete your teaching credentials to join the SpacePoint instructor onboarding pipeline.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
          {error && (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-xs text-destructive">
              {error}
            </div>
          )}

          {/* Account Snapshot (Read Only) */}
          <div className="rounded-xl border border-border bg-muted/30 p-3 text-xs flex flex-col gap-1">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Applicant Name:</span>
              <span className="font-medium text-foreground">{currentUser?.full_name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Email:</span>
              <span className="font-medium text-foreground">{currentUser?.email}</span>
            </div>
          </div>

          {/* Degree */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Highest Degree
            </label>
            <select
              className="input w-full"
              value={highestDegree}
              onChange={(e) => setHighestDegree(e.target.value)}
            >
              {DEGREES.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </div>

          {highestDegree === "Other" && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">
                Specify Degree
              </label>
              <input
                type="text"
                className="input w-full"
                value={highestDegreeOther}
                onChange={(e) => setHighestDegreeOther(e.target.value)}
                placeholder="e.g. Higher Diploma"
                required
              />
            </div>
          )}

          {/* University */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              University / Institution
            </label>
            <input
              type="text"
              className="input w-full"
              value={university}
              onChange={(e) => setUniversity(e.target.value)}
              placeholder="e.g. Khalifa University"
              required
            />
          </div>

          {/* Background Disciplines */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1.5">
              Academic & Technical Background
            </label>
            <div className="flex flex-wrap gap-2">
              {BACKGROUNDS.map((bg) => {
                const active = backgroundAreas.includes(bg)
                return (
                  <button
                    key={bg}
                    type="button"
                    onClick={() => toggleBackground(bg)}
                    className={`px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors flex items-center gap-1.5 ${
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-border bg-card text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {active && <Check size={12} />}
                    {bg}
                  </button>
                )
              })}
            </div>
          </div>

          {backgroundAreas.includes("Other") && (
            <div>
              <input
                type="text"
                className="input w-full"
                value={backgroundOther}
                onChange={(e) => setBackgroundOther(e.target.value)}
                placeholder="Specify discipline (e.g. Aerospace Systems)"
                required
              />
            </div>
          )}

          {/* Own Transportation */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1.5">
              Do you have own transportation / car for workshop delivery?
            </label>
            <div className="flex items-center gap-4 text-xs">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="transportation"
                  checked={hasTransportation}
                  onChange={() => setHasTransportation(true)}
                />
                Yes
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="transportation"
                  checked={!hasTransportation}
                  onChange={() => setHasTransportation(false)}
                />
                No
              </label>
            </div>
          </div>

          {/* CV Upload */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              CV / Resume (PDF)
            </label>
            <div className="flex items-center gap-3">
              <label className="relative cursor-pointer h-9 px-3 bg-secondary text-secondary-foreground font-semibold text-xs rounded-xl hover:opacity-90 transition-opacity flex items-center gap-1.5 shrink-0">
                <Upload size={14} />
                {cvFile ? "Replace File" : "Choose PDF"}
                <input
                  type="file"
                  accept="application/pdf"
                  className="hidden"
                  onChange={(e) => {
                    const f = e.target.files?.[0]
                    if (f) setCvFile(f)
                  }}
                />
              </label>
              <span className="text-xs text-muted-foreground truncate">
                {cvFile ? cvFile.name : "No file selected"}
              </span>
            </div>
          </div>

          {/* Invite Code */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Ambassador / Referral Code (Optional)
            </label>
            <input
              type="text"
              className="input w-full uppercase"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="e.g. AMB-1234"
            />
          </div>

          <DialogFooter className="mt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={loading}
            >
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={loading} className="font-semibold">
              {loading ? "Submitting..." : "Submit Application"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
