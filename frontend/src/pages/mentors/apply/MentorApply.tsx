import { type FormEvent, useEffect, useState } from "react"
import { Link } from "@tanstack/react-router"
import { DomainIcon } from "@/components/ui/DomainIcon"
import { ThemeToggle } from "@/components/layout/ThemeToggle"
import { SiteFooter } from "@/components/layout/SiteFooter"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { PasswordInput } from "@/components/ui/PasswordInput"
import { LinkedInIcon } from "@/components/icons/LinkedInIcon"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/primitives"
import { applyPublicMentorApi, getPublicMentorDomains } from "@/api/mentors"
import type { MentorDomain } from "@/types/mentors"
import { cn } from "@/lib/utils"
import {
  Building2,
  Calendar,
  CheckCircle2,
  AlertCircle,
  Mail,
  ArrowRight,
  ShieldCheck,
} from "lucide-react"

export default function MentorApply() {
  const [domains, setDomains] = useState<MentorDomain[]>([])
  const [loadingDomains, setLoadingDomains] = useState(true)

  // Form State
  const [fullName, setFullName] = useState("")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [phone, setPhone] = useState("")
  const [country, setCountry] = useState("AE")
  const [headline, setHeadline] = useState("")
  const [company, setCompany] = useState("")
  const [linkedinUrl, setLinkedinUrl] = useState("")
  const [selectedDomainIds, setSelectedDomainIds] = useState<string[]>([])
  const [bio, setBio] = useState("")
  const [missionsHistory, setMissionsHistory] = useState("")
  const [whatICanHelpWith, setWhatICanHelpWith] = useState("")
  const [contactMode, setContactMode] = useState<"calendar" | "email">("calendar")
  const [contactEmail, setContactEmail] = useState("")

  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  useEffect(() => {
    getPublicMentorDomains()
      .then((data) => {
        setDomains(data.filter((d) => d.is_active))
      })
      .catch((err) => console.error("Failed to load domains", err))
      .finally(() => setLoadingDomains(false))
  }, [])

  const toggleDomain = (id: string) => {
    setSelectedDomainIds((prev) =>
      prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id]
    )
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setErrorMsg(null)

    if (!fullName.trim() || !email.trim() || !password.trim() || !headline.trim()) {
      setErrorMsg("Please fill in all required fields marked with *.")
      return
    }

    if (password.length < 8) {
      setErrorMsg("Password must be at least 8 characters long.")
      return
    }

    try {
      setSubmitting(true)
      await applyPublicMentorApi({
        full_name: fullName.trim(),
        email: email.trim().toLowerCase(),
        password: password,
        phone: phone.trim() || undefined,
        country: country || undefined,
        headline: headline.trim(),
        company: company.trim() || undefined,
        linkedin_url: linkedinUrl.trim() || undefined,
        bio: bio.trim() || undefined,
        missions_history: missionsHistory.trim() || undefined,
        what_i_can_help_with: whatICanHelpWith.trim() || undefined,
        contact_mode: contactMode,
        contact_email: contactEmail.trim().toLowerCase() || undefined,
        domain_ids: selectedDomainIds,
      })
      setSubmitted(true)
      window.scrollTo({ top: 0, behavior: "smooth" })
    } catch (err: any) {
      console.error("Mentor application failed", err)
      const detail = err.response?.data?.detail
      if (typeof detail === "string") {
        setErrorMsg(detail)
      } else if (Array.isArray(detail)) {
        setErrorMsg(detail.map((d: any) => d.msg).join(", "))
      } else {
        setErrorMsg("Failed to submit mentor application. Please verify your entries and try again.")
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col justify-between selection:bg-primary/20">
      {/* Top Navigation */}
      <header className="border-b border-border/60 bg-background/80 backdrop-blur-md sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <DomainIcon label="Mentors" className="h-10 w-auto" />
          </Link>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <Link
              to="/login"
              className="text-xs font-medium text-muted-foreground hover:text-foreground transition-colors px-3 py-1.5"
            >
              Sign In
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-4xl mx-auto px-4 sm:px-6 py-12 w-full">
        {submitted ? (
          <div className="max-w-xl mx-auto py-12 text-center flex flex-col items-center gap-6 animate-in fade-in zoom-in-95 duration-300">
            <div className="w-20 h-20 rounded-3xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 flex items-center justify-center shadow-lg shadow-emerald-500/10">
              <CheckCircle2 size={42} strokeWidth={2.2} />
            </div>

            <div className="space-y-2">
              <h1 className="font-display text-3xl font-extrabold text-foreground tracking-tight">
                Application Received!
              </h1>
              <p className="text-muted-foreground text-sm leading-relaxed max-w-md mx-auto">
                Thank you for applying to the SpacePoint Mentorship Network,{" "}
                <span className="font-semibold text-foreground">{fullName}</span>.
              </p>
            </div>

            <div className="rounded-2xl border border-border/80 bg-card p-6 text-left space-y-3 shadow-sm w-full">
              <div className="flex items-start gap-3">
                <ShieldCheck size={18} className="text-primary mt-0.5 shrink-0" />
                <div className="text-xs space-y-1">
                  <p className="font-semibold text-foreground">What happens next?</p>
                  <p className="text-muted-foreground leading-relaxed">
                    Our Operations team reviews your aerospace experience and credentials within 1-2 business days.
                    Once approved, you will be notified at{" "}
                    <span className="font-mono font-medium text-foreground">{email}</span>.
                  </p>
                </div>
              </div>
              <div className="flex items-start gap-3 pt-3 border-t border-border/60">
                <Calendar size={18} className="text-primary mt-0.5 shrink-0" />
                <div className="text-xs space-y-1">
                  <p className="font-semibold text-foreground">Account Created</p>
                  <p className="text-muted-foreground leading-relaxed">
                    Your account has been prepared with your chosen password. You will be able to log in to configure your availability schedule and manage sessions as soon as your profile is activated.
                  </p>
                </div>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 pt-4 w-full sm:w-auto">
              <Button asChild className="w-full sm:w-auto rounded-xl px-6 h-11 font-semibold gap-2 shadow-sm">
                <Link to="/login">
                  <span>Go to Sign In</span>
                  <ArrowRight size={16} />
                </Link>
              </Button>
              <Button asChild variant="outline" className="w-full sm:w-auto rounded-xl px-6 h-11 font-semibold">
                <Link to="/">Back to Home</Link>
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-10">
            {/* Header Hero */}
            <div className="space-y-3 text-center sm:text-left">
              <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight">
                Apply as a Space &amp; Satellite Mentor
              </h1>
              <p className="text-sm sm:text-base text-muted-foreground max-w-2xl leading-relaxed">
                Share your satellite engineering, payload design, and mission operations expertise with universities,
                aspiring researchers, and CubeSat mission teams worldwide.
              </p>
            </div>

            {errorMsg && (
              <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive flex items-center gap-3 animate-in fade-in">
                <AlertCircle size={18} className="shrink-0" />
                <span>{errorMsg}</span>
              </div>
            )}

            {/* Application Form */}
            <form onSubmit={handleSubmit} className="flex flex-col gap-8">
              {/* Section 1: User Account & Authentication */}
              <div className="rounded-2xl border border-border/80 bg-card p-6 sm:p-8 flex flex-col gap-6 shadow-sm">
                <div>
                  <h2 className="font-display text-lg font-bold text-foreground">1. Account Credentials</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Your login details for the SpacePoint platform.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Full Name *
                    </label>
                    <input
                      type="text"
                      placeholder="Dr. Sarah Johnson"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Email Address *
                    </label>
                    <input
                      type="email"
                      placeholder="sarah.johnson@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Password *
                    </label>
                    <PasswordInput
                      placeholder="Minimum 8 characters"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Phone Number (Optional)
                    </label>
                    <input
                      type="tel"
                      placeholder="+971 50 123 4567"
                      value={phone}
                      onChange={(e) => setPhone(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Country of Residence
                    </label>
                    <CountrySelect
                      value={country}
                      onChange={setCountry}
                      valueType="code"
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                    />
                  </div>
                </div>
              </div>

              {/* Section 2: Professional Profile & Aerospace Experience */}
              <div className="rounded-2xl border border-border/80 bg-card p-6 sm:p-8 flex flex-col gap-6 shadow-sm">
                <div>
                  <h2 className="font-display text-lg font-bold text-foreground">2. Aerospace Advisory Profile</h2>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Displayed on your public SpacePoint mentor listing for mission teams and organizations.
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Professional Headline *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Lead Avionics Systems Engineer · CubeSat Bus Architecture"
                      value={headline}
                      onChange={(e) => setHeadline(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                      required
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Building2 size={13} />
                      <span>Company / Organization</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Space Dynamics Lab, MBRSC, or Independent"
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <LinkedInIcon className="w-3.5 h-3.5" />
                      <span>LinkedIn Profile</span>
                    </label>
                    <input
                      type="text"
                      placeholder="https://linkedin.com/in/username"
                      value={linkedinUrl}
                      onChange={(e) => setLinkedinUrl(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                    />
                  </div>

                  {/* Areas of Support Topics */}
                  <div className="flex flex-col gap-2.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Areas of Support & Technical Topics
                    </label>
                    {loadingDomains ? (
                      <Spinner />
                    ) : (
                      <div className="flex flex-wrap gap-2 pt-1">
                        {domains.map((domain) => {
                          const isSelected = selectedDomainIds.includes(domain.id)
                          return (
                            <button
                              key={domain.id}
                              type="button"
                              onClick={() => toggleDomain(domain.id)}
                              className={cn(
                                "text-xs font-semibold px-3 py-1.5 rounded-lg border transition-all cursor-pointer select-none",
                                isSelected
                                  ? "bg-primary text-primary-foreground border-primary shadow-xs"
                                  : "bg-muted/40 text-muted-foreground border-border hover:border-primary/40 hover:text-foreground"
                              )}
                            >
                              {domain.name}
                            </button>
                          )
                        })}
                      </div>
                    )}
                  </div>

                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Biography & Professional Background
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Summarize your engineering journey, key space missions, research areas, or mentoring philosophy."
                      value={bio}
                      onChange={(e) => setBio(e.target.value)}
                      className="p-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm resize-y leading-relaxed"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Mission / Project Experience
                    </label>
                    <textarea
                      rows={2}
                      placeholder="e.g. 3U CubeSat ADCS lead; Ground Station deployment at 437 MHz; sub-orbital payload integration."
                      value={missionsHistory}
                      onChange={(e) => setMissionsHistory(e.target.value)}
                      className="p-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm resize-y leading-relaxed"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5 sm:col-span-2">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      What You Can Help With
                    </label>
                    <textarea
                      rows={2}
                      placeholder="e.g. Reviewing CDR packages, link budget calculation, flight software review..."
                      value={whatICanHelpWith}
                      onChange={(e) => setWhatICanHelpWith(e.target.value)}
                      className="p-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm resize-y leading-relaxed"
                    />
                  </div>

                  {/* Preferred Interaction Mode */}
                  <div className="flex flex-col gap-2 sm:col-span-2 pt-2 border-t border-border/60">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Preferred Mentorship Format
                    </label>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div
                        onClick={() => setContactMode("calendar")}
                        className={cn(
                          "rounded-xl border p-4 cursor-pointer transition-all flex items-start gap-3 select-none",
                          contactMode === "calendar"
                            ? "border-primary bg-primary/5 ring-1 ring-primary/40 shadow-xs"
                            : "border-border bg-card/60 hover:bg-muted/30"
                        )}
                      >
                        <Calendar size={18} className="text-primary mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-bold text-foreground">30-Minute Video Consultations</p>
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            Set weekly availability slots for mission teams to book 1-on-1 virtual sessions.
                          </p>
                        </div>
                      </div>

                      <div
                        onClick={() => setContactMode("email")}
                        className={cn(
                          "rounded-xl border p-4 cursor-pointer transition-all flex items-start gap-3 select-none",
                          contactMode === "email"
                            ? "border-primary bg-primary/5 ring-1 ring-primary/40 shadow-xs"
                            : "border-border bg-card/60 hover:bg-muted/30"
                        )}
                      >
                        <Mail size={18} className="text-primary mt-0.5 shrink-0" />
                        <div>
                          <p className="text-xs font-bold text-foreground">Written Inquiries Only</p>
                          <p className="text-[11px] text-muted-foreground mt-0.5">
                            Receive direct technical advisory questions via verified email inquiries.
                          </p>
                        </div>
                      </div>
                    </div>

                    {contactMode === "email" && (
                      <div className="flex flex-col gap-1.5 pt-2 animate-in fade-in">
                        <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                          Direct Contact Email (Optional)
                        </label>
                        <input
                          type="email"
                          placeholder={email || "inquiries@example.com"}
                          value={contactEmail}
                          onChange={(e) => setContactEmail(e.target.value)}
                          className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                        />
                        <span className="text-[10px] text-muted-foreground">
                          If omitted, inquiries will be routed to your account email address.
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* Submit Action */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-2">
                <p className="text-xs text-muted-foreground">
                  By applying, you agree to the SpacePoint platform guidelines and mentorship code of conduct.
                </p>
                <Button
                  type="submit"
                  disabled={submitting}
                  className="rounded-xl px-8 h-12 font-bold text-sm gap-2 shadow-md shrink-0"
                >
                  {submitting ? (
                    <>
                      <Spinner />
                      <span>Submitting Application...</span>
                    </>
                  ) : (
                    <>
                      <span>Submit Application</span>
                      <ArrowRight size={16} />
                    </>
                  )}
                </Button>
              </div>
            </form>
          </div>
        )}
      </main>

      <SiteFooter />
    </div>
  )
}
