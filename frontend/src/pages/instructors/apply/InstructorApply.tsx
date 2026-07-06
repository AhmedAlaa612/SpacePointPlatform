import { useEffect, useState } from "react"
import { PLAIN_LOGO } from "@/lib/logos"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { Check } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { applyInstructorApi, validateInviteApi } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { SiteFooter } from "@/components/layout/SiteFooter"
import { BODY_BACKGROUND } from "@/lib/theme"

/**
 * Two-step "Access Gate" apply flow, matching the reference app's
 * var/www/spacepoint_portal/backend/app/templates/apply.html.
 */

const DEGREES = ["Currently Pursuing Bachelors Degree", "Bachelors", "Masters", "PhD", "Other"]
const BACKGROUNDS = ["Engineering", "Science", "Education", "Other"]
const UAE_CITIES = ["Dubai", "Abu Dhabi", "Sharjah", "Al Ain", "Ajman", "Umm Al Quwain", "Fujairah", "Ras Al Khaimah"]

const COUNTRIES = [
  "United Arab Emirates", "Afghanistan", "Albania", "Algeria", "Andorra", "Angola",
  "Antigua and Barbuda", "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan",
  "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
  "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
  "Burkina Faso", "Burundi", "Cabo Verde", "Cambodia", "Cameroon", "Canada",
  "Central African Republic", "Chad", "Chile", "China", "Colombia", "Comoros",
  "Congo (Congo-Brazzaville)", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czechia",
  "Democratic Republic of the Congo", "Denmark", "Djibouti", "Dominica",
  "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea",
  "Estonia", "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
  "Georgia", "Germany", "Ghana", "Greece", "Grenada", "Guatemala", "Guinea",
  "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India",
  "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan",
  "Kazakhstan", "Kenya", "Kiribati", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon",
  "Lesotho", "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg",
  "Madagascar", "Malawi", "Malaysia", "Maldives", "Mali", "Malta",
  "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova",
  "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia",
  "Nauru", "Nepal", "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria",
  "North Korea", "North Macedonia", "Norway", "Oman", "Pakistan", "Palau", "Panama",
  "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar",
  "Romania", "Russia", "Rwanda", "Saint Kitts and Nevis", "Saint Lucia",
  "Saint Vincent and the Grenadines", "Samoa", "San Marino", "Sao Tome and Principe",
  "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone", "Singapore",
  "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Korea",
  "South Sudan", "Spain", "Sri Lanka", "Sudan", "Suriname", "Sweden", "Switzerland",
  "Syria", "Taiwan", "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo",
  "Tonga", "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu",
  "Uganda", "Ukraine", "United Kingdom", "United States", "Uruguay", "Uzbekistan",
  "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe",
]

type ApplyLocation = "within" | "outside"

export default function InstructorApplyPage() {
  const { code } = useParams({ strict: false }) as { code?: string }
  const navigate = useNavigate()
  const { setCurrentUser, setActiveRole } = useAuth()

  // Step 1: Access Gate
  const [step, setStep] = useState<1 | 2>(1)
  const [inviteCode, setInviteCode] = useState(code ?? "")
  const [referrer, setReferrer] = useState<string | null>(null)
  const [inviteError, setInviteError] = useState("")
  const [inviteBusy, setInviteBusy] = useState(false)

  // Step 2: Your Profile
  const [applyLocation, setApplyLocation] = useState<ApplyLocation>("within")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    full_name: "", phone: "", email: "", password: "",
    university: "", highest_degree: "", highest_degree_other: "",
    city_of_residence: "", background_other: "", has_own_transportation: "" as "" | "true" | "false",
    country: "United Arab Emirates",
  })
  const [backgroundAreas, setBackgroundAreas] = useState<string[]>([])
  const [deliverCities, setDeliverCities] = useState<string[]>([])

  useEffect(() => {
    if (code) {
      validateInviteApi(code).then((r) => setReferrer(r.ambassador_name)).catch(() => setReferrer(null))
    }
  }, [code])

  // If we already have a code from the URL, verify it up front like the
  // reference does when `code` is present, and jump straight to step 2 once valid.
  useEffect(() => {
    if (!code) return
    setInviteBusy(true)
    validateInviteApi(code)
      .then(() => setStep(2))
      .catch(() => setInviteError("Invalid or expired invitation code."))
      .finally(() => setInviteBusy(false))
  }, [code])

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const toggleBackground = (value: string) =>
    setBackgroundAreas((a) => (a.includes(value) ? a.filter((v) => v !== value) : [...a, value]))

  const toggleDeliverCity = (value: string) =>
    setDeliverCities((a) => (a.includes(value) ? a.filter((v) => v !== value) : [...a, value]))

  const handleLocationChange = (loc: ApplyLocation) => {
    setApplyLocation(loc)
    if (loc === "outside") {
      setForm((f) => ({ ...f, city_of_residence: "", has_own_transportation: "" }))
      setDeliverCities([])
    } else {
      setForm((f) => ({ ...f, country: "United Arab Emirates" }))
    }
  }

  const continueToProfile = async (e: React.FormEvent) => {
    e.preventDefault()
    setInviteError("")
    const trimmed = inviteCode.trim().toUpperCase()
    if (!trimmed) return
    setInviteBusy(true)
    try {
      const r = await validateInviteApi(trimmed)
      setReferrer(r.ambassador_name)
      setInviteCode(trimmed)
      setStep(2)
    } catch (err: any) {
      setInviteError(err?.response?.data?.detail || "Invalid invitation code")
    } finally {
      setInviteBusy(false)
    }
  }

  const goBack = () => {
    setStep(1)
    setError("")
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (applyLocation === "within") {
      if (deliverCities.length === 0) {
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
        invite_code: inviteCode,
        university: form.university,
        highest_degree: form.highest_degree,
        highest_degree_other: form.highest_degree === "Other" ? form.highest_degree_other : undefined,
        city_of_residence: applyLocation === "within" ? form.city_of_residence : undefined,
        deliver_cities: applyLocation === "within" ? deliverCities : [],
        background_areas: backgroundAreas,
        background_other: backgroundAreas.includes("Other") ? form.background_other : undefined,
        has_own_transportation: applyLocation === "within" ? form.has_own_transportation === "true" : false,
        country: form.country,
      })
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
    <div className="min-h-screen text-white flex flex-col" style={BODY_BACKGROUND}>
      <div className="flex-1 flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-2xl">
        <div className="mb-8 flex items-center gap-2 justify-center">
          <img src={PLAIN_LOGO} alt="SpacePoint" className="h-12 w-auto object-contain" />
        </div>

        {/* Step indicator */}
        <ol className="flex items-center w-full justify-between mb-8">
          <li
            className={`flex w-full items-center after:content-[''] after:w-full after:h-1 after:border-b after:border-4 after:inline-block ${
              step === 2 ? "text-primary after:border-primary" : "text-primary after:border-primary"
            }`}
          >
            <span className="flex items-center justify-center w-8 h-8 bg-background border-2 border-primary rounded-full shrink-0 font-bold z-10 text-foreground">
              1
            </span>
          </li>
          <li className={`flex items-center ${step === 2 ? "text-primary" : "text-muted-foreground"}`}>
            <span
              className={`flex items-center justify-center w-8 h-8 bg-background border-2 rounded-full shrink-0 font-bold z-10 text-foreground ${
                step === 2 ? "border-primary" : "border-muted-foreground"
              }`}
            >
              2
            </span>
          </li>
        </ol>

        {step === 1 && (
          <div>
            <h1 className="text-center text-2xl font-bold text-foreground tracking-tight">Access Gate</h1>
            <p className="mt-2 text-center text-sm text-muted-foreground mb-6">
              Please enter your valid invitation code to proceed to the scholarship application.
            </p>
            <form onSubmit={continueToProfile} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Invitation Code</label>
                <input
                  className="input uppercase"
                  placeholder="INV-XXXXX"
                  value={inviteCode}
                  onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                  required
                />
              </div>
              {inviteError && <p className="text-sm text-destructive text-center">{inviteError}</p>}
              <Button type="submit" disabled={inviteBusy} className="w-full">
                {inviteBusy ? "Verifying…" : "Continue Application"}
              </Button>
            </form>
          </div>
        )}

        {step === 2 && (
          <div>
            <h1 className="text-center text-2xl font-bold text-foreground tracking-tight">Your Profile</h1>
            <p className="mt-2 text-center text-sm text-muted-foreground mb-2">
              Complete your details to create your SpacePoint account.
            </p>
            {referrer && <p className="text-sm text-primary mb-4 text-center">Referred by {referrer}</p>}

            <form onSubmit={submit} className="flex flex-col gap-6 mt-6">
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
                <select
                  className="input"
                  value={form.country}
                  onChange={set("country")}
                  disabled={applyLocation === "within"}
                  required
                >
                  {COUNTRIES.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              {applyLocation === "within" && (
                <>
                  {/* City of residence */}
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">City of Residence</label>
                    <select className="input" value={form.city_of_residence} onChange={set("city_of_residence")} required>
                      <option value="" disabled>Select...</option>
                      {UAE_CITIES.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
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
                      {UAE_CITIES.map((c) => (
                        <label
                          key={c}
                          className="flex items-center gap-3 rounded-xl border border-border px-4 py-3 text-sm cursor-pointer transition-colors hover:bg-muted"
                        >
                          <input
                            type="checkbox"
                            className="sr-only peer"
                            checked={deliverCities.includes(c)}
                            onChange={() => toggleDeliverCity(c)}
                          />
                          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md border border-border bg-background transition-colors peer-checked:border-primary peer-checked:bg-primary">
                            <Check className="h-3.5 w-3.5 text-primary-foreground opacity-0 peer-checked:opacity-100" strokeWidth={3} />
                          </span>
                          <span className="text-muted-foreground peer-checked:text-foreground">{c}</span>
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

              {error && <p className="text-sm text-destructive text-center">{error}</p>}

              <div className="space-y-3">
                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? "Submitting…" : "Create Account & Start Task"}
                </Button>
                <button
                  type="button"
                  onClick={goBack}
                  className="w-full py-2.5 rounded-lg border border-border text-sm font-medium text-foreground hover:bg-muted transition-colors"
                >
                  Back
                </button>
              </div>
            </form>
          </div>
        )}

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
