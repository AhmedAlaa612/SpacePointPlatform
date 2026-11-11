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
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect"
import { LanguageMultiSelect } from "@/components/ui/LanguageMultiSelect"

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

  const [nationality, setNationality] = useState(currentUser?.nationality || "")
  const [fluentLanguages, setFluentLanguages] = useState<string[]>(
    currentUser?.fluent_languages && currentUser.fluent_languages.length > 0
      ? currentUser.fluent_languages
      : ["English"]
  )
  const [country, setCountry] = useState(currentUser?.country || "AE")
  const [cityOfResidenceId, setCityOfResidenceId] = useState(
    currentUser?.city_of_residence_id || currentUser?.city_id || ""
  )
  const [deliverCityIds, setDeliverCityIds] = useState<string[]>(
    currentUser?.deliver_city_ids || []
  )
  const [university, setUniversity] = useState(currentUser?.organization_name || "")
  const [highestDegree, setHighestDegree] = useState(DEGREES[0])
  const [highestDegreeOther, setHighestDegreeOther] = useState("")
  const [backgroundAreas, setBackgroundAreas] = useState<string[]>(["Engineering"])
  const [backgroundOther, setBackgroundOther] = useState("")
  const [hasTransportation, setHasTransportation] = useState<boolean>(
    currentUser?.has_own_transportation ?? false
  )
  const [inviteCode, setInviteCode] = useState("")
  const [cvFile, setCvFile] = useState<File | null>(null)

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const countryCities = useCitiesForCountry(country)

  const toggleBackground = (bg: string) => {
    setBackgroundAreas((prev) =>
      prev.includes(bg) ? prev.filter((b) => b !== bg) : [...prev, bg]
    )
  }

  const toggleDeliverCity = (cityId: string) => {
    setDeliverCityIds((prev) =>
      prev.includes(cityId) ? prev.filter((id) => id !== cityId) : [...prev, cityId]
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
    if (countryCities.length > 0 && deliverCityIds.length === 0) {
      setError("Please select at least one city where you can deliver workshops.")
      return
    }

    setLoading(true)
    setError(null)

    try {
      const payload = {
        university: university.trim() || undefined,
        graduated_university: university.trim() || undefined,
        highest_degree: highestDegree,
        highest_degree_other: highestDegree === "Other" ? highestDegreeOther.trim() : undefined,
        nationality: nationality || undefined,
        work_status: currentUser?.work_status || "Student",
        fluent_languages: fluentLanguages,
        country: country || undefined,
        city_of_residence_id: cityOfResidenceId || undefined,
        deliver_city_ids: deliverCityIds,
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
      <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
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
            {currentUser?.phone && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">Phone / WhatsApp:</span>
                <span className="font-medium text-foreground">{currentUser.phone}</span>
              </div>
            )}
          </div>

          {/* Nationality */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Nationality
            </label>
            <CountrySelect
              className="input w-full"
              value={nationality}
              onChange={setNationality}
              valueType="name"
              placeholder="Select nationality..."
            />
          </div>

          {/* Fluent Languages */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Fluent Languages
            </label>
            <LanguageMultiSelect
              value={fluentLanguages}
              onChange={setFluentLanguages}
              placeholder="Select fluent languages..."
            />
          </div>

          {/* Country of Residence */}
          <div>
            <label className="text-xs font-medium text-foreground block mb-1">
              Country of Residence
            </label>
            <CountrySelect
              className="input w-full"
              value={country}
              onChange={(code) => {
                setCountry(code)
                setCityOfResidenceId("")
                setDeliverCityIds([])
              }}
              valueType="code"
              placeholder="Select country..."
            />
          </div>

          {/* City of Residence (when cities exist for selected country) */}
          {countryCities.length > 0 && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1">
                City of Residence
              </label>
              <CitySelect
                country={country}
                value={cityOfResidenceId}
                onChange={setCityOfResidenceId}
                placeholder="Select city of residence..."
                className="input w-full"
              />
            </div>
          )}

          {/* Cities I Can Deliver In */}
          {countryCities.length > 0 && (
            <div>
              <label className="text-xs font-medium text-foreground block mb-1.5">
                Cities I Can Deliver In
              </label>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                {countryCities.map((c) => {
                  const active = deliverCityIds.includes(c.id)
                  return (
                    <label
                      key={c.id}
                      className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 text-xs cursor-pointer hover:bg-muted transition-colors"
                    >
                      <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={active}
                        onChange={() => toggleDeliverCity(c.id)}
                      />
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-md border border-border bg-background transition-colors peer-checked:border-primary peer-checked:bg-primary">
                        <Check className="h-3 w-3 text-primary-foreground opacity-0 peer-checked:opacity-100" strokeWidth={3} />
                      </span>
                      <span className="text-muted-foreground peer-checked:text-foreground font-medium truncate">
                        {c.name}
                      </span>
                    </label>
                  )
                })}
              </div>
            </div>
          )}

          {/* Degree & University */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
              Do you have a car / own transportation for workshop delivery?
            </label>
            <div className="flex items-center gap-4 text-xs">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="transportation"
                  checked={hasTransportation}
                  onChange={() => setHasTransportation(true)}
                />
                Yes, I have a car
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name="transportation"
                  checked={!hasTransportation}
                  onChange={() => setHasTransportation(false)}
                />
                No, I don't
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
              Referral Code (Optional)
            </label>
            <input
              type="text"
              className="input w-full uppercase"
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              placeholder="e.g. REF-1234"
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
