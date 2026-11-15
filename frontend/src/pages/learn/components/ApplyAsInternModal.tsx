import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { Briefcase, Upload } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getPublicFormConfigApi } from "@/api/apply"
import { applyAsStudentInternApi } from "@/api/internship"
import { fetchPublicCities } from "@/api/lms"
import {
  CustomQuestionsFields,
  isFieldEnabled,
  isFieldRequired,
  validateCustomQuestionAnswers,
} from "@/components/apply/CustomQuestionsFields"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"

interface ApplyAsInternModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialUniversity?: string
  initialStudentId?: string
  onSuccess?: () => void
}

const DURATION_OPTIONS = [
  { value: 4, label: "4 weeks (1 month)" },
  { value: 8, label: "8 weeks (2 months)" },
  { value: 12, label: "12 weeks (3 months)" },
  { value: 16, label: "16 weeks (4 months)" },
]

export function ApplyAsInternModal({
  open,
  onOpenChange,
  initialUniversity = "",
  initialStudentId = "",
  onSuccess,
}: ApplyAsInternModalProps) {
  const { currentUser } = useAuth()
  const queryClient = useQueryClient()

  const [university, setUniversity] = useState(initialUniversity || currentUser?.organization_name || "")
  const [universityIdNumber, setUniversityIdNumber] = useState(initialStudentId || currentUser?.student_id || "")
  const [major, setMajor] = useState("")
  const [preferredCityId, setPreferredCityId] = useState("")
  const [requestedStartDate, setRequestedStartDate] = useState("")
  const [requestedDurationWeeks, setRequestedDurationWeeks] = useState(8)
  const [cvFile, setCvFile] = useState<File | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: cities = [] } = useQuery({
    queryKey: ["public-cities"],
    queryFn: fetchPublicCities,
    enabled: open,
  })

  const { data: formConfig } = useQuery({
    queryKey: ["apply-form-config", "intern"],
    queryFn: () => getPublicFormConfigApi("intern"),
    enabled: open,
  })
  const fields = formConfig?.fields
  const questions = formConfig?.questions ?? []
  const cvRequired = isFieldRequired(fields, "cv", false)
  const cvEnabled = isFieldEnabled(fields, "cv", true)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!university.trim()) {
      setError("Please specify your university or institution.")
      return
    }
    if (!universityIdNumber.trim()) {
      setError("Please enter your university or student ID number.")
      return
    }
    if (isFieldRequired(fields, "major", false) && !major.trim()) {
      setError("Please enter your major / academic discipline.")
      return
    }
    if (isFieldRequired(fields, "preferred_city_id", false) && !preferredCityId) {
      setError("Please select a preferred work city.")
      return
    }
    if (isFieldRequired(fields, "requested_start_date", false) && !requestedStartDate) {
      setError("Please choose a requested start date.")
      return
    }
    if (cvRequired && !cvFile) {
      setError("Please upload your CV / Resume.")
      return
    }
    const qErr = validateCustomQuestionAnswers(questions, answers)
    if (qErr) {
      setError(qErr)
      return
    }

    setLoading(true)
    setError(null)

    try {
      await applyAsStudentInternApi(
        {
          university: university.trim(),
          university_id_number: universityIdNumber.trim(),
          major: major.trim() || undefined,
          preferred_city_id: preferredCityId || undefined,
          requested_start_date: requestedStartDate || undefined,
          requested_duration_weeks: requestedDurationWeeks,
          answers,
        },
        cvFile
      )

      void queryClient.invalidateQueries({ queryKey: ["me"] })
      void queryClient.invalidateQueries({ queryKey: ["internship-intake-eligibility"] })
      void queryClient.invalidateQueries({ queryKey: ["my-role-requests"] })

      if (onSuccess) onSuccess()
      onOpenChange(false)
    } catch (err: unknown) {
      if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
        setError(err.response.data.detail)
      } else {
        setError("Failed to submit internship application. Please try again.")
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
            <Briefcase className="size-4" />
            Internship Application
          </div>
          <DialogTitle className="text-lg font-bold">Apply for an Internship</DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Submit your university information and preferences to join our engineering and space missions.
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

          {/* University / Institution */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              University / Institution <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              className="input w-full"
              value={university}
              onChange={(e) => setUniversity(e.target.value)}
              placeholder="e.g. Khalifa University"
              required
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Updated automatically on your profile.
            </p>
          </div>

          {/* Student ID */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              University / Student ID Number <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              className="input w-full font-mono"
              value={universityIdNumber}
              onChange={(e) => setUniversityIdNumber(e.target.value)}
              placeholder="e.g. 10008543"
              required
            />
            <p className="text-[11px] text-muted-foreground mt-1">
              Used for your official internship placement letter.
            </p>
          </div>

          {/* Major / Field of Study */}
          {isFieldEnabled(fields, "major", true) && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">
                Major / Academic Discipline{" "}
                {isFieldRequired(fields, "major", false) && <span className="text-destructive">*</span>}
              </label>
              <input
                type="text"
                className="input w-full"
                value={major}
                onChange={(e) => setMajor(e.target.value)}
                placeholder="e.g. Aerospace Engineering / Computer Science"
                required={isFieldRequired(fields, "major", false)}
              />
            </div>
          )}

          {/* Preferred Location */}
          {isFieldEnabled(fields, "preferred_city_id", true) && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">
                Preferred Work City / Center{" "}
                {isFieldRequired(fields, "preferred_city_id", false) && <span className="text-destructive">*</span>}
              </label>
              <select
                className="input w-full"
                value={preferredCityId}
                onChange={(e) => setPreferredCityId(e.target.value)}
              >
                <option value="">No preference / Remote</option>
                {cities.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Requested Start Date */}
            {isFieldEnabled(fields, "requested_start_date", true) && (
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Requested Start Date{" "}
                  {isFieldRequired(fields, "requested_start_date", false) && <span className="text-destructive">*</span>}
                </label>
                <input
                  type="date"
                  className="input w-full"
                  value={requestedStartDate}
                  onChange={(e) => setRequestedStartDate(e.target.value)}
                />
              </div>
            )}

            {/* Duration Weeks */}
            {isFieldEnabled(fields, "requested_duration_weeks", true) && (
              <div>
                <label className="text-xs font-medium text-foreground block mb-1">
                  Internship Duration{" "}
                  {isFieldRequired(fields, "requested_duration_weeks", false) && <span className="text-destructive">*</span>}
                </label>
                <select
                  className="input w-full"
                  value={requestedDurationWeeks}
                  onChange={(e) => setRequestedDurationWeeks(Number(e.target.value))}
                >
                  {DURATION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* CV Upload */}
          {cvEnabled && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">
                CV / Resume (PDF){cvRequired && <span className="text-destructive"> *</span>}
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
          )}

          {questions.length > 0 && (
            <div className="pt-2 border-t border-border">
              <CustomQuestionsFields
                questions={questions}
                answers={answers}
                onChange={setAnswers}
                labelClassName="text-xs font-medium text-foreground block mb-1"
              />
            </div>
          )}

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
