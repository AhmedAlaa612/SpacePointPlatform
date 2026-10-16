import { type FormEvent, useEffect, useState, useMemo } from "react"
import { Link, useParams } from "@tanstack/react-router"
import { bookMentorSession, getMentorAvailableSlots, getPublicMentor } from "@/api/mentors"
import type { AvailableSlot, MentorBooking, MentorProfile } from "@/types/mentors"
import { Spinner } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  CheckCircle2,
  ArrowLeft,
  AlertCircle,
  Calendar as CalendarIcon,
  Clock,
  ChevronLeft,
  ChevronRight,
  Mail,
  Send,
  X,
  Building2,
  Award,
  MessageSquare,
} from "lucide-react"
import { LinkedInIcon } from "@/components/icons/LinkedInIcon"

export default function PublicProfile() {
  const { slug } = useParams({ strict: false }) as { slug: string }
  const [mentor, setMentor] = useState<MentorProfile | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)

  // Expandable bio state
  const [bioExpanded, setBioExpanded] = useState<boolean>(false)

  const clientTimeZone = useMemo(() => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
    } catch {
      return "UTC"
    }
  }, [])

  // Calendar dates list (next 14 days starting tomorrow in local time)
  const availableDates = useMemo(() => {
    const list: { dateStr: string; dayName: string; formattedDate: string; fullDateLabel: string }[] = []
    const now = new Date()
    for (let i = 1; i <= 14; i++) {
      const d = new Date(now)
      d.setDate(now.getDate() + i)
      const year = d.getFullYear()
      const month = String(d.getMonth() + 1).padStart(2, "0")
      const day = String(d.getDate()).padStart(2, "0")
      const dateStr = `${year}-${month}-${day}`
      const dayName = d.toLocaleDateString("en-US", { weekday: "short" }).toUpperCase()
      const formattedDate = d.toLocaleDateString("en-US", { day: "numeric", month: "short" })
      const fullDateLabel = d.toLocaleDateString("en-US", { day: "numeric", month: "short", year: "numeric" })
      list.push({ dateStr, dayName, formattedDate, fullDateLabel })
    }
    return list
  }, [])

  const [selectedDate, setSelectedDate] = useState<string>(
    availableDates[0]?.dateStr || new Date().toISOString().split("T")[0]
  )
  const [dateStartIndex, setDateStartIndex] = useState<number>(0)
  const visibleDates = availableDates.slice(dateStartIndex, dateStartIndex + 5)

  // Slots cache & current slots state
  const [slotsCache, setSlotsCache] = useState<Record<string, AvailableSlot[]>>({})
  const [loadingSlots, setLoadingSlots] = useState<boolean>(false)
  const [selectedSlot, setSelectedSlot] = useState<AvailableSlot | null>(null)

  // Booking Modal & Form state
  const [bookingModalOpen, setBookingModalOpen] = useState<boolean>(false)
  const [menteeName, setMenteeName] = useState<string>("")
  const [menteeEmail, setMenteeEmail] = useState<string>("")
  const [menteeAffiliation, setMenteeAffiliation] = useState<string>("")
  const [topics, setTopics] = useState<string>("")
  const [bookingSuccess, setBookingSuccess] = useState<MentorBooking | null>(null)
  const [submitting, setSubmitting] = useState<boolean>(false)
  const [bookingError, setBookingError] = useState<string | null>(null)

  // Contact Mentor Direct Inquiry Modal state
  const [contactModalOpen, setContactModalOpen] = useState<boolean>(false)
  const [inquiryName, setInquiryName] = useState<string>("")
  const [inquiryEmail, setInquiryEmail] = useState<string>("")
  const [inquiryAffiliation, setInquiryAffiliation] = useState<string>("")
  const [inquiryMessage, setInquiryMessage] = useState<string>("")
  const [inquirySending, setInquirySending] = useState<boolean>(false)
  const [inquirySuccess, setInquirySuccess] = useState<boolean>(false)
  const [inquiryError, setInquiryError] = useState<string | null>(null)

  useEffect(() => {
    async function loadMentor() {
      try {
        setLoading(true)
        setError(null)
        const data = await getPublicMentor(slug)
        setMentor(data)
      } catch (err: any) {
        setError(err.response?.data?.detail || "Mentor profile not found")
      } finally {
        setLoading(false)
      }
    }
    if (slug) {
      loadMentor()
    }
  }, [slug])

  // Load available slots whenever selectedDate or mentor changes
  useEffect(() => {
    async function fetchSlots() {
      if (!mentor || mentor.contact_mode !== "calendar" || !selectedDate) return
      if (slotsCache[selectedDate]) {
        return
      }
      try {
        setLoadingSlots(true)
        const slotsData = await getMentorAvailableSlots(slug, selectedDate, clientTimeZone)
        setSlotsCache((prev) => ({ ...prev, [selectedDate]: slotsData }))
      } catch (err) {
        console.error("Failed to load slots for", selectedDate, err)
      } finally {
        setLoadingSlots(false)
      }
    }
    fetchSlots()
  }, [mentor, selectedDate, slug, slotsCache, clientTimeZone])

  const currentSlots = slotsCache[selectedDate] || []

  const handlePrevDates = () => {
    setDateStartIndex((prev) => Math.max(0, prev - 1))
  }

  const handleNextDates = () => {
    setDateStartIndex((prev) => Math.min(availableDates.length - 5, prev + 1))
  }

  const selectedDateObj = availableDates.find((d) => d.dateStr === selectedDate)
  const selectedFullDateLabel = selectedDateObj ? selectedDateObj.fullDateLabel : selectedDate

  const handleOpenBookingModal = () => {
    if (mentor?.contact_mode === "calendar" && !selectedSlot) {
      setBookingError("Please select an available time slot first.")
      return
    }
    setBookingError(null)
    setBookingModalOpen(true)
  }

  const handleConfirmBooking = async (e: FormEvent) => {
    e.preventDefault()
    if (!menteeName.trim() || !menteeEmail.trim() || !topics.trim()) {
      setBookingError("Please fill out all required fields.")
      return
    }

    if (mentor?.contact_mode === "calendar" && !selectedSlot) {
      setBookingError("Please select an available time slot.")
      return
    }

    try {
      setSubmitting(true)
      setBookingError(null)
      const res = await bookMentorSession(slug, {
        mentee_name: menteeName,
        mentee_email: menteeEmail,
        affiliation: menteeAffiliation.trim() || null,
        topics: topics,
        booking_type: mentor?.contact_mode === "calendar" ? "session" : "inquiry",
        scheduled_start: selectedSlot ? selectedSlot.start : null,
      })
      setBookingSuccess(res)
    } catch (err: any) {
      setBookingError(err.response?.data?.detail || "Failed to submit booking. Please try again.")
    } finally {
      setSubmitting(false)
    }
  }

  const handleSendDirectInquiry = async (e: FormEvent) => {
    e.preventDefault()
    if (!inquiryName.trim() || !inquiryEmail.trim() || !inquiryMessage.trim()) {
      setInquiryError("Please complete all fields.")
      return
    }
    try {
      setInquirySending(true)
      setInquiryError(null)
      await bookMentorSession(slug, {
        mentee_name: inquiryName,
        mentee_email: inquiryEmail,
        affiliation: inquiryAffiliation.trim() || null,
        topics: inquiryMessage,
        booking_type: "inquiry",
        scheduled_start: null,
      })
      setInquirySuccess(true)
    } catch (err: any) {
      setInquiryError(err.response?.data?.detail || "Failed to deliver inquiry. Please try again.")
    } finally {
      setInquirySending(false)
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center bg-background text-foreground">
        <Spinner />
      </div>
    )
  }

  if (error || !mentor) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-20 text-center flex flex-col items-center gap-4">
        <div className="w-12 h-12 rounded-full bg-destructive/10 text-destructive flex items-center justify-center">
          <AlertCircle size={24} />
        </div>
        <p className="text-lg font-bold text-foreground">{error || "Mentor profile not found"}</p>
        <p className="text-xs text-muted-foreground max-w-sm">
          The requested mentor profile may be private, unpublished, or the link has changed.
        </p>
        <Link to="/mentors" className="mt-2">
          <Button variant="outline" className="rounded-xl">
            Return to Mentors Directory
          </Button>
        </Link>
      </div>
    )
  }

  const initial = mentor.user_full_name?.charAt(0).toUpperCase() || "M"
  const portraitUrl = mentor.photo_url || mentor.user_photo_url

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto w-full pb-20">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <Link
            to="/mentors"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={14} />
            <span>Mentors Directory</span>
          </Link>
          <span>/</span>
          <span className="text-foreground font-semibold truncate max-w-[200px] sm:max-w-none">
            {mentor.user_full_name}
          </span>
        </div>
      </div>

      {/* Main Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 items-start">
        {/* ── LEFT COLUMN: Open, Free-Flowing Profile (No Boxes, Big & High Weight) ──── */}
        <div className="lg:col-span-7 flex flex-col gap-10 sm:gap-12 pt-1">
          {/* Top Profile Header (Open layout matching example) */}
          <div className="flex flex-col sm:flex-row items-start gap-6 sm:gap-8">
            {/* Portrait Picture (Square/Rectangular frame with active indicator) */}
            <div className="w-28 h-32 sm:w-36 sm:h-44 rounded-2xl overflow-hidden border border-border shadow-md bg-muted/20 shrink-0 relative">
              {portraitUrl ? (
                <img
                  src={portraitUrl}
                  alt={mentor.user_full_name || "Mentor"}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full bg-gradient-to-br from-space-800 via-card to-space-900 flex items-center justify-center font-display font-bold text-4xl text-primary">
                  {initial}
                </div>
              )}
              <span className="absolute bottom-2.5 right-2.5 w-3.5 h-3.5 rounded-full bg-emerald-500 ring-2 ring-background" />
            </div>

            {/* Profile Info */}
            <div className="flex-1 space-y-2.5">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight">
                  {mentor.user_full_name}
                </h1>
                {mentor.user_country && (
                  <span className="text-xs px-2.5 py-0.5 rounded-full font-bold bg-muted text-foreground border border-border uppercase">
                    {mentor.user_country}
                  </span>
                )}
                {mentor.linkedin_url && (
                  <a
                    href={mentor.linkedin_url.startsWith("http") ? mentor.linkedin_url : `https://${mentor.linkedin_url}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center hover:opacity-85 transition-opacity shadow-sm"
                    title="View LinkedIn Profile"
                  >
                    <LinkedInIcon className="w-5 h-5 rounded-[4px]" />
                  </a>
                )}
              </div>

              <p className="text-base sm:text-lg font-semibold text-foreground/80 leading-snug">
                {mentor.headline || "Aerospace & Satellite Systems Engineer"}
              </p>

              {mentor.company && (
                <p className="text-sm sm:text-base font-semibold text-primary flex items-center gap-1.5">
                  <Building2 size={16} className="shrink-0" />
                  <span>{mentor.company}</span>
                </p>
              )}

              {/* Highlights List (Free text, clear and bold) */}
              <div className="space-y-1.5 pt-2 text-sm sm:text-base text-foreground/85 font-medium">
                <div className="flex items-center gap-2">
                  <Award size={16} className="text-primary shrink-0" />
                  <span>
                    <strong className="text-foreground font-bold">{mentor.completed_sessions_count || 0}</strong> sessions delivered
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock size={16} className="text-primary shrink-0" />
                  <span>
                    <strong className="text-foreground font-bold">Session format:</strong>{" "}
                    {mentor.contact_mode === "calendar"
                      ? `${mentor.session_duration_minutes || 30}-Min 1-on-1 via Google Meet`
                      : "Email Inquiry"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Section: About me (Free flowing, generous size & high weight) */}
          {mentor.bio && (
            <div className="space-y-3">
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                About me
              </h2>
              <div className="space-y-3">
                <p
                  className={cn(
                    "text-base sm:text-lg text-foreground/90 font-medium leading-relaxed whitespace-pre-line",
                    !bioExpanded && "line-clamp-5"
                  )}
                >
                  {mentor.bio}
                </p>
                {mentor.bio.length > 220 && (
                  <button
                    type="button"
                    onClick={() => setBioExpanded(!bioExpanded)}
                    className="font-bold text-foreground hover:underline text-sm sm:text-base cursor-pointer inline-block"
                  >
                    {bioExpanded ? "Show less ↑" : "Show more"}
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Section: Technical Experience (Free, no box) */}
          {mentor.missions_history && (
            <div className="space-y-3">
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Technical Experience
              </h2>
              <p className="text-base sm:text-lg text-foreground/90 font-medium leading-relaxed">
                {mentor.missions_history}
              </p>
            </div>
          )}

          {/* Section: What I can help with (Dynamic, free text, bold weight) */}
          {mentor.what_i_can_help_with && (
            <div className="space-y-3">
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                What I can help with
              </h2>
              <p className="text-base sm:text-lg text-foreground/90 font-medium leading-relaxed whitespace-pre-line">
                {mentor.what_i_can_help_with}
              </p>
            </div>
          )}
        </div>

        {/* ── RIGHT COLUMN (STICKY): Interactive Calendar ── */}
        <div className="lg:col-span-5 flex flex-col gap-6 lg:sticky lg:top-24">
          {/* Interactive Available Sessions & Calendar Card */}
          <div className="rounded-3xl border border-border bg-card p-6 shadow-md space-y-5">
            <div>
              <h2 className="font-display text-lg font-bold text-foreground">
                Available sessions
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                Book 1:1 sessions from the options based on your needs
              </p>
            </div>

            {mentor.contact_mode === "calendar" ? (
              <>
                {/* Horizontal Date Picker Carousel */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      Select Date
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={handlePrevDates}
                        disabled={dateStartIndex === 0}
                        className="p-1 rounded-lg border border-border bg-background hover:bg-muted text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        aria-label="Previous dates"
                      >
                        <ChevronLeft size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={handleNextDates}
                        disabled={dateStartIndex >= availableDates.length - 5}
                        className="p-1 rounded-lg border border-border bg-background hover:bg-muted text-muted-foreground hover:text-foreground disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        aria-label="Next dates"
                      >
                        <ChevronRight size={14} />
                      </button>
                    </div>
                  </div>

                  <div className="grid grid-cols-5 gap-1.5 sm:gap-2">
                    {visibleDates.map((item) => {
                      const isSelected = selectedDate === item.dateStr
                      return (
                        <button
                          key={item.dateStr}
                          type="button"
                          onClick={() => {
                            setSelectedDate(item.dateStr)
                            setSelectedSlot(null)
                          }}
                          className={cn(
                            "flex flex-col items-center justify-center py-2.5 px-1 rounded-xl transition-all border text-center cursor-pointer",
                            isSelected
                              ? "border-primary bg-primary/10 shadow-sm ring-1 ring-primary/30"
                              : "border-border bg-background hover:border-primary/40 text-muted-foreground"
                          )}
                        >
                          <span
                            className={cn(
                              "text-[10px] font-bold uppercase tracking-wider",
                              isSelected ? "text-primary" : "text-muted-foreground"
                            )}
                          >
                            {item.dayName}
                          </span>
                          <span
                            className={cn(
                              "text-xs sm:text-sm font-extrabold mt-0.5",
                              isSelected ? "text-foreground font-bold" : "text-foreground"
                            )}
                          >
                            {item.formattedDate}
                          </span>
                          <span className="text-[9px] font-semibold text-emerald-500 dark:text-emerald-400 mt-1">
                            open
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Available Time Slots Grid */}
                <div className="space-y-2.5 pt-2 border-t border-border/80">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-foreground">
                      Available time slots
                    </span>
                    <span className="text-[11px] text-muted-foreground font-medium truncate max-w-[180px]">
                      {clientTimeZone}
                    </span>
                  </div>

                  {loadingSlots ? (
                    <div className="py-8 flex flex-col items-center justify-center gap-2">
                      <Spinner size="sm" />
                      <span className="text-xs text-muted-foreground">Checking schedule…</span>
                    </div>
                  ) : currentSlots.length === 0 ? (
                    <div className="p-4 rounded-xl border border-dashed border-border bg-background/50 text-center space-y-1">
                      <p className="text-xs font-semibold text-foreground">No slots on this date</p>
                      <p className="text-[11px] text-muted-foreground">
                        Please pick another day above or send a direct inquiry.
                      </p>
                    </div>
                  ) : (
                    <div className="grid grid-cols-3 gap-2">
                      {currentSlots.map((slot) => {
                        const isSelected = selectedSlot?.start === slot.start
                        const timeDisplay = new Date(slot.start).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                          hour12: true,
                        })
                        return (
                          <button
                            key={slot.start}
                            type="button"
                            onClick={() => setSelectedSlot(slot)}
                            className={cn(
                              "h-11 px-2 rounded-xl text-xs font-bold transition-all border flex items-center justify-center cursor-pointer",
                              isSelected
                                ? "border-primary bg-primary text-primary-foreground shadow-sm ring-2 ring-primary/30"
                                : "border-border bg-background text-foreground hover:border-primary/50"
                            )}
                          >
                            {timeDisplay}
                          </button>
                        )
                      })}
                    </div>
                  )}
                </div>

                {/* Booking CTA Button + Contact Icon Button (Matches user screenshot) */}
                <div className="pt-2 flex items-center gap-2">
                  <Button
                    onClick={handleOpenBookingModal}
                    disabled={!selectedSlot && currentSlots.length > 0}
                    className="flex-1 h-12 rounded-xl font-bold text-sm shadow-md gap-2"
                  >
                    <CalendarIcon size={16} />
                    <span>
                      {selectedSlot
                        ? `Book Session for ${selectedFullDateLabel}`
                        : currentSlots.length === 0
                        ? `No Slots on ${selectedFullDateLabel}`
                        : "Select a Time Slot Above"}
                    </span>
                  </Button>
                  {mentor.show_contact_button !== false && (
                    <button
                      type="button"
                      onClick={() => setContactModalOpen(true)}
                      title="Contact Mentor"
                      aria-label="Contact Mentor"
                      className="h-12 w-12 rounded-xl border border-border bg-background hover:bg-muted text-foreground flex items-center justify-center shrink-0 transition-colors shadow-sm cursor-pointer"
                    >
                      <MessageSquare size={18} />
                    </button>
                  )}
                </div>
              </>
            ) : (
              /* Email Inquiry Mode */
              <div className="space-y-4">
                <div className="p-3.5 rounded-xl bg-primary/5 border border-primary/20 text-xs text-foreground/90 leading-relaxed">
                  This mentor accepts inquiries and technical reviews directly via written submission.
                </div>
                {mentor.show_contact_button !== false ? (
                  <Button
                    onClick={() => setContactModalOpen(true)}
                    className="w-full h-12 rounded-xl font-bold text-sm shadow-md gap-2"
                  >
                    <Mail size={16} />
                    <span>Send Technical Inquiry</span>
                  </Button>
                ) : (
                  <div className="p-3 rounded-xl bg-muted/40 border border-border text-center text-xs text-muted-foreground">
                    Inquiries are currently closed for this mentor.
                  </div>
                )}
              </div>
            )}

            {/* Secondary Direct Message Action */}
            {mentor.show_contact_button !== false && (
              <div className="pt-2 border-t border-border/80 flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Have questions before booking?</span>
                <button
                  type="button"
                  onClick={() => setContactModalOpen(true)}
                  className="font-semibold text-primary hover:underline cursor-pointer"
                >
                  Contact Mentor
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── BOOKING MODAL (Mentee Name, Email, Discussion Brief) ──────────── */}
      {bookingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in">
          <div className="relative w-full max-w-lg bg-card border border-border rounded-3xl p-6 sm:p-8 shadow-2xl space-y-5">
            {/* Modal Header */}
            <div className="flex items-start justify-between border-b border-border pb-4">
              <div>
                <h3 className="font-display text-lg font-bold text-foreground">
                  Confirm 1-on-1 Mentorship Session
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  with {mentor.user_full_name} ({mentor.company || "Independent"})
                </p>
              </div>
              <button
                onClick={() => setBookingModalOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* Success View inside modal */}
            {bookingSuccess ? (
              <div className="py-6 text-center space-y-4">
                <div className="w-14 h-14 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                  <CheckCircle2 size={32} />
                </div>
                <div className="space-y-1">
                  <h4 className="font-display text-lg font-bold text-foreground">
                    Session Confirmed!
                  </h4>
                  <p className="text-xs text-muted-foreground max-w-sm mx-auto leading-relaxed">
                    Your 30-minute session is confirmed for{" "}
                    <strong className="text-foreground">
                      {bookingSuccess.scheduled_start
                        ? new Date(bookingSuccess.scheduled_start).toLocaleString([], {
                            weekday: "short",
                            month: "short",
                            day: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                            hour12: true,
                          }) + ` (${clientTimeZone})`
                        : selectedFullDateLabel}
                    </strong>
                    . Google Meet join instructions have been emailed to{" "}
                    <strong className="text-foreground">{menteeEmail}</strong>.
                  </p>
                </div>
                <div className="pt-2">
                  <Button
                    onClick={() => {
                      setBookingModalOpen(false)
                      setBookingSuccess(null)
                    }}
                    className="rounded-xl px-8"
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleConfirmBooking} className="space-y-4">
                {/* Selected Slot summary pill */}
                {selectedSlot && (
                  <div className="flex items-center gap-2.5 p-3 rounded-xl bg-primary/10 border border-primary/20 text-xs">
                    <Clock size={16} className="text-primary shrink-0" />
                    <div>
                      <span className="font-bold text-foreground">
                        {new Date(selectedSlot.start).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                          hour12: true,
                        })}{" "}
                        -{" "}
                        {new Date(selectedSlot.end).toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                          hour12: true,
                        })}{" "}
                        <span className="text-muted-foreground font-normal">({clientTimeZone})</span>
                      </span>
                      <span className="text-muted-foreground ml-1.5">
                        · {selectedFullDateLabel}
                      </span>
                    </div>
                  </div>
                )}

                {bookingError && (
                  <div className="p-3 rounded-xl bg-destructive/10 border border-destructive/20 text-destructive text-xs flex items-center gap-2">
                    <AlertCircle size={14} className="shrink-0" />
                    <span>{bookingError}</span>
                  </div>
                )}

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">
                    Your Full Name <span className="text-destructive">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Alex Morgan"
                    value={menteeName}
                    onChange={(e) => setMenteeName(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">
                    Your Email Address <span className="text-destructive">*</span>
                  </label>
                  <input
                    type="email"
                    required
                    placeholder="alex@domain.ae"
                    value={menteeEmail}
                    onChange={(e) => setMenteeEmail(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                  <p className="text-[11px] text-muted-foreground">
                    Calendar invite and meeting link will be sent to this address.
                  </p>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">
                    Affiliation / Organization
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Khalifa University, Startup, Space Agency"
                    value={menteeAffiliation}
                    onChange={(e) => setMenteeAffiliation(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">
                    Discussion Scope / Technical Questions <span className="text-destructive">*</span>
                  </label>
                  <textarea
                    required
                    rows={4}
                    placeholder="Briefly describe your discussion scope..."
                    value={topics}
                    onChange={(e) => setTopics(e.target.value)}
                    className="w-full p-3 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setBookingModalOpen(false)}
                    className="rounded-xl text-xs h-10 px-4"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={submitting}
                    className="rounded-xl text-xs h-10 px-6 gap-2"
                  >
                    {submitting ? "Booking…" : "Confirm Booking"}
                  </Button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* ── QUICK CONTACT / INQUIRY MODAL ─────────────────────────────────── */}
      {contactModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm animate-in fade-in">
          <div className="relative w-full max-w-lg bg-card border border-border rounded-3xl p-6 sm:p-8 shadow-2xl space-y-5">
            <div className="flex items-start justify-between border-b border-border pb-4">
              <div>
                <h3 className="font-display text-lg font-bold text-foreground">
                  Contact {mentor.user_full_name}
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Send a written question or technical inquiry to this mentor.
                </p>
              </div>
              <button
                onClick={() => setContactModalOpen(false)}
                className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {inquirySuccess ? (
              <div className="py-6 text-center space-y-3">
                <div className="w-12 h-12 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto">
                  <CheckCircle2 size={24} />
                </div>
                <h4 className="font-display text-base font-bold text-foreground">
                  Inquiry Sent Successfully!
                </h4>
                <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                  {mentor.user_full_name} has received your message and will reply to your email address shortly.
                </p>
                <div className="pt-2">
                  <Button
                    onClick={() => {
                      setContactModalOpen(false)
                      setInquirySuccess(false)
                    }}
                    className="rounded-xl px-6"
                  >
                    Done
                  </Button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSendDirectInquiry} className="space-y-4">
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
                    value={inquiryName}
                    onChange={(e) => setInquiryName(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Your Email Address</label>
                  <input
                    type="email"
                    required
                    placeholder="sarah@spaceorg.ae"
                    value={inquiryEmail}
                    onChange={(e) => setInquiryEmail(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Affiliation / Organization</label>
                  <input
                    type="text"
                    placeholder="e.g. Khalifa University, Startup, Space Agency"
                    value={inquiryAffiliation}
                    onChange={(e) => setInquiryAffiliation(e.target.value)}
                    className="w-full h-10 px-3.5 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">Message / Technical Scope</label>
                  <textarea
                    required
                    rows={4}
                    placeholder="Describe your question or the project you need advice on..."
                    value={inquiryMessage}
                    onChange={(e) => setInquiryMessage(e.target.value)}
                    className="w-full p-3 rounded-xl border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary transition-colors resize-none"
                  />
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-border">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setContactModalOpen(false)}
                    className="rounded-xl text-xs h-10 px-4"
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    disabled={inquirySending}
                    className="rounded-xl text-xs h-10 px-5 gap-2"
                  >
                    {inquirySending ? (
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
