import { useEffect, useRef, useState } from "react"
import logo from "@/assets/logos/ambassador.svg"
import { Link, useParams } from "@tanstack/react-router"
import { CheckCircle2, ArrowLeft } from "lucide-react"
import type { ApplicationQuestion } from "@/types/ambassadors"
import { applyTeacherApi, validateInviteApi } from "@/api/auth"
import { getTeacherApplicationQuestionsApi } from "@/api/ambassadors/application"
import { Button } from "@/components/ui/button"

export default function TeacherApplyPage() {
  const { code } = useParams({ strict: false }) as { code?: string }
  const [ambassador, setAmbassador] = useState<string | null>(null)
  const [form, setForm] = useState({ full_name: "", email: "", password: "", invite_code: code ?? "" })
  const [answers, setAnswers] = useState<Record<string, string | string[]>>({})
  const [questions, setQuestions] = useState<ApplicationQuestion[]>([])
  const [questionsLoading, setQuestionsLoading] = useState(true)
  const [step, setStep] = useState<1 | 2>(1)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const step1Ref = useRef<HTMLFormElement>(null)

  useEffect(() => {
    getTeacherApplicationQuestionsApi()
      .then((q) => setQuestions(q))
      .catch(() => setQuestions([]))
      .finally(() => setQuestionsLoading(false))
  }, [])

  useEffect(() => {
    if (code) {
      validateInviteApi(code)
        .then((r) => setAmbassador(r.ambassador_name))
        .catch(() => setAmbassador(null))
    }
  }, [code])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const setAnswer = (questionId: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setAnswers((a) => ({ ...a, [questionId]: e.target.value }))

  const toggleCheckbox = (questionId: string, value: string) => {
    setAnswers((a) => {
      const current = Array.isArray(a[questionId]) ? (a[questionId] as string[]) : []
      const updated = current.includes(value) ? current.filter(v => v !== value) : [...current, value]
      return { ...a, [questionId]: updated }
    })
  }

  const goToStep2 = (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setStep(2)
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await applyTeacherApi({ ...form, answers })
      setDone(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }

  const hasQuestions = !questionsLoading && questions.length > 0

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2 justify-center">
          <img src={logo} alt="SpacePoint" className="h-10 w-auto object-contain" />
        </div>

        {done ? (
          <div className="text-center">
            <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-green-50 text-green-600 flex items-center justify-center">
              <CheckCircle2 size={28} />
            </div>
            <h1 className="text-2xl font-bold text-foreground mb-2">Application received</h1>
            <p className="text-sm text-gray-500 mb-6">Your ambassador will review and approve your account.</p>
            <Link to="/login"><Button variant="outline" className="w-full">Back to sign in</Button></Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-foreground mb-1 tracking-tight">Join as a teacher</h1>
            <p className="text-sm text-gray-500 mb-5">
              {code && ambassador ? `Invited by ${ambassador}.` : "Enter the invite code from your ambassador."}
            </p>

            {/* Step indicator ── only show when there are questions */}
            {hasQuestions && (
              <div className="flex items-center gap-2 mb-6">
                {[1, 2].map((n) => (
                  <div key={n} className="flex items-center gap-2">
                    <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold transition-colors ${step >= n ? "bg-foreground text-background" : "bg-muted text-muted-foreground"}`}>
                      {n}
                    </div>
                    {n < 2 && <div className={`h-px w-8 transition-colors ${step >= 2 ? "bg-foreground" : "bg-border"}`} />}
                  </div>
                ))}
                <span className="text-xs text-gray-400 ml-1">Step {step} of 2</span>
              </div>
            )}

            {/* Step 1 ── account details */}
            {step === 1 && (
              <form ref={step1Ref} onSubmit={hasQuestions ? goToStep2 : submit} className="flex flex-col gap-4">
                <input className="input" placeholder="Full name" value={form.full_name} onChange={set("full_name")} required />
                <input className="input" type="email" placeholder="Email" value={form.email} onChange={set("email")} required />
                <input className="input" type="password" placeholder="Password" value={form.password} onChange={set("password")} required />
                <input className="input" placeholder="Invite code" value={form.invite_code} onChange={set("invite_code")} />
                {error && <p className="text-sm text-red-500">{error}</p>}
                <Button type="submit" disabled={questionsLoading} className="mt-2">
                  {questionsLoading ? "Loading…" : hasQuestions ? "Next" : loading ? "Submitting…" : "Submit application"}
                </Button>
              </form>
            )}

            {/* Step 2 ── application questions */}
            {step === 2 && (
              <form onSubmit={submit} className="flex flex-col gap-4">
                {questions.map((q) => (
                  <div key={q.id}>
                    <label className="text-sm font-medium text-foreground block mb-1">
                      {q.question_text}
                      {q.required && <span className="text-red-500 ml-0.5">*</span>}
                    </label>
                    {q.question_type === "text" && (
                      <input
                        type="text"
                        className="input"
                        value={(answers[q.id] as string) ?? ""}
                        onChange={setAnswer(q.id)}
                        required={q.required}
                      />
                    )}
                    {q.question_type === "number" && (
                      <input
                        type="number"
                        className="input"
                        value={(answers[q.id] as string) ?? ""}
                        onChange={setAnswer(q.id)}
                        required={q.required}
                      />
                    )}
                    {q.question_type === "radio" && (
                      <div className="flex flex-col gap-2 mt-1">
                        {(q.options ?? []).map((opt) => (
                          <label key={opt} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                            <input
                              type="radio"
                              name={q.id}
                              value={opt}
                              checked={answers[q.id] === opt}
                              onChange={setAnswer(q.id)}
                              required={q.required && !answers[q.id]}
                            />
                            {opt}
                          </label>
                        ))}
                      </div>
                    )}
                    {q.question_type === "multiple_choice" && (
                      <div className="flex flex-col gap-2 mt-1">
                        {(q.options ?? []).map((opt) => (
                          <label key={opt} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                            <input
                              type="checkbox"
                              value={opt}
                              checked={Array.isArray(answers[q.id]) && (answers[q.id] as string[]).includes(opt)}
                              onChange={() => toggleCheckbox(q.id, opt)}
                            />
                            {opt}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                {error && <p className="text-sm text-red-500">{error}</p>}

                <div className="flex gap-3 mt-2">
                  <Button type="button" variant="outline" onClick={() => { setStep(1); setError("") }} className="gap-1.5">
                    <ArrowLeft size={15} /> Back
                  </Button>
                  <Button type="submit" disabled={loading} className="flex-1">
                    {loading ? "Submitting…" : "Submit application"}
                  </Button>
                </div>
              </form>
            )}
          </>
        )}
      </div>
    </div>
  )
}
