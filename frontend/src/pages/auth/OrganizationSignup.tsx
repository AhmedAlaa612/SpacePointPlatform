import { useState, type FormEvent } from "react"
import { Link } from "@tanstack/react-router"
import { Building2, Eye, EyeOff, Loader2, Lock, Mail, Phone, User as UserIcon } from "lucide-react"
import { PLAIN_LOGO } from "@/lib/logos"
import { Button } from "@/components/ui/button"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CityNameSelect } from "@/components/ui/CitySelect"
import { getErrorMessage } from "@/lib/utils"
import { organizationSignupApi } from "@/api/websiteEvents"
import { useAuth } from "@/context/AuthContext"

export function OrganizationSignup() {
  const { setCurrentUser, setActiveRole } = useAuth()
  const [orgNameLatin, setOrgNameLatin] = useState("")
  const [orgType, setOrgType] = useState("university")
  const [country, setCountry] = useState("AE")
  const [city, setCity] = useState("")
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const user = await organizationSignupApi({
        org_name_latin: orgNameLatin,
        org_type: orgType,
        country,
        city,
        full_name: fullName,
        email,
        phone,
        password,
      })
      setCurrentUser(user)
      setActiveRole("organization")
      window.location.href = "/organization/events"
    } catch (err) {
      setError(getErrorMessage(err, "Could not create organization account."))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="dark relative flex min-h-screen items-center justify-center bg-[#08040f] text-white px-4 py-10 overflow-hidden select-none">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.015)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.015)_1px,transparent_1px)] bg-[size:4rem_4rem] pointer-events-none opacity-40" />
      <div className="absolute top-[-10%] right-[-10%] w-[60%] h-[60%] rounded-full bg-[#a880ff]/10 blur-[130px] pointer-events-none" />

      <form
        onSubmit={onSubmit}
        className="relative z-10 w-full max-w-lg space-y-5 rounded-2xl border border-[#653f84]/40 bg-[#12091e]/90 backdrop-blur-xl p-8 shadow-2xl"
      >
        <div className="space-y-3 text-center">
          <img src={PLAIN_LOGO} alt="SpacePoint" className="mx-auto h-11 w-auto object-contain" />
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight text-white">
              Partner Organization Sign Up
            </h1>
            <p className="text-xs text-white/60">
              Create an organization account to add and customize your events on SpacePoint
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
              Organization Name *
            </label>
            <div className="relative">
              <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
              <input
                type="text"
                required
                placeholder="Abu Dhabi University / Space Club"
                value={orgNameLatin}
                onChange={(e) => setOrgNameLatin(e.target.value)}
                className="w-full h-11 pl-11 pr-4 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Type
              </label>
              <select
                value={orgType}
                onChange={(e) => setOrgType(e.target.value)}
                className="w-full h-11 px-3 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              >
                <option value="university">University</option>
                <option value="school">School</option>
                <option value="company">Company</option>
                <option value="government">Government</option>
                <option value="ngo">Club / NGO</option>
                <option value="other">Other</option>
              </select>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Country
              </label>
              <CountrySelect
                value={country}
                onChange={setCountry}
                valueType="code"
                placeholder="Select country..."
                className="w-full h-11 px-3 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                City
              </label>
              <CityNameSelect
                country={country}
                value={city}
                onChange={setCity}
                placeholder="Select city..."
                className="w-full h-11 px-3 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
              Representative Full Name *
            </label>
            <div className="relative">
              <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
              <input
                type="text"
                required
                placeholder="Your Full Name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full h-11 pl-11 pr-4 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Work Email *
              </label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                <input
                  type="email"
                  required
                  placeholder="name@organization.ae"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full h-11 pl-11 pr-3 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Phone *
              </label>
              <div className="relative">
                <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                <input
                  type="tel"
                  required
                  placeholder="+971 50 000 0000"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full h-11 pl-11 pr-3 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
                />
              </div>
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
              Password *
            </label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
              <input
                type={showPassword ? "text" : "password"}
                required
                minLength={6}
                placeholder="At least 6 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full h-11 pl-11 pr-11 rounded-xl border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none focus:border-[#a880ff]"
              />
              <button
                type="button"
                tabIndex={-1}
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-white/50 hover:text-white"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>
        </div>

        {error && (
          <div className="rounded-xl border border-white/20 bg-white/5 px-4 py-3 text-xs text-white text-center">
            {error}
          </div>
        )}

        <Button
          type="submit"
          disabled={busy || !orgNameLatin || !fullName || !email || !password}
          className="w-full h-11 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-[#653f84] to-[#7e4fa3] hover:from-[#583574] hover:to-[#6d438f] transition-all"
        >
          {busy ? (
            <>
              <Loader2 className="mr-2 size-4 animate-spin" />
              Creating Organization Account...
            </>
          ) : (
            "Create Organization Account & Continue"
          )}
        </Button>

        <div className="text-center text-xs text-white/60 pt-1">
          Already have an account?{" "}
          <Link to="/login" className="text-[#a880ff] hover:underline font-medium">
            Sign in
          </Link>
        </div>
      </form>
    </div>
  )
}
export default OrganizationSignup
