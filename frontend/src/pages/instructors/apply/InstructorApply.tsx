import { useEffect, useState } from "react"
import { PLAIN_LOGO } from "@/lib/logos"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { Check, Upload } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { applyInstructorApi, validateInviteApi } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect"
import { SiteFooter } from "@/components/layout/SiteFooter"
import { BODY_BACKGROUND } from "@/lib/theme"

/**
 * Single "Submit Your Interest" apply flow — the invitation code is an
 * optional field (organic applicants have none; referred applicants type
 * one in and it's validated on submit), not a gate blocking the form.
 */

const DEGREES = ["Currently Pursuing Bachelors Degree", "Bachelors", "Masters", "PhD", "Other"]
const BACKGROUNDS = ["Engineering", "Science", "Education", "Other"]

type ApplyLocation = "within" | "outside"

export default function InstructorApplyPage() {
  const { code } = useParams({ strict: false }) as { code?: string }
  const navigate = useNavigate()
  const { setCurrentUser, setActiveRole } = useAuth()

  // Invitation code is optional — organic applicants (no referrer) select "No".
  const [hasInviteCode, setHasInviteCode] = useState<boolean>(!!code)
  const [inviteCode, setInviteCode] = useState(code ?? "")
  const [referrer, setReferrer] = useState<string | null>(null)
  const [inviteError, setInviteError] = useState("")

  const [applyLocation, setApplyLocation] = useState<ApplyLocation>("within")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    full_name: "", phone: "", email: "", password: "",
    university: "", highest_degree: "", highest_degree_other: "",
    city_of_residence_id: "", background_other: "", has_own_transportation: "" as "" | "true" | "false",
    country: "United Arab Emirates",
  })
  const [backgroundAreas, setBackgroundAreas] = useState<string[]>([])
  const [deliverCityIds, setDeliverCityIds] = useState<string[]>([])
  const [cv, setCv] = useState<File | null>(null)

  const countryCities = useCitiesForCountry(form.country)

  // Pre-fill from a referral link (/apply/instructor/$code) and show the
  // referrer right away — still just informational, doesn't gate the form.
  useEffect(() => {
    if (!code) return
    setHasInviteCode(true)
    validateInviteApi(code)
      .then((r) => setReferrer(r.ambassador_name))
      .catch(() => setInviteError("Invalid or expired invitation code."))
  }, [code])

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const toggleBackground = (value: string) =>
    setBackgroundAreas((a) => (a.includes(value) ? a.filter((v) => v !== value) : [...a, value]))

  const toggleDeliverCity = (cityId: string) =>
    setDeliverCityIds((a) => (a.includes(cityId) ? a.filter((v) => v !== cityId) : [...a, cityId]))

  const handleLocationChange = (loc: ApplyLocation) => {
    setApplyLocation(loc)
    if (loc === "outside") {
      setForm((f) => ({ ...f, city_of_residence_id: "", has_own_transportation: "" }))
      setDeliverCityIds([])
    } else {
      setForm((f) => ({ ...f, country: "United Arab Emirates" }))
    }
  }

  const handleHasCodeChange = (yes: boolean) => {
    setHasInviteCode(yes)
    setInviteError("")
    if (!yes) {
      setInviteCode("")
      setReferrer(null)
    }
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setInviteError("")

    let submittedCode: string | undefined
    if (hasInviteCode) {
      submittedCode = inviteCode.trim().toUpperCase()
      if (!submittedCode) {
        setError('Please enter your invitation code, or select "No" if you don\'t have one.')
        return
      }
      try {
        const r = await validateInviteApi(submittedCode)
        setReferrer(r.ambassador_name)
      } catch (err: any) {
        const msg = err?.response?.data?.detail || "Invalid or expired invitation code."
        setInviteError(msg)
        setError(msg)
        return
      }
    }

    if (applyLocation === "within") {
      if (deliverCityIds.length === 0) {
        setError("Please select at least one delivery city.")
        return
      }
      if (form.has_own_transportation === "") {
        setError("Please specify if you have own transportation/car.")
        return
      }
    }

    if (backgroundAreas.length === 0) {
      setError("Please select at least one background area.")
      return
    }

    if (!cv) {
      setError("Please upload your CV / resume.")
      return
    }

    // Note: the backend (InstructorApply schema / instructor_apply endpoint) does
    // NOT enforce a gmail-only email domain, so we don't invent that restriction
    // here either — any valid email the backend accepts should be allowed.
    const emailVal = form.email.trim()

    setLoading(true)
    try {
      const user = await applyInstructorApi({
        full_name: form.full_name,
        phone: form.phone,
        email: emailVal,
        password: form.password,
        invite_code: submittedCode,
        university: form.university,
        highest_degree: form.highest_degree,
        highest_degree_other: form.highest_degree === "Other" ? form.highest_degree_other : undefined,
        city_of_residence_id: applyLocation === "within" ? form.city_of_residence_id : undefined,
        deliver_city_ids: applyLocation === "within" ? deliverCityIds : [],
        background_areas: backgroundAreas,
        background_other: backgroundAreas.includes("Other") ? form.background_other : undefined,
        has_own_transportation: applyLocation === "within" ? form.has_own_transportation === "true" : false,
        country: form.country,
      }, cv)
      setCurrentUser(user)
      setActiveRole(user.roles[0])
      void navigate({ to: "/instructors/status" })
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="dark min-h-screen text-white flex flex-col" style={BODY_BACKGROUND}>
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl">
        <div className="mb-8 flex items-center gap-2 justify-center">
          <img src={PLAIN_LOGO} alt="SpacePoint" className="h-12 w-auto object-contain" />
        </div>

        <div>
          <h1 className="text-center text-2xl font-bold text-foreground tracking-tight">Submit Your Interest</h1>
          <p className="mt-2 text-center text-sm text-muted-foreground mb-6">
            Complete your details to create your SpacePoint account.
          </p>

          <form onSubmit={submit} className="flex flex-col gap-6 mt-6">
            {/* Invitation code — optional */}
            <div className="rounded-2xl border border-border p-5 space-y-3">
              <label className="block text-sm font-medium text-foreground">
                Do you have an invitation code?
              </label>
              <div className="flex gap-4">
                <button
                  type="button"
                  onClick={() => handleHasCodeChange(true)}
                  className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                    hasInviteCode
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Yes
                </button>
                <button
                  type="button"
                  onClick={() => handleHasCodeChange(false)}
                  className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                    !hasInviteCode
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  No
                </button>
              </div>
              {hasInviteCode && (
                <div className="pt-2 space-y-2">
                  <input
                    className="input uppercase"
                    placeholder="INV-XXXXX"
                    value={inviteCode}
                    onChange={(e) => { setInviteCode(e.target.value.toUpperCase()); setInviteError("") }}
                  />
                  {referrer && <p className="text-sm text-primary">Referred by {referrer}</p>}
                  {inviteError && <p className="text-sm text-destructive">{inviteError}</p>}
                </div>
              )}
            </div>

            {/* Within / Outside UAE toggle */}
            <div className="rounded-2xl border border-border p-5 space-y-3">
              <label className="block text-sm font-medium text-foreground">
                Are you applying from within the UAE or outside the UAE?
              </label>
              <div className="flex gap-4">
                <button
                  type="button"
                  onClick={() => handleLocationChange("within")}
                  className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                    applyLocation === "within"
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Within UAE
                </button>
                <button
                  type="button"
                  onClick={() => handleLocationChange("outside")}
                  className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                    applyLocation === "outside"
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Outside UAE
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Full Name</label>
                <input className="input" placeholder="Full name" value={form.full_name} onChange={set("full_name")} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Phone Number</label>
                <input
                  className="input"
                  type="tel"
                  placeholder="e.g., +971 50 123 4567"
                  value={form.phone}
                  onChange={set("phone")}
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Email Address</label>
                <input className="input" type="email" placeholder="you@example.com" value={form.email} onChange={set("email")} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Password</label>
                <input className="input" type="password" placeholder="Password" value={form.password} onChange={set("password")} required minLength={6} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">University</label>
                <input className="input" placeholder="University" value={form.university} onChange={set("university")} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Highest Degree</label>
                <select className="input" value={form.highest_degree} onChange={set("highest_degree")} required>
                  <option value="" disabled>Select...</option>
                  {DEGREES.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            </div>

            {form.highest_degree === "Other" && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Specify Degree</label>
                <input className="input" placeholder="Specify degree" value={form.highest_degree_other} onChange={set("highest_degree_other")} required />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-foreground mb-1">Country of Residence</label>
              <CountrySelect
                className="input"
                value={form.country}
                onChange={(name) => setForm((f) => ({ ...f, country: name }))}
                disabled={applyLocation === "within"}
                required
              />
            </div>

            {applyLocation === "within" && countryCities.length > 0 && (
              <>
                {/* City of residence */}
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">City of Residence</label>
                  <CitySelect
                    country={form.country}
                    value={form.city_of_residence_id}
                    onChange={(v) => setForm((f) => ({ ...f, city_of_residence_id: v }))}
                    placeholder="Select..."
                    required
                    className="input"
                  />
                </div>

                {/* Own transportation */}
                <div className="rounded-2xl border border-border p-5 space-y-3">
                  <label className="block text-sm font-medium text-foreground">
                    Do you have a car / own transportation?
                  </label>
                  <div className="flex gap-4">
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, has_own_transportation: "true" }))}
                      className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                        form.has_own_transportation === "true"
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      Yes, I have a car
                    </button>
                    <button
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, has_own_transportation: "false" }))}
                      className={`flex-1 py-3 rounded-xl border font-bold transition-all ${
                        form.has_own_transportation === "false"
                          ? "bg-destructive/20 text-destructive border-destructive/50"
                          : "border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      No, I don't
                    </button>
                  </div>
                </div>

                {/* Deliver cities */}
                <div>
                  <p className="text-sm font-medium text-foreground mb-3">
                    Can you deliver sessions in any of the following cities?
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    {countryCities.map((c) => (
                      <label
                        key={c.id}
                        className="flex items-center gap-3 rounded-xl border border-border px-4 py-3 text-sm cursor-pointer transition-colors hover:bg-muted"
                      >
                        <input
                          type="checkbox"
                          className="sr-only peer"
                          checked={deliverCityIds.includes(c.id)}
                          onChange={() => toggleDeliverCity(c.id)}
                        />
                        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border bg-background transition-colors peer-checked:border-primary peer-checked:bg-primary">
                          <Check className="h-3.5 w-3.5 text-primary-foreground opacity-0 peer-checked:opacity-100" strokeWidth={3} />
                        </span>
                        <span className="text-muted-foreground peer-checked:text-foreground">{c.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              </>
            )}

            {/* Background areas */}
            <div>
              <p className="text-sm font-medium text-foreground mb-3">Which areas best describe your background?</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {BACKGROUNDS.map((b) => (
                  <label
                    key={b}
                    className="flex items-center gap-3 rounded-xl border border-border px-3 py-2.5 text-sm cursor-pointer transition-colors hover:bg-muted"
                  >
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={backgroundAreas.includes(b)}
                      onChange={() => toggleBackground(b)}
                    />
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border bg-background transition-colors peer-checked:border-primary peer-checked:bg-primary">
                      <Check className="h-3.5 w-3.5 text-primary-foreground opacity-0 peer-checked:opacity-100" strokeWidth={3} />
                    </span>
                    <span className="text-muted-foreground peer-checked:text-foreground">{b}</span>
                  </label>
                ))}
              </div>
              {backgroundAreas.includes("Other") && (
                <input
                  className="input mt-3"
                  placeholder="Specify other background"
                  value={form.background_other}
                  onChange={set("background_other")}
                  required
                />
              )}
            </div>

            {/* CV / Resume */}
            <div>
              <label className="block text-sm font-medium text-foreground mb-1">
                CV / Resume <span className="text-destructive">*</span>
              </label>
              <label className="flex items-center gap-3 p-3 border border-border rounded-xl cursor-pointer hover:bg-muted transition-colors">
                <Upload size={16} className="text-muted-foreground shrink-0" />
                <span className="text-sm text-muted-foreground truncate">
                  {cv ? cv.name : "Upload PDF or Word doc"}
                </span>
                <input type="file" accept=".pdf,.doc,.docx" className="hidden"
                  onChange={(e) => setCv(e.target.files?.[0] ?? null)} />
              </label>
            </div>

            {error && <p className="text-sm text-destructive text-center">{error}</p>}

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? "Submitting…" : "Create Account & Start Task"}
            </Button>
          </form>
        </div>

        <p className="text-sm text-muted-foreground mt-6 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-heliotrope font-semibold hover:underline">Sign in</Link>
        </p>
      </div>
      </div>
      <SiteFooter />
    </div>
  )
}
