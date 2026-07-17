import { useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { ChevronRight, Upload, CheckCircle2 } from "lucide-react"
import { getApplyQuestionsApi, submitApplicationApi } from "@/api/apply"
import { applyInstructorApi } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const ROLE_LABEL: Record<string, string> = {
  ambassador: "Ambassador",
  intern: "Intern",
  teacher: "Teacher",
  facilitator: "Facilitator",
  instructor: "Instructor",
}

const ROLES_WITH_CV = new Set(["ambassador", "intern", "teacher", "facilitator"])
const ROLES_REQUIRING_CODE = new Set(["teacher", "instructor"])
const ROLES_WITH_QUESTIONS = new Set(["intern", "teacher", "facilitator"])

interface Props {
  role: string
  prefillCode?: string
}

export default function ApplyFlow({ role, prefillCode }: Props) {
  const navigate = useNavigate()

  // Step 2 exists when the role has questions OR a CV upload (ambassador has
  // no questions but still uploads a CV).
  const hasStep2 = ROLES_WITH_QUESTIONS.has(role) || ROLES_WITH_CV.has(role)

  // Step 1 fields
  const [step, setStep] = useState(1)
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [country, setCountry] = useState("")
  const [password, setPassword] = useState("")
  const [inviteCode, setInviteCode] = useState(prefillCode ?? "")
  const [cv, setCv] = useState<File | null>(null)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: questions = [] } = useQuery({
    queryKey: ["apply-questions", role],
    queryFn: () => getApplyQuestionsApi(role),
    enabled: ROLES_WITH_QUESTIONS.has(role),
  })

  const submit = useMutation({
    mutationFn: async () => {
      setError(null)
      if (role === "instructor") {
        const user = await applyInstructorApi({
          full_name: fullName, email, password,
          invite_code: inviteCode, country: country || "United Arab Emirates",
        })
        return { instructor: true, user }
      }
      const form = new FormData()
      form.append("full_name", fullName)
      form.append("email", email)
      form.append("password", password)
      if (phone)      form.append("phone", phone)
      if (country)    form.append("country", country)
      if (inviteCode) form.append("invite_code", inviteCode)
      if (cv)         form.append("cv", cv)
      form.append("answers", JSON.stringify(answers))
      return submitApplicationApi(role, form)
    },
    onSuccess: (data: any) => {
      if (data?.instructor) {
        // Auto-logged in — navigate to their portal
        navigate({ to: "/instructors/status" })
      } else {
        setDone(true)
      }
    },
    onError: (e: any) => {
      setError(e?.response?.data?.detail ?? "Something went wrong. Please try again.")
    },
  })

  const step1Valid = fullName.trim() && email.trim() && password.length >= 6 &&
    (!ROLES_REQUIRING_CODE.has(role) || inviteCode.trim())

  if (done) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
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
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
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
              {(ROLES_REQUIRING_CODE.has(role) || prefillCode) && (
                <Field label="Invite code" required={ROLES_REQUIRING_CODE.has(role)}>
                  <input className="input" placeholder="e.g. AB12CD" value={inviteCode}
                    onChange={(e) => setInviteCode(e.target.value.toUpperCase())} />
                </Field>
              )}
              <Field label="Full name" required>
                <input className="input" placeholder="Your full name" value={fullName}
                  onChange={(e) => setFullName(e.target.value)} />
              </Field>
              <Field label="Email" required>
                <input className="input" type="email" placeholder="you@email.com" value={email}
                  onChange={(e) => setEmail(e.target.value)} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="WhatsApp">
                  <input className="input" placeholder="+20 10 0000 0000" value={phone}
                    onChange={(e) => setPhone(e.target.value)} />
                </Field>
                <Field label="Country">
                  <input className="input" placeholder="Egypt" value={country}
                    onChange={(e) => setCountry(e.target.value)} />
                </Field>
              </div>
              <Field label="Password" required>
                <input className="input" type="password" placeholder="Min. 6 characters" value={password}
                  onChange={(e) => setPassword(e.target.value)} />
              </Field>

              <Button
                className="mt-1 w-full"
                disabled={!step1Valid || submit.isPending}
                onClick={() => {
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
              {ROLES_WITH_CV.has(role) && (
                <Field label="CV / Resume" required>
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

              {questions.map((q) => (
                <Field key={q.id} label={q.question_text} required={q.required}>
                  {q.question_type === "radio" || q.question_type === "multiple_choice" ? (
                    <div className="flex flex-col gap-2">
                      {q.options.map((opt) => (
                        <label key={opt} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                          <input
                            type={q.question_type === "multiple_choice" ? "checkbox" : "radio"}
                            name={q.id}
                            value={opt}
                            checked={
                              q.question_type === "multiple_choice"
                                ? (answers[q.id] ?? "").split(",").includes(opt)
                                : answers[q.id] === opt
                            }
                            onChange={(e) => {
                              if (q.question_type === "multiple_choice") {
                                const current = (answers[q.id] ?? "").split(",").filter(Boolean)
                                const next = e.target.checked
                                  ? [...current, opt]
                                  : current.filter((v) => v !== opt)
                                setAnswers({ ...answers, [q.id]: next.join(",") })
                              } else {
                                setAnswers({ ...answers, [q.id]: opt })
                              }
                            }}
                          />
                          {opt}
                        </label>
                      ))}
                    </div>
                  ) : (
                    <input
                      className="input"
                      type={q.question_type === "number" ? "number" : "text"}
                      value={answers[q.id] ?? ""}
                      onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
                    />
                  )}
                </Field>
              ))}

              <div className="flex gap-2 mt-1">
                <Button variant="outline" className="flex-1" onClick={() => setStep(1)}>Back</Button>
                <Button
                  className="flex-1"
                  disabled={submit.isPending || (ROLES_WITH_CV.has(role) && !cv)}
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
