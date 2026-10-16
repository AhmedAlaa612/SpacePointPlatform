import { type FormEvent, useEffect, useState } from "react"
import { Link } from "@tanstack/react-router"
import { bookMentorSession, getPublicMentorDomains, getPublicMentors } from "@/api/mentors"
import type { MentorDomain, MentorProfile } from "@/types/mentors"
import { Spinner, EmptyState } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Search,
  Building2,
  Briefcase,
  Mail,
  ArrowRight,
  Globe,
  CheckCircle2,
  X,
  Send,
  AlertCircle,
} from "lucide-react"
import { LinkedInIcon } from "@/components/icons/LinkedInIcon"

export default function PublicDirectory() {
  const [mentors, setMentors] = useState<MentorProfile[]>([])
  const [domains, setDomains] = useState<MentorDomain[]>([])
  const [selectedDomain, setSelectedDomain] = useState<string>("")
  const [search, setSearch] = useState<string>("")
  const [loading, setLoading] = useState<boolean>(true)

  // Contact Modal State
  const [contactingMentor, setContactingMentor] = useState<MentorProfile | null>(null)
  const [senderName, setSenderName] = useState<string>("")
  const [senderEmail, setSenderEmail] = useState<string>("")
  const [messageTopic, setMessageTopic] = useState<string>("")
  const [sendingInquiry, setSendingInquiry] = useState<boolean>(false)
  const [inquirySuccess, setInquirySuccess] = useState<boolean>(false)
  const [inquiryError, setInquiryError] = useState<string | null>(null)

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true)
        const [mentorsData, domainsData] = await Promise.all([
          getPublicMentors(),
          getPublicMentorDomains(),
        ])
        setMentors(mentorsData)
        setDomains(domainsData)
      } catch (err) {
        console.error("Failed to load mentors directory", err)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  const filteredMentors = mentors.filter((m) => {
    if (selectedDomain) {
      const hasDomain = m.domains.some((d) => d.slug === selectedDomain)
      if (!hasDomain) return false
    }
    if (search.trim()) {
      const q = search.toLowerCase()
      const matchName = m.user_full_name?.toLowerCase().includes(q)
      const matchCompany = m.company?.toLowerCase().includes(q)
      const matchHeadline = m.headline?.toLowerCase().includes(q)
      const matchBio = m.bio?.toLowerCase().includes(q)
      if (!matchName && !matchCompany && !matchHeadline && !matchBio) return false
    }
    return true
  })

  const handleSendInquiry = async (e: FormEvent) => {
    e.preventDefault()
    if (!contactingMentor) return
    if (!senderName.trim() || !senderEmail.trim() || !messageTopic.trim()) {
      setInquiryError("Please fill out all required fields.")
      return
    }

    try {
      setSendingInquiry(true)
      setInquiryError(null)
      await bookMentorSession(contactingMentor.slug, {
        mentee_name: senderName,
        mentee_email: senderEmail,
        topics: messageTopic,
        booking_type: "inquiry",
      })
      setInquirySuccess(true)
    } catch (err: any) {
      setInquiryError(err.response?.data?.detail || "Failed to send message. Please try again.")
    } finally {
      setSendingInquiry(false)
    }
  }

  const closeContactModal = () => {
    setContactingMentor(null)
    setSenderName("")
    setSenderEmail("")
    setMessageTopic("")
    setInquirySuccess(false)
    setInquiryError(null)
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto w-full px-4 sm:px-6 py-6">
      
      {/* 1. Breadcrumbs */}
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <span>Portal</span>
        <span>/</span>
        <span className="text-primary font-medium">Mentors</span>
      </div>

      {/* 2. Page Headline & Subtext */}
      <div className="space-y-1.5">
        <h1 className="font-display text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-foreground">
          Find Space Mentors in Satellite Engineering &amp; Operations
        </h1>
        <p className="text-xs sm:text-sm text-muted-foreground">
          1-on-1 technical advisory sessions with experienced aerospace engineers.
        </p>
      </div>

      {/* 3. Search Bar */}
      <div className="flex flex-col sm:flex-row items-center gap-3">
        <div className="relative flex-1 w-full">
          <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-primary pointer-events-none" />
          <input
            type="text"
            placeholder="Search by mentor name, company, or subsystem..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-11 pl-10 pr-10 w-full border border-border bg-card text-foreground placeholder:text-muted-foreground rounded-xl text-xs sm:text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              className="absolute right-3.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground text-xs"
            >
              Clear
            </button>
          )}
        </div>
      </div>

      {/* 4. Sleek Topics Navigation (NO BOXES) */}
      <div className="flex items-center gap-6 sm:gap-8 overflow-x-auto pb-3 border-b border-border/70 scrollbar-none">
        <button
          onClick={() => setSelectedDomain("")}
          className={cn(
            "flex items-center gap-2 text-xs relative pb-2.5 shrink-0 transition-colors cursor-pointer",
            selectedDomain === ""
              ? "font-bold text-foreground"
              : "font-medium text-muted-foreground hover:text-foreground"
          )}
        >
          <Globe size={15} className={cn(selectedDomain === "" ? "text-primary" : "text-muted-foreground")} />
          <span>All Topics</span>
          <span className={cn(
            "text-[10px] px-1.5 py-0.2 rounded font-semibold",
            selectedDomain === "" ? "bg-primary/15 text-primary" : "text-muted-foreground"
          )}>
            {mentors.length}
          </span>
          {selectedDomain === "" && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
          )}
        </button>

        {domains.map((d) => {
          const isSelected = selectedDomain === d.slug
          const domainMentorsCount = mentors.filter((m) => m.domains.some((dom) => dom.slug === d.slug)).length
          return (
            <button
              key={d.id}
              onClick={() => setSelectedDomain(d.slug)}
              className={cn(
                "flex items-center gap-2 text-xs relative pb-2.5 shrink-0 transition-colors cursor-pointer",
                isSelected
                  ? "font-bold text-foreground"
                  : "font-medium text-muted-foreground hover:text-foreground"
              )}
            >
              <span>{d.name}</span>
              {domainMentorsCount > 0 && (
                <span className={cn(
                  "text-[10px] px-1.5 py-0.2 rounded font-semibold",
                  isSelected ? "bg-primary/15 text-primary" : "text-muted-foreground"
                )}>
                  {domainMentorsCount}
                </span>
              )}
              {isSelected && (
                <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
              )}
            </button>
          )
        })}
      </div>

      {/* 5. Horizontal Mentor Cards List (Preply-Style) */}
      {loading ? (
        <Spinner />
      ) : filteredMentors.length === 0 ? (
        <EmptyState
          title="No mentors found"
          hint="Try selecting a different topic filter or clearing your search query."
        />
      ) : (
        <div className="flex flex-col gap-5">
          {filteredMentors.map((mentor) => {
            const initial = mentor.user_full_name?.charAt(0).toUpperCase() || "M"
            const reviewsCount = Math.max(1, mentor.completed_sessions_count)
            return (
              <div
                key={mentor.id}
                className="rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm hover:border-primary/50 transition-all duration-300 flex flex-col lg:flex-row gap-6 justify-between items-start"
              >
                {/* Left Column: Full Rectangular Photo (NOT a circle) */}
                <div className="w-full sm:w-44 lg:w-48 h-52 sm:h-56 rounded-xl overflow-hidden border border-border/80 bg-muted/20 shrink-0 relative shadow-inner">
                  {(mentor.photo_url || mentor.user_photo_url) ? (
                    <img
                      src={(mentor.photo_url || mentor.user_photo_url)!}
                      alt={mentor.user_full_name || "Mentor"}
                      className="w-full h-full object-cover hover:scale-105 transition-transform duration-500"
                      onError={(e) => {
                        e.currentTarget.style.display = "none"
                      }}
                    />
                  ) : (
                    <div className="w-full h-full bg-gradient-to-b from-[#231134] via-[#140A21] to-[#05030A] flex flex-col items-center justify-center relative overflow-hidden p-4">
                      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(167,125,255,0.18),transparent_60%)]" />
                      <div className="w-24 h-24 rounded-2xl border-2 border-primary/40 bg-primary/10 text-primary font-display font-extrabold text-4xl flex items-center justify-center shadow-2xl relative z-10 backdrop-blur-sm">
                        {initial}
                      </div>
                      <span className="text-[11px] font-semibold text-[#a79fb8] tracking-wider uppercase mt-3 relative z-10">
                        Space Mentor
                      </span>
                    </div>
                  )}
                </div>

                {/* Middle Column: Details (Role, Affiliation, Areas of Support, Description) */}
                <div className="flex-1 space-y-3 min-w-0">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link to={`/mentors/${mentor.slug}` as any}>
                        <h2 className="font-display text-xl font-bold text-foreground hover:text-primary transition-colors">
                          {mentor.user_full_name}
                        </h2>
                      </Link>
                      {mentor.user_country && (
                        <span className="text-[11px] font-semibold text-muted-foreground px-1.5 py-0.5 bg-muted rounded">
                          {mentor.user_country}
                        </span>
                      )}
                      {mentor.linkedin_url && (
                        <a
                          href={mentor.linkedin_url.startsWith("http") ? mentor.linkedin_url : `https://${mentor.linkedin_url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center hover:opacity-80 transition-opacity"
                          title="LinkedIn Profile"
                        >
                          <LinkedInIcon className="w-4 h-4 rounded-[3px]" />
                        </a>
                      )}
                    </div>

                    {/* Role */}
                    {mentor.headline && (
                      <p className="text-xs sm:text-sm font-semibold text-primary flex items-center gap-1.5">
                        <Briefcase size={14} className="shrink-0" />
                        <span>{mentor.headline}</span>
                      </p>
                    )}

                    {/* Affiliation */}
                    {mentor.company && (
                      <p className="text-xs sm:text-sm text-muted-foreground flex items-center gap-1.5">
                        <Building2 size={14} className="shrink-0" />
                        <span>{mentor.company}</span>
                      </p>
                    )}
                  </div>

                  {/* Areas of Support */}
                  {mentor.domains.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                        Areas of Support:
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {mentor.domains.map((d) => (
                          <span
                            key={d.id}
                            className="text-xs bg-primary/10 text-primary border border-primary/20 px-2.5 py-1 rounded-lg font-medium"
                          >
                            {d.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Description / Bio */}
                  {mentor.bio && (
                    <div className="pt-1">
                      <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed line-clamp-3">
                        {mentor.bio}
                      </p>
                      <Link
                        to={`/mentors/${mentor.slug}` as any}
                        className="text-xs text-primary font-semibold hover:underline inline-block mt-1"
                      >
                        View Full Profile &amp; Experience →
                      </Link>
                    </div>
                  )}
                </div>

                {/* Right Column: Pricing, Stats, & Dual Action CTAs */}
                <div className="w-full lg:w-64 flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-border/80 pt-4 lg:pt-0 lg:pl-6 space-y-4 shrink-0">
                  <div>
                    <span className="font-display text-lg font-bold text-foreground">
                      {mentor.session_duration_minutes || 30}-min session
                    </span>
                  </div>

                  {/* Stats: Number of sessions delivered & reviews */}
                  <div className="flex items-center gap-4 py-2 border-y border-border/60">
                    <div>
                      <div className="font-bold text-foreground text-sm">
                        {mentor.completed_sessions_count || 0}
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        sessions delivered
                      </span>
                    </div>
                    <div className="w-px h-8 bg-border/60" />
                    <div>
                      <div className="font-bold text-foreground text-sm">
                        {reviewsCount}
                      </div>
                      <span className="text-[11px] text-muted-foreground">
                        reviews
                      </span>
                    </div>
                  </div>

                  {/* Dual Action CTAs */}
                  <div className="flex flex-col gap-2 w-full">
                    <Link to={`/mentors/${mentor.slug}` as any} className="w-full">
                      <Button className="w-full rounded-xl font-semibold h-11 shadow-sm gap-2">
                        <span>Book Session</span>
                        <ArrowRight size={14} />
                      </Button>
                    </Link>
                    {mentor.show_contact_button !== false && (
                      <Button
                        variant="outline"
                        onClick={() => setContactingMentor(mentor)}
                        className="w-full rounded-xl font-medium h-10 border-border text-foreground hover:bg-muted/60"
                      >
                        <Mail size={14} className="mr-2 text-primary" />
                        <span>Contact Mentor</span>
                      </Button>
                    )}
                  </div>
                </div>

              </div>
            )
          })}
        </div>
      )}

      {/* 6. Quick Contact Modal */}
      {contactingMentor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in">
          <div className="relative w-full max-w-lg bg-card border border-border rounded-2xl p-6 shadow-2xl space-y-5">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-border/70 pb-4">
              <div>
                <h3 className="font-display text-lg font-bold text-foreground">
                  Contact {contactingMentor.user_full_name}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Send a direct technical question or inquiry to this mentor.
                </p>
              </div>
              <button
                onClick={closeContactModal}
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Content */}
            {inquirySuccess ? (
              <div className="py-6 text-center space-y-3">
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                  <CheckCircle2 size={24} />
                </div>
                <h4 className="font-display text-base font-bold text-foreground">
                  Inquiry Sent Successfully!
                </h4>
                <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                  {contactingMentor.user_full_name} has received your message and will reply to your email address shortly.
                </p>
                <div className="pt-2">
                  <Button onClick={closeContactModal} className="rounded-xl px-6">
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSendInquiry} className="space-y-4">
                {inquiryError && (
                  <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-center gap-2">
                    <AlertCircle size={14} />
                    <span>{inquiryError}</span>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Your Name</label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Sarah Connor"
                    value={senderName}
                    onChange={(e) => setSenderName(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Your Email Address</label>
                  <input
                    type="email"
                    required
                    placeholder="sarah@spaceorg.ae"
                    value={senderEmail}
                    onChange={(e) => setSenderEmail(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Message / Discussion Topic</label>
                  <textarea
                    required
                    rows={4}
                    placeholder="Briefly describe your discussion scope..."
                    value={messageTopic}
                    onChange={(e) => setMessageTopic(e.target.value)}
                    className="w-full p-3 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border/70">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={closeContactModal}
                    className="rounded-xl text-xs h-10 px-4"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={sendingInquiry}
                    className="rounded-xl text-xs h-10 px-5 gap-2"
                  >
                    {sendingInquiry ? (
                      <span>Sending…</span>
                    ) : (
                      <>
                        <span>Send Message</span>
                        <Send size={13} />
                      </>
                    )}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

    </div>
  )
}
