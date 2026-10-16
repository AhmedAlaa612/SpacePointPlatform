import { type FormEvent, useEffect, useState } from "react"
import {
  createMentorDomain,
  deleteMentorDomain,
  getAllMentors,
  getMentorApplications,
  getMentorDomains,
  reviewMentorApplication,
  updateMentorDomain,
  updateMentorStatus,
} from "@/api/mentors"
import type { MentorDomain, MentorProfile } from "@/types/mentors"
import { Spinner, EmptyState } from "@/components/ui/primitives"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
  Briefcase,
  Building2,
  Check,
  X,
  Plus,
  Trash2,
  Pencil,
  ExternalLink,
  Tag,
} from "lucide-react"
import { LinkedInIcon } from "@/components/icons/LinkedInIcon"

interface MentorsManagementProps {
  initialTab?: "roster" | "applications" | "topics" | "domains"
}

function ActiveToggle({
  active,
  label,
  onToggle,
  disabled,
}: {
  active: boolean
  label: string
  onToggle: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onToggle}
      className={cn(
        "relative w-11 h-6 rounded-full transition-colors shrink-0 cursor-pointer focus:outline-none",
        active ? "bg-primary" : "bg-muted-foreground/30",
        disabled && "opacity-50 cursor-not-allowed"
      )}
      aria-label={label}
      aria-pressed={active}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform",
          active && "translate-x-5"
        )}
      />
    </button>
  )
}

function MentorCardPortrait({
  photoUrl,
  name,
  fallbackInitial,
  subtitle = "Space Mentor",
}: {
  photoUrl?: string | null
  name?: string | null
  fallbackInitial?: string
  subtitle?: string
}) {
  const [imgError, setImgError] = useState(false)
  const initial = fallbackInitial || name?.charAt(0).toUpperCase() || "M"

  return (
    <div className="w-full sm:w-44 lg:w-48 h-52 sm:h-56 rounded-xl overflow-hidden border border-border/80 bg-muted/20 shrink-0 relative shadow-inner">
      {photoUrl && !imgError ? (
        <img
          src={photoUrl}
          alt={name || "Mentor"}
          className="w-full h-full object-cover"
          onError={() => setImgError(true)}
        />
      ) : (
        <div className="w-full h-full bg-gradient-to-b from-[#231134] via-[#140A21] to-[#05030A] flex flex-col items-center justify-center relative overflow-hidden p-4">
          <div className="w-20 h-20 rounded-2xl border-2 border-primary/40 bg-primary/10 text-primary font-display font-extrabold text-3xl flex items-center justify-center shadow-2xl relative z-10 backdrop-blur-sm">
            {initial}
          </div>
          <span className="text-[10px] font-semibold text-[#a79fb8] tracking-wider uppercase mt-2.5 relative z-10">
            {subtitle}
          </span>
        </div>
      )}
    </div>
  )
}

export default function MentorsManagement({ initialTab = "roster" }: MentorsManagementProps) {
  const [tab, setTab] = useState<"roster" | "applications" | "topics">(
    initialTab === "domains" ? "topics" : (initialTab as "roster" | "applications" | "topics")
  )

  useEffect(() => {
    if (initialTab) {
      setTab(initialTab === "domains" ? "topics" : (initialTab as "roster" | "applications" | "topics"))
    }
  }, [initialTab])

  // Topics (Domains) State
  const [domains, setDomains] = useState<MentorDomain[]>([])
  const [newDomainName, setNewDomainName] = useState<string>("")
  const [newDomainCategory, setNewDomainCategory] = useState<string>("")
  const [savingDomain, setSavingDomain] = useState<boolean>(false)
  const [showAddTopic, setShowAddTopic] = useState<boolean>(false)
  const [editingDomainId, setEditingDomainId] = useState<string | null>(null)
  const [editName, setEditName] = useState<string>("")
  const [editCategory, setEditCategory] = useState<string>("")

  // Applications State
  const [applications, setApplications] = useState<MentorProfile[]>([])
  const [loadingApps, setLoadingApps] = useState<boolean>(false)

  // Roster State
  const [roster, setRoster] = useState<MentorProfile[]>([])
  const [loadingRoster, setLoadingRoster] = useState<boolean>(false)

  // Load functions
  const loadDomains = async () => {
    try {
      const data = await getMentorDomains()
      setDomains(data)
    } catch (err) {
      console.error("Failed to load topics", err)
    }
  }

  const loadApplications = async () => {
    try {
      setLoadingApps(true)
      const data = await getMentorApplications()
      setApplications(data)
    } catch (err) {
      console.error("Failed to load applications", err)
    } finally {
      setLoadingApps(false)
    }
  }

  const loadRoster = async () => {
    try {
      setLoadingRoster(true)
      const data = await getAllMentors()
      setRoster(data)
    } catch (err) {
      console.error("Failed to load mentor roster", err)
    } finally {
      setLoadingRoster(false)
    }
  }

  useEffect(() => {
    loadDomains()
    loadApplications()
    loadRoster()
  }, [])

  const handleCreateDomain = async (e: FormEvent) => {
    e.preventDefault()
    if (!newDomainName.trim()) return
    try {
      setSavingDomain(true)
      await createMentorDomain({
        name: newDomainName.trim(),
        category: newDomainCategory.trim() || undefined,
      })
      setNewDomainName("")
      setNewDomainCategory("")
      setShowAddTopic(false)
      await loadDomains()
    } catch (err) {
      console.error("Failed to create topic", err)
    } finally {
      setSavingDomain(false)
    }
  }

  const handleToggleDomain = async (domain: MentorDomain) => {
    try {
      await updateMentorDomain(domain.id, { is_active: !domain.is_active })
      await loadDomains()
    } catch (err) {
      console.error("Failed to toggle topic", err)
    }
  }

  const handleDeleteDomain = async (id: string) => {
    if (!confirm("Are you sure you want to delete this space topic tag?")) return
    try {
      await deleteMentorDomain(id)
      await loadDomains()
    } catch (err) {
      console.error("Failed to delete topic", err)
    }
  }

  const handleStartEdit = (d: MentorDomain) => {
    setEditingDomainId(d.id)
    setEditName(d.name)
    setEditCategory(d.category || "")
  }

  const handleSaveEdit = async (id: string) => {
    if (!editName.trim()) return
    try {
      await updateMentorDomain(id, {
        name: editName.trim(),
        category: editCategory.trim() || undefined,
      })
      setEditingDomainId(null)
      await loadDomains()
    } catch (err) {
      console.error("Failed to update topic", err)
    }
  }

  const handleReview = async (id: string, action: "approved" | "rejected") => {
    try {
      await reviewMentorApplication(id, action)
      await loadApplications()
      await loadRoster()
    } catch (err) {
      console.error("Failed to review application", err)
    }
  }

  const handleToggleMentor = async (mentor: MentorProfile) => {
    try {
      await updateMentorStatus(mentor.id, !mentor.is_active)
      await loadRoster()
    } catch (err) {
      console.error("Failed to toggle mentor active state", err)
    }
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto w-full pt-2">
      {/* Tab 1: Mentors List (Exact Directory Card Look with Deactivate button) */}
      {tab === "roster" && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Mentors Roster
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Active and registered mentors in the SpacePoint directory.
              </p>
            </div>
            <span className="text-xs font-semibold px-3 py-1 rounded-full bg-primary/10 text-primary border border-primary/20">
              {roster.length} {roster.length === 1 ? "Mentor" : "Mentors"}
            </span>
          </div>

          {loadingRoster ? (
            <Spinner />
          ) : roster.length === 0 ? (
            <EmptyState
              title="No mentors registered"
              hint="Approved mentors will appear in this roster."
            />
          ) : (
            <div className="flex flex-col gap-5">
              {roster.map((mentor) => {
                const initial = mentor.user_full_name?.charAt(0).toUpperCase() || "M"
                return (
                  <div
                    key={mentor.id}
                    className="rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm hover:border-primary/50 transition-all duration-300 flex flex-col lg:flex-row gap-6 justify-between items-start"
                  >
                    {/* Left Column: Full Rectangular Photo (exact match with directory) */}
                    <MentorCardPortrait
                      photoUrl={mentor.photo_url || mentor.user_photo_url}
                      name={mentor.user_full_name}
                      subtitle="Space Mentor"
                    />

                    {/* Middle Column: Details (Role, Affiliation, Areas of Support, Description) */}
                    <div className="flex-1 space-y-3 min-w-0">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-display text-xl font-bold text-foreground">
                            {mentor.user_full_name}
                          </h3>
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
                              className="inline-flex items-center hover:opacity-80 transition-opacity"
                              title="LinkedIn Profile"
                            >
                              <LinkedInIcon className="w-4 h-4 rounded-[3px]" />
                            </a>
                          )}
                          <span
                            className={cn(
                              "text-xs px-2.5 py-0.5 rounded-full font-medium border",
                              mentor.status === "approved"
                                ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30"
                                : mentor.status === "rejected"
                                ? "bg-destructive/15 text-destructive border-destructive/30"
                                : "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30"
                            )}
                          >
                            {mentor.status.charAt(0).toUpperCase() + mentor.status.slice(1)}
                          </span>
                          <span
                            className={cn(
                              "text-[11px] px-2 py-0.5 rounded-md font-medium border",
                              mentor.is_published !== false
                                ? "bg-primary/10 text-primary border-primary/20"
                                : "bg-muted text-muted-foreground border-border"
                            )}
                          >
                            {mentor.is_published !== false ? "Published" : "Unpublished"}
                          </span>
                          {mentor.is_active ? (
                            <span className="text-[11px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-md font-medium">
                              Directory Active
                            </span>
                          ) : (
                            <span className="text-[11px] text-muted-foreground bg-muted px-2 py-0.5 rounded-md font-medium">
                              Hidden by Ops
                            </span>
                          )}
                        </div>

                        {/* Role */}
                        {mentor.headline && (
                          <p className="text-xs sm:text-sm font-semibold text-primary flex items-center gap-1.5">
                            <Briefcase size={14} className="shrink-0" />
                            <span>{mentor.headline}</span>
                          </p>
                        )}

                        {/* Affiliation & Email */}
                        <p className="text-xs sm:text-sm text-muted-foreground flex items-center gap-2 flex-wrap">
                          {mentor.company && (
                            <span className="flex items-center gap-1.5">
                              <Building2 size={14} className="shrink-0" />
                              <span>{mentor.company}</span>
                            </span>
                          )}
                          {mentor.company && mentor.user_email && <span>·</span>}
                          {mentor.user_email && <span>{mentor.user_email}</span>}
                        </p>
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
                        </div>
                      )}
                    </div>

                    {/* Right Column: Pricing, Stats, & Deactivate CTA */}
                    <div className="w-full lg:w-64 flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-border/80 pt-4 lg:pt-0 lg:pl-6 space-y-4 shrink-0">
                      <div>
                        <span className="font-display text-lg font-bold text-foreground">
                          {mentor.session_duration_minutes || 30}-min session
                        </span>
                      </div>

                      {/* Stats */}
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
                            {mentor.total_completed_minutes || 0}m
                          </div>
                          <span className="text-[11px] text-muted-foreground">
                            total mentored
                          </span>
                        </div>
                      </div>

                      {/* Dual Action CTAs: Deactivate with exact same button specs as Book Session */}
                      <div className="flex flex-col gap-2 w-full">
                        <Button
                          variant={mentor.is_active ? "destructive" : "default"}
                          onClick={() => handleToggleMentor(mentor)}
                          className="w-full rounded-xl font-semibold h-11 shadow-sm gap-2"
                        >
                          <span>{mentor.is_active ? "Deactivate" : "Activate"}</span>
                        </Button>
                        {mentor.slug && (
                          <a
                            href={`/mentors/${mentor.slug}`}
                            target="_blank"
                            rel="noreferrer"
                            className="w-full"
                          >
                            <Button
                              type="button"
                              variant="outline"
                              className="w-full rounded-xl font-medium h-10 border-border text-foreground hover:bg-muted/60 text-xs gap-1.5"
                            >
                              <span>View Public Profile</span>
                              <ExternalLink size={13} />
                            </Button>
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Applications */}
      {tab === "applications" && (
        <div className="flex flex-col gap-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Mentor Applications
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Review candidate submissions to join the SpacePoint mentor network.
              </p>
            </div>
            <span className="text-xs font-semibold px-3 py-1 rounded-full bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20">
              {applications.length} Pending
            </span>
          </div>

          {loadingApps ? (
            <Spinner />
          ) : applications.length === 0 ? (
            <EmptyState
              title="No pending mentor applications"
              hint="When candidates apply to become mentors, their applications will appear here for review."
            />
          ) : (
            <div className="flex flex-col gap-5">
              {applications.map((app) => {
                const initial = app.user_full_name?.charAt(0).toUpperCase() || "M"
                return (
                  <div
                    key={app.id}
                    className="rounded-2xl border border-border bg-card p-5 sm:p-6 shadow-sm hover:border-primary/50 transition-all duration-300 flex flex-col lg:flex-row gap-6 justify-between items-start"
                  >
                    {/* Left Column: Portrait Frame */}
                    <MentorCardPortrait
                      photoUrl={app.photo_url || app.user_photo_url}
                      name={app.user_full_name}
                      subtitle="Applicant"
                    />

                    {/* Middle Column: Details */}
                    <div className="flex-1 space-y-3 min-w-0">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h3 className="font-display text-xl font-bold text-foreground">
                            {app.user_full_name}
                          </h3>
                          {app.linkedin_url && (
                            <a
                              href={app.linkedin_url.startsWith("http") ? app.linkedin_url : `https://${app.linkedin_url}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center hover:opacity-80 transition-opacity"
                              title="LinkedIn Profile"
                            >
                              <LinkedInIcon className="w-4 h-4 rounded-[3px]" />
                            </a>
                          )}
                          <span className="bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/30 text-xs px-2.5 py-0.5 rounded-full font-medium">
                            Pending Review
                          </span>
                        </div>

                        {app.headline && (
                          <p className="text-xs sm:text-sm font-semibold text-primary flex items-center gap-1.5">
                            <Briefcase size={14} className="shrink-0" />
                            <span>{app.headline}</span>
                          </p>
                        )}

                        <p className="text-xs sm:text-sm text-muted-foreground flex items-center gap-2 flex-wrap">
                          {app.company && (
                            <span className="flex items-center gap-1.5">
                              <Building2 size={14} className="shrink-0" />
                              <span>{app.company}</span>
                            </span>
                          )}
                          {app.company && app.user_email && <span>·</span>}
                          {app.user_email && <span>{app.user_email}</span>}
                        </p>
                      </div>

                      {app.domains.length > 0 && (
                        <div className="space-y-1.5 pt-1">
                          <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                            Areas of Support:
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {app.domains.map((d) => (
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

                      {app.bio && (
                        <div className="pt-1">
                          <p className="text-xs sm:text-sm text-muted-foreground leading-relaxed">
                            {app.bio}
                          </p>
                        </div>
                      )}

                      {app.missions_history && (
                        <div className="rounded-xl bg-muted/40 p-3 text-xs text-muted-foreground border border-border/60">
                          <span className="font-semibold text-foreground">Technical Experience: </span>
                          {app.missions_history}
                        </div>
                      )}
                    </div>

                    {/* Right Column: Actions */}
                    <div className="w-full lg:w-56 flex flex-col justify-between border-t lg:border-t-0 lg:border-l border-border/80 pt-4 lg:pt-0 lg:pl-6 space-y-4 shrink-0">
                      <div>
                        <span className="text-xs font-semibold text-muted-foreground">
                          Mode: {app.contact_mode === "calendar" ? "30-min Video Call" : "Written Inquiries"}
                        </span>
                      </div>

                      <div className="flex flex-col gap-2 w-full pt-4">
                        <Button
                          variant="default"
                          onClick={() => handleReview(app.id, "approved")}
                          className="w-full rounded-xl font-semibold h-11 shadow-sm gap-2 bg-emerald-600 hover:bg-emerald-700 text-white"
                        >
                          <Check size={16} />
                          <span>Approve</span>
                        </Button>
                        <Button
                          variant="destructive"
                          onClick={() => handleReview(app.id, "rejected")}
                          className="w-full rounded-xl font-semibold h-10 shadow-sm gap-2"
                        >
                          <X size={16} />
                          <span>Reject</span>
                        </Button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Topics (Curate space subsystems & taxonomy, Team cards style, No containers) */}
      {tab === "topics" && (
        <div className="flex flex-col gap-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight">
                Topics Taxonomy
              </h2>
              <p className="text-sm text-muted-foreground mt-0.5">
                Active tags available to mentors and organizations for discovery.
              </p>
            </div>
            <Button
              onClick={() => setShowAddTopic((prev) => !prev)}
              className="rounded-xl font-semibold text-xs h-10 px-4 gap-2 self-start sm:self-auto shadow-sm"
            >
              <Plus size={15} />
              <span>{showAddTopic ? "Close Form" : "Add Topic"}</span>
            </Button>
          </div>

          {/* Floating Add Topic Form */}
          {showAddTopic && (
            <form
              onSubmit={handleCreateDomain}
              className="rounded-2xl border border-border bg-card/60 p-4 sm:p-5 flex flex-col sm:flex-row items-center gap-3 animate-in fade-in"
            >
              <input
                type="text"
                placeholder="Topic name (e.g. ADCS, CubeSat Bus, Propulsion)"
                value={newDomainName}
                onChange={(e) => setNewDomainName(e.target.value)}
                className="h-10 px-3.5 w-full sm:flex-1 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
                required
              />
              <input
                type="text"
                placeholder="Category (e.g. Avionics, Payloads, Operations)"
                value={newDomainCategory}
                onChange={(e) => setNewDomainCategory(e.target.value)}
                className="h-10 px-3.5 w-full sm:w-64 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors shadow-sm"
              />
              <Button
                type="submit"
                disabled={savingDomain}
                className="h-10 px-5 rounded-xl font-semibold text-xs gap-1.5 w-full sm:w-auto shadow-sm"
              >
                <Plus size={14} />
                <span>{savingDomain ? "Adding..." : "Add Topic"}</span>
              </Button>
            </form>
          )}

          {/* Topics List styled like Team cards in Ops */}
          {domains.length === 0 ? (
            <EmptyState
              title="No topics found"
              hint="Add your first space topic using the Add Topic button above."
            />
          ) : (
            <div className="flex flex-col gap-3">
              {domains.map((domain) => {
                const isEditing = editingDomainId === domain.id
                return (
                  <div
                    key={domain.id}
                    className="rounded-2xl border border-border bg-card p-4 sm:p-5 flex items-center gap-4 flex-wrap shadow-xs transition-colors"
                  >
                    {/* Left Thumb: Circular Icon Container matching Team Cards */}
                    <div className="w-12 h-12 rounded-full overflow-hidden shrink-0 bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                      <Tag size={18} />
                    </div>

                    {/* Middle Info / Inline Edit */}
                    <div className="flex-1 min-w-40">
                      {isEditing ? (
                        <div className="flex items-center gap-2 flex-wrap">
                          <input
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            className="h-8 px-2.5 rounded-lg border border-border bg-background text-foreground text-xs font-semibold focus:outline-none focus:border-primary"
                          />
                          <input
                            type="text"
                            value={editCategory}
                            onChange={(e) => setEditCategory(e.target.value)}
                            placeholder="Category"
                            className="h-8 px-2.5 rounded-lg border border-border bg-background text-foreground text-xs focus:outline-none focus:border-primary"
                          />
                          <Button
                            size="sm"
                            onClick={() => handleSaveEdit(domain.id)}
                            className="h-8 px-3 rounded-lg text-xs"
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => setEditingDomainId(null)}
                            className="h-8 px-2.5 rounded-lg text-xs text-muted-foreground"
                          >
                            Cancel
                          </Button>
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-2 flex-wrap">
                            <p className="text-sm sm:text-base font-bold text-foreground">
                              {domain.name}
                            </p>
                            {!domain.is_active && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
                                Hidden
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
                            <span>{domain.category || "General"}</span>
                          </div>
                        </>
                      )}
                    </div>

                    {/* Right Actions: ActiveToggle switch, Edit pencil, Delete trash icon */}
                    <div className="flex items-center gap-2.5 shrink-0">
                      <ActiveToggle
                        active={domain.is_active}
                        label={`Toggle ${domain.name}`}
                        onToggle={() => handleToggleDomain(domain)}
                      />
                      <button
                        type="button"
                        onClick={() => handleStartEdit(domain)}
                        className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors cursor-pointer"
                        title={`Edit ${domain.name}`}
                        aria-label={`Edit ${domain.name}`}
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteDomain(domain.id)}
                        className="p-2 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-destructive/10 transition-colors cursor-pointer"
                        title="Delete Topic"
                        aria-label="Delete Topic"
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
