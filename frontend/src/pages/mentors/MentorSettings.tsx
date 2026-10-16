import { type FormEvent, useEffect, useState, useMemo } from "react"
import { Link } from "@tanstack/react-router"
import {
  applyToBecomeMentor,
  getMentorDomains,
  getMyAvailability,
  getMyMentorBookings,
  getMyMentorProfile,
  setMyAvailability,
  updateMyMentorProfile,
  uploadMyMentorPhoto,
} from "@/api/mentors"
import type {
  MentorAvailability,
  MentorBooking,
  MentorDomain,
  MentorProfile,
} from "@/types/mentors"
import { Spinner, EmptyState } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import { cn } from "@/lib/utils"
import { Trash2, CheckCircle2, AlertCircle, Eye, ArrowLeft, Camera, Mail } from "lucide-react"
import { LinkedInIcon } from "@/components/icons/LinkedInIcon"

function getCountryFlag(countryCode?: string | null) {
  if (!countryCode || countryCode.length !== 2) return ""
  const codePoints = countryCode
    .toUpperCase()
    .split("")
    .map((char) => 127397 + char.charCodeAt(0))
  return String.fromCodePoint(...codePoints)
}

const DAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

const CLIENT_TIMEZONE = (() => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
})()

function parseAvailabilitiesToGrid(rules: MentorAvailability[], tz: string = CLIENT_TIMEZONE): Set<string> {
  const set = new Set<string>()
  for (const r of rules) {
    if (r.day_of_week === null || r.day_of_week === undefined || !r.is_active) continue
    const startHour = parseInt(r.start_time.split(":")[0], 10)
    let endHour = parseInt(r.end_time.split(":")[0], 10)
    if (endHour === 0 && startHour > 0) {
      endHour = 24
    }

    if (!r.timezone || r.timezone === tz) {
      for (let h = startHour; h < endHour; h++) {
        if (h >= 0 && h < 24) {
          set.add(`${r.day_of_week}-${h}`)
        }
      }
    } else {
      // Legacy rule in different timezone (e.g. UTC) -> project to client timezone
      for (let h = startHour; h < endHour; h++) {
        try {
          // 2026-01-05 is Monday (day_of_week = 0)
          const refDay = 5 + r.day_of_week
          if (r.timezone === "UTC") {
            const date = new Date(Date.UTC(2026, 0, refDay, h, 0, 0))
            const localHourStr = date.toLocaleTimeString("en-US", { timeZone: tz, hour: "numeric", hour12: false })
            const localDayStr = date.toLocaleDateString("en-US", { timeZone: tz, weekday: "short" })
            const dayIdx = DAYS_SHORT.indexOf(localDayStr)
            const localH = parseInt(localHourStr, 10) % 24
            if (dayIdx >= 0 && localH >= 0 && localH < 24) {
              set.add(`${dayIdx}-${localH}`)
            }
          } else {
            if (h >= 0 && h < 24) {
              set.add(`${r.day_of_week}-${h}`)
            }
          }
        } catch {
          if (h >= 0 && h < 24) {
            set.add(`${r.day_of_week}-${h}`)
          }
        }
      }
    }
  }
  return set
}

function convertGridToAvailabilities(selectedSlots: Set<string>, tz: string = CLIENT_TIMEZONE): Partial<MentorAvailability>[] {
  const result: Partial<MentorAvailability>[] = []

  for (let d = 0; d < 7; d++) {
    const hours: number[] = []
    for (let h = 0; h < 24; h++) {
      if (selectedSlots.has(`${d}-${h}`)) {
        hours.push(h)
      }
    }
    if (hours.length === 0) continue
    hours.sort((a, b) => a - b)

    let startHour = hours[0]
    let prevHour = hours[0]

    for (let i = 1; i < hours.length; i++) {
      const current = hours[i]
      if (current === prevHour + 1) {
        prevHour = current
      } else {
        const endHour = prevHour + 1
        result.push({
          day_of_week: d,
          start_time: `${String(startHour).padStart(2, "0")}:00:00`,
          end_time: `${String(endHour === 24 ? "00" : endHour).padStart(2, "0")}:00:00`,
          timezone: tz,
          is_active: true,
        })
        startHour = current
        prevHour = current
      }
    }

    const endHour = prevHour + 1
    result.push({
      day_of_week: d,
      start_time: `${String(startHour).padStart(2, "0")}:00:00`,
      end_time: `${String(endHour === 24 ? "00" : endHour).padStart(2, "0")}:00:00`,
      timezone: tz,
      is_active: true,
    })
  }

  return result
}

interface MentorSettingsProps {
  initialTab?: "profile" | "slots" | "bookings"
}

export default function MentorSettings({ initialTab = "profile" }: MentorSettingsProps) {
  const [profile, setProfile] = useState<MentorProfile | null>(null)
  const [domains, setDomains] = useState<MentorDomain[]>([])
  const [bookings, setBookings] = useState<MentorBooking[]>([])

  const [loading, setLoading] = useState<boolean>(true)
  const [activeTab, setActiveTab] = useState<"profile" | "slots" | "bookings">(initialTab)

  useEffect(() => {
    if (initialTab) {
      setActiveTab(initialTab)
    }
  }, [initialTab])

  // Form states
  const [headline, setHeadline] = useState<string>("")
  const [company, setCompany] = useState<string>("")
  const [contactEmail, setContactEmail] = useState<string>("")
  const [showContactButton, setShowContactButton] = useState<boolean>(true)
  const [linkedinUrl, setLinkedinUrl] = useState<string>("")
  const [bio, setBio] = useState<string>("")
  const [missionsHistory, setMissionsHistory] = useState<string>("")
  const [whatICanHelpWith, setWhatICanHelpWith] = useState<string>("")
  const [sessionDurationMinutes, setSessionDurationMinutes] = useState<number>(30)
  const [contactMode, setContactMode] = useState<"email" | "calendar">("email")
  const [googleMeetUrl, setGoogleMeetUrl] = useState<string>("")
  const [selectedDomainIds, setSelectedDomainIds] = useState<string[]>([])
  const [isPublished, setIsPublished] = useState<boolean>(true)
  const [photoUrl, setPhotoUrl] = useState<string>("")
  const [uploadingPhoto, setUploadingPhoto] = useState<boolean>(false)
  const [cropModalOpen, setCropModalOpen] = useState<boolean>(false)
  const [rawImageSrc, setRawImageSrc] = useState<string | null>(null)

  // Track initial values to only show Save button when form is dirty
  const [initialValues, setInitialValues] = useState<{
    headline: string
    company: string
    contactEmail: string
    showContactButton: boolean
    linkedinUrl: string
    bio: string
    missionsHistory: string
    whatICanHelpWith: string
    sessionDurationMinutes: number
    contactMode: "email" | "calendar"
    googleMeetUrl: string
    selectedDomainIds: string[]
    isPublished: boolean
    photoUrl: string
  } | null>(null)

  const isDirty = useMemo(() => {
    if (!profile) return true // apply mode: show submit button
    if (!initialValues) return false
    if (headline !== initialValues.headline) return true
    if (company !== initialValues.company) return true
    if (contactEmail !== initialValues.contactEmail) return true
    if (showContactButton !== initialValues.showContactButton) return true
    if (linkedinUrl !== initialValues.linkedinUrl) return true
    if (bio !== initialValues.bio) return true
    if (missionsHistory !== initialValues.missionsHistory) return true
    if (whatICanHelpWith !== initialValues.whatICanHelpWith) return true
    if (sessionDurationMinutes !== initialValues.sessionDurationMinutes) return true
    if (contactMode !== initialValues.contactMode) return true
    if (googleMeetUrl !== initialValues.googleMeetUrl) return true
    if (isPublished !== initialValues.isPublished) return true
    if (photoUrl !== initialValues.photoUrl) return true
    const currentSortedDomains = [...selectedDomainIds].sort().join(",")
    const initialSortedDomains = [...initialValues.selectedDomainIds].sort().join(",")
    if (currentSortedDomains !== initialSortedDomains) return true
    return false
  }, [
    profile,
    initialValues,
    headline,
    company,
    contactEmail,
    showContactButton,
    linkedinUrl,
    bio,
    missionsHistory,
    whatICanHelpWith,
    sessionDurationMinutes,
    contactMode,
    googleMeetUrl,
    isPublished,
    photoUrl,
    selectedDomainIds,
  ])

  const [saving, setSaving] = useState<boolean>(false)
  const [msg, setMsg] = useState<{ type: "success" | "error"; text: string } | null>(null)
  const [fullscreenPreview, setFullscreenPreview] = useState<boolean>(false)

  // Week Calendar Grid state
  const [selectedGridSlots, setSelectedGridSlots] = useState<Set<string>>(new Set())
  const [initialGridSlots, setInitialGridSlots] = useState<Set<string>>(new Set())
  const [isMouseDown, setIsMouseDown] = useState<boolean>(false)
  const [dragMode, setDragMode] = useState<"select" | "deselect" | null>(null)
  const [savingSlots, setSavingSlots] = useState<boolean>(false)

  const loadAll = async () => {
    try {
      setLoading(true)
      const allDomains = await getMentorDomains(true)
      setDomains(allDomains)

      try {
        const myProfile = await getMyMentorProfile()
        setProfile(myProfile)
        setHeadline(myProfile.headline || "")
        setCompany(myProfile.company || "")
        setContactEmail(myProfile.contact_email || "")
        setShowContactButton(myProfile.show_contact_button !== false)
        setLinkedinUrl(myProfile.linkedin_url || "")
        setBio(myProfile.bio || "")
        setMissionsHistory(myProfile.missions_history || "")
        setWhatICanHelpWith(myProfile.what_i_can_help_with || "")
        setContactMode(myProfile.contact_mode || "email")
        setSessionDurationMinutes(myProfile.session_duration_minutes || 30)
        setGoogleMeetUrl(myProfile.google_meet_url || "")
        setIsPublished(myProfile.is_published !== false)
        const effectivePhoto = myProfile.photo_url || myProfile.user_photo_url || ""
        setPhotoUrl(effectivePhoto)
        const sortedDomains = myProfile.domains.map((d) => d.id).sort()
        setSelectedDomainIds(sortedDomains)

        setInitialValues({
          headline: myProfile.headline || "",
          company: myProfile.company || "",
          contactEmail: myProfile.contact_email || "",
          showContactButton: myProfile.show_contact_button !== false,
          linkedinUrl: myProfile.linkedin_url || "",
          bio: myProfile.bio || "",
          missionsHistory: myProfile.missions_history || "",
          whatICanHelpWith: myProfile.what_i_can_help_with || "",
          sessionDurationMinutes: myProfile.session_duration_minutes || 30,
          contactMode: (myProfile.contact_mode || "email") as "email" | "calendar",
          googleMeetUrl: myProfile.google_meet_url || "",
          selectedDomainIds: sortedDomains,
          isPublished: myProfile.is_published !== false,
          photoUrl: effectivePhoto,
        })

        const [myAvails, myBookings] = await Promise.all([
          getMyAvailability(),
          getMyMentorBookings(),
        ])
        const parsedGrid = parseAvailabilitiesToGrid(myAvails)
        setSelectedGridSlots(parsedGrid)
        setInitialGridSlots(new Set(parsedGrid))
        setBookings(myBookings)
      } catch (err: any) {
        if (err.response?.status === 404) {
          setProfile(null)
        }
      }
    } catch (err) {
      console.error("Failed to load mentor data", err)
    } finally {
      setLoading(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setRawImageSrc(reader.result)
        setCropModalOpen(true)
      }
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const handleCropComplete = async (croppedFile: File) => {
    try {
      setUploadingPhoto(true)
      setMsg(null)
      const previewReader = new FileReader()
      previewReader.onload = () => {
        if (typeof previewReader.result === "string") {
          setPhotoUrl(previewReader.result)
        }
      }
      previewReader.readAsDataURL(croppedFile)

      const uploadRes = await uploadMyMentorPhoto(croppedFile)
      if (uploadRes.photo_url) {
        setPhotoUrl(uploadRes.photo_url)
      }
      if (profile) {
        setProfile((prev) => (prev ? { ...prev, photo_url: uploadRes.photo_url } : null))
        setMsg({ type: "success", text: "Portrait picture cropped and uploaded successfully!" })
      } else {
        setMsg({ type: "success", text: "Portrait cropped and loaded. Submit application to save." })
      }
      setCropModalOpen(false)
      setRawImageSrc(null)
    } catch (err: any) {
      console.error("Failed to upload cropped photo", err)
      setMsg({ type: "error", text: err.response?.data?.detail || "Crop preview loaded. Click 'Save Settings' to submit." })
      setCropModalOpen(false)
      setRawImageSrc(null)
    } finally {
      setUploadingPhoto(false)
    }
  }

  useEffect(() => {
    loadAll()
  }, [])

  const handleSaveProfile = async (e: FormEvent) => {
    e.preventDefault()
    try {
      setSaving(true)
      setMsg(null)
      if (!profile) {
        // Apply
        const created = await applyToBecomeMentor({
          headline,
          company,
          contact_email: contactEmail.trim() || undefined,
          show_contact_button: showContactButton,
          linkedin_url: linkedinUrl.trim() || undefined,
          bio,
          missions_history: missionsHistory,
          what_i_can_help_with: whatICanHelpWith.trim() || undefined,
          contact_mode: contactMode,
          session_duration_minutes: sessionDurationMinutes,
          google_meet_url: googleMeetUrl || undefined,
          domain_ids: selectedDomainIds,
          is_published: isPublished,
          photo_url: photoUrl.trim() || undefined,
        })
        setProfile(created)
        setInitialValues({
          headline,
          company,
          contactEmail,
          showContactButton,
          linkedinUrl,
          bio,
          missionsHistory,
          whatICanHelpWith,
          sessionDurationMinutes,
          contactMode,
          googleMeetUrl,
          selectedDomainIds: [...selectedDomainIds].sort(),
          isPublished,
          photoUrl,
        })
        setMsg({
          type: "success",
          text: "Application submitted successfully! Our operations team will review your profile shortly.",
        })
      } else {
        // Update profile
        const updated = await updateMyMentorProfile({
          headline,
          company,
          contact_email: contactEmail.trim() || null,
          show_contact_button: showContactButton,
          linkedin_url: linkedinUrl.trim() || null,
          bio,
          missions_history: missionsHistory,
          what_i_can_help_with: whatICanHelpWith.trim() || undefined,
          contact_mode: contactMode,
          session_duration_minutes: sessionDurationMinutes,
          google_meet_url: googleMeetUrl || undefined,
          domain_ids: selectedDomainIds,
          is_published: isPublished,
          photo_url: photoUrl.trim() || undefined,
        })
        setProfile(updated)
        setInitialValues({
          headline,
          company,
          contactEmail,
          showContactButton,
          linkedinUrl,
          bio,
          missionsHistory,
          whatICanHelpWith,
          sessionDurationMinutes,
          contactMode,
          googleMeetUrl,
          selectedDomainIds: [...selectedDomainIds].sort(),
          isPublished,
          photoUrl,
        })
        setMsg({
          type: "success",
          text: "Mentor profile updated successfully.",
        })
      }
    } catch (err: any) {
      setMsg({
        type: "error",
        text: err.response?.data?.detail || "Failed to save profile.",
      })
    } finally {
      setSaving(false)
    }
  }

  const handleTogglePublish = async () => {
    if (!profile) return
    const nextPublished = !isPublished
    try {
      setIsPublished(nextPublished)
      const updated = await updateMyMentorProfile({ is_published: nextPublished })
      setProfile(updated)
      setMsg({
        type: "success",
        text: nextPublished
          ? "Profile published. Organizations can now view your profile and book sessions."
          : "Profile unpublished. Your profile is now hidden from organizations.",
      })
    } catch (err) {
      setIsPublished(profile.is_published !== false)
      setMsg({
        type: "error",
        text: "Failed to update publish state.",
      })
    }
  }

  useEffect(() => {
    const handleMouseUp = () => {
      setIsMouseDown(false)
      setDragMode(null)
    }
    window.addEventListener("mouseup", handleMouseUp)
    return () => window.removeEventListener("mouseup", handleMouseUp)
  }, [])

  const isGridDirty = useMemo(() => {
    if (!initialGridSlots) return false
    if (selectedGridSlots.size !== initialGridSlots.size) return true
    for (const key of selectedGridSlots) {
      if (!initialGridSlots.has(key)) return true
    }
    return false
  }, [selectedGridSlots, initialGridSlots])

  const handleCellMouseDown = (d: number, h: number) => {
    setIsMouseDown(true)
    const key = `${d}-${h}`
    const isSelected = selectedGridSlots.has(key)
    const mode = isSelected ? "deselect" : "select"
    setDragMode(mode)

    setSelectedGridSlots((prev) => {
      const next = new Set(prev)
      if (mode === "select") {
        next.add(key)
      } else {
        next.delete(key)
      }
      return next
    })
  }

  const handleCellMouseEnter = (d: number, h: number) => {
    if (!isMouseDown || !dragMode) return
    const key = `${d}-${h}`
    setSelectedGridSlots((prev) => {
      const next = new Set(prev)
      if (dragMode === "select") {
        next.add(key)
      } else {
        next.delete(key)
      }
      return next
    })
  }


  const handleClearAllSlots = () => {
    setSelectedGridSlots(new Set())
  }

  const handleSaveAvailability = async () => {
    try {
      setSavingSlots(true)
      setMsg(null)
      const intervals = convertGridToAvailabilities(selectedGridSlots)
      const saved = await setMyAvailability(intervals)
      const newGrid = parseAvailabilitiesToGrid(saved)
      setSelectedGridSlots(newGrid)
      setInitialGridSlots(new Set(newGrid))
      setMsg({ type: "success", text: "Availability schedule saved successfully!" })
    } catch (err: any) {
      console.error("Failed to save availability", err)
      setMsg({ type: "error", text: err.response?.data?.detail || "Failed to save availability schedule." })
    } finally {
      setSavingSlots(false)
    }
  }

  const toggleDomain = (id: string) => {
    setSelectedDomainIds((prev) =>
      prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id]
    )
  }

  if (loading) {
    return <Spinner />
  }

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto w-full pt-2">
      {msg && (
        <div
          className={cn(
            "rounded-xl border p-4 text-sm flex items-center gap-3",
            msg.type === "success"
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : "border-destructive/30 bg-destructive/10 text-destructive"
          )}
        >
          {msg.type === "success" ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
          <span>{msg.text}</span>
        </div>
      )}

      {/* Tab 1: Settings (Floating, No nested card boxes) */}
      {(!profile || activeTab === "profile") && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-12 items-start">
          {/* Main Floating Form (No card boxes! Clean floating fields) */}
          <form
            id="mentor-settings-form"
            onSubmit={handleSaveProfile}
            className="lg:col-span-8 flex flex-col gap-8"
          >
            {/* Header intro text matching Preply + Save Changes on top right */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                  {profile ? "Profile Settings" : "Become a SpacePoint Mentor"}
                </h2>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {profile
                    ? "Set up your public aerospace advisory profile, background, and booking preferences."
                    : "Share your satellite, CubeSat, and aerospace engineering experience with partner organizations."}
                </p>
                {profile && (
                  <p className="text-xs text-muted-foreground pt-1">
                    Looking to change your name or password? Visit{" "}
                    <Link to="/mentor/profile" className="text-primary hover:underline font-semibold">
                      Profile &amp; Settings
                    </Link>
                    .
                  </p>
                )}
              </div>

              {isDirty && (
                <Button
                  type="submit"
                  form="mentor-settings-form"
                  disabled={saving}
                  className="rounded-xl shadow-md font-bold text-xs h-10 px-5 gap-1.5 transition-all self-start sm:self-auto shrink-0 animate-in fade-in zoom-in-95"
                >
                  {saving ? "Saving..." : profile ? "Save Changes" : "Submit Application"}
                </Button>
              )}
            </div>

            {/* Floating Portrait Photo Section with Profile Visibility alongside */}
            <div className="pb-6 border-b border-border/70">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
                {/* Left: Portrait Photo */}
                <div className="flex flex-col gap-2">
                  <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    Profile Photo
                  </label>
                  <div className="w-32 h-40 sm:w-36 sm:h-44 rounded-2xl overflow-hidden border border-border bg-muted/20 shrink-0 relative group shadow-sm">
                    {photoUrl ? (
                      <>
                        <img
                          src={photoUrl}
                          alt="Mentor Portrait Preview"
                          className="w-full h-full object-cover"
                        />
                        <div className="absolute inset-0 bg-background/85 dark:bg-black/75 backdrop-blur-[2px] opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2.5 p-3">
                          <label
                            htmlFor="mentor-photo-file-input"
                            className="w-full py-1.5 px-3 rounded-md bg-primary text-primary-foreground text-xs font-semibold cursor-pointer hover:opacity-90 shadow-sm flex items-center justify-center gap-1.5 transition-all text-center"
                          >
                            <Camera size={13} />
                            <span>Change Picture</span>
                          </label>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              setPhotoUrl("")
                            }}
                            className="w-full py-1.5 px-3 rounded-md bg-destructive/15 text-destructive hover:bg-destructive/25 text-xs font-semibold cursor-pointer transition-colors flex items-center justify-center gap-1.5 text-center"
                          >
                            <Trash2 size={13} />
                            <span>Remove</span>
                          </button>
                        </div>
                      </>
                    ) : (
                      <label
                        htmlFor="mentor-photo-file-input"
                        className="w-full h-full flex flex-col items-center justify-center p-3 text-center cursor-pointer hover:bg-muted/40 transition-colors"
                      >
                        <div className="w-10 h-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center mb-1.5">
                          <Camera size={20} />
                        </div>
                        <span className="text-xs font-semibold text-foreground">Upload Portrait</span>
                        <span className="text-[10px] text-muted-foreground mt-0.5">Fills card</span>
                      </label>
                    )}

                    {uploadingPhoto && (
                      <div className="absolute inset-0 bg-background/80 flex items-center justify-center">
                        <Spinner />
                      </div>
                    )}
                  </div>

                  <input
                    type="file"
                    id="mentor-photo-file-input"
                    accept="image/*"
                    onChange={handleFileSelect}
                    className="hidden"
                  />
                </div>

                {/* Right / Next to Photo: Profile Visibility */}
                {profile && (
                  <div className="flex flex-col sm:items-start gap-2.5 sm:border-l sm:border-border/60 sm:pl-6 sm:py-2">
                    <div>
                      <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground block">
                        Profile Visibility
                      </span>
                      <p className="text-xs text-muted-foreground mt-1 max-w-xs leading-relaxed">
                        {isPublished
                          ? "Publicly active — visible in the directory and accepting bookings."
                          : "Unpublished — hidden from organizations and directory listings."}
                      </p>
                    </div>
                    <div className="pt-1">
                      <Button
                        type="button"
                        variant={isPublished ? "default" : "outline"}
                        onClick={handleTogglePublish}
                        className={cn(
                          "rounded-md px-6 py-2.5 h-auto text-xs font-bold transition-all shadow-sm flex items-center gap-2",
                          isPublished
                            ? "bg-primary text-primary-foreground hover:bg-primary/90"
                            : "border-border text-foreground hover:bg-muted"
                        )}
                      >
                        <span
                          className={cn(
                            "w-2 h-2 rounded-full",
                            isPublished ? "bg-emerald-400" : "bg-muted-foreground"
                          )}
                        />
                        <span>{isPublished ? "Published" : "Unpublished"}</span>
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Floating Text Inputs: Headline & Company */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Headline *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Lead Avionics Engineer · CubeSat Architecture"
                  value={headline}
                  onChange={(e) => setHeadline(e.target.value)}
                  className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                  required
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Company / Organization
                </label>
                <input
                  type="text"
                  placeholder="e.g. Space Dynamics Lab, MBRSC, or Independent"
                  value={company}
                  onChange={(e) => setCompany(e.target.value)}
                  className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                />
              </div>
            </div>

            {/* Floating Contact Email & Profile Contact Icon Toggle */}
            <div className="flex flex-col gap-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                  <Mail size={13} />
                  <span>Contact Email</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={showContactButton}
                    onChange={(e) => setShowContactButton(e.target.checked)}
                    className="w-4 h-4 rounded border-border accent-primary cursor-pointer"
                  />
                  <span className="text-xs font-medium text-foreground">
                    Show contact icon on profile
                  </span>
                </label>
              </div>
              <input
                type="email"
                placeholder={profile?.user_email || "your-inquiries@example.com"}
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
              />
            </div>

            {/* Floating LinkedIn Profile URL */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <LinkedInIcon className="w-3.5 h-3.5 rounded-[2px]" />
                <span>LinkedIn Profile URL</span>
              </label>
              <input
                type="url"
                placeholder="https://linkedin.com/in/username"
                value={linkedinUrl}
                onChange={(e) => setLinkedinUrl(e.target.value)}
                className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
              />
            </div>

            {/* Floating Textarea: Bio */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Bio &amp; Mentorship Focus
              </label>
              <textarea
                rows={4}
                placeholder="Share your technical experience and the topics you are open to discussing with satellite engineers..."
                value={bio}
                onChange={(e) => setBio(e.target.value)}
                className="w-full px-3.5 py-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed shadow-sm"
              />
            </div>

            {/* Floating Textarea: Technical Experience */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Technical Experience
              </label>
              <textarea
                rows={3}
                placeholder="e.g. Nayif-1 CubeSat, ADCS testing on HDEV payload, Falcon 9 rideshare integration..."
                value={missionsHistory}
                onChange={(e) => setMissionsHistory(e.target.value)}
                className="w-full px-3.5 py-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed shadow-sm"
              />
            </div>

            {/* Floating Textarea: What I Can Help With */}
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                What I Can Help With
              </label>
              <textarea
                rows={3}
                placeholder="Specific guidance, technical areas, or challenges you can advise satellite teams on (e.g. CubeSat link budgets, solar array sizing, flight software testing)..."
                value={whatICanHelpWith}
                onChange={(e) => setWhatICanHelpWith(e.target.value)}
                className="w-full px-3.5 py-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-y leading-relaxed shadow-sm"
              />
            </div>

            {/* Floating Space Topics Pills */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Space Topics
              </label>
              <div className="flex flex-wrap gap-2">
                {domains.map((d) => {
                  const selected = selectedDomainIds.includes(d.id)
                  return (
                    <button
                      type="button"
                      key={d.id}
                      onClick={() => toggleDomain(d.id)}
                      className={cn(
                        "px-3.5 py-1.5 rounded-full text-xs font-bold transition-all border cursor-pointer",
                        selected
                          ? "bg-primary text-primary-foreground border-primary shadow-sm"
                          : "border-border bg-background text-muted-foreground hover:text-foreground hover:border-muted-foreground/40"
                      )}
                    >
                      {d.name}
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Floating Mentorship Mode & Duration */}
            <div className="space-y-3 pt-2">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Mentorship Contact Mode
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label
                  className={cn(
                    "p-4 rounded-xl border cursor-pointer transition-all flex flex-col gap-1.5 shadow-sm",
                    contactMode === "email"
                      ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                      : "border-border bg-background hover:border-muted-foreground/40"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="contactMode"
                      value="email"
                      checked={contactMode === "email"}
                      onChange={() => setContactMode("email")}
                      className="accent-primary"
                    />
                    <span className="text-sm font-bold text-foreground">Inquiry via Email</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed pl-6">
                    Organizations submit an inquiry form sent directly to your email.
                  </p>
                </label>

                <label
                  className={cn(
                    "p-4 rounded-xl border cursor-pointer transition-all flex flex-col gap-1.5 shadow-sm",
                    contactMode === "calendar"
                      ? "border-primary bg-primary/5 ring-1 ring-primary/30"
                      : "border-border bg-background hover:border-muted-foreground/40"
                  )}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      name="contactMode"
                      value="calendar"
                      checked={contactMode === "calendar"}
                      onChange={() => setContactMode("calendar")}
                      className="accent-primary"
                    />
                    <span className="text-sm font-bold text-foreground">Direct Calendar Booking</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed pl-6">
                    Organizations book directly into your calendar slots with Google Meet.
                  </p>
                </label>
              </div>

              {contactMode === "calendar" && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-3">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Session Duration
                    </label>
                    <select
                      value={sessionDurationMinutes}
                      onChange={(e) => setSessionDurationMinutes(Number(e.target.value))}
                      className="h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                    >
                      <option value={15}>15 Minutes</option>
                      <option value={30}>30 Minutes</option>
                      <option value={45}>45 Minutes</option>
                      <option value={60}>60 Minutes</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                      Personal Google Meet Link
                    </label>
                    <input
                      type="url"
                      placeholder="https://meet.google.com/xxx-yyyy-zzz"
                      value={googleMeetUrl}
                      onChange={(e) => setGoogleMeetUrl(e.target.value)}
                      className="h-10 px-3.5 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                      required={contactMode === "calendar"}
                    />
                  </div>
                </div>
              )}
            </div>
          </form>

          {/* Right Column: Floating Profile Preview Box (Matching Screenshot, NO SHARE) */}
          <div className="lg:col-span-4 lg:sticky lg:top-24 flex flex-col gap-4">
            <div className="rounded-2xl border border-border bg-card p-5 shadow-sm space-y-4">
              <div className="flex items-center gap-3">
                <div className="w-12 h-14 rounded-xl overflow-hidden border border-border bg-muted/20 shrink-0 shadow-inner">
                  {photoUrl ? (
                    <img
                      src={photoUrl}
                      alt={profile?.user_full_name || "Mentor"}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full bg-gradient-to-br from-space-800 via-card to-space-900 flex items-center justify-center font-display font-bold text-lg text-primary">
                      {profile?.user_full_name?.charAt(0).toUpperCase() || "M"}
                    </div>
                  )}
                </div>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-display font-bold text-foreground text-sm truncate">
                      {profile?.user_full_name || "Your Name"}
                    </span>
                    {profile?.user_country && (
                      <span className="text-sm leading-none" title={profile.user_country}>
                        {getCountryFlag(profile.user_country)}
                      </span>
                    )}
                    {linkedinUrl && (
                      <a
                        href={linkedinUrl.startsWith("http") ? linkedinUrl : `https://${linkedinUrl}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center hover:opacity-80 transition-opacity"
                        title="LinkedIn Profile"
                      >
                        <LinkedInIcon className="w-3.5 h-3.5 rounded-[2px]" />
                      </a>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate mt-0.5">
                    {headline || "Space Mentor"}
                  </p>
                </div>
              </div>

              {/* Preview profile button (NO SHARE BUTTON) */}
              {profile?.slug ? (
                <Link
                  to={`/mentors/${profile.slug}` as any}
                  target="_blank"
                  className="block w-full"
                >
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full rounded-xl text-xs font-bold gap-2 h-10 border-border hover:bg-muted"
                  >
                    <Eye size={15} />
                    <span>Preview profile</span>
                  </Button>
                </Link>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  disabled
                  className="w-full rounded-xl text-xs font-bold gap-2 h-10 border-border opacity-50"
                >
                  <Eye size={15} />
                  <span>Preview profile</span>
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Availability (Preply-Style Week Calendar Grid, No Containers!) */}
      {profile && activeTab === "slots" && (
        <div className="flex flex-col gap-6">
          {/* Floating Header & Quick Actions */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Select time slots when you&apos;re available for booking
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Click or drag across the weekly calendar to set recurring hours. Times shown in your local timezone ({CLIENT_TIMEZONE}).
              </p>
            </div>

            <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleClearAllSlots}
                className="rounded-xl text-xs text-muted-foreground hover:text-destructive h-9"
              >
                Clear All
              </Button>
              <Button
                type="button"
                onClick={handleSaveAvailability}
                disabled={savingSlots}
                className={cn(
                  "rounded-xl font-bold text-xs h-9 px-4 gap-1.5 shadow-sm transition-all",
                  isGridDirty
                    ? "bg-primary text-primary-foreground shadow-md animate-in fade-in"
                    : "bg-primary/80 opacity-90"
                )}
              >
                {savingSlots ? "Saving..." : isGridDirty ? "Save Schedule *" : "Save Schedule"}
              </Button>
            </div>
          </div>

          {/* Week Calendar Grid (Matches Screenshot 2) */}
          <div className="w-full overflow-x-auto select-none pb-4">
            <div className="min-w-[700px] border border-border/70 rounded-2xl bg-card/30 overflow-hidden shadow-xs">
              {/* Day Headers */}
              <div className="grid grid-cols-8 border-b border-border/70 bg-muted/40">
                <div className="p-3 text-center text-xs font-semibold text-muted-foreground border-r border-border/50">
                  Time
                </div>
                {DAYS_SHORT.map((dayName) => (
                  <div
                    key={dayName}
                    className="p-3 text-center text-xs font-bold text-foreground border-r border-border/50 last:border-r-0"
                  >
                    {dayName}
                  </div>
                ))}
              </div>

              {/* 24 Hour Rows */}
              <div className="divide-y divide-border/40">
                {Array.from({ length: 24 }, (_, i) => i).map((h) => {
                  const isNightBadge = h === 5
                  return (
                    <div key={h} className="relative">
                      {isNightBadge && (
                        <div className="absolute -top-3 left-0 right-0 z-10 flex items-center justify-center pointer-events-none">
                          <span className="bg-muted px-3 py-0.5 rounded-full text-[10px] font-bold text-muted-foreground uppercase tracking-wider border border-border shadow-xs">
                            Night time
                          </span>
                        </div>
                      )}
                      <div className="grid grid-cols-8 h-10 items-stretch">
                        {/* Hour Label */}
                        <div className="flex items-center justify-center text-[11px] font-mono text-muted-foreground border-r border-border/50 bg-muted/15">
                          {String(h).padStart(2, "0")}:00
                        </div>

                        {/* 7 Day Cells */}
                        {DAYS_SHORT.map((_, d) => {
                          const key = `${d}-${h}`
                          const isSelected = selectedGridSlots.has(key)
                          const topSelected = selectedGridSlots.has(`${d}-${h - 1}`)
                          const bottomSelected = selectedGridSlots.has(`${d}-${h + 1}`)

                          return (
                            <div
                              key={key}
                              onMouseDown={(e) => {
                                e.preventDefault()
                                handleCellMouseDown(d, h)
                              }}
                              onMouseEnter={() => handleCellMouseEnter(d, h)}
                              className={cn(
                                "border-r border-border/40 last:border-r-0 transition-colors cursor-pointer p-0.5 flex flex-col justify-center",
                                isSelected ? "bg-primary/5" : "hover:bg-muted/30"
                              )}
                            >
                              <div
                                className={cn(
                                  "w-full h-full transition-all border",
                                  isSelected
                                    ? cn(
                                        "bg-[#85b7eb]/35 dark:bg-primary/30 border-[#85b7eb] dark:border-primary/50 text-foreground font-semibold flex items-center justify-center shadow-xs",
                                        !topSelected && "rounded-t-lg",
                                        !bottomSelected && "rounded-b-lg",
                                        topSelected && "border-t-0",
                                        bottomSelected && "border-b-0"
                                      )
                                    : "border-transparent"
                                )}
                              />
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Sessions (Floating Cards, No Outer Container!) */}
      {profile && activeTab === "bookings" && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Mentorship Sessions &amp; Inquiries
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Review completed sessions, upcoming calls, and submitted inquiries.
              </p>
            </div>
            {bookings.length > 0 && (
              <span className="text-xs font-semibold px-3 py-1 rounded-full bg-muted/60 text-muted-foreground border border-border self-start sm:self-auto">
                {bookings.length} {bookings.length === 1 ? "Session" : "Sessions"}
              </span>
            )}
          </div>

          {bookings.length === 0 ? (
            <div className="py-16 text-center">
              <EmptyState
                title="No sessions or inquiries yet"
                hint="When organizations book a session or send an inquiry, it will show up here."
              />
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {bookings.map((booking) => (
                <div
                  key={booking.id}
                  className="p-5 border border-border/80 rounded-2xl bg-card/60 hover:bg-card hover:border-primary/40 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-4 shadow-sm"
                >
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-bold text-foreground">
                        {booking.mentee_name}
                      </p>
                      <span
                        className={cn(
                          "text-xs px-2.5 py-0.5 rounded-full font-semibold border",
                          booking.status === "completed"
                            ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                            : booking.status === "cancelled"
                            ? "bg-destructive/15 text-destructive border-destructive/30"
                            : "bg-primary/15 text-primary border-primary/30"
                        )}
                      >
                        {booking.status}
                      </span>
                      <span className="text-xs text-muted-foreground font-medium">
                        · {booking.booking_type === "session" ? "30-min Video Call" : "Written Inquiry"}
                      </span>
                    </div>

                    <p className="text-xs text-muted-foreground">
                      Contact: <span className="text-foreground/90 font-medium">{booking.mentee_email}</span>
                      {booking.scheduled_start && (
                        <> · Scheduled: <span className="text-foreground/90 font-medium">{new Date(booking.scheduled_start).toLocaleString()}</span></>
                      )}
                    </p>

                    {booking.topics && (
                      <p className="text-xs text-foreground/80 italic pt-1 leading-relaxed">
                        &ldquo;{booking.topics}&rdquo;
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Full Screen Profile Preview Modal */}
      {fullscreenPreview && (
        <div className="fixed inset-0 z-50 bg-background overflow-y-auto flex flex-col">
          {/* Preview Navigation Bar */}
          <div className="border-b border-border bg-card/95 backdrop-blur-md sticky top-0 z-10 px-4 sm:px-8 py-3.5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFullscreenPreview(false)}
                className="gap-1.5 rounded-xl"
              >
                <ArrowLeft size={14} />
                Exit Preview
              </Button>
              <div className="flex items-center gap-2 pl-2 border-l border-border">
                <span className="text-xs font-semibold text-primary uppercase tracking-wider">
                  Full Screen Preview
                </span>
                <span className="text-xs text-muted-foreground hidden sm:inline">
                  · How organizations view your profile
                </span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  "text-xs px-2.5 py-1 rounded-full font-medium border",
                  isPublished
                    ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                    : "bg-muted text-muted-foreground border-border"
                )}
              >
                {isPublished ? "Status: Published" : "Status: Unpublished"}
              </span>
            </div>
          </div>

          {/* Full Profile View */}
          <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10 w-full flex flex-col gap-6">
            <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 flex flex-col gap-5">
              <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                <div className="flex items-start gap-5">
                  <div className="w-24 h-28 sm:w-28 sm:h-32 rounded-xl overflow-hidden border border-border bg-muted/20 shrink-0 shadow-inner">
                    {photoUrl ? (
                      <img
                        src={photoUrl}
                        alt={profile?.user_full_name || "Mentor"}
                        className="w-full h-full object-cover"
                      />
                    ) : (
                      <div className="w-full h-full bg-gradient-to-br from-space-800 via-card to-space-900 flex items-center justify-center font-display font-bold text-3xl text-primary">
                        {profile?.user_full_name?.charAt(0).toUpperCase() || "M"}
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h1 className="font-display text-2xl font-bold text-foreground">
                        {profile?.user_full_name || "Your Name"}
                      </h1>
                      {linkedinUrl && (
                        <a
                          href={linkedinUrl.startsWith("http") ? linkedinUrl : `https://${linkedinUrl}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center hover:opacity-80 transition-opacity"
                          title="LinkedIn Profile"
                        >
                          <LinkedInIcon className="w-4 h-4 rounded-[3px]" />
                        </a>
                      )}
                    </div>
                    <p className="text-sm font-medium text-muted-foreground mt-0.5">
                      {company || "Independent"}
                    </p>
                    {headline && (
                      <p className="text-sm font-medium text-foreground mt-1">
                        {headline}
                      </p>
                    )}
                  </div>
                </div>

                <span className="text-xs font-medium text-muted-foreground bg-muted px-2.5 py-1 rounded-md self-start">
                  {contactMode === "calendar" ? "30-Min Meet" : "Email Inquiry"}
                </span>
              </div>

              {bio && (
                <p className="text-sm text-foreground/90 leading-relaxed">
                  {bio}
                </p>
              )}

              {missionsHistory && (
                <div className="rounded-xl bg-muted/50 p-4 text-xs text-muted-foreground">
                  <span className="font-semibold text-foreground">Technical Experience: </span>
                  {missionsHistory}
                </div>
              )}

              {selectedDomainIds.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-2 border-t border-border">
                  {domains
                    .filter((d) => selectedDomainIds.includes(d.id))
                    .map((d) => (
                      <span
                        key={d.id}
                        className="bg-muted text-muted-foreground text-xs px-2.5 py-0.5 rounded-md font-medium"
                      >
                        {d.name}
                      </span>
                    ))}
                </div>
              )}
            </div>

            {/* Simulated Booking Card */}
            <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 flex flex-col gap-4 opacity-90">
              <h2 className="font-display text-xl font-bold text-foreground">
                {contactMode === "calendar" ? "Book a 30-Minute 1-on-1 Session" : "Send a Mentorship Inquiry"}
              </h2>
              <p className="text-xs text-muted-foreground">
                {contactMode === "calendar"
                  ? "Organizations pick an open date/time from your availability and share discussion topics."
                  : "Organizations send their questions directly to your email."}
              </p>
              <div className="p-4 rounded-xl border border-dashed border-border text-center text-xs text-muted-foreground">
                Interactive booking form renders here for organizations.
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Image Crop Modal */}
      <ImageCropModal
        isOpen={cropModalOpen}
        onClose={() => {
          setCropModalOpen(false)
          setRawImageSrc(null)
        }}
        imageSrc={rawImageSrc}
        title="Crop Mentor Portrait"
        aspect={4 / 5}
        circularCrop={false}
        showPreview={false}
        isUploading={uploadingPhoto}
        onCropComplete={handleCropComplete}
      />
    </div>
  )
}
