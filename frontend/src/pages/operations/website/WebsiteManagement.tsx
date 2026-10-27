import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { ChevronDown, ChevronUp, Globe, Pencil, Plus, Save, Trash2, Upload } from "lucide-react"
import { cn } from "@/lib/utils"
import { apiBaseUrl } from "@/api/client"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import { PageHeader, Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import { Modal, ModalActions } from "@/pages/admin/components/common"
import {
  getWebsiteConfig,
  updateWebsiteConfig,
  uploadWebsiteAsset,
  type WebsiteConfigUpdate,
} from "@/api/websiteConfig"
import {
  getWebsitePrograms,
  updateWebsiteProgram,
  type WebsiteProgram,
  type WebsiteProgramUpdate,
} from "@/api/websitePrograms"
import {
  SPONSOR_TIERS,
  createWebsiteSponsor,
  deleteWebsiteSponsor,
  getWebsiteSponsors,
  updateWebsiteSponsor,
  type SponsorTier,
  type WebsiteSponsor,
} from "@/api/websiteSponsors"
import {
  createWebsiteFaq,
  createWebsiteMedia,
  createWebsiteNewsletter,
  deleteWebsiteFaq,
  deleteWebsiteMedia,
  deleteWebsiteNewsletter,
  getWebsiteFaqs,
  getWebsiteLeads,
  getWebsiteMedia,
  getWebsiteNewsletters,
  updateWebsiteFaq,
  updateWebsiteMedia,
  updateWebsiteNewsletter,
  type WebsiteFaq,
  type WebsiteLead,
  type WebsiteMediaClipping,
  type WebsiteNewsletter,
} from "@/api/websiteContent"
import { marked } from "marked"
import {
  createArticle,
  deleteArticle,
  getAllArticles,
  reviewArticle,
  unpublishArticle,
  updateArticle,
  type ReviewAction,
  type WebsiteArticle,
} from "@/api/articles"
import {
  createWebsiteLab,
  deleteWebsiteLab,
  getWebsiteLabs,
  updateWebsiteLab,
  type WebsiteLabProject,
} from "@/api/websiteLabs"
import {
  createWebsiteAlumni,
  createWebsiteAmbassador,
  createWebsiteStudentMission,
  createWebsiteTeamMember,
  deleteWebsiteAlumni,
  deleteWebsiteAmbassador,
  deleteWebsiteStudentMission,
  deleteWebsiteTeamMember,
  getWebsiteAlumni,
  getWebsiteAmbassadors,
  getWebsiteStudentMissions,
  getWebsiteTeam,
  updateWebsiteAlumni,
  updateWebsiteAmbassador,
  updateWebsiteStudentMission,
  updateWebsiteTeamMember,
  type WebsiteAlumni,
  type WebsiteAmbassador,
  type WebsiteStudentMission,
  type WebsiteTeamMember,
} from "@/api/websitePeople"
import { WebsiteEventsPanel } from "./WebsiteEventsPanel"

type Tab = "general" | "events" | "programs" | "partners" | "faqs" | "media" | "newsletters" | "articles" | "people" | "labs"

const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? "https://spacepoint.ae"
    : "http://localhost:4321")

export function resolveWebsiteAsset(url: string | null | undefined): string {
  const raw = (url ?? "").trim()
  if (!raw) return ""
  const apiPrefix = apiBaseUrl.replace(/\/$/, "")
  if (raw.startsWith("https://portal.spacepoint.ae/public/website/uploads/")) {
    return raw.replace(
      "https://portal.spacepoint.ae/public/website/uploads/",
      `${apiPrefix}/public/website/uploads/`
    )
  }
  if (raw.startsWith("/public/website/uploads/") || raw.startsWith("/files/")) {
    return `${apiPrefix}${raw}`
  }
  if (/^(https?:|data:|blob:)/i.test(raw)) return raw
  const path = raw.startsWith("/") ? raw : `/${raw}`
  return `${WEBSITE_BASE_URL}${encodeURI(path)}`
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  helper,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  helper?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
      />
      {helper && <span className="text-[11px] text-muted-foreground">{helper}</span>}
    </label>
  )
}

export function AssetField({
  label,
  value,
  onChange,
  placeholder = "https://… or upload a file",
  accept = "image/*,.svg,.pdf,.docx",
  helper,
  aspect,
  circularCrop = false,
  aspectHint,
  disableCrop = false,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  accept?: string
  helper?: string
  aspect?: number
  circularCrop?: boolean
  aspectHint?: string
  disableCrop?: boolean
}) {
  const toast = useToast()
  const fileRef = useRef<HTMLInputElement | null>(null)
  const [uploading, setUploading] = useState(false)
  const [cropSrc, setCropSrc] = useState<string | null>(null)
  const [cropFileName, setCropFileName] = useState<string>("cropped.png")

  const uploadFile = async (file: File) => {
    setUploading(true)
    try {
      const res = await uploadWebsiteAsset(file)
      onChange(res.url)
      toast.success(`Uploaded ${res.filename}`)
      setCropSrc(null)
    } catch (e) {
      toast.error(mutationError(e, "Could not upload file"))
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  const handleFile = async (file: File | undefined) => {
    if (!file) return
    const isRasterImage =
      file.type.startsWith("image/") && file.type !== "image/svg+xml"
    if (isRasterImage && !disableCrop) {
      const stem = file.name.replace(/\.[^.]+$/, "") || "cropped"
      setCropFileName(`${stem}.png`)
      const reader = new FileReader()
      reader.onload = () => {
        if (typeof reader.result === "string") {
          setCropSrc(reader.result)
        }
      }
      reader.readAsDataURL(file)
      if (fileRef.current) fileRef.current.value = ""
      return
    }
    await uploadFile(file)
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          {label}
        </span>
        {aspectHint && (
          <span className="text-[10px] font-medium text-muted-foreground/80">
            Frame: {aspectHint}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="h-10 px-3 flex-1 min-w-0 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
        />
        <input
          ref={fileRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="h-10 px-3.5 shrink-0 border border-border bg-muted/60 hover:bg-muted text-foreground text-xs font-semibold rounded-xl inline-flex items-center gap-1.5 transition-colors disabled:opacity-50"
        >
          <Upload size={14} />
          {uploading ? "Uploading…" : "Upload"}
        </button>
      </div>
      {helper && <span className="text-[11px] text-muted-foreground">{helper}</span>}
      <ImageCropModal
        isOpen={Boolean(cropSrc)}
        onClose={() => {
          if (!uploading) setCropSrc(null)
        }}
        imageSrc={cropSrc}
        title={aspectHint ? `Select Area to Show — ${label} (${aspectHint})` : `Select Area to Show — ${label}`}
        aspect={aspect}
        circularCrop={circularCrop}
        showPreview={false}
        isUploading={uploading}
        onCropComplete={async (croppedFile) => {
          const named = new File([croppedFile], cropFileName, { type: croppedFile.type })
          await uploadFile(named)
        }}
      />
    </div>
  )
}


/**
 * Website management (Step 1 — Global Config & Live Counters, Step 2 —
 * Core Programs & AED Pricing).
 * Tab 1 "General Config" edits the website_settings singleton (id=1);
 * Tab 2 "Programs & Pricing" edits website_programs rows. Both save via
 * PUT /admin/website/* and the public site picks them up via
 * GET /public/website/* with no redeploy.
 */
export default function WebsiteManagement({ initialTab = "general" }: { initialTab?: Tab }) {
  const qc = useQueryClient()
  const toast = useToast()
  // Each sidebar section mounts this page with its own initialTab via its
  // own route; navigation between sections lives in the sidebar group.
  const [activeTab] = useState<Tab>(initialTab)
  const [form, setForm] = useState<WebsiteConfigUpdate | null>(null)
  const [seeded, setSeeded] = useState(false)

  const { data: config, isLoading, isError } = useQuery({
    queryKey: ["website-config"],
    queryFn: getWebsiteConfig,
  })

  // Seed the form once the query resolves (same render-body pattern as
  // pages/admin/Settings.tsx — never re-syncs, so in-flight edits survive
  // a background refetch).
  if (config && !seeded) {
    setForm({
      students_count: config.students_count,
      workshops_count: config.workshops_count,
      partners_count: config.partners_count,
      satellites_flown_count: config.satellites_flown_count,
      instructor_invite_code: config.instructor_invite_code,
      intern_invite_code: config.intern_invite_code,
      contact_email: config.contact_email,
      contact_phone: config.contact_phone,
      contact_whatsapp: config.contact_whatsapp,
      office_address: config.office_address,
      social_linkedin: config.social_linkedin,
      social_x: config.social_x,
      social_instagram: config.social_instagram,
      social_youtube: config.social_youtube,
    })
    setSeeded(true)
  }

  const save = useMutation({
    mutationFn: (payload: WebsiteConfigUpdate) => updateWebsiteConfig(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-config"] })
      toast.success("Website config saved — the public site updates immediately")
    },
    onError: (e: unknown) => {
      const detail =
        isAxiosError(e) && typeof e.response?.data?.detail === "string"
          ? e.response.data.detail
          : "Could not save website config"
      toast.error(detail)
    },
  })

  if (isLoading || form === null) return <Spinner />
  if (isError || !config) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="Website Management"
          subtitle="Global config for the public marketing site — counters, invite codes, contact info."
        />
        <p className="text-sm text-red-600 dark:text-red-400">
          Could not load website config. Check your connection and try again.
        </p>
      </div>
    )
  }

  const set = (key: keyof WebsiteConfigUpdate) => (v: string) =>
    setForm((prev) => ({ ...(prev ?? {}), [key]: v }))

  const str = (v: string | null | undefined) => v ?? ""

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Website Management"
        subtitle="Update live impact counters, application invite codes, and contact info — changes reflect on the public site instantly, no redeploy."
        action={
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Globe size={14} />
            {config.updated_at
              ? `Last updated ${new Date(config.updated_at).toLocaleString()}`
              : ""}
          </span>
        }
      />

      {activeTab === "general" && (
        <div className="flex flex-col gap-6">
          <section className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
            <div>
              <p className="text-sm font-semibold text-foreground">Impact Counters</p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Field label="Students Count" value={str(form.students_count)} onChange={set("students_count")} />
              <Field label="Workshops Delivered" value={str(form.workshops_count)} onChange={set("workshops_count")} />
              <Field label="Partners" value={str(form.partners_count)} onChange={set("partners_count")} />
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
            <div>
              <p className="text-sm font-semibold text-foreground">Application Codes</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Invite codes appended to the public apply links.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field
                label="Instructor Apply Code"
                value={str(form.instructor_invite_code)}
                onChange={set("instructor_invite_code")}
                placeholder="e.g. UOWD26"
                helper="When set, links to /apply/instructor/{code}. When empty, links to /apply/instructor"
              />
              <Field
                label="Intern Apply Code"
                value={str(form.intern_invite_code)}
                onChange={set("intern_invite_code")}
                placeholder="e.g. UOWD26"
                helper="When set, links to /apply/intern/{code}. When empty, links to /apply/intern"
              />
            </div>
          </section>

          <section className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
            <div>
              <p className="text-sm font-semibold text-foreground">Contact &amp; Corporate Info</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Support channels, office address, and social profiles shown on the site.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Field label="Support Email" value={str(form.contact_email)} onChange={set("contact_email")} />
              <Field label="Phone" value={str(form.contact_phone)} onChange={set("contact_phone")} />
              <div className="sm:col-span-2">
                <Field label="Address" value={str(form.office_address)} onChange={set("office_address")} />
              </div>
              <Field label="LinkedIn URL" value={str(form.social_linkedin)} onChange={set("social_linkedin")} />
              <Field label="TikTok / X URL" value={str(form.social_x)} onChange={set("social_x")} />
              <Field label="Instagram URL" value={str(form.social_instagram)} onChange={set("social_instagram")} />
              <Field label="YouTube URL" value={str(form.social_youtube)} onChange={set("social_youtube")} />
            </div>
          </section>

          <button
            onClick={() => save.mutate(form)}
            disabled={save.isPending}
            className="h-10 px-5 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 disabled:opacity-40 w-fit inline-flex items-center gap-2"
          >
            <Save size={15} />
            {save.isPending ? "Saving…" : "Save Changes"}
          </button>
        </div>
      )}

      {activeTab === "events" && <WebsiteEventsPanel />}

      {activeTab === "programs" && <ProgramsSection />}

      {activeTab === "partners" && <SponsorsSection />}

      {activeTab === "faqs" && <FaqsSection />}

      {activeTab === "media" && <MediaSection />}

      {activeTab === "newsletters" && <NewslettersSection />}

      {activeTab === "articles" && <EditorialQueueSection />}

      {activeTab === "people" && <PeopleSection />}

      {activeTab === "labs" && <LabsSection />}
    </div>
  )
}

function mutationError(e: unknown, fallback: string): string {
  if (isAxiosError(e)) {
    const detail = (e.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === "string") return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (typeof d === "object" && d !== null && "msg" in d ? String((d as { msg: unknown }).msg) : "Invalid value"))
        .join("; ")
    }
  } else if (e instanceof Error) {
    return e.message
  }
  return fallback
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
        "relative w-11 h-6 rounded-full transition-colors shrink-0",
        active ? "bg-primary" : "bg-muted-foreground/30",
      )}
      aria-label={label}
      aria-pressed={active}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform",
          active && "translate-x-5",
        )}
      />
    </button>
  )
}

function exportCsv(filename: string, rows: string[][]) {
  const csv = rows
    .map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(","))
    .join("\r\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function ProgramsSection() {
  const { data: programs = [], isLoading, isError } = useQuery({
    queryKey: ["website-programs"],
    queryFn: getWebsitePrograms,
  })
  const [editingId, setEditingId] = useState<string | null>(null)

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load programs. Check your connection and try again.
      </p>
    )
  }

  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
      {programs.map((p) => (
        <article
          key={p.id}
          className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-semibold text-foreground">{p.title}</h3>
                <span
                  className={cn(
                    "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border",
                    p.is_published
                      ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20"
                      : "bg-muted text-muted-foreground border-border",
                  )}
                >
                  {p.is_published ? "Published" : "Hidden"}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {p.duration}
              </p>
              {p.tagline && (
                <p className="text-xs text-muted-foreground/80 mt-1.5 line-clamp-2">
                  {p.tagline}
                </p>
              )}
            </div>
            <p className="text-lg font-bold text-foreground whitespace-nowrap tabular-nums">
              {p.badge_text || `${p.price_aed.toLocaleString("en-US")} AED`}
            </p>
          </div>

          {editingId === p.id ? (
            <ProgramEditor
              program={p}
              onDone={() => setEditingId(null)}
            />
          ) : (
            <button
              onClick={() => setEditingId(p.id)}
              className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted w-fit inline-flex items-center gap-1.5 text-foreground"
            >
              <Pencil size={14} /> Edit
            </button>
          )}
        </article>
      ))}
    </div>
  )
}

function ProgramEditor({ program, onDone }: { program: WebsiteProgram; onDone: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [title, setTitle] = useState(program.title)
  const [tagline, setTagline] = useState(program.tagline ?? "")
  const [duration, setDuration] = useState(program.duration)
  const [priceText, setPriceText] = useState(
    program.badge_text || `${program.price_aed.toLocaleString("en-US")} AED`
  )
  const [features, setFeatures] = useState((program.features_list ?? []).join("\n"))
  const [published, setPublished] = useState(program.is_published)

  const save = useMutation({
    mutationFn: () => {
      if (!priceText.trim()) {
        throw new Error("Price / Cost is required")
      }
      const match = priceText.replace(/,/g, "").match(/\d+/)
      const numericPrice = match ? parseInt(match[0], 10) : program.price_aed
      const payload: WebsiteProgramUpdate = {
        title: title.trim(),
        tagline: tagline.trim() || null,
        duration: duration.trim(),
        price_aed: Number.isFinite(numericPrice) && numericPrice >= 0 ? numericPrice : 0,
        badge_text: priceText.trim(),
        features_list: features.split("\n").map((f) => f.trim()).filter(Boolean),
        is_published: published,
      }
      return updateWebsiteProgram(program.id, payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-programs"] })
      toast.success(`“${title.trim()}” saved — the public site updates immediately`)
      onDone()
    },
    onError: (e: unknown) => {
      const detail =
        e instanceof Error && !(isAxiosError(e))
          ? e.message
          : isAxiosError(e) && typeof e.response?.data?.detail === "string"
            ? e.response.data.detail
            : "Could not save this program"
      toast.error(detail)
    },
  })

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Field label="Title" value={title} onChange={setTitle} />
        <Field label="Duration" value={duration} onChange={setDuration} placeholder="e.g. 2-3 Hours" />
        <Field label="Price / Cost" value={priceText} onChange={setPriceText} placeholder="e.g. 2000 - 3000 AED or 1,000 AED / Participant" />
      </div>

      <Field label="Description" value={tagline} onChange={setTagline} />

      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          What Students Learn (one bullet per line)
        </span>
        <textarea
          value={features} onChange={(e) => setFeatures(e.target.value)} rows={4}
          placeholder={"Hands-on satellite model builds\nTeam mission challenges"}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>

      <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer w-fit">
        <input
          type="checkbox" checked={published}
          onChange={(e) => setPublished(e.target.checked)}
          className="w-4 h-4 accent-primary"
        />
        Published on the public site
      </label>

      <div className="flex items-center gap-2">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 disabled:opacity-40 inline-flex items-center gap-1.5"
        >
          <Save size={14} />
          {save.isPending ? "Saving…" : "Save program"}
        </button>
        <button
          onClick={onDone}
          disabled={save.isPending}
          className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted text-foreground"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

type TierFilter = "all" | SponsorTier

function tierLabel(tier: string): string {
  return SPONSOR_TIERS.find((t) => t.value === tier)?.label ?? tier
}

function SponsorsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState<TierFilter>("all")
  const [modal, setModal] = useState<{ open: boolean; sponsor: WebsiteSponsor | null }>({
    open: false,
    sponsor: null,
  })

  const { data: sponsors = [], isLoading, isError } = useQuery({
    queryKey: ["website-sponsors"],
    queryFn: getWebsiteSponsors,
  })

  const toggleActive = useMutation({
    mutationFn: (s: WebsiteSponsor) => updateWebsiteSponsor(s.id, { is_active: !s.is_active }),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: ["website-sponsors"] })
      toast.success(
        updated.is_active ? `“${updated.name}” is now visible on the site` : `“${updated.name}” hidden from the site`,
      )
    },
    onError: () => toast.error("Could not update this sponsor"),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteSponsor(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-sponsors"] })
      toast.success("Sponsor deleted")
    },
    onError: () => toast.error("Could not delete this sponsor"),
  })

  const updateOrder = useMutation({
    mutationFn: ({ id, order }: { id: string; order: number }) =>
      updateWebsiteSponsor(id, { display_order: order }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-sponsors"] })
    },
    onError: () => toast.error("Could not update order"),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load sponsors. Check your connection and try again.
      </p>
    )
  }

  const visible = filter === "all" ? sponsors : sponsors.filter((s) => s.tier === filter)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start flex-wrap">
          {(["all", ...SPONSOR_TIERS.map((t) => t.value)] as TierFilter[]).map((t) => (
            <button
              key={t}
              onClick={() => setFilter(t)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                filter === t
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t === "all" ? "All" : tierLabel(t)}
            </button>
          ))}
        </div>
        <button
          onClick={() => setModal({ open: true, sponsor: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Partner / Client
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {visible.map((s) => (
          <div
            key={s.id}
            className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 flex-wrap"
          >
            <div className="flex items-center gap-2 shrink-0">
              {/* White (Default) Version */}
              <div className="flex flex-col items-center gap-1">
                <div
                  className="w-24 h-14 rounded-lg bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-2 py-1"
                  title="White / Default version"
                >
                  {s.logo_url ? (
                    <img
                      src={resolveWebsiteAsset(s.logo_url)}
                      alt={`${s.name} white logo`}
                      className="max-w-full max-h-full object-contain"
                      onError={(e) => {
                        e.currentTarget.style.display = "none"
                      }}
                    />
                  ) : (
                    <span className="text-[9px] text-muted-foreground">No white</span>
                  )}
                </div>
                <span className="text-[9px] text-muted-foreground uppercase font-semibold tracking-wider">White</span>
              </div>

              {/* Color (Hover) Version */}
              <div className="flex flex-col items-center gap-1">
                <div
                  className="w-24 h-14 rounded-lg bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-2 py-1"
                  title="Colored / Hover version"
                >
                  {s.logo_hover_url ? (
                    <img
                      src={resolveWebsiteAsset(s.logo_hover_url)}
                      alt={`${s.name} colored logo`}
                      className="max-w-full max-h-full object-contain"
                      onError={(e) => {
                        e.currentTarget.style.display = "none"
                      }}
                    />
                  ) : (
                    <span className="text-[9px] text-muted-foreground/60 italic">Fallback</span>
                  )}
                </div>
                <span className="text-[9px] text-muted-foreground uppercase font-semibold tracking-wider">Color</span>
              </div>
            </div>
            <div className="flex-1 min-w-40">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{s.name}</p>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20">
                  {tierLabel(s.tier)}
                </span>
                {!s.is_active && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
                    Hidden
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground flex-wrap">
                {s.website_url ? (
                  <a
                    href={s.website_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-foreground hover:underline truncate max-w-60"
                  >
                    {s.website_url}
                  </a>
                ) : (
                  <span>No link</span>
                )}
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-muted font-mono font-medium text-foreground text-[11px]">
                  Order #{s.display_order}
                </span>
              </div>
            </div>
            <button
              type="button"
              disabled={toggleActive.isPending}
              onClick={() => toggleActive.mutate(s)}
              className={cn(
                "relative w-11 h-6 rounded-full transition-colors shrink-0",
                s.is_active ? "bg-primary" : "bg-muted-foreground/30",
              )}
              aria-label={s.is_active ? `Hide ${s.name}` : `Show ${s.name}`}
              aria-pressed={s.is_active}
            >
              <span
                className={cn(
                  "absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform",
                  s.is_active && "translate-x-5",
                )}
              />
            </button>
            <div className="flex items-center gap-1 shrink-0">
              <div className="flex items-center border border-border rounded-lg overflow-hidden bg-muted/40 mr-1">
                <button
                  type="button"
                  disabled={updateOrder.isPending || s.display_order <= 1}
                  onClick={() => updateOrder.mutate({ id: s.id, order: Math.max(1, s.display_order - 1) })}
                  className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-20 transition-colors cursor-pointer"
                  title="Move order up (#1 is first)"
                >
                  <ChevronUp size={14} />
                </button>
                <div className="w-[1px] h-4 bg-border" />
                <button
                  type="button"
                  disabled={updateOrder.isPending}
                  onClick={() => updateOrder.mutate({ id: s.id, order: s.display_order + 2 })}
                  className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted disabled:opacity-20 transition-colors cursor-pointer"
                  title="Move order down"
                >
                  <ChevronDown size={14} />
                </button>
              </div>
              <button
                onClick={() => setModal({ open: true, sponsor: s })}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label={`Edit ${s.name}`}
              >
                <Pencil size={15} />
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete “${s.name}” from the showcase?`)) remove.mutate(s.id)
                }}
                className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
                aria-label={`Delete ${s.name}`}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No sponsors in this tier yet — add one to feature it on the public site.
          </p>
        )}
      </div>

      {modal.open && (
        <SponsorModal
          key={modal.sponsor?.id ?? "new"}
          sponsor={modal.sponsor}
          allSponsors={sponsors}
          onClose={() => setModal({ open: false, sponsor: null })}
        />
      )}
    </div>
  )
}

function SponsorModal({
  sponsor,
  allSponsors,
  onClose,
}: {
  sponsor: WebsiteSponsor | null
  allSponsors: WebsiteSponsor[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()

  const getNextOrder = (t: string) => {
    const inTier = allSponsors.filter((s) => s.tier === t)
    const max = inTier.reduce((m, s) => Math.max(m, s.display_order), 0)
    return String(max + 1)
  }

  const [name, setName] = useState(sponsor?.name ?? "")
  const [logoUrl, setLogoUrl] = useState(sponsor?.logo_url ?? "")
  const [logoHoverUrl, setLogoHoverUrl] = useState(sponsor?.logo_hover_url ?? "")
  const [websiteUrl, setWebsiteUrl] = useState(sponsor?.website_url ?? "")
  const [tier, setTier] = useState<SponsorTier>((sponsor?.tier as SponsorTier | undefined) ?? "partner")
  const [order, setOrder] = useState(
    sponsor ? String(sponsor.display_order) : getNextOrder(sponsor?.tier ?? "partner")
  )
  const [active, setActive] = useState(sponsor?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Name is required")
      if (!logoUrl.trim()) throw new Error("Default (White) Logo is required")
      const parsedOrder = Math.max(1, Number(order) || 1)
      const payload = {
        name: name.trim(),
        logo_url: logoUrl.trim(),
        logo_hover_url: logoHoverUrl.trim() || null,
        website_url: websiteUrl.trim() || null,
        tier,
        display_order: parsedOrder,
        is_active: active,
      }
      return sponsor
        ? updateWebsiteSponsor(sponsor.id, payload)
        : createWebsiteSponsor(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-sponsors"] })
      toast.success(`“${saved.name}” saved — order #${saved.display_order}`)
      onClose()
    },
    onError: (e: unknown) => {
      const detail =
        e instanceof Error && !isAxiosError(e)
          ? e.message
          : isAxiosError(e) && typeof e.response?.data?.detail === "string"
            ? Array.isArray(e.response.data.detail)
              ? e.response.data.detail.map((d: { msg?: string }) => d.msg ?? "Invalid value").join("; ")
              : e.response.data.detail
            : "Could not save this sponsor"
      toast.error(detail)
    },
  })

  return (
    <Modal title={sponsor ? `Edit ${sponsor.name}` : "Add Partner / Client"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Name" value={name} onChange={setName} placeholder="e.g. EDGE Group" />
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Tier
          </span>
          <select
            value={tier}
            onChange={(e) => {
              const nextTier = e.target.value as SponsorTier
              setTier(nextTier)
              if (!sponsor) {
                setOrder(getNextOrder(nextTier))
              }
            }}
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          >
            {SPONSOR_TIERS.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AssetField
          label="Default Logo (White Version)"
          value={logoUrl}
          onChange={setLogoUrl}
          accept="image/*,.svg"
          placeholder="Upload white logo or paste URL"
          aspectHint="Freeform (No Lock)"
          helper="Shown on dark backgrounds. Cropper opens with full flexibility and no lock."
        />
        <AssetField
          label="Hover Logo (Colored Version)"
          value={logoHoverUrl}
          onChange={setLogoHoverUrl}
          accept="image/*,.svg"
          placeholder="Upload colored logo or paste URL"
          aspectHint="Freeform (No Lock)"
          helper="Revealed on mouse hover. Cropper opens with full flexibility and no lock."
        />
      </div>

      {(logoUrl.trim() || logoHoverUrl.trim()) && (
        <div className="flex flex-col gap-1.5 p-3 rounded-xl bg-muted/40 border border-border">
          <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
            Logo Previews (Hover right box to test)
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="flex flex-col items-center gap-1">
              <div className="w-full h-16 rounded-xl bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-4 py-2">
                {logoUrl.trim() ? (
                  <img
                    src={resolveWebsiteAsset(logoUrl.trim())}
                    alt="White logo preview"
                    className="max-w-full max-h-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.display = "none"
                    }}
                  />
                ) : (
                  <span className="text-xs text-muted-foreground">No white logo</span>
                )}
              </div>
              <span className="text-[10px] text-muted-foreground font-medium">1. White (Default)</span>
            </div>

            <div className="flex flex-col items-center gap-1">
              <div className="w-full h-16 rounded-xl bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-4 py-2">
                {logoHoverUrl.trim() ? (
                  <img
                    src={resolveWebsiteAsset(logoHoverUrl.trim())}
                    alt="Colored logo preview"
                    className="max-w-full max-h-full object-contain"
                    onError={(e) => {
                      e.currentTarget.style.display = "none"
                    }}
                  />
                ) : (
                  <span className="text-xs text-muted-foreground italic">None (Falls back)</span>
                )}
              </div>
              <span className="text-[10px] text-muted-foreground font-medium">2. Color (Hover)</span>
            </div>

            <div className="flex flex-col items-center gap-1">
              <div
                className="w-full h-16 rounded-xl bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-4 py-2 relative group cursor-pointer"
                title="Hover cursor here to preview the transition"
              >
                {logoUrl.trim() && (
                  <img
                    src={resolveWebsiteAsset(logoUrl.trim())}
                    alt="Preview default"
                    className={cn(
                      "max-w-full max-h-full object-contain transition-opacity duration-300",
                      logoHoverUrl.trim() ? "group-hover:opacity-0" : ""
                    )}
                  />
                )}
                {logoHoverUrl.trim() && (
                  <img
                    src={resolveWebsiteAsset(logoHoverUrl.trim())}
                    alt="Preview hover"
                    className="absolute max-w-full max-h-full object-contain opacity-0 transition-opacity duration-300 group-hover:opacity-100"
                  />
                )}
              </div>
              <span className="text-[10px] text-primary font-semibold">Hover to Test</span>
            </div>
          </div>
        </div>
      )}
      <Field label="Website URL" value={websiteUrl} onChange={setWebsiteUrl} placeholder="https://… (optional)" />

      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Display Order (Starts from 1)
          </span>
          <input
            type="number" min={1} step={1} value={order}
            onChange={(e) => setOrder(e.target.value)}
            placeholder="1, 2, 3..."
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
          />
          <span className="text-[10px] text-muted-foreground">Auto-renumbers with no duplicates</span>
        </label>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer self-end pb-2.5">
          <input
            type="checkbox" checked={active}
            onChange={(e) => setActive(e.target.checked)}
            className="w-4 h-4 accent-primary"
          />
          Active (visible on site)
        </label>
      </div>

      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!name.trim() || !logoUrl.trim()}
        label={sponsor ? "Save changes" : "Add sponsor"}
      />
    </Modal>
  )
}

// ── Tab 4: FAQs ─────────────────────────────────────────────────────────────

function FaqsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [category, setCategory] = useState<string>("all")
  const [modal, setModal] = useState<{ open: boolean; faq: WebsiteFaq | null }>({
    open: false,
    faq: null,
  })

  const { data: faqs = [], isLoading, isError } = useQuery({
    queryKey: ["website-faqs"],
    queryFn: getWebsiteFaqs,
  })

  const toggleActive = useMutation({
    mutationFn: (f: WebsiteFaq) => updateWebsiteFaq(f.id, { is_active: !f.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-faqs"] })
      toast.success("FAQ visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this FAQ")),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteFaq(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-faqs"] })
      toast.success("FAQ deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this FAQ")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load FAQs. Check your connection and try again.
      </p>
    )
  }

  const categories = [...new Set(faqs.map((f) => f.category))]
  const visible = category === "all" ? faqs : faqs.filter((f) => f.category === category)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start flex-wrap">
          {(["all", ...categories] as string[]).map((c) => (
            <button
              key={c}
              onClick={() => setCategory(c)}
              className={cn(
                "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                category === c
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {c === "all" ? "All" : c}
            </button>
          ))}
        </div>
        <button
          onClick={() => setModal({ open: true, faq: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add FAQ
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {visible.map((f) => (
          <div key={f.id} className="rounded-2xl border border-border bg-card p-4 flex flex-col gap-2">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{f.question}</p>
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20">
                  {f.category}
                </span>
                {!f.is_active && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
                    Hidden
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <ActiveToggle
                  active={f.is_active}
                  label={f.is_active ? "Hide FAQ" : "Show FAQ"}
                  onToggle={() => toggleActive.mutate(f)}
                  disabled={toggleActive.isPending}
                />
                <button
                  onClick={() => setModal({ open: true, faq: f })}
                  className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  aria-label="Edit FAQ"
                >
                  <Pencil size={15} />
                </button>
                <button
                  onClick={() => {
                    if (confirm("Delete this FAQ?")) remove.mutate(f.id)
                  }}
                  className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
                  aria-label="Delete FAQ"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">{f.answer}</p>
            <p className="text-[11px] text-muted-foreground tabular-nums">Order {f.display_order}</p>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No FAQs here yet — add one to answer it on the public site.
          </p>
        )}
      </div>

      {modal.open && (
        <FaqModal
          key={modal.faq?.id ?? "new"}
          faq={modal.faq}
          categories={categories}
          onClose={() => setModal({ open: false, faq: null })}
        />
      )}
    </div>
  )
}

function FaqModal({
  faq,
  categories,
  onClose,
}: {
  faq: WebsiteFaq | null
  categories: string[]
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [category, setCategory] = useState(faq?.category ?? categories[0] ?? "General")
  const [question, setQuestion] = useState(faq?.question ?? "")
  const [answer, setAnswer] = useState(faq?.answer ?? "")
  const [order, setOrder] = useState(String(faq?.display_order ?? 0))
  const [active, setActive] = useState(faq?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!question.trim()) throw new Error("Question is required")
      if (!answer.trim()) throw new Error("Answer is required")
      const payload = {
        category: category.trim() || "General",
        question: question.trim(),
        answer: answer.trim(),
        display_order: Number(order) || 0,
        is_active: active,
      }
      return faq ? updateWebsiteFaq(faq.id, payload) : createWebsiteFaq(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-faqs"] })
      toast.success("FAQ saved — the public site updates immediately")
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this FAQ")),
  })

  return (
    <Modal title={faq ? "Edit FAQ" : "Add FAQ"} onClose={onClose}>
      <Field label="Category" value={category} onChange={setCategory} placeholder="General" />
      {categories.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              className={cn(
                "px-2.5 py-1 rounded-lg text-xs font-medium border transition-colors",
                category === c
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {c}
            </button>
          ))}
        </div>
      )}
      <Field label="Question" value={question} onChange={setQuestion} placeholder="What is…?" />
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Answer
        </span>
        <textarea
          value={answer} onChange={(e) => setAnswer(e.target.value)} rows={4}
          placeholder="The full answer shown in the accordion…"
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Display Order (Starts from 1)
          </span>
          <input
            type="number" min={1} step={1} value={order}
            onChange={(e) => setOrder(e.target.value)}
            placeholder="1, 2, 3..."
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
          />
          <span className="text-[10px] text-muted-foreground">Auto-renumbers with no duplicates</span>
        </label>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer self-end pb-2.5">
          <input
            type="checkbox" checked={active}
            onChange={(e) => setActive(e.target.checked)}
            className="w-4 h-4 accent-primary"
          />
          Active (visible on site)
        </label>
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!question.trim() || !answer.trim()}
        label={faq ? "Save changes" : "Add FAQ"}
      />
    </Modal>
  )
}

// ── Tab 5: Media & Press ────────────────────────────────────────────────────

function MediaSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; clipping: WebsiteMediaClipping | null }>({
    open: false,
    clipping: null,
  })

  const { data: clippings = [], isLoading, isError } = useQuery({
    queryKey: ["website-media"],
    queryFn: getWebsiteMedia,
  })

  const toggleActive = useMutation({
    mutationFn: (c: WebsiteMediaClipping) => updateWebsiteMedia(c.id, { is_active: !c.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-media"] })
      toast.success("Clipping visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this clipping")),
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteMedia(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-media"] })
      toast.success("Clipping deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this clipping")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load media clippings. Check your connection and try again.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, clipping: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Clipping
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {clippings.map((c) => (
          <div
            key={c.id}
            className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 flex-wrap"
          >
            <div className="w-28 h-14 rounded-lg bg-[#130921] border border-border flex items-center justify-center overflow-hidden shrink-0 px-2">
              {c.logo_url ? (
                <img
                  src={resolveWebsiteAsset(c.logo_url)}
                  alt={`${c.publisher_name} logo`}
                  className="max-w-full max-h-full object-contain"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              ) : (
                <span className="text-[10px] text-muted-foreground">No logo</span>
              )}
            </div>
            <div className="flex-1 min-w-40" dir={c.is_arabic ? "rtl" : undefined}>
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{c.article_title}</p>
                {c.is_arabic && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20">
                    RTL · AR
                  </span>
                )}
                {!c.is_active && (
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
                    Hidden
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
                <span>{c.publisher_name}</span>
                {c.published_date && <span>{c.published_date}</span>}
                <span className="tabular-nums">Order {c.display_order}</span>
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <ActiveToggle
                active={c.is_active}
                label={c.is_active ? "Hide clipping" : "Show clipping"}
                onToggle={() => toggleActive.mutate(c)}
                disabled={toggleActive.isPending}
              />
              <button
                onClick={() => setModal({ open: true, clipping: c })}
                className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                aria-label="Edit clipping"
              >
                <Pencil size={15} />
              </button>
              <button
                onClick={() => {
                  if (confirm(`Delete the “${c.article_title}” clipping?`)) remove.mutate(c.id)
                }}
                className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
                aria-label="Delete clipping"
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>
        ))}
        {clippings.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            No press clippings yet — add one to feature it on the public site.
          </p>
        )}
      </div>

      {modal.open && (
        <MediaModal
          key={modal.clipping?.id ?? "new"}
          clipping={modal.clipping}
          onClose={() => setModal({ open: false, clipping: null })}
        />
      )}
    </div>
  )
}

function MediaModal({
  clipping,
  onClose,
}: {
  clipping: WebsiteMediaClipping | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [publisher, setPublisher] = useState(clipping?.publisher_name ?? "")
  const [title, setTitle] = useState(clipping?.article_title ?? "")
  const [url, setUrl] = useState(clipping?.article_url ?? "")
  const [date, setDate] = useState(clipping?.published_date ?? "")
  const [logoUrl, setLogoUrl] = useState(clipping?.logo_url ?? "")
  const [arabic, setArabic] = useState(clipping?.is_arabic ?? false)
  const [order, setOrder] = useState(String(clipping?.display_order ?? 0))
  const [active, setActive] = useState(clipping?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!publisher.trim()) throw new Error("Publisher name is required")
      if (!title.trim()) throw new Error("Article title is required")
      if (!url.trim()) throw new Error("Article URL is required")
      const payload = {
        publisher_name: publisher.trim(),
        article_title: title.trim(),
        article_url: url.trim(),
        published_date: date.trim(),
        logo_url: logoUrl.trim() || null,
        is_arabic: arabic,
        snippet: null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return clipping
        ? updateWebsiteMedia(clipping.id, payload)
        : createWebsiteMedia(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-media"] })
      toast.success("Clipping saved — the public site updates immediately")
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this clipping")),
  })

  return (
    <Modal title={clipping ? "Edit Clipping" : "Add Clipping"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Publisher" value={publisher} onChange={setPublisher} placeholder="e.g. Gulf News" />
        <Field label="Published Date (optional badge)" value={date} onChange={setDate} placeholder="e.g. May 2025" />
      </div>
      <Field label="Article Title" value={title} onChange={setTitle} placeholder="Headline…" />
      <Field label="Article URL" value={url} onChange={setUrl} placeholder="https://…" />
      <AssetField
        label="Card Image / Logo"
        value={logoUrl}
        onChange={setLogoUrl}
        accept="image/*,.svg"
        placeholder="https://… or upload card image"
        aspect={16 / 10}
        aspectHint="16:10 Card"
      />
      {logoUrl.trim() && (
        <div className="w-full h-24 rounded-xl bg-[#130921] border border-border flex items-center justify-center overflow-hidden px-4 py-2">
          <img
            src={resolveWebsiteAsset(logoUrl.trim())}
            alt="Logo preview"
            className="max-w-full max-h-full object-contain"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Display Order (Starts from 1)
          </span>
          <input
            type="number" min={1} step={1} value={order}
            onChange={(e) => setOrder(e.target.value)}
            placeholder="1, 2, 3..."
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
          />
          <span className="text-[10px] text-muted-foreground">Auto-renumbers with no duplicates</span>
        </label>
        <div className="flex flex-col gap-2 self-end pb-1">
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox" checked={arabic}
              onChange={(e) => setArabic(e.target.checked)}
              className="w-4 h-4 accent-primary"
            />
            Arabic (RTL layout)
          </label>
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox" checked={active}
              onChange={(e) => setActive(e.target.checked)}
              className="w-4 h-4 accent-primary"
            />
            Active (visible on site)
          </label>
        </div>
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!publisher.trim() || !title.trim() || !url.trim()}
        label={clipping ? "Save changes" : "Add clipping"}
      />
    </Modal>
  )
}

// ── Tab 6: Newsletters & Leads ──────────────────────────────────────────────

function NewslettersSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; issue: WebsiteNewsletter | null }>({
    open: false,
    issue: null,
  })

  const {
    data: issues = [],
    isLoading: issuesLoading,
    isError: issuesError,
  } = useQuery({ queryKey: ["website-newsletters"], queryFn: getWebsiteNewsletters })
  const {
    data: leads = [],
    isLoading: leadsLoading,
    isError: leadsError,
  } = useQuery({ queryKey: ["website-leads"], queryFn: () => getWebsiteLeads("newsletter") })

  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteNewsletter(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-newsletters"] })
      toast.success("Newsletter issue deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this issue")),
  })

  const toggleActive = useMutation({
    mutationFn: (n: WebsiteNewsletter) => updateWebsiteNewsletter(n.id, { is_active: !n.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-newsletters"] })
      toast.success("Issue visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this issue")),
  })

  if (issuesLoading || leadsLoading) return <Spinner />
  if (issuesError || leadsError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load newsletters or subscribers. Check your connection and try again.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <section className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">Past Issues</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Archived issues shown on the public site.
            </p>
          </div>
          <button
            onClick={() => setModal({ open: true, issue: null })}
            className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
          >
            <Plus size={15} /> Add Issue
          </button>
        </div>
        <div className="flex flex-col gap-2">
          {issues.map((n) => (
            <NewsletterLeadRow
              key={n.id}
              coverUrl={n.cover_url}
              title={n.title}
              subtitle={n.issue_date}
              href={resolveWebsiteAsset(n.file_url)}
              linkLabel="Open PDF"
              hidden={!n.is_active}
              meta={`Order ${n.display_order}`}
              onToggle={() => toggleActive.mutate(n)}
              toggleDisabled={toggleActive.isPending}
              toggleLabel={n.is_active ? "Hide issue" : "Show issue"}
              onEdit={() => setModal({ open: true, issue: n })}
              onDelete={() => {
                if (confirm(`Delete the “${n.title}” issue?`)) remove.mutate(n.id)
              }}
            />
          ))}
          {issues.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No issues yet — add the first one to start the archive.
            </p>
          )}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">
              Subscribers <span className="text-muted-foreground font-normal">({leads.length})</span>
            </p>
            <p className="text-xs text-muted-foreground mt-0.5">
              Emails captured by the public newsletter form.
            </p>
          </div>
          <button
            onClick={() =>
              exportCsv(
                "newsletter-subscribers.csv",
                [["email", "status", "subscribed_at"], ...leads.map((l) => [l.email, l.status, l.created_at])],
              )
            }
            disabled={leads.length === 0}
            className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted text-foreground disabled:opacity-40"
          >
            Export CSV
          </button>
        </div>
        <div className="flex flex-col gap-1.5 max-h-96 overflow-y-auto">
          {leads.map((l: WebsiteLead) => (
            <div
              key={l.id}
              className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl border border-border/60 text-sm"
            >
              <span className="text-foreground truncate">{l.email}</span>
              <span className="text-[11px] text-muted-foreground whitespace-nowrap tabular-nums">
                {new Date(l.created_at).toLocaleDateString()}
              </span>
            </div>
          ))}
          {leads.length === 0 && (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No subscribers yet.
            </p>
          )}
        </div>
      </section>

      {modal.open && (
        <NewsletterModal
          key={modal.issue?.id ?? "new"}
          issue={modal.issue}
          onClose={() => setModal({ open: false, issue: null })}
        />
      )}
    </div>
  )
}

function NewsletterLeadRow({
  coverUrl,
  title,
  subtitle,
  href,
  linkLabel,
  hidden,
  meta,
  onToggle,
  toggleDisabled,
  toggleLabel,
  onEdit,
  onDelete,
}: {
  coverUrl?: string | null
  title: string
  subtitle: string
  href: string
  linkLabel: string
  hidden: boolean
  meta: string
  onToggle: () => void
  toggleDisabled?: boolean
  toggleLabel: string
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="rounded-xl border border-border/60 px-3 py-2.5 flex items-center gap-3 flex-wrap">
      <PhotoThumb src={coverUrl ?? null} name={title} />
      <div className="flex-1 min-w-40">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          {hidden && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
              Hidden
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-0.5 text-xs text-muted-foreground">
          <span>{subtitle}</span>
          <a href={href} target="_blank" rel="noopener noreferrer" className="hover:text-foreground hover:underline">
            {linkLabel}
          </a>
          <span className="tabular-nums">{meta}</span>
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <ActiveToggle active={!hidden} label={toggleLabel} onToggle={onToggle} disabled={toggleDisabled} />
        <button
          onClick={onEdit}
          className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label="Edit issue"
        >
          <Pencil size={15} />
        </button>
        <button
          onClick={onDelete}
          className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
          aria-label="Delete issue"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )
}

function NewsletterModal({
  issue,
  onClose,
}: {
  issue: WebsiteNewsletter | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [title, setTitle] = useState(issue?.title ?? "")
  const [issueDate, setIssueDate] = useState(issue?.issue_date ?? "")
  const [coverUrl, setCoverUrl] = useState(issue?.cover_url ?? "")
  const [fileUrl, setFileUrl] = useState(issue?.file_url ?? "")
  const [order, setOrder] = useState(String(issue?.display_order ?? 0))
  const [active, setActive] = useState(issue?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!title.trim()) throw new Error("Title is required")
      if (!issueDate.trim()) throw new Error("Issue date is required")
      if (!fileUrl.trim()) throw new Error("File URL is required")
      const payload = {
        title: title.trim(),
        issue_date: issueDate.trim(),
        cover_url: coverUrl.trim() || null,
        file_url: fileUrl.trim(),
        display_order: Number(order) || 0,
        is_active: active,
      }
      return issue
        ? updateWebsiteNewsletter(issue.id, payload)
        : createWebsiteNewsletter(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-newsletters"] })
      toast.success("Newsletter issue saved — the public site updates immediately")
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this issue")),
  })

  return (
    <Modal title={issue ? "Edit Issue" : "Add Issue"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Title" value={title} onChange={setTitle} placeholder="e.g. SpacePoint Newsletter - Issue 6" />
        <Field label="Subtitle / Description" value={issueDate} onChange={setIssueDate} placeholder="e.g. Latest updates on space missions…" />
      </div>
      <AssetField
        label="Newsletter File (PDF)"
        value={fileUrl}
        onChange={setFileUrl}
        accept=".pdf,application/pdf,*/*"
        placeholder="https://… or upload PDF"
      />
      <AssetField
        label="Cover Image"
        value={coverUrl}
        onChange={setCoverUrl}
        accept="image/*"
        placeholder="https://… or upload cover image"
        aspect={3 / 2}
        aspectHint="3:2 Card"
      />
      {coverUrl.trim() && (
        <div className="w-full h-28 rounded-xl overflow-hidden border border-border bg-muted/40">
          <img
            src={resolveWebsiteAsset(coverUrl.trim())}
            alt="Cover preview"
            className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <div className="grid grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Display Order (Starts from 1)
          </span>
          <input
            type="number" min={1} step={1} value={order}
            onChange={(e) => setOrder(e.target.value)}
            placeholder="1, 2, 3..."
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
          />
          <span className="text-[10px] text-muted-foreground">Auto-renumbers with no duplicates</span>
        </label>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer self-end pb-2.5">
          <input
            type="checkbox" checked={active}
            onChange={(e) => setActive(e.target.checked)}
            className="w-4 h-4 accent-primary"
          />
          Active (visible on site)
        </label>
      </div>
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!title.trim() || !issueDate.trim() || !fileUrl.trim()}
        label={issue ? "Save changes" : "Add issue"}
      />
    </Modal>
  )
}

// ── Tab 7: Articles & Editorial Queue ───────────────────────────────────────

type ArticleFilter = "all" | "needs_review" | "changes_requested" | "published" | "drafts"

const ARTICLE_FILTERS: { value: ArticleFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "needs_review", label: "Submitted (Needs Review)" },
  { value: "changes_requested", label: "Changes Requested" },
  { value: "published", label: "Published" },
  { value: "drafts", label: "Drafts" },
]

function articleMatchesFilter(a: WebsiteArticle, filter: ArticleFilter): boolean {
  switch (filter) {
    case "needs_review":
      return a.status === "submitted" || a.status === "in_review"
    case "changes_requested":
      return a.status === "changes_requested"
    case "published":
      return a.status === "published"
    case "drafts":
      return a.status === "draft" || a.status === "archived"
    default:
      return true
  }
}

function EditorialQueueSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [filter, setFilter] = useState<ArticleFilter>("all")
  const [reviewId, setReviewId] = useState<string | null>(null)
  const [editor, setEditor] = useState<{ open: boolean; article: WebsiteArticle | null }>({
    open: false,
    article: null,
  })

  const { data: articles = [], isLoading, isError } = useQuery({
    queryKey: ["website-articles"],
    queryFn: getAllArticles,
  })

  const togglePublish = useMutation({
    mutationFn: (a: WebsiteArticle) =>
      a.status === "published" ? unpublishArticle(a.id) : reviewArticle(a.id, "approve"),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-articles"] })
      qc.invalidateQueries({ queryKey: ["my-articles"] })
      toast.success(
        saved.status === "published"
          ? `“${saved.title}” published on /blog`
          : `“${saved.title}” unpublished`,
      )
    },
    onError: (e) => toast.error(mutationError(e, "Could not update article status")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load the editorial queue. Check your connection and try again.
      </p>
    )
  }

  const visible = articles.filter((a) => articleMatchesFilter(a, filter))
  const reviewing = reviewId ? articles.find((a) => a.id === reviewId) ?? null : null

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start flex-wrap">
          {ARTICLE_FILTERS.map((f) => {
            const count =
              f.value === "all" ? articles.length : articles.filter((a) => articleMatchesFilter(a, f.value)).length
            return (
              <button
                key={f.value}
                onClick={() => setFilter(f.value)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
                  filter === f.value
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {f.label} <span className="tabular-nums opacity-70">({count})</span>
              </button>
            )
          })}
        </div>
        <button
          onClick={() => setEditor({ open: true, article: null })}
          className="h-9 px-3.5 bg-primary text-primary-foreground text-xs font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus className="w-3.5 h-3.5" /> New Article
        </button>
      </div>

      <div className="flex flex-col gap-2">
        {visible.map((a) => (
          <div key={a.id} className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 flex-wrap">
            {a.cover_image_url && (
              <div className="w-16 h-12 rounded-lg overflow-hidden bg-muted/40 border border-border shrink-0">
                <img
                  src={resolveWebsiteAsset(a.cover_image_url)}
                  alt={a.title}
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    e.currentTarget.style.display = "none"
                  }}
                />
              </div>
            )}
            <div className="flex-1 min-w-48">
              <div className="flex items-center gap-2 flex-wrap">
                <p className="text-sm font-semibold text-foreground">{a.title}</p>
                <ArticleStatusBadge status={a.status} />
                <span className="text-[11px] text-muted-foreground uppercase tracking-widest">
                  {a.category}
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                {a.author_display_name}
                {a.author_role ? ` · ${a.author_role}` : ""} · Updated{" "}
                {new Date(a.updated_at).toLocaleString()}
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={() => togglePublish.mutate(a)}
                disabled={togglePublish.isPending}
                className={cn(
                  "h-9 px-3.5 text-xs font-semibold rounded-xl transition-colors disabled:opacity-40",
                  a.status === "published"
                    ? "border border-border hover:bg-muted text-foreground"
                    : "bg-primary text-primary-foreground hover:opacity-90",
                )}
              >
                {a.status === "published" ? "Unpublish" : "Publish"}
              </button>
              <button
                onClick={() => setEditor({ open: true, article: a })}
                className="h-9 px-3.5 border border-border text-xs font-medium rounded-xl hover:bg-muted text-foreground inline-flex items-center gap-1.5"
              >
                <Pencil className="w-3.5 h-3.5" /> Edit
              </button>
              <button
                onClick={() => setReviewId(a.id)}
                className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted text-foreground"
              >
                Review
              </button>
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">
            Nothing in this bucket — the queue is clear.
          </p>
        )}
      </div>

      {reviewing && (
        <ArticleReviewModal
          key={reviewing.id}
          article={reviewing}
          onClose={() => setReviewId(null)}
        />
      )}

      {editor.open && (
        <AdminArticleEditorModal
          key={editor.article?.id ?? "new"}
          article={editor.article}
          onClose={() => setEditor({ open: false, article: null })}
        />
      )}
    </div>
  )
}

function AdminArticleEditorModal({
  article,
  onClose,
}: {
  article: WebsiteArticle | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [title, setTitle] = useState(article?.title ?? "")
  const [category, setCategory] = useState(article?.category ?? "SCIENCE")
  const [coverUrl, setCoverUrl] = useState(article?.cover_image_url ?? "")
  const [authorName, setAuthorName] = useState(article?.author_display_name ?? "")
  const [authorRole, setAuthorRole] = useState(article?.author_role ?? "")
  const [authorInitials, setAuthorInitials] = useState(article?.author_initials ?? "")
  const [summary, setSummary] = useState(article?.summary ?? "")
  const [markdown, setMarkdown] = useState(article?.content_markdown ?? "")
  const [tab, setTab] = useState<"write" | "preview">("write")

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        title: title.trim(),
        category: category.trim().toUpperCase() || "SCIENCE",
        cover_image_url: coverUrl.trim() || null,
        author_display_name: authorName.trim() || undefined,
        author_role: authorRole.trim() || null,
        author_initials: authorInitials.trim().toUpperCase() || null,
        summary: summary.trim() || null,
        content_markdown: markdown,
      }
      return article ? updateArticle(article.id, payload) : createArticle(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-articles"] })
      qc.invalidateQueries({ queryKey: ["my-articles"] })
      toast.success(article ? "Article updated" : "Article created")
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save article")),
  })

  return (
    <Modal
      title={article ? "Edit Article" : "New Article"}
      onClose={onClose}
      maxWidth="sm:max-w-3xl max-w-3xl"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Title
          </span>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Mission Control: Real-time Simulation Platforms in the Classroom"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Category
          </span>
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="SCIENCE"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground uppercase"
          />
        </label>
        <AssetField
          label="Cover Image"
          value={coverUrl}
          onChange={setCoverUrl}
          accept="image/*"
          placeholder="https://… or upload cover image"
          aspect={16 / 9}
          aspectHint="16:9 Cover"
        />
        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Author Name
          </span>
          <input
            type="text"
            value={authorName}
            onChange={(e) => setAuthorName(e.target.value)}
            placeholder="Rayan Al Dahre"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          />
        </label>
        <div className="grid grid-cols-3 gap-2">
          <label className="flex flex-col gap-1.5 col-span-2">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Author Role
            </span>
            <input
              type="text"
              value={authorRole}
              onChange={(e) => setAuthorRole(e.target.value)}
              placeholder="Lead Systems Engineer"
              className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
            />
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Initials
            </span>
            <input
              type="text"
              value={authorInitials}
              onChange={(e) => setAuthorInitials(e.target.value)}
              placeholder="RA"
              className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground uppercase"
            />
          </label>
        </div>
        <label className="flex flex-col gap-1.5 sm:col-span-2">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Summary
          </span>
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="One-line teaser shown on the article…"
            className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground"
          />
        </label>
      </div>

      <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start">
        {(["write", "preview"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-1.5 rounded-lg text-xs font-semibold transition-all capitalize",
              tab === t ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "write" ? (
        <textarea
          value={markdown}
          onChange={(e) => setMarkdown(e.target.value)}
          rows={14}
          placeholder={"## Heading\n\nWrite in **Markdown** — headings, *emphasis*, lists, and [links](https://…)."}
          className="w-full shrink-0 px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y font-mono"
        />
      ) : (
        <div
          className="w-full min-h-60 max-h-96 overflow-y-auto shrink-0 px-4 py-3 border border-border bg-background rounded-xl text-sm text-foreground markdown-preview"
          dangerouslySetInnerHTML={{ __html: marked.parse(markdown || "*Nothing to preview yet…*") as string }}
        />
      )}

      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!title.trim() || !markdown.trim()}
        label={article ? "Save changes" : "Create article"}
      />
    </Modal>
  )
}

function ArticleStatusBadge({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase border",
        status === "published" &&
          "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
        status === "changes_requested" &&
          "bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/20",
        (status === "submitted" || status === "in_review") &&
          "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
        (status === "draft" || status === "archived") &&
          "bg-muted text-muted-foreground border-border",
      )}
    >
      {status.replace(/_/g, " ")}
    </span>
  )
}

function ArticleReviewModal({ article, onClose }: { article: WebsiteArticle; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [feedback, setFeedback] = useState(article.reviewer_feedback ?? "")
  const [pendingAction, setPendingAction] = useState<ReviewAction | "delete" | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["website-articles"] })

  const review = useMutation({
    mutationFn: ({ action, fb }: { action: ReviewAction; fb?: string }) =>
      reviewArticle(article.id, action, fb),
    onSuccess: (saved) => {
      invalidate()
      qc.invalidateQueries({ queryKey: ["my-articles"] })
      toast.success(
        saved.status === "published"
          ? `“${saved.title}” is live on spacepoint.ae/blog`
          : saved.status === "changes_requested"
            ? "Sent back to the author with your feedback"
            : "Article unpublished",
      )
      setPendingAction(null)
      onClose()
    },
    onError: (e) => {
      toast.error(mutationError(e, "Review action failed"))
      setPendingAction(null)
    },
  })

  const unpublish = useMutation({
    mutationFn: () => unpublishArticle(article.id),
    onSuccess: () => {
      invalidate()
      toast.success("Article unpublished — back to draft")
      setPendingAction(null)
      onClose()
    },
    onError: (e) => {
      toast.error(mutationError(e, "Could not unpublish"))
      setPendingAction(null)
    },
  })

  const remove = useMutation({
    mutationFn: () => deleteArticle(article.id),
    onSuccess: () => {
      invalidate()
      toast.success("Article deleted")
      setPendingAction(null)
      onClose()
    },
    onError: (e) => {
      toast.error(mutationError(e, "Could not delete this article"))
      setPendingAction(null)
    },
  })

  const busy = review.isPending || unpublish.isPending || remove.isPending

  return (
    <Modal title="Review Article" onClose={onClose} maxWidth="sm:max-w-3xl max-w-3xl">
      <div className="flex flex-col gap-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h3 className="text-base font-semibold text-foreground">{article.title}</h3>
            <ArticleStatusBadge status={article.status} />
          </div>
          <p className="text-xs text-muted-foreground">
            {article.author_display_name}
            {article.author_role ? ` · ${article.author_role}` : ""} · {article.category} · Updated{" "}
            {new Date(article.updated_at).toLocaleString()}
          </p>
        </div>

        {article.cover_image_url && (
          <div className="w-full h-44 rounded-xl overflow-hidden border border-border bg-muted/40">
            <img
              src={resolveWebsiteAsset(article.cover_image_url)}
              alt={article.title}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = "none"
              }}
            />
          </div>
        )}

        {article.summary && (
          <p className="text-xs text-muted-foreground leading-relaxed border-l-2 border-primary/40 pl-3">
            {article.summary}
          </p>
        )}

        {/* Server-sanitized HTML — safe to inject, same source the public site renders. */}
        <div
          className="rounded-xl border border-border bg-background px-4 py-3 text-sm text-foreground max-h-96 overflow-y-auto markdown-preview"
          dangerouslySetInnerHTML={{ __html: article.content_html }}
        />

        <label className="flex flex-col gap-1.5">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            Reviewer Feedback (required to request changes)
          </span>
          <textarea
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            rows={3}
            placeholder="Actionable notes for the author — what exactly should change?"
            className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
          />
        </label>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => {
              setPendingAction("approve")
              review.mutate({ action: "approve" })
            }}
            disabled={busy}
            className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 disabled:opacity-40"
          >
            {pendingAction === "approve" ? "Publishing…" : "Approve & Publish"}
          </button>
          <button
            onClick={() => {
              if (!feedback.trim()) {
                toast.error("Write feedback first — the author needs to know what to fix")
                return
              }
              setPendingAction("request_changes")
              review.mutate({ action: "request_changes", fb: feedback.trim() })
            }}
            disabled={busy}
            className="h-9 px-4 border border-amber-500/40 text-amber-600 dark:text-amber-400 text-sm font-semibold rounded-xl hover:bg-amber-500/10 disabled:opacity-40"
          >
            {pendingAction === "request_changes" ? "Sending…" : "Request Changes"}
          </button>
          {article.status === "published" && (
            <button
              onClick={() => {
                setPendingAction("unpublish")
                unpublish.mutate()
              }}
              disabled={busy}
              className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted text-foreground disabled:opacity-40"
            >
              Unpublish
            </button>
          )}
          <button
            onClick={() => {
              if (confirm(`Permanently delete “${article.title}”?`)) {
                setPendingAction("delete")
                remove.mutate()
              }
            }}
            disabled={busy}
            className="h-9 px-4 border border-border text-sm font-medium rounded-xl hover:bg-muted text-muted-foreground hover:text-red-600 dark:hover:text-red-400 disabled:opacity-40 ml-auto"
          >
            Delete
          </button>
        </div>
      </div>
    </Modal>
  )
}

// ── People & Showcase (Step 6) ────────────────────────────────────────────

type PeopleDomain = "team" | "ambassadors" | "alumni" | "missions"

const PEOPLE_DOMAINS: { value: PeopleDomain; label: string }[] = [
  { value: "team", label: "Team" },
  { value: "ambassadors", label: "Ambassadors" },
  { value: "alumni", label: "Alumni" },
  { value: "missions", label: "Student Missions" },
]

function PeopleSection() {
  const [domain, setDomain] = useState<PeopleDomain>("team")

  return (
    <div className="flex flex-col gap-4">
      <div className="inline-flex rounded-xl bg-muted/60 p-1 ring-1 ring-border self-start flex-wrap">
        {PEOPLE_DOMAINS.map((d) => (
          <button
            key={d.value}
            onClick={() => setDomain(d.value)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-semibold transition-all",
              domain === d.value
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {d.label}
          </button>
        ))}
      </div>

      {domain === "team" && <TeamSection />}
      {domain === "ambassadors" && <AmbassadorsSection />}
      {domain === "alumni" && <AlumniSection />}
      {domain === "missions" && <MissionsSection />}
    </div>
  )
}

function PhotoThumb({ src, name, round }: { src: string | null; name: string; round?: boolean }) {
  return (
    <div
      className={cn(
        "w-14 h-14 overflow-hidden shrink-0 bg-muted/60 border border-border flex items-center justify-center",
        round ? "rounded-full" : "rounded-xl",
      )}
    >
      {src ? (
        <img
          src={resolveWebsiteAsset(src)}
          alt={name}
          className="w-full h-full object-cover"
          onError={(e) => {
            e.currentTarget.style.display = "none"
          }}
        />
      ) : (
        <span className="text-lg font-bold text-muted-foreground">
          {(name.trim()[0] ?? "?").toUpperCase()}
        </span>
      )}
    </div>
  )
}

function ShowcaseRow({
  thumb,
  title,
  badges,
  meta,
  order,
  active,
  onToggle,
  toggleDisabled,
  toggleLabel,
  onEdit,
  onDelete,
}: {
  thumb: React.ReactNode
  title: string
  badges?: React.ReactNode
  meta: string
  order: number
  active: boolean
  onToggle: () => void
  toggleDisabled?: boolean
  toggleLabel: string
  onEdit: () => void
  onDelete: () => void
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-4 flex items-center gap-4 flex-wrap">
      {thumb}
      <div className="flex-1 min-w-40">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground">{title}</p>
          {badges}
          {!active && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
              Hidden
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 mt-1 text-xs text-muted-foreground">
          <span className="truncate">{meta}</span>
          <span className="tabular-nums whitespace-nowrap">Order {order}</span>
        </div>
      </div>
      <div className="flex items-center gap-1 shrink-0">
        <ActiveToggle active={active} label={toggleLabel} onToggle={onToggle} disabled={toggleDisabled} />
        <button
          onClick={onEdit}
          className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          aria-label={`Edit ${title}`}
        >
          <Pencil size={15} />
        </button>
        <button
          onClick={onDelete}
          className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
          aria-label={`Delete ${title}`}
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  )
}

function OrderActiveFields({
  order,
  setOrder,
  active,
  setActive,
}: {
  order: string
  setOrder: (v: string) => void
  active: boolean
  setActive: (v: boolean) => void
}) {
  return (
    <div className="grid grid-cols-2 gap-4">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Display Order
        </span>
        <input
          type="number" min={0} step={1} value={order}
          onChange={(e) => setOrder(e.target.value)}
          className="h-10 px-3 bg-background border border-border rounded-xl text-sm focus:outline-none focus:border-primary text-foreground tabular-nums"
        />
      </label>
      <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer self-end pb-2.5">
        <input
          type="checkbox" checked={active}
          onChange={(e) => setActive(e.target.checked)}
          className="w-4 h-4 accent-primary"
        />
        Active (visible on site)
      </label>
    </div>
  )
}

// ── Team ────────────────────────────────────────────────────────────────────

function TeamSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; member: WebsiteTeamMember | null }>({
    open: false,
    member: null,
  })

  const { data: members = [], isLoading, isError } = useQuery({
    queryKey: ["website-team"],
    queryFn: getWebsiteTeam,
  })

  const toggle = useMutation({
    mutationFn: (m: WebsiteTeamMember) => updateWebsiteTeamMember(m.id, { is_active: !m.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-team"] })
      toast.success("Team visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this member")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteTeamMember(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-team"] })
      toast.success("Team member deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this member")),
  })

  if (isLoading) return <Spinner />
  if (isError) return <p className="text-sm text-red-600 dark:text-red-400">Could not load the team.</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, member: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Member
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {members.map((m) => (
          <ShowcaseRow
            key={m.id}
            thumb={<PhotoThumb src={m.photo_url} name={m.name} round />}
            title={m.name}
            meta={m.role}
            order={m.display_order}
            active={m.is_active}
            onToggle={() => toggle.mutate(m)}
            toggleDisabled={toggle.isPending}
            toggleLabel={m.is_active ? `Hide ${m.name}` : `Show ${m.name}`}
            onEdit={() => setModal({ open: true, member: m })}
            onDelete={() => {
              if (confirm(`Delete “${m.name}” from the team?`)) remove.mutate(m.id)
            }}
          />
        ))}
        {members.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">No team members yet.</p>
        )}
      </div>
      {modal.open && (
        <TeamModal
          key={modal.member?.id ?? "new"}
          member={modal.member}
          onClose={() => setModal({ open: false, member: null })}
        />
      )}
    </div>
  )
}

function TeamModal({ member, onClose }: { member: WebsiteTeamMember | null; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState(member?.name ?? "")
  const [role, setRole] = useState(member?.role ?? "")
  const [photoUrl, setPhotoUrl] = useState(member?.photo_url ?? "")
  const [order, setOrder] = useState(String(member?.display_order ?? 0))
  const [active, setActive] = useState(member?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Name is required")
      if (!role.trim()) throw new Error("Role is required")
      if (!photoUrl.trim()) throw new Error("Photo URL is required")
      const payload = {
        name: name.trim(),
        role: role.trim(),
        department: member?.department || "Leadership",
        bio: null,
        photo_url: photoUrl.trim(),
        linkedin_url: null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return member ? updateWebsiteTeamMember(member.id, payload) : createWebsiteTeamMember(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-team"] })
      toast.success(`“${saved.name}” saved — the public site updates immediately`)
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this member")),
  })

  return (
    <Modal title={member ? "Edit Team Member" : "Add Team Member"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Name" value={name} onChange={setName} placeholder="e.g. Abdullah AlSalmani" />
        <Field label="Role" value={role} onChange={setRole} placeholder="e.g. CEO & Founder" />
      </div>
      <AssetField
        label="Photo"
        value={photoUrl}
        onChange={setPhotoUrl}
        accept="image/*"
        placeholder="https://… or upload photo"
        aspect={1}
        circularCrop
        aspectHint="1:1 Circle"
      />
      {photoUrl.trim() && (
        <div className="w-20 h-20 rounded-full overflow-hidden border border-border bg-muted/40">
          <img
            src={resolveWebsiteAsset(photoUrl.trim())} alt="Preview" className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <OrderActiveFields order={order} setOrder={setOrder} active={active} setActive={setActive} />
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!name.trim() || !role.trim() || !photoUrl.trim()}
        label={member ? "Save changes" : "Add member"}
      />
    </Modal>
  )
}

// ── Ambassadors ─────────────────────────────────────────────────────────────

function AmbassadorsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; ambassador: WebsiteAmbassador | null }>({
    open: false,
    ambassador: null,
  })

  const { data: ambassadors = [], isLoading, isError } = useQuery({
    queryKey: ["website-ambassadors"],
    queryFn: getWebsiteAmbassadors,
  })

  const toggle = useMutation({
    mutationFn: (a: WebsiteAmbassador) => updateWebsiteAmbassador(a.id, { is_active: !a.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-ambassadors"] })
      toast.success("Ambassador visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this ambassador")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteAmbassador(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-ambassadors"] })
      toast.success("Ambassador deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this ambassador")),
  })

  if (isLoading) return <Spinner />
  if (isError) return <p className="text-sm text-red-600 dark:text-red-400">Could not load ambassadors.</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, ambassador: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Ambassador
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {ambassadors.map((a) => (
          <ShowcaseRow
            key={a.id}
            thumb={<PhotoThumb src={a.photo_url} name={a.name} />}
            title={a.name}
            badges={
              a.badge ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20">
                  {a.badge}
                </span>
              ) : undefined
            }
            meta={a.university}
            order={a.display_order}
            active={a.is_active}
            onToggle={() => toggle.mutate(a)}
            toggleDisabled={toggle.isPending}
            toggleLabel={a.is_active ? `Hide ${a.name}` : `Show ${a.name}`}
            onEdit={() => setModal({ open: true, ambassador: a })}
            onDelete={() => {
              if (confirm(`Delete ambassador “${a.name}”?`)) remove.mutate(a.id)
            }}
          />
        ))}
        {ambassadors.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">No ambassadors yet.</p>
        )}
      </div>
      {modal.open && (
        <AmbassadorModal
          key={modal.ambassador?.id ?? "new"}
          ambassador={modal.ambassador}
          onClose={() => setModal({ open: false, ambassador: null })}
        />
      )}
    </div>
  )
}

function AmbassadorModal({
  ambassador,
  onClose,
}: {
  ambassador: WebsiteAmbassador | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState(ambassador?.name ?? "")
  const [university, setUniversity] = useState(ambassador?.university ?? "")
  const [badge, setBadge] = useState(ambassador?.badge ?? "")
  const [photoUrl, setPhotoUrl] = useState(ambassador?.photo_url ?? "")
  const [order, setOrder] = useState(String(ambassador?.display_order ?? 0))
  const [active, setActive] = useState(ambassador?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Name is required")
      if (!university.trim()) throw new Error("Country is required")
      if (!photoUrl.trim()) throw new Error("Photo URL is required")
      const payload = {
        name: name.trim(),
        university: university.trim(),
        major: null,
        year: null,
        bio: null,
        photo_url: photoUrl.trim(),
        badge: badge.trim() || null,
        linkedin_url: null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return ambassador
        ? updateWebsiteAmbassador(ambassador.id, payload)
        : createWebsiteAmbassador(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-ambassadors"] })
      toast.success(`“${saved.name}” saved — the public site updates immediately`)
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this ambassador")),
  })

  return (
    <Modal title={ambassador ? "Edit Ambassador" : "Add Ambassador"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Name" value={name} onChange={setName} />
        <Field label="Country" value={university} onChange={setUniversity} placeholder="e.g. United Arab Emirates" />
        <Field label="Flag Emoji" value={badge} onChange={setBadge} placeholder="e.g. 🇦🇪" />
        <AssetField
          label="Photo"
          value={photoUrl}
          onChange={setPhotoUrl}
          accept="image/*"
          placeholder="https://… or upload photo"
          aspect={1}
          aspectHint="1:1 Square"
        />
      </div>
      {photoUrl.trim() && (
        <div className="w-20 h-20 rounded-xl overflow-hidden border border-border bg-muted/40">
          <img
            src={resolveWebsiteAsset(photoUrl.trim())} alt="Preview" className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <OrderActiveFields order={order} setOrder={setOrder} active={active} setActive={setActive} />
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!name.trim() || !university.trim() || !photoUrl.trim()}
        label={ambassador ? "Save changes" : "Add ambassador"}
      />
    </Modal>
  )
}

// ── Alumni ──────────────────────────────────────────────────────────────────

function AlumniSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; alumni: WebsiteAlumni | null }>({
    open: false,
    alumni: null,
  })

  const { data: alumni = [], isLoading, isError } = useQuery({
    queryKey: ["website-alumni"],
    queryFn: getWebsiteAlumni,
  })

  const toggle = useMutation({
    mutationFn: (a: WebsiteAlumni) => updateWebsiteAlumni(a.id, { is_active: !a.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-alumni"] })
      toast.success("Alumni visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this alumni card")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteAlumni(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-alumni"] })
      toast.success("Alumni card deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this alumni card")),
  })

  if (isLoading) return <Spinner />
  if (isError) return <p className="text-sm text-red-600 dark:text-red-400">Could not load alumni.</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, alumni: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Alumni
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {alumni.map((a) => (
          <ShowcaseRow
            key={a.id}
            thumb={<PhotoThumb src={a.photo_url} name={a.name} round />}
            title={a.name}
            meta={`${a.program_completed} → ${a.current_role}`}
            order={a.display_order}
            active={a.is_active}
            onToggle={() => toggle.mutate(a)}
            toggleDisabled={toggle.isPending}
            toggleLabel={a.is_active ? `Hide ${a.name}` : `Show ${a.name}`}
            onEdit={() => setModal({ open: true, alumni: a })}
            onDelete={() => {
              if (confirm(`Delete alumni card “${a.name}”?`)) remove.mutate(a.id)
            }}
          />
        ))}
        {alumni.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">No alumni cards yet.</p>
        )}
      </div>
      {modal.open && (
        <AlumniModal
          key={modal.alumni?.id ?? "new"}
          alumni={modal.alumni}
          onClose={() => setModal({ open: false, alumni: null })}
        />
      )}
    </div>
  )
}

function AlumniModal({ alumni, onClose }: { alumni: WebsiteAlumni | null; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [name, setName] = useState(alumni?.name ?? "")
  const [program, setProgram] = useState(alumni?.program_completed ?? "")
  const [role, setRole] = useState(alumni?.current_role ?? "")
  const [photoUrl, setPhotoUrl] = useState(alumni?.photo_url ?? "")
  const [linkedin, setLinkedin] = useState(alumni?.linkedin_url ?? "")
  const [order, setOrder] = useState(String(alumni?.display_order ?? 0))
  const [active, setActive] = useState(alumni?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!name.trim()) throw new Error("Name is required")
      if (!program.trim()) throw new Error("Major / Degree is required")
      if (!role.trim()) throw new Error("Current role is required")
      if (!photoUrl.trim()) throw new Error("Photo URL is required")
      const payload = {
        name: name.trim(),
        program_completed: program.trim(),
        current_role: role.trim(),
        testimonial: null,
        photo_url: photoUrl.trim(),
        linkedin_url: linkedin.trim() || null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return alumni ? updateWebsiteAlumni(alumni.id, payload) : createWebsiteAlumni(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-alumni"] })
      toast.success(`“${saved.name}” saved — the public site updates immediately`)
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this alumni card")),
  })

  return (
    <Modal title={alumni ? "Edit Alumni Card" : "Add Alumni Card"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Name" value={name} onChange={setName} />
        <Field label="Major / Degree" value={program} onChange={setProgram} placeholder="e.g. B.Sc. in Mechanical Engineering" />
      </div>
      <Field label="Current Role / Placement" value={role} onChange={setRole} placeholder="e.g. Mechanical Engineering Intern at SpacePoint" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <AssetField
          label="Photo"
          value={photoUrl}
          onChange={setPhotoUrl}
          accept="image/*"
          placeholder="https://… or upload photo"
          aspect={1}
          circularCrop
          aspectHint="1:1 Circle"
        />
        <Field label="LinkedIn URL" value={linkedin} onChange={setLinkedin} placeholder="https://… (optional)" />
      </div>
      {photoUrl.trim() && (
        <div className="w-20 h-20 rounded-full overflow-hidden border border-border bg-muted/40">
          <img
            src={resolveWebsiteAsset(photoUrl.trim())} alt="Preview" className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <OrderActiveFields order={order} setOrder={setOrder} active={active} setActive={setActive} />
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!name.trim() || !program.trim() || !role.trim() || !photoUrl.trim()}
        label={alumni ? "Save changes" : "Add alumni"}
      />
    </Modal>
  )
}

// ── Student missions ────────────────────────────────────────────────────────

function MissionsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; mission: WebsiteStudentMission | null }>({
    open: false,
    mission: null,
  })

  const { data: missions = [], isLoading, isError } = useQuery({
    queryKey: ["website-student-missions"],
    queryFn: getWebsiteStudentMissions,
  })

  const toggle = useMutation({
    mutationFn: (m: WebsiteStudentMission) =>
      updateWebsiteStudentMission(m.id, { is_active: !m.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-student-missions"] })
      toast.success("Mission visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this mission")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteStudentMission(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-student-missions"] })
      toast.success("Mission deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this mission")),
  })

  if (isLoading) return <Spinner />
  if (isError) return <p className="text-sm text-red-600 dark:text-red-400">Could not load missions.</p>

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, mission: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Mission
        </button>
      </div>
      <div className="flex flex-col gap-2">
        {missions.map((m) => (
          <ShowcaseRow
            key={m.id}
            thumb={<PhotoThumb src={m.photo_url} name={m.project_title} />}
            title={m.project_title}
            meta={m.student_name}
            order={m.display_order}
            active={m.is_active}
            onToggle={() => toggle.mutate(m)}
            toggleDisabled={toggle.isPending}
            toggleLabel={m.is_active ? "Hide mission" : "Show mission"}
            onEdit={() => setModal({ open: true, mission: m })}
            onDelete={() => {
              if (confirm(`Delete “${m.project_title}”?`)) remove.mutate(m.id)
            }}
          />
        ))}
        {missions.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center">No missions yet.</p>
        )}
      </div>
      {modal.open && (
        <MissionModal
          key={modal.mission?.id ?? "new"}
          mission={modal.mission}
          onClose={() => setModal({ open: false, mission: null })}
        />
      )}
    </div>
  )
}

function MissionModal({
  mission,
  onClose,
}: {
  mission: WebsiteStudentMission | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [student, setStudent] = useState(mission?.student_name ?? "")
  const [title, setTitle] = useState(mission?.project_title ?? "")
  const [description, setDescription] = useState(mission?.description ?? "")
  const [photoUrl, setPhotoUrl] = useState(mission?.photo_url ?? "")
  const [order, setOrder] = useState(String(mission?.display_order ?? 0))
  const [active, setActive] = useState(mission?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!student.trim()) throw new Error("Student name is required")
      if (!title.trim()) throw new Error("Project title is required")
      if (!description.trim()) throw new Error("Description is required")
      const payload = {
        student_name: student.trim(),
        project_title: title.trim(),
        category: mission?.category || "Student Project",
        description: description.trim(),
        metrics_json: null,
        docx_url: null,
        photo_url: photoUrl.trim() || null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return mission
        ? updateWebsiteStudentMission(mission.id, payload)
        : createWebsiteStudentMission(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-student-missions"] })
      toast.success(`“${saved.project_title}” saved — the public site updates immediately`)
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this mission")),
  })

  return (
    <Modal title={mission ? "Edit Mission" : "Add Mission"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Student Name" value={student} onChange={setStudent} />
        <Field label="Project Title" value={title} onChange={setTitle} />
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Description
        </span>
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)} rows={4}
          placeholder="What the student built and learned…"
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <AssetField
        label="Photo"
        value={photoUrl}
        onChange={setPhotoUrl}
        accept="image/*"
        placeholder="https://… or upload photo (optional)"
        aspect={16 / 9}
        aspectHint="16:9 Card"
      />
      {photoUrl.trim() && (
        <div className="w-full h-32 rounded-xl overflow-hidden border border-border bg-muted/40">
          <img
            src={resolveWebsiteAsset(photoUrl.trim())} alt="Preview" className="w-full h-full object-cover"
            onError={(e) => {
              e.currentTarget.style.display = "none"
            }}
          />
        </div>
      )}
      <OrderActiveFields order={order} setOrder={setOrder} active={active} setActive={setActive} />
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!student.trim() || !title.trim() || !description.trim()}
        label={mission ? "Save changes" : "Add mission"}
      />
    </Modal>
  )
}

// ── Labs R&D (Step 7) ───────────────────────────────────────────────────────

function LabsSection() {
  const qc = useQueryClient()
  const toast = useToast()
  const [modal, setModal] = useState<{ open: boolean; project: WebsiteLabProject | null }>({
    open: false,
    project: null,
  })

  const { data: projects = [], isLoading, isError } = useQuery({
    queryKey: ["website-labs"],
    queryFn: getWebsiteLabs,
  })

  const toggle = useMutation({
    mutationFn: (p: WebsiteLabProject) => updateWebsiteLab(p.id, { is_active: !p.is_active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-labs"] })
      toast.success("Project visibility updated")
    },
    onError: (e) => toast.error(mutationError(e, "Could not update this project")),
  })
  const remove = useMutation({
    mutationFn: (id: string) => deleteWebsiteLab(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["website-labs"] })
      toast.success("Project deleted")
    },
    onError: (e) => toast.error(mutationError(e, "Could not delete this project")),
  })

  if (isLoading) return <Spinner />
  if (isError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400">
        Could not load R&amp;D projects. Check your connection and try again.
      </p>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-end">
        <button
          onClick={() => setModal({ open: true, project: null })}
          className="h-9 px-4 bg-primary text-primary-foreground text-sm font-semibold rounded-xl hover:opacity-90 inline-flex items-center gap-1.5"
        >
          <Plus size={15} /> Add Project
        </button>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {projects.map((p) => (
          <article key={p.id} className="rounded-2xl border border-border bg-card p-5 flex flex-col gap-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h3 className="text-sm font-semibold text-foreground">{p.title}</h3>
                  {!p.is_active && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-muted text-muted-foreground border border-border">
                      Hidden
                    </span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-1 font-mono">{p.slug}</p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <ActiveToggle
                  active={p.is_active}
                  label={p.is_active ? `Hide ${p.title}` : `Show ${p.title}`}
                  onToggle={() => toggle.mutate(p)}
                  disabled={toggle.isPending}
                />
                <button
                  onClick={() => setModal({ open: true, project: p })}
                  className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  aria-label={`Edit ${p.title}`}
                >
                  <Pencil size={15} />
                </button>
                <button
                  onClick={() => {
                    if (confirm(`Delete project “${p.title}”?`)) remove.mutate(p.id)
                  }}
                  className="p-2 rounded-lg text-muted-foreground hover:text-red-600 dark:hover:text-red-400 hover:bg-muted transition-colors"
                  aria-label={`Delete ${p.title}`}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
            {p.badges.length > 0 && (
              <div className="flex gap-1.5 flex-wrap">
                {p.badges.map((b) => (
                  <span
                    key={b}
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wide uppercase bg-primary/10 text-primary border border-primary/20"
                  >
                    {b}
                  </span>
                ))}
              </div>
            )}
            <p className="text-xs text-muted-foreground leading-relaxed line-clamp-3">{p.description}</p>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              <span className="font-mono truncate">{p.project_url}</span>
              <span className="tabular-nums whitespace-nowrap">Order {p.display_order}</span>
            </div>
          </article>
        ))}
        {projects.length === 0 && (
          <p className="text-sm text-muted-foreground py-8 text-center col-span-full">
            No R&amp;D projects yet.
          </p>
        )}
      </div>
      {modal.open && (
        <LabModal
          key={modal.project?.id ?? "new"}
          project={modal.project}
          onClose={() => setModal({ open: false, project: null })}
        />
      )}
    </div>
  )
}

function LabModal({ project, onClose }: { project: WebsiteLabProject | null; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [title, setTitle] = useState(project?.title ?? "")
  const [slug, setSlug] = useState(project?.slug ?? "")
  const [badges, setBadges] = useState((project?.badges ?? []).join("\n"))
  const [description, setDescription] = useState(project?.description ?? "")
  const [projectUrl, setProjectUrl] = useState(project?.project_url ?? "/miura-ori")
  const [cta, setCta] = useState(project?.cta_label ?? "Launch Project →")
  const [coverUrl, setCoverUrl] = useState(project?.cover_image_url ?? "")
  const [order, setOrder] = useState(String(project?.display_order ?? 0))
  const [active, setActive] = useState(project?.is_active ?? true)

  const save = useMutation({
    mutationFn: () => {
      if (!title.trim()) throw new Error("Title is required")
      if (!description.trim()) throw new Error("Description is required")
      const payload = {
        title: title.trim(),
        slug: slug.trim() || undefined,
        badges: badges.split("\n").map((b) => b.trim()).filter(Boolean),
        description: description.trim(),
        project_url: projectUrl.trim() || "/miura-ori",
        cta_label: cta.trim() || "Launch Project →",
        cover_image_url: coverUrl.trim() || null,
        display_order: Number(order) || 0,
        is_active: active,
      }
      return project ? updateWebsiteLab(project.id, payload) : createWebsiteLab(payload)
    },
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ["website-labs"] })
      toast.success(`“${saved.title}” saved — labs.spacepoint.ae updates immediately`)
      onClose()
    },
    onError: (e) => toast.error(mutationError(e, "Could not save this project")),
  })

  return (
    <Modal title={project ? "Edit Project" : "Add Project"} onClose={onClose}>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Title" value={title} onChange={setTitle} />
        <Field
          label="Slug (blank = auto)"
          value={slug}
          onChange={setSlug}
          placeholder="auto-generated from title"
        />
      </div>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Badges (one per line)
        </span>
        <textarea
          value={badges} onChange={(e) => setBadges(e.target.value)} rows={2}
          placeholder={"Active Simulation\nDeployable Origami Mechanics"}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Description
        </span>
        <textarea
          value={description} onChange={(e) => setDescription(e.target.value)} rows={3}
          className="w-full px-3 py-2 border border-border bg-background text-foreground rounded-xl text-sm resize-y"
        />
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="Project URL" value={projectUrl} onChange={setProjectUrl} placeholder="/miura-ori" />
        <Field label="CTA Label" value={cta} onChange={setCta} />
      </div>
      <AssetField
        label="Cover Image"
        value={coverUrl}
        onChange={setCoverUrl}
        accept="image/*"
        placeholder="https://… or upload cover image (optional)"
        aspect={16 / 9}
        aspectHint="16:9 Cover"
      />
      <OrderActiveFields order={order} setOrder={setOrder} active={active} setActive={setActive} />
      <ModalActions
        onCancel={onClose}
        onConfirm={() => save.mutate()}
        loading={save.isPending}
        disabled={!title.trim() || !description.trim()}
        label={project ? "Save changes" : "Add project"}
      />
    </Modal>
  )
}
