import { useEffect, useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ChevronRight, Upload, CheckCircle2 } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { getPublicFormConfigApi, submitApplicationApi } from "@/api/apply"
import { applyInstructorApi } from "@/api/auth"
import { fetchPublicCities } from "@/api/lms"
import {
  CustomQuestionsFields,
  isFieldEnabled,
  isFieldRequired,
  validateCustomQuestionAnswers,
} from "@/components/apply/CustomQuestionsFields"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CitySelect } from "@/components/ui/CitySelect"
import { PasswordInput } from "@/components/ui/PasswordInput"

const ROLE_LABEL: Record<string, string> = {
  ambassador: "Ambassador",
  intern: "Intern",
  teacher: "Teacher",
  facilitator: "Facilitator",
  instructor: "Instructor",
}

const DEFAULT_CV_ROLES = new Set(["ambassador", "intern", "teacher", "facilitator"])
const DEFAULT_CODE_ROLES = new Set(["teacher", "instructor"])

interface Props {
  role: string
  prefillCode?: string
}

export default function ApplyFlow({ role, prefillCode }: Props) {
  const navigate = useNavigate()
  const { currentUser } = useAuth()

  // Step 1 fields
  const [step, setStep] = useState(1)
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [birthdate, setBirthdate] = useState("")
  const [nationality, setNationality] = useState("")
  const [country, setCountry] = useState("")
  const [cityId, setCityId] = useState("")
  const [cityOther, setCityOther] = useState("")
  const [password, setPassword] = useState("")
  const [inviteCode, setInviteCode] = useState(prefillCode ?? "")
  const [cv, setCv] = useState<File | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Internship-specific fields (2026-08-20) — HANDOFF_INTERNSHIP.md
  const isIntern = role === "intern"
  const [university, setUniversity] = useState("")
  const [major, setMajor] = useState("")
  const [universityId, setUniversityId] = useState("")
  const [preferredCityId, setPreferredCityId] = useState("")
  const [requestedStartDate, setRequestedStartDate] = useState("")
  const [requestedDurationWeeks, setRequestedDurationWeeks] = useState("")

  useEffect(() => {
    if (!currentUser) return
    setFullName((v) => v || currentUser.full_name || "")
    setEmail((v) => v || currentUser.email || "")
    setPhone((v) => v || currentUser.phone || "")
    setBirthdate((v) => v || (currentUser.birthdate || currentUser.date_of_birth || "").slice(0, 10))
    setNationality((v) => v || currentUser.nationality || "")
    setCountry((v) => v || (currentUser.country === "uae" ? "AE" : currentUser.country || ""))
    setCityId((v) => v || currentUser.city_id || "")
    if (!currentUser.city_id && currentUser.city_other) {
      setCityOther((v) => v || currentUser.city_other || "")
    }
    if (isIntern) {
      setUniversity((v) => v || currentUser.graduated_university || currentUser.organization_name || "")
      setUniversityId((v) => v || currentUser.student_id || "")
    }
  }, [currentUser, isIntern])

  const { data: formConfig } = useQuery({
    queryKey: ["apply-form-config", role],
    queryFn: () => getPublicFormConfigApi(role),
  })

  const fields = formConfig?.fields
  const questions = formConfig?.questions ?? []
  const cvEnabled = isFieldEnabled(fields, "cv", DEFAULT_CV_ROLES.has(role))
  const cvRequired = isFieldRequired(fields, "cv", DEFAULT_CV_ROLES.has(role))
  const codeEnabled = isFieldEnabled(fields, "invite_code", true)
  const codeRequired = isFieldRequired(fields, "invite_code", DEFAULT_CODE_ROLES.has(role))
  const phoneEnabled = isFieldEnabled(fields, "phone", true)
  const phoneRequired = isFieldRequired(fields, "phone", false)
  const birthdateEnabled = isFieldEnabled(fields, "birthdate", true)
  const birthdateRequired = isFieldRequired(fields, "birthdate", false)
  const nationalityEnabled = isIntern && isFieldEnabled(fields, "nationality", true)
  const nationalityRequired = isIntern && isFieldRequired(fields, "nationality", true)
  const countryEnabled = isFieldEnabled(fields, "country", true)
  const countryRequired = isFieldRequired(fields, "country", true)
  const cityEnabled = isFieldEnabled(fields, "city", true)
  const cityRequired = isFieldRequired(fields, "city", true)

  const hasInternStep2Fields = isIntern && (
    isFieldEnabled(fields, "university", true) ||
    isFieldEnabled(fields, "major", true) ||
    isFieldEnabled(fields, "university_id_number", true) ||
    isFieldEnabled(fields, "preferred_city_id", true) ||
    isFieldEnabled(fields, "requested_start_date", true) ||
    isFieldEnabled(fields, "requested_duration_weeks", true)
  )
  const hasStep2 = cvEnabled || questions.length > 0 || hasInternStep2Fields

  const { data: workCities = [] } = useQuery({
    queryKey: ["public-cities"],
    queryFn: fetchPublicCities,
    enabled: isIntern,
  })

  const submit = useMutation({
    mutationFn: async () => {
      setError(null)
      if (cvRequired && !cv) {
        throw new Error("Please upload your CV / Resume.")
      }
      if (isIntern) {
        if (isFieldRequired(fields, "university", false) && !university.trim()) {
          throw new Error("University / Institution is required.")
        }
        if (isFieldRequired(fields, "major", false) && !major.trim()) {
          throw new Error("Major / Field of Study is required.")
        }
        if (isFieldRequired(fields, "university_id_number", false) && !universityId.trim()) {
          throw new Error("University ID number is required.")
        }
        if (isFieldRequired(fields, "preferred_city_id", false) && !preferredCityId) {
          throw new Error("Preferred training city is required.")
        }
        if (isFieldRequired(fields, "requested_start_date", false) && !requestedStartDate) {
          throw new Error("Preferred start date is required.")
        }
        if (isFieldRequired(fields, "requested_duration_weeks", false) && !requestedDurationWeeks) {
          throw new Error("Requested duration is required.")
        }
      }
      const qErr = validateCustomQuestionAnswers(questions, answers)
      if (qErr) {
        throw new Error(qErr)
      }

      if (role === "instructor") {
        const user = await applyInstructorApi({
          full_name: fullName, email, password,
          phone: phone || undefined,
          birthdate: birthdate || undefined,
          invite_code: inviteCode, country: country || "AE",
          answers,
        }, cv)
        return { instructor: true, user }
      }
      const form = new FormData()
      form.append("full_name", fullName)
      form.append("email", email)
      form.append("password", password)
      if (phone) form.append("phone", phone)
      if (birthdate) form.append("birthdate", birthdate)
      if (nationality) form.append("nationality", nationality)
      if (country) form.append("country", country)
      if (cityId) form.append("city_id", cityId)
      if (cityOther && !cityId) form.append("city_other", cityOther)
      if (inviteCode) form.append("invite_code", inviteCode)
      if (cv) form.append("cv", cv)
      if (isIntern) {
        if (university.trim()) form.append("university", university.trim())
        if (major.trim()) form.append("major", major.trim())
        if (universityId.trim()) form.append("university_id_number", universityId.trim())
        if (preferredCityId) form.append("preferred_city_id", preferredCityId)
        if (requestedStartDate) form.append("requested_start_date", requestedStartDate)
        if (requestedDurationWeeks) form.append("requested_duration_weeks", requestedDurationWeeks)
      }
      form.append("answers", JSON.stringify({
        ...answers,
        ...(cityOther && !cityId ? { city_other: cityOther } : {}),
      }))
      return submitApplicationApi(role, form)
    },
    onSuccess: (data: any) => {
      if (data?.instructor) {
        navigate({ to: "/instructors/status" })
      } else {
        setDone(true)
      }
    },
    onError: (e: any) => {
      setError(e?.response?.data?.detail ?? e?.message ?? "Something went wrong. Please try again.")
    },
  })

  const validateStep1 = (): boolean => {
    setError(null)
    if (!fullName.trim() || !email.trim() || password.length < 6) {
      setError("Please fill in your full name, email, and a password of at least 6 characters.")
      return false
    }
    if (codeRequired && !inviteCode.trim()) {
      setError("An invite code is required for this role.")
      return false
    }
    if (phoneRequired && !phone.trim()) {
      setError("Phone number is required.")
      return false
    }
    if (birthdateRequired && !birthdate) {
      setError("Date of birth is required.")
      return false
    }
    if (nationalityRequired && !nationality) {
      setError("Nationality is required.")
      return false
    }
    if (countryRequired && !country) {
      setError("Country is required.")
      return false
    }
    if (cityRequired && country && !cityId && !cityOther.trim()) {
      setError("City is required.")
      return false
    }
    return true
  }

  const step1Valid = Boolean(
    fullName.trim() &&
    email.trim() &&
    password.length >= 6 &&
    (!codeRequired || inviteCode.trim()) &&
    (!phoneRequired || phone.trim()) &&
    (!birthdateRequired || birthdate) &&
    (!nationalityRequired || nationality) &&
    (!countryRequired || country) &&
    (!cityRequired || !country || cityId || cityOther.trim()),
  )

  if (done) {
    return (
      <div className="dark min-h-screen bg-background flex items-center justify-center p-4">
        <Card className="w-full max-w-md">
          <CardContent className="p-8 flex flex-col items-center gap-4 text-center">
            <CheckCircle2 size={48} className="text-emerald-500" />
            <h1 className="text-xl font-bold text-foreground">Application submitted!</h1>
            <p className="text-muted-foreground text-sm">
              We'll review your {ROLE_LABEL[role] ?? role} application and get back to you via email.
            </p>
            <Button variant="outline" onClick={() => navigate({ to: "/login" })}>Back to login</Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="dark min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-lg">
        <CardContent className="p-6 flex flex-col gap-5">
          {/* Header */}
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-0.5">
              Apply as
            </p>
            <h1 className="text-2xl font-bold text-foreground">{ROLE_LABEL[role] ?? role}</h1>
            {hasStep2 && (
              <div className="flex items-center gap-2 mt-2">
                {[1, 2].map((s) => (
                  <div
                    key={s}
                    className={`h-1.5 rounded-full flex-1 transition-colors ${step >= s ? "bg-primary" : "bg-muted"}`}
                  />
                ))}
              </div>
            )}
          </div>

          {error && (
            <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-xl px-3 py-2">
              {error}
            </div>
          )}

          {/* Step 1 */}
          {step === 1 && (
            <div className="flex flex-col gap-3">
              {codeEnabled && (
                <Field label="Invite code" required={codeRequired}>
                  <input className="input" placeholder="e.g. AB12CD" value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value.toUpperCase())} />
                </Field>
              )}
              <Field label="Full name" required>
                <input className="input" placeholder="Your full name" value={fullName}
                  onChange={(e) => setFullName(e.target.value)} />
              </Field>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <Field label="Email" required>
                  <input className="input" type="email" placeholder="you@email.com" value={email}
                    onChange={(e) => setEmail(e.target.value)} />
                </Field>
                {birthdateEnabled && (
                  <Field label="Date of birth" required={birthdateRequired}>
                    <input className="input" type="date" value={birthdate}
                      onChange={(e) => setBirthdate(e.target.value)} />
                  </Field>
                )}
              </div>
              {nationalityEnabled && (
                <Field label="Nationality" required={nationalityRequired}>
                  <CountrySelect value={nationality} onChange={setNationality} valueType="name" className="input" placeholder="Select nationality..." />
                </Field>
              )}
              {(phoneEnabled || countryEnabled) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {phoneEnabled && (
                    <Field label="Phone / WhatsApp" required={phoneRequired}>
                      <input className="input" placeholder="+971 50 000 0000" value={phone}
                        onChange={(e) => setPhone(e.target.value)} />
                    </Field>
                  )}
                  {countryEnabled && (
                    <Field label="Country" required={countryRequired}>
                      <CountrySelect value={country} onChange={setCountry} valueType="code" className="input" placeholder="Select country..." />
                    </Field>
                  )}
                </div>
              )}
              {cityEnabled && country && (
                <Field label="City" required={cityRequired}>
                  <CitySelect
                    country={country}
                    value={cityId}
                    onChange={setCityId}
                    otherValue={cityOther}
                    onOtherChange={setCityOther}
                    className="input"
                  />
                </Field>
              )}
              <Field label="Password" required>
                <PasswordInput className="input" placeholder="Min. 6 characters" value={password}
                  onChange={(e) => setPassword(e.target.value)} />
              </Field>

              <Button
                className="mt-1 w-full"
                disabled={!step1Valid || submit.isPending}
                onClick={() => {
                  if (!validateStep1()) return
                  if (hasStep2) {
                    setStep(2)
                  } else {
                    submit.mutate()
                  }
                }}
              >
                {submit.isPending ? "Submitting…" : hasStep2 ? (
                  <span className="flex items-center gap-1.5">Next <ChevronRight size={16} /></span>
                ) : "Submit application"}
              </Button>

              <p className="text-xs text-center text-muted-foreground">
                Already have an account?{" "}
                <button onClick={() => navigate({ to: "/login" })} className="text-primary hover:underline">
                  Sign in
                </button>
              </p>
            </div>
          )}

          {/* Step 2 — CV + questions */}
          {step === 2 && (
            <div className="flex flex-col gap-4">
              {cvEnabled && (
                <Field label="CV / Resume" required={cvRequired}>
                  <label className="flex items-center gap-3 p-3 border border-border rounded-xl cursor-pointer hover:bg-muted transition-colors">
                    <Upload size={16} className="text-muted-foreground shrink-0" />
                    <span className="text-sm text-muted-foreground truncate">
                      {cv ? cv.name : "Upload PDF or Word doc"}
                    </span>
                    <input type="file" accept=".pdf,.doc,.docx" className="hidden"
                      onChange={(e) => setCv(e.target.files?.[0] ?? null)} />
                  </label>
                </Field>
              )}

              {isIntern && (
                <>
                  {(isFieldEnabled(fields, "university", true) || isFieldEnabled(fields, "major", true)) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {isFieldEnabled(fields, "university", true) && (
                        <Field label="University / Institution" required={isFieldRequired(fields, "university", false)}>
                          <input className="input" placeholder="e.g. UAE University" value={university}
                            onChange={(e) => setUniversity(e.target.value)} />
                        </Field>
                      )}
                      {isFieldEnabled(fields, "major", true) && (
                        <Field label="Major / Field of study" required={isFieldRequired(fields, "major", false)}>
                          <input className="input" placeholder="e.g. Computer Engineering" value={major}
                            onChange={(e) => setMajor(e.target.value)} />
                        </Field>
                      )}
                    </div>
                  )}
                  {isFieldEnabled(fields, "university_id_number", true) && (
                    <Field label="University ID number" required={isFieldRequired(fields, "university_id_number", false)}>
                      <input className="input" value={universityId}
                        onChange={(e) => setUniversityId(e.target.value)} />
                    </Field>
                  )}
                  {isFieldEnabled(fields, "preferred_city_id", true) && (
                    <Field label="Which city do you want to work at?" required={isFieldRequired(fields, "preferred_city_id", false)}>
                      <select className="input" value={preferredCityId}
                        onChange={(e) => setPreferredCityId(e.target.value)}>
                        <option value="">Select a city...</option>
                        {workCities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </Field>
                  )}
                  {(isFieldEnabled(fields, "requested_start_date", true) || isFieldEnabled(fields, "requested_duration_weeks", true)) && (
                    <div className="grid grid-cols-2 gap-3">
                      {isFieldEnabled(fields, "requested_start_date", true) && (
                        <Field label="Preferred start date" required={isFieldRequired(fields, "requested_start_date", false)}>
                          <input className="input" type="date" value={requestedStartDate}
                            onChange={(e) => setRequestedStartDate(e.target.value)} />
                        </Field>
                      )}
                      {isFieldEnabled(fields, "requested_duration_weeks", true) && (
                        <Field label="Duration (weeks)" required={isFieldRequired(fields, "requested_duration_weeks", false)}>
                          <input className="input" type="number" min={1} value={requestedDurationWeeks}
                            onChange={(e) => setRequestedDurationWeeks(e.target.value)} />
                        </Field>
                      )}
                    </div>
                  )}
                </>
              )}

              <CustomQuestionsFields
                questions={questions}
                answers={answers}
                onChange={setAnswers}
              />

              <div className="flex gap-2 mt-1">
                <Button variant="outline" className="flex-1" onClick={() => setStep(1)}>Back</Button>
                <Button
                  className="flex-1"
                  disabled={submit.isPending || (cvRequired && !cv)}
                  onClick={() => submit.mutate()}
                >
                  {submit.isPending ? "Submitting…" : "Submit application"}
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
        {label}{required && <span className="text-destructive ml-0.5">*</span>}
      </label>
      {children}
    </div>
  )
}
