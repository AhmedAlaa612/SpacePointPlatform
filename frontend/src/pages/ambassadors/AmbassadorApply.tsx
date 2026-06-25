import { useState } from "react"
import logo from "@/assets/logos/ambassador.svg"
import { Link } from "@tanstack/react-router"
import { CheckCircle2 } from "lucide-react"
import { applyAmbassadorApi } from "@/api/auth"
import { Button } from "@/components/ui/button"

export default function AmbassadorApplyPage() {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", country: "" })
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }))

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      await applyAmbassadorApi(form)
      setDone(true)
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Something went wrong.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-white dark:bg-zinc-950 flex flex-col items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center gap-2 justify-center">
          <img src={logo} alt="SpacePoint" className="h-10 w-auto object-contain" />
        </div>

        {done ? (
          <div className="text-center">
            <div className="w-14 h-14 mx-auto mb-3 rounded-full bg-green-50 text-green-600 flex items-center justify-center"><CheckCircle2 size={28} /></div>
            <h1 className="text-2xl font-bold text-foreground mb-2">Application received</h1>
            <p className="text-sm text-gray-500 mb-6">
              An administrator will review your application. You can sign in once approved.
            </p>
            <Link to="/login"><Button variant="outline" className="w-full">Back to sign in</Button></Link>
          </div>
        ) : (
          <>
            <h1 className="text-2xl font-bold text-foreground mb-1 tracking-tight">Become an ambassador</h1>
            <p className="text-sm text-gray-500 mb-8">Join the global education outreach network.</p>
            <form onSubmit={submit} className="flex flex-col gap-4">
              <input className="input" placeholder="Full name" value={form.full_name} onChange={set("full_name")} required />
              <input className="input" type="email" placeholder="Email" value={form.email} onChange={set("email")} required />
              <input className="input" placeholder="Country" value={form.country} onChange={set("country")} />
              <input className="input" type="password" placeholder="Password" value={form.password} onChange={set("password")} required />
              {error && <p className="text-sm text-red-500">{error}</p>}
              <Button type="submit" disabled={loading} className="mt-2">
                {loading ? "Submitting…" : "Submit application"}
              </Button>
            </form>
            <p className="text-sm text-gray-500 mt-6 text-center">
              Already have an account?{" "}
              <Link to="/login" className="text-heliotrope font-semibold hover:underline">Sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  )
}
