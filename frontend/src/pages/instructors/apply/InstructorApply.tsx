import { useEffect, useState } from "react"
import logo from "@/assets/logos/logo.png"
import { Link, useNavigate, useParams } from "@tanstack/react-router"
import { useAuth } from "@/context/AuthContext"
import { applyInstructorApi, validateInviteApi } from "@/api/auth"
import { Button } from "@/components/ui/button"

const DEGREES = ["High School", "Bachelors", "Masters", "PhD", "Other"]
const BACKGROUNDS = ["Aerospace", "Mechanical", "Electrical", "Computer Science", "Physics", "Other"]

export default function InstructorApplyPage() {
  const { code } = useParams({ strict: false }) as { code?: string }
  const navigate = useNavigate()
  const { setCurrentUser } = useAuth()
  const [referrer, setReferrer] = useState<string | null>(null)
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)

  const [form, setForm] = useState({
    full_name: "", email: "", password: "", invite_code: code ?? "",
    university: "", highest_degree: "", highest_degree_other: "",
    city_of_residence: "", background_other: "", has_own_transportation: false,
    country: "United Arab Emirates",
  })
  const [backgroundAreas, setBackgroundAreas] = useState<string[]>([])

  useEffect(() => {
    if (code) {
      validateInviteApi(code).then((r) => setReferrer(r.ambassador_name)).catch(() => setReferrer(null))
    }
  }, [code])

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const toggleBackground = (value: string) =>
    setBackgroundAreas((a) => (a.includes(value) ? a.filter((v) => v !== value) : [...a, value]))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const user = await applyInstructorApi({ ...form, background_areas: backgroundAreas })
      setCurrentUser(user)
      void navigate({ to: "/instructors/status" })
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex items-center gap-2 justify-center">
          <img src={logo} alt="SpacePoint" className="h-10 w-auto object-contain" />
        </div>

        <h1 className="text-2xl font-bold text-foreground mb-1 tracking-tight">Apply to become an instructor</h1>
        <p className="text-sm text-muted-foreground mb-2">Join the SpacePoint scholarship & instructor pipeline.</p>
        {referrer && <p className="text-sm text-primary mb-6">Referred by {referrer}</p>}

        <form onSubmit={submit} className="flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <input className="input" placeholder="Full name" value={form.full_name} onChange={set("full_name")} required />
            <input className="input" type="email" placeholder="Email" value={form.email} onChange={set("email")} required />
            <input className="input" type="password" placeholder="Password" value={form.password} onChange={set("password")} required />
            <input className="input" placeholder="Invite code" value={form.invite_code} onChange={set("invite_code")} required />
          </div>

          <hr className="border-border my-2" />
          <p className="text-sm font-semibold text-foreground">Background</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <input className="input" placeholder="University" value={form.university} onChange={set("university")} />
            <select className="input" value={form.highest_degree} onChange={set("highest_degree")}>
              <option value="">Highest degree…</option>
              {DEGREES.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            {form.highest_degree === "Other" && (
              <input className="input" placeholder="Specify degree" value={form.highest_degree_other} onChange={set("highest_degree_other")} />
            )}
            <input className="input" placeholder="City of residence" value={form.city_of_residence} onChange={set("city_of_residence")} />
            <input className="input" placeholder="Country" value={form.country} onChange={set("country")} />
          </div>

          <div>
            <p className="text-sm font-medium text-foreground mb-2">Background areas</p>
            <div className="flex flex-wrap gap-2">
              {BACKGROUNDS.map((b) => (
                <button
                  type="button" key={b} onClick={() => toggleBackground(b)}
                  className={`rounded-full px-3 py-1.5 text-xs font-medium border transition-colors ${
                    backgroundAreas.includes(b)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {b}
                </button>
              ))}
            </div>
            {backgroundAreas.includes("Other") && (
              <input className="input mt-2" placeholder="Specify other background" value={form.background_other} onChange={set("background_other")} />
            )}
          </div>

          <label className="flex items-center gap-2 text-sm text-foreground">
            <input
              type="checkbox" checked={form.has_own_transportation}
              onChange={(e) => setForm((f) => ({ ...f, has_own_transportation: e.target.checked }))}
            />
            I have my own transportation
          </label>

          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" disabled={loading} className="mt-2">
            {loading ? "Submitting…" : "Submit application"}
          </Button>
        </form>

        <p className="text-sm text-muted-foreground mt-6 text-center">
          Already have an account?{" "}
          <Link to="/login" className="text-heliotrope font-semibold hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  )
}
