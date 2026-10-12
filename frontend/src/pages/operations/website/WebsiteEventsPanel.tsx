import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  ArrowLeft,
  Building2,
  CalendarDays,
  CheckCircle2,
  Clock,
  Crop,
  ExternalLink,
  Eye,
  EyeOff,
  ImagePlus,
  Layers,
  Pencil,
  Plus,
  Save,
  Trash2,
  Upload,
} from "lucide-react"
import { cn, getErrorMessage } from "@/lib/utils"
import { Spinner } from "@/components/ui/primitives"
import { ImageCropModal } from "@/components/ui/ImageCropModal"
import { useToast } from "@/components/ui/toast"
import { CountrySelect } from "@/components/ui/CountrySelect"
import { CityNameSelect } from "@/components/ui/CitySelect"
import { UserProfileModal } from "@/components/UserProfileModal"
import { apiBaseUrl } from "@/api/client"
import { uploadWebsiteAsset } from "@/api/websiteConfig"
import {
  createAdminMegaEvent,
  createAdminOrganizationAccount,
  createAdminWebsiteEvent,
  deleteAdminMegaEvent,
  deleteAdminOrganizationAccount,
  deleteAdminWebsiteEvent,
  getAdminEventOrganizations,
  getAdminMegaEvents,
  getAdminOrganizationResetLink,
  getAdminWebsiteEvents,
  togglePublishWebsiteEvent,
  updateAdminMegaEvent,
  updateAdminOrganizationAccount,
  updateAdminWebsiteEvent,
  type MegaEvent,
  type MegaEventCreateInput,
  type OrganizationAccountSummary,
  type WebsiteEvent,
  type WebsiteEventInput,
} from "@/api/websiteEvents"

const WEBSITE_BASE_URL =
  (import.meta.env.VITE_WEBSITE_URL as string | undefined)?.replace(/\/$/, "") ||
  (typeof window !== "undefined" &&
  window.location.hostname !== "localhost" &&
  window.location.hostname !== "127.0.0.1"
    ? "https://spacepoint.ae"
    : "http://localhost:4321")

const EVENT_TYPES = [
  { value: "competition", label: "Competition" },
  { value: "workshop", label: "Workshop" },
  { value: "talk", label: "Talk / Keynote" },
  { value: "exhibition", label: "Exhibition" },
  { value: "panel", label: "Panel Discussion" },
  { value: "hackathon", label: "Hackathon" },
  { value: "stargazing", label: "Stargazing" },
  { value: "other", label: "Other" },
]

const COUNTRIES = [
  { value: "uae", label: "UAE (United Arab Emirates)" },
  { value: "ksa", label: "KSA (Saudi Arabia)" },
  { value: "oman", label: "Oman" },
  { value: "bahrain", label: "Bahrain" },
  { value: "kuwait", label: "Kuwait" },
  { value: "qatar", label: "Qatar" },
  { value: "egypt", label: "Egypt" },
  { value: "jordan", label: "Jordan" },
  { value: "global", label: "Global / International" },
]

const inputCls =
  "w-full h-10 rounded-xl border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

const textareaCls =
  "w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

function InputField({
  label,
  value,
  onChange,
  placeholder,
  helper,
  type = "text",
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  helper?: string
  type?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={inputCls}
      />
      {helper && <span className="text-[11px] text-muted-foreground">{helper}</span>}
    </label>
  )
}

function TextAreaField({
  label,
  value,
  onChange,
  rows = 3,
  placeholder,
  helper,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  rows?: number
  placeholder?: string
  helper?: string
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <textarea
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={textareaCls}
      />
      {helper && <span className="text-[11px] text-muted-foreground">{helper}</span>}
    </label>
  )
}

export function getUploadedBannerUrl(url?: string | null): string | null {
  const clean = (url || "").trim()
  if (!clean || clean === "/assets/img/The Mission.jpg") return null
  return clean
}

export function resolvePreviewImageUrl(url?: string | null): string | null {
  const clean = (url || "").trim()
  if (!clean) return null
  const apiPrefix = apiBaseUrl.replace(/\/$/, "")
  if (clean.startsWith("/public/website/uploads/") || clean.startsWith("/files/")) {
    return `${apiPrefix}${clean}`
  }
  if (clean.startsWith("https://portal.spacepoint.ae/public/website/uploads/")) {
    return clean.replace(
      "https://portal.spacepoint.ae/public/website/uploads/",
      `${apiPrefix}/public/website/uploads/`
    )
  }
  if (clean.startsWith("/assets/")) return `${WEBSITE_BASE_URL}${clean}`
  return clean
}

export function EventBannerUploader({
  bannerUrl,
  onChange,
  eventTitle,
  breadcrumb,
}: {
  bannerUrl: string | null | undefined
  onChange: (url: string | null) => void
  eventTitle: string
  breadcrumb: string
}) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [cropModalOpen, setCropModalOpen] = useState(false)
  const [selectedImageForCrop, setSelectedImageForCrop] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)

  const effectiveUrl = resolvePreviewImageUrl(getUploadedBannerUrl(bannerUrl))

  const handleFilePicked = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === "string") {
        setSelectedImageForCrop(reader.result)
        setCropModalOpen(true)
      }
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }

  const handleCropConfirmed = async (croppedFile: File) => {
    setUploading(true)
    try {
      const res = await uploadWebsiteAsset(croppedFile)
      onChange(res.url)
      setCropModalOpen(false)
      setSelectedImageForCrop(null)
      toast.success("Top banner uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload banner"))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-background p-4 space-y-3">
      <div className="flex items-start gap-4">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="group relative w-24 h-24 shrink-0 rounded-2xl bg-muted overflow-hidden ring-1 ring-border cursor-pointer"
          title="Upload top banner image"
        >
          {effectiveUrl ? (
            <img src={effectiveUrl} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1 text-muted-foreground">
              <ImagePlus size={16} />
              <span className="text-[10px]">Add banner</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-medium">
            {uploading ? "Uploading..." : effectiveUrl ? "Change" : "Upload"}
          </div>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFilePicked}
        />

        <div className="flex flex-col gap-1 pt-0.5 flex-1 min-w-0">
          <div className="text-sm font-semibold text-foreground">
            Event Page Top Banner (Optional)
          </div>
          <div className="text-xs text-muted-foreground">
            Displayed full-width between the top navbar and the route breadcrumb (just like LMS checklists). If no banner is uploaded, nothing is shown.
          </div>

          <div className="flex flex-wrap items-center gap-3 mt-1.5">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition cursor-pointer"
            >
              <Upload size={12} />
              <span>{effectiveUrl ? "Replace Image" : "Upload Banner"}</span>
            </button>

            {effectiveUrl && (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedImageForCrop(effectiveUrl)
                    setCropModalOpen(true)
                  }}
                  className="text-xs font-semibold text-primary hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Crop size={12} />
                  <span>Crop &amp; Preview Banner</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    onChange(null)
                    toast.success("Banner removed (click Save to apply)")
                  }}
                  className="text-xs font-semibold text-destructive hover:underline flex items-center gap-1 cursor-pointer"
                >
                  <Trash2 size={12} />
                  <span>Remove Banner</span>
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {effectiveUrl && (
        <div className="relative rounded-xl overflow-hidden border border-border bg-neutral-950">
          <img src={effectiveUrl} alt="Event top banner preview" className="w-full h-auto max-h-44 object-cover block" />
        </div>
      )}

      <ImageCropModal
        isOpen={cropModalOpen}
        onClose={() => {
          if (!uploading) {
            setCropModalOpen(false)
            setSelectedImageForCrop(null)
          }
        }}
        imageSrc={selectedImageForCrop}
        title="Crop & Preview Event Banner"
        previewMode="event"
        previewBreadcrumb={breadcrumb}
        programName={eventTitle || "Event Title"}
        onCropComplete={handleCropConfirmed}
        isUploading={uploading}
      />
    </div>
  )
}

export function HeroBackgroundUploader({
  imageUrl,
  onChange,
}: {
  imageUrl: string | null | undefined
  onChange: (url: string | null) => void
}) {
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  const cleanUrl = (imageUrl || "").trim() || null
  const previewSrc = resolvePreviewImageUrl(cleanUrl)

  const handleFilePicked = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ""
    setUploading(true)
    try {
      const res = await uploadWebsiteAsset(file)
      onChange(res.url)
      toast.success("Hero background image uploaded")
    } catch (err) {
      toast.error(getErrorMessage(err, "Failed to upload background image"))
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-background p-4 space-y-3">
      <div className="flex items-start gap-4">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="group relative w-24 h-24 shrink-0 rounded-2xl bg-muted overflow-hidden ring-1 ring-border cursor-pointer"
          title="Upload hero card background image"
        >
          {previewSrc ? (
            <img src={previewSrc} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center gap-1 text-muted-foreground">
              <ImagePlus size={16} />
              <span className="text-[10px]">No bg image</span>
            </div>
          )}
          <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center text-white text-xs font-medium">
            {uploading ? "Uploading..." : previewSrc ? "Change" : "Upload"}
          </div>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={handleFilePicked}
        />

        <div className="flex flex-col gap-1 pt-0.5 flex-1 min-w-0">
          <div className="text-sm font-semibold text-foreground">
            Hero Card Background Image (Inside Hero Box)
          </div>
          <div className="text-xs text-muted-foreground">
            Displayed as a subtle 20%-opacity background inside the Hero card and on event directory cards.
          </div>

          <div className="flex flex-wrap items-center gap-2.5 mt-1.5">
            <button
              type="button"
              disabled={uploading}
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition cursor-pointer"
            >
              <Upload size={12} />
              <span>{uploading ? "Uploading..." : cleanUrl ? "Upload Custom Image" : "Upload Image"}</span>
            </button>

            {cleanUrl !== "/assets/img/The Mission.jpg" && (
              <button
                type="button"
                onClick={() => {
                  onChange("/assets/img/The Mission.jpg")
                  toast.success("Restored default Hero background (click Save to apply)")
                }}
                className="text-xs font-semibold text-primary hover:underline cursor-pointer"
              >
                Use Default (The Mission.jpg)
              </button>
            )}

            {cleanUrl && (
              <button
                type="button"
                onClick={() => {
                  onChange(null)
                  toast.success("Hero background removed (click Save to apply)")
                }}
                className="text-xs font-semibold text-destructive hover:underline flex items-center gap-1 cursor-pointer"
              >
                <Trash2 size={12} />
                <span>Remove Background</span>
              </button>
            )}
          </div>

          <div className="mt-2">
            <input
              type="text"
              value={cleanUrl || ""}
              onChange={(e) => onChange(e.target.value || null)}
              placeholder="/assets/img/The Mission.jpg or uploaded image URL"
              className={cn(inputCls, "h-8 text-xs")}
            />
          </div>
        </div>
      </div>
    </div>
  )
}

const AR_LOCALIZED_KEYS = new Set<string>([
  "title",
  "subtitle",
  "tagline",
  "city",
  "audience",
  "host_org_name",
  "date_label",
  "location",
  "about_text",
  "benefits",
  "at_a_glance",
  "eligibility_intro",
  "eligibility_rows",
  "eligibility_note",
  "journey_stages",
  "timeline",
  "timeline_note",
  "deliverables",
  "deliverables_note",
  "awards_text",
  "registration_text",
  "registration_deadline",
  "registration_note",
  "faqs",
  "partners",
  "partners_note",
  "contacts",
  "contact_meta",
])

export function emptyEventDraft(defaults?: Partial<WebsiteEventInput>): WebsiteEventInput {
  return {
    slug: "",
    mega_event_id: null,
    organization_id: null,
    country: "uae",
    city: "Abu Dhabi",
    event_type: "competition",
    audience: "Universities",
    venue_type: "onsite",
    title: "",
    title_ar: "",
    subtitle: "",
    tagline: "",
    banner_url: "/assets/img/The Mission.jpg",
    top_banner_url: null,
    host_org_name: "",
    date_label: "",
    location: "",
    registration_url: "",
    guidelines_url: "",
    wsw_official_url: "",
    about_text: "",
    benefits: [],
    at_a_glance: [],
    eligibility_intro: "",
    eligibility_rows: [],
    eligibility_note: "",
    journey_stages: [],
    timeline: [],
    timeline_note: "",
    deliverables: [],
    deliverables_note: "",
    awards_text: "",
    registration_text: "",
    registration_deadline: "",
    whatsapp_url: "",
    registration_note: "",
    faqs: [],
    partners: [],
    partners_note: "",
    contacts: [],
    contact_meta: [],
    display_order: 0,
    is_published: false,
    default_language: "en",
    ar_content: { enabled: false, en_enabled: true },
    ...defaults,
  }
}

/* ========================================================================== */
/* FULL-PAGE EVENT EDITOR VIEW (Used by both Admin/Ops & Partner Orgs)        */
/* ========================================================================== */
export function EventEditorModal({
  open = true,
  onClose,
  initial,
  megaEvents,
  organizations,
  isAdmin,
  onSave,
  saving,
}: {
  open?: boolean
  onClose: () => void
  initial: WebsiteEventInput
  megaEvents: MegaEvent[]
  organizations?: OrganizationAccountSummary[]
  isAdmin: boolean
  onSave: (payload: WebsiteEventInput) => void
  saving: boolean
}) {
  const toast = useToast()
  const [rawForm, setRawForm] = useState<WebsiteEventInput>({
    default_language: "en",
    ar_content: { enabled: false, en_enabled: true },
    ...initial,
  })
  const [editorLang, setEditorLang] = useState<"en" | "ar">("en")
  const [sectionTab, setSectionTab] = useState<
    "hero" | "about" | "eligibility" | "journey" | "deliverables" | "registration" | "faqs" | "partners"
  >("hero")

  if (!open) return null

  const arContent = (rawForm.ar_content || {}) as Record<string, any>
  const isArMode = editorLang === "ar"
  const enEnabled = arContent.en_enabled !== false
  const arEnabled = Boolean(arContent.enabled)
  const defaultLanguage = rawForm.default_language === "ar" ? "ar" : "en"

  const form: WebsiteEventInput = isArMode
    ? {
        ...rawForm,
        title: arContent.title ?? rawForm.title_ar ?? "",
        subtitle: arContent.subtitle ?? "",
        tagline: arContent.tagline ?? "",
        city: arContent.city ?? rawForm.city ?? "",
        audience: arContent.audience ?? "",
        host_org_name: arContent.host_org_name ?? "",
        date_label: arContent.date_label ?? "",
        location: arContent.location ?? "",
        about_text: arContent.about_text ?? "",
        benefits: arContent.benefits ?? [],
        at_a_glance: arContent.at_a_glance ?? [],
        eligibility_intro: arContent.eligibility_intro ?? "",
        eligibility_rows: arContent.eligibility_rows ?? [],
        eligibility_note: arContent.eligibility_note ?? "",
        journey_stages: arContent.journey_stages ?? [],
        timeline: arContent.timeline ?? [],
        timeline_note: arContent.timeline_note ?? "",
        deliverables: arContent.deliverables ?? [],
        deliverables_note: arContent.deliverables_note ?? "",
        awards_text: arContent.awards_text ?? "",
        registration_text: arContent.registration_text ?? "",
        registration_deadline: arContent.registration_deadline ?? "",
        registration_note: arContent.registration_note ?? "",
        faqs: arContent.faqs ?? [],
        partners: arContent.partners ?? rawForm.partners ?? [],
        partners_note: arContent.partners_note ?? "",
        contacts: arContent.contacts ?? rawForm.contacts ?? [],
        contact_meta: arContent.contact_meta ?? [],
      }
    : rawForm

  const set = <K extends keyof WebsiteEventInput>(key: K, val: WebsiteEventInput[K]) => {
    if (isArMode && AR_LOCALIZED_KEYS.has(key as string)) {
      setRawForm((prev) => ({
        ...prev,
        ...(key === "title" ? { title_ar: String(val || "") } : {}),
        ar_content: {
          ...(prev.ar_content || {}),
          enabled: true,
          [key]: val,
        },
      }))
    } else {
      setRawForm((prev) => ({ ...prev, [key]: val }))
    }
  }

  const copyEnglishToArabic = () => {
    setRawForm((prev) => ({
      ...prev,
      title_ar: prev.title_ar || prev.title || "",
      ar_content: {
        ...(prev.ar_content || {}),
        enabled: true,
        title: prev.ar_content?.title || prev.title_ar || prev.title || "",
        subtitle: prev.ar_content?.subtitle || prev.subtitle || "",
        tagline: prev.ar_content?.tagline || prev.tagline || "",
        city: prev.ar_content?.city || prev.city || "",
        audience: prev.ar_content?.audience || prev.audience || "",
        host_org_name: prev.ar_content?.host_org_name || prev.host_org_name || "",
        date_label: prev.ar_content?.date_label || prev.date_label || "",
        location: prev.ar_content?.location || prev.location || "",
        about_text: prev.ar_content?.about_text || prev.about_text || "",
        benefits: prev.ar_content?.benefits?.length ? prev.ar_content.benefits : [...(prev.benefits || [])],
        at_a_glance: prev.ar_content?.at_a_glance?.length ? prev.ar_content.at_a_glance : [...(prev.at_a_glance || [])],
        eligibility_intro: prev.ar_content?.eligibility_intro || prev.eligibility_intro || "",
        eligibility_rows: prev.ar_content?.eligibility_rows?.length ? prev.ar_content.eligibility_rows : [...(prev.eligibility_rows || [])],
        eligibility_note: prev.ar_content?.eligibility_note || prev.eligibility_note || "",
        journey_stages: prev.ar_content?.journey_stages?.length ? prev.ar_content.journey_stages : [...(prev.journey_stages || [])],
        timeline: prev.ar_content?.timeline?.length ? prev.ar_content.timeline : [...(prev.timeline || [])],
        timeline_note: prev.ar_content?.timeline_note || prev.timeline_note || "",
        deliverables: prev.ar_content?.deliverables?.length ? prev.ar_content.deliverables : [...(prev.deliverables || [])],
        deliverables_note: prev.ar_content?.deliverables_note || prev.deliverables_note || "",
        awards_text: prev.ar_content?.awards_text || prev.awards_text || "",
        registration_text: prev.ar_content?.registration_text || prev.registration_text || "",
        registration_deadline: prev.ar_content?.registration_deadline || prev.registration_deadline || "",
        registration_note: prev.ar_content?.registration_note || prev.registration_note || "",
        faqs: prev.ar_content?.faqs?.length ? prev.ar_content.faqs : [...(prev.faqs || [])],
        partners: prev.ar_content?.partners?.length ? prev.ar_content.partners : [...(prev.partners || [])],
        contacts: prev.ar_content?.contacts?.length ? prev.ar_content.contacts : [...(prev.contacts || [])],
        contact_meta: prev.ar_content?.contact_meta?.length ? prev.ar_content.contact_meta : [...(prev.contact_meta || [])],
      },
    }))
    toast.success("Copied English sections into Arabic template (click Save to apply)")
  }

  const SECTION_TABS = [
    { id: "hero", label: "1. Hero & Routing" },
    { id: "about", label: "2–3. About, Benefits & Glance" },
    { id: "eligibility", label: "4. Eligibility" },
    { id: "journey", label: "5–6. Journey & Timeline" },
    { id: "deliverables", label: "7–8. Deliverables & Awards" },
    { id: "registration", label: "9. Registration" },
    { id: "faqs", label: "10. FAQs" },
    { id: "partners", label: "11–12. Partners & Contacts" },
  ] as const

  const canSave = Boolean(
    (rawForm.title && rawForm.title.trim()) ||
      (arContent.title && String(arContent.title).trim()) ||
      (rawForm.title_ar && rawForm.title_ar.trim())
  )

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card p-5">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={onClose}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to Events
          </button>
          <div>
            <h2 className="text-lg font-bold text-foreground">
              {initial.title
                ? `Edit Event: ${rawForm.title || arContent.title || initial.title}`
                : "Create Event"}
            </h2>
            <p className="text-xs text-muted-foreground">
              Public Routes:{" "}
              <span className="font-mono text-primary">
                /events/{rawForm.country || "uae"}/{rawForm.slug || "slug"}/en
              </span>{" "}
              &amp;{" "}
              <span className="font-mono text-primary">
                /events/{rawForm.country || "uae"}/{rawForm.slug || "slug"}/ar
              </span>
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          {rawForm.slug && enEnabled && (
            <a
              href={`${WEBSITE_BASE_URL}/events/${rawForm.country || "uae"}/${rawForm.slug}/en`}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Preview /en
            </a>
          )}
          {rawForm.slug && arEnabled && (
            <a
              href={`${WEBSITE_BASE_URL}/events/${rawForm.country || "uae"}/${rawForm.slug}/ar`}
              target="_blank"
              rel="noreferrer"
              className="font-thmanyah inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              معاينة /ar
            </a>
          )}
          <button
            type="button"
            disabled={saving || !canSave}
            onClick={() =>
              onSave({
                ...rawForm,
                title:
                  (rawForm.title || "").trim() ||
                  String(arContent.title || rawForm.title_ar || "Event"),
              })
            }
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 transition"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : "Save Event"}
          </button>
        </div>
      </div>

      {/* Bilingual Language Configuration & Editor Switcher Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground mr-1">
            Editing Language:
          </span>
          <button
            type="button"
            onClick={() => setEditorLang("en")}
            className={cn(
              "rounded-xl px-4 py-2 text-xs font-bold transition cursor-pointer",
              editorLang === "en"
                ? "bg-primary text-primary-foreground shadow"
                : "border border-border bg-background text-muted-foreground hover:text-foreground"
            )}
          >
            English Version (/en)
          </button>
          <button
            type="button"
            onClick={() => setEditorLang("ar")}
            className={cn(
              "font-thmanyah rounded-xl px-4 py-2 text-xs font-bold transition cursor-pointer",
              editorLang === "ar"
                ? "bg-primary text-primary-foreground shadow"
                : "border border-border bg-background text-muted-foreground hover:text-foreground"
            )}
          >
            النسخة العربية (/ar)
          </button>

          {isArMode && (
            <button
              type="button"
              onClick={copyEnglishToArabic}
              className="rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold text-primary hover:bg-muted transition cursor-pointer"
            >
              Copy Missing Fields from English
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={enEnabled}
              onChange={(e) =>
                setRawForm((prev) => ({
                  ...prev,
                  ar_content: {
                    ...(prev.ar_content || {}),
                    en_enabled: e.target.checked,
                  },
                }))
              }
              className="h-4 w-4 rounded accent-primary"
            />
            <span className="font-semibold text-foreground">Enable English (/en)</span>
          </label>

          <label className="inline-flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={arEnabled}
              onChange={(e) =>
                setRawForm((prev) => ({
                  ...prev,
                  ar_content: {
                    ...(prev.ar_content || {}),
                    enabled: e.target.checked,
                  },
                }))
              }
              className="h-4 w-4 rounded accent-primary"
            />
            <span className="font-thmanyah font-semibold text-foreground">
              تفعيل النسخة العربية (/ar)
            </span>
          </label>

          <label className="inline-flex items-center gap-2">
            <span className="font-semibold text-muted-foreground">Default Page:</span>
            <select
              value={defaultLanguage}
              onChange={(e) =>
                setRawForm((prev) => ({
                  ...prev,
                  default_language: e.target.value,
                }))
              }
              className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold text-foreground"
            >
              <option value="en">English (/en)</option>
              <option value="ar">Arabic (/ar — العربية)</option>
            </select>
          </label>
        </div>
      </div>

      {/* Section Navigation Bar */}
      <div className="flex flex-wrap gap-2 rounded-2xl border border-border bg-card p-2">
        {SECTION_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setSectionTab(t.id)}
            className={cn(
              "rounded-xl px-4 py-2 text-xs font-semibold transition",
              sectionTab === t.id
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Full-Page Section Content Card */}
      <div
        dir={isArMode ? "rtl" : "ltr"}
        className={cn(
          "rounded-2xl border border-border bg-card p-6 sm:p-8 space-y-6",
          isArMode && "font-thmanyah"
        )}
      >
        {/* TAB 1: HERO & ROUTING */}
        {sectionTab === "hero" && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              <InputField
                label={isArMode ? "عنوان الفعالية بالعربية *" : "Event Title *"}
                value={form.title || ""}
                onChange={(v) => set("title", v)}
                placeholder={isArMode ? "مثال: سات فورج الإمارات 2026" : "e.g. SatForge UAE 2026"}
              />
              <InputField
                label="Arabic Subtitle Line on English Hero (Optional)"
                value={rawForm.title_ar || ""}
                onChange={(v) => setRawForm((p) => ({ ...p, title_ar: v }))}
                placeholder="سات فورج الإمارات 2026..."
              />
              <InputField
                label="URL Slug (Shared for /en and /ar)"
                value={rawForm.slug || ""}
                onChange={(v) => setRawForm((p) => ({ ...p, slug: v }))}
                placeholder="satforge-2026 (auto-generated if blank)"
                helper={`Routes: /events/${rawForm.country || "uae"}/${rawForm.slug || "slug"}/en & /ar`}
              />
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <InputField
                label={isArMode ? "العنوان الفرعي (Subtitle)" : "Subtitle"}
                value={form.subtitle || ""}
                onChange={(v) => set("subtitle", v)}
                placeholder={
                  isArMode
                    ? "التحدي الوطني لطلبة الجامعات في هندسة الأقمار الصناعية"
                    : "National University Satellite Engineering Challenge"
                }
              />
              <InputField
                label={isArMode ? "الشعار الوصفي (Tagline)" : "Tagline"}
                value={form.tagline || ""}
                onChange={(v) => set("tagline", v)}
                placeholder={
                  isArMode
                    ? "من ابتكارات الحرم الجامعي إلى مهمات الفضاء المستقبلية"
                    : "From Campus Innovation to Future Space Missions"
                }
              />
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-4">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Country Route
                </span>
                <select
                  value={rawForm.country || "uae"}
                  onChange={(e) => setRawForm((p) => ({ ...p, country: e.target.value }))}
                  className={inputCls}
                >
                  {COUNTRIES.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </label>

              {isArMode ? (
                <InputField
                  label="المدينة (بالعربية)"
                  value={form.city || ""}
                  onChange={(v) => set("city", v)}
                  placeholder="العين، أبوظبي"
                />
              ) : (
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    City
                  </span>
                  <CityNameSelect
                    country={rawForm.country || "uae"}
                    value={form.city || ""}
                    onChange={(v) => set("city", v)}
                    className={inputCls}
                  />
                </label>
              )}

              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Event Type
                </span>
                <select
                  value={rawForm.event_type || "competition"}
                  onChange={(e) => setRawForm((p) => ({ ...p, event_type: e.target.value }))}
                  className={inputCls}
                >
                  {EVENT_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>

              <InputField
                label="Target Audience"
                value={form.audience || ""}
                onChange={(v) => set("audience", v)}
                placeholder="Universities / Schools / Public"
              />
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Parent Featured Event (Optional)
                </span>
                <select
                  value={form.mega_event_id || ""}
                  onChange={(e) => set("mega_event_id", e.target.value || null)}
                  className={inputCls}
                >
                  <option value="">Standalone Event (Not under a Mega Event)</option>
                  {megaEvents.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.title} (/events/{m.country}/{m.slug})
                    </option>
                  ))}
                </select>
              </label>

              {isAdmin && organizations && (
                <label className="flex flex-col gap-1.5">
                  <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Assigned Partner Organization
                  </span>
                  <select
                    value={form.organization_id || ""}
                    onChange={(e) => set("organization_id", e.target.value || null)}
                    className={inputCls}
                  >
                    <option value="">SpacePoint (Unassigned)</option>
                    {organizations.map((o) => (
                      <option key={o.id} value={o.id}>
                        {o.name_latin} ({o.owner_email || "No login yet"})
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <InputField
                label="Host Organization Display Name"
                value={form.host_org_name || ""}
                onChange={(v) => set("host_org_name", v)}
                placeholder="College of Engineering at Abu Dhabi University"
              />
            </div>

            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              <InputField
                label="Dates Label"
                value={form.date_label || ""}
                onChange={(v) => set("date_label", v)}
                placeholder="11 October – 11 November 2026"
              />
              <InputField
                label="Location / Venue"
                value={form.location || ""}
                onChange={(v) => set("location", v)}
                placeholder="Abu Dhabi University, Al Ain Campus & Online"
              />
              <label className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Format
                </span>
                <select
                  value={form.venue_type || "onsite"}
                  onChange={(e) => set("venue_type", e.target.value)}
                  className={inputCls}
                >
                  <option value="onsite">On-Site</option>
                  <option value="online">Online</option>
                  <option value="hybrid">Hybrid (Online + On-Site)</option>
                </select>
              </label>
            </div>

            <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
              <EventBannerUploader
                bannerUrl={form.top_banner_url}
                onChange={(url) => set("top_banner_url", url)}
                eventTitle={form.title || "Event Title"}
                breadcrumb={`EVENTS / ${(form.country || "UAE").toUpperCase()} / ${(form.title || "EVENT").toUpperCase()}`}
              />
              <HeroBackgroundUploader
                imageUrl={form.banner_url}
                onChange={(url) => set("banner_url", url)}
              />
            </div>

            {form.mega_event_id && (
              <InputField
                label="Official World Space Week / Campaign Listing URL (Optional)"
                value={form.wsw_official_url || ""}
                onChange={(v) => set("wsw_official_url", v)}
                placeholder="https://www.worldspaceweek.org/events/..."
              />
            )}

            {isAdmin && (
              <div className="flex items-center justify-between rounded-xl border border-border bg-background p-4">
                <div>
                  <p className="text-sm font-semibold text-foreground">
                    Publish Status
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Only published events are visible on spacepoint.ae/events
                  </p>
                </div>
                <label className="inline-flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={Boolean(form.is_published)}
                    onChange={(e) => set("is_published", e.target.checked)}
                    className="h-4 w-4 rounded accent-primary"
                  />
                  <span className="text-sm font-semibold text-foreground">
                    {form.is_published ? "Published Live" : "Draft / Unpublished"}
                  </span>
                </label>
              </div>
            )}
          </div>
        )}

        {/* TAB 2: ABOUT, BENEFITS & AT A GLANCE */}
        {sectionTab === "about" && (
          <div className="space-y-8">
            <TextAreaField
              label="Section 1: About the Event / Competition"
              rows={6}
              value={form.about_text || ""}
              onChange={(v) => set("about_text", v)}
              placeholder="Write 1–3 paragraphs describing the event, hosts, and learning experience..."
              helper="Leave blank to hide the About section."
            />

            {/* At a Glance */}
            <div className="space-y-3 border-t border-border pt-6">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 2: At a Glance (Key Highlights Table)
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("at_a_glance", [
                      ...(form.at_a_glance || []),
                      { highlight: "", details: "" },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Row
                </button>
              </div>
              {(form.at_a_glance || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-5">
                    <input
                      value={row.highlight}
                      onChange={(e) => {
                        const next = [...(form.at_a_glance || [])]
                        next[idx] = { ...row, highlight: e.target.value }
                        set("at_a_glance", next)
                      }}
                      placeholder="Highlight (e.g. Target participation)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-6">
                    <input
                      value={row.details}
                      onChange={(e) => {
                        const next = [...(form.at_a_glance || [])]
                        next[idx] = { ...row, details: e.target.value }
                        set("at_a_glance", next)
                      }}
                      placeholder="Details (e.g. Approximately 500 students)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "at_a_glance",
                          (form.at_a_glance || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Why Participate / Benefits */}
            <div className="space-y-3 border-t border-border pt-6">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 3: Why Participate? (Benefits)
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("benefits", [...(form.benefits || []), { title: "", description: "" }])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Benefit
                </button>
              </div>
              {(form.benefits || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-4">
                    <input
                      value={row.title}
                      onChange={(e) => {
                        const next = [...(form.benefits || [])]
                        next[idx] = { ...row, title: e.target.value }
                        set("benefits", next)
                      }}
                      placeholder="Title (e.g. Hands-on engineering)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-7">
                    <input
                      value={row.description}
                      onChange={(e) => {
                        const next = [...(form.benefits || [])]
                        next[idx] = { ...row, description: e.target.value }
                        set("benefits", next)
                      }}
                      placeholder="Description..."
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "benefits",
                          (form.benefits || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 3: ELIGIBILITY */}
        {sectionTab === "eligibility" && (
          <div className="space-y-6">
            <TextAreaField
              label="Section 4: Who Can Participate? (Intro Text)"
              rows={2}
              value={form.eligibility_intro || ""}
              onChange={(v) => set("eligibility_intro", v)}
              placeholder="SatForge UAE 2026 welcomes eligible students enrolled in universities..."
            />

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Eligibility Requirements Table
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("eligibility_rows", [
                      ...(form.eligibility_rows || []),
                      { label: "", requirement: "" },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Requirement Row
                </button>
              </div>
              {(form.eligibility_rows || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-4">
                    <input
                      value={row.label}
                      onChange={(e) => {
                        const next = [...(form.eligibility_rows || [])]
                        next[idx] = { ...row, label: e.target.value }
                        set("eligibility_rows", next)
                      }}
                      placeholder="Criterion (e.g. Enrollment, Age, Team size)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-7">
                    <input
                      value={row.requirement}
                      onChange={(e) => {
                        const next = [...(form.eligibility_rows || [])]
                        next[idx] = { ...row, requirement: e.target.value }
                        set("eligibility_rows", next)
                      }}
                      placeholder="Requirement details..."
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "eligibility_rows",
                          (form.eligibility_rows || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            <TextAreaField
              label="Eligibility Closing Note"
              rows={2}
              value={form.eligibility_note || ""}
              onChange={(v) => set("eligibility_note", v)}
              placeholder="Participation is particularly encouraged from Electrical, Computer, Mechanical..."
            />
          </div>
        )}

        {/* TAB 4: JOURNEY & TIMELINE */}
        {sectionTab === "journey" && (
          <div className="space-y-8">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 5: Event / Competition Journey (Stages)
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("journey_stages", [
                      ...(form.journey_stages || []),
                      {
                        stage: `Stage ${(form.journey_stages?.length || 0) + 1}`,
                        title: "",
                        description: "",
                      },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Stage
                </button>
              </div>
              {(form.journey_stages || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-2">
                    <input
                      value={row.stage}
                      onChange={(e) => {
                        const next = [...(form.journey_stages || [])]
                        next[idx] = { ...row, stage: e.target.value }
                        set("journey_stages", next)
                      }}
                      placeholder="Stage 1"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-4">
                    <input
                      value={row.title}
                      onChange={(e) => {
                        const next = [...(form.journey_stages || [])]
                        next[idx] = { ...row, title: e.target.value }
                        set("journey_stages", next)
                      }}
                      placeholder="Form Your Team & Register"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-5">
                    <input
                      value={row.description}
                      onChange={(e) => {
                        const next = [...(form.journey_stages || [])]
                        next[idx] = { ...row, description: e.target.value }
                        set("journey_stages", next)
                      }}
                      placeholder="Stage description..."
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "journey_stages",
                          (form.journey_stages || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Timeline */}
            <div className="space-y-3 border-t border-border pt-6">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 6: Timeline / Important Dates
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("timeline", [...(form.timeline || []), { date: "", milestone: "" }])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Milestone
                </button>
              </div>
              {(form.timeline || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-4">
                    <input
                      value={row.date}
                      onChange={(e) => {
                        const next = [...(form.timeline || [])]
                        next[idx] = { ...row, date: e.target.value }
                        set("timeline", next)
                      }}
                      placeholder="Date (e.g. 11 October)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-7">
                    <input
                      value={row.milestone}
                      onChange={(e) => {
                        const next = [...(form.timeline || [])]
                        next[idx] = { ...row, milestone: e.target.value }
                        set("timeline", next)
                      }}
                      placeholder="Milestone description"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "timeline",
                          (form.timeline || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
              <InputField
                label="Timeline Footnote"
                value={form.timeline_note || ""}
                onChange={(v) => set("timeline_note", v)}
                placeholder="All times are UAE local time. Final on-site dates are tentative."
              />
            </div>
          </div>
        )}

        {/* TAB 5: DELIVERABLES & AWARDS */}
        {sectionTab === "deliverables" && (
          <div className="space-y-8">
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 7: Requirements & Deliverables (Phases)
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("deliverables", [
                      ...(form.deliverables || []),
                      { phase: "", deadline: "", items: [""] },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Deliverable Phase
                </button>
              </div>
              {(form.deliverables || []).map((phase, pIdx) => (
                <div
                  key={pIdx}
                  className="rounded-xl border border-border bg-background p-4 space-y-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <input
                      value={phase.phase}
                      onChange={(e) => {
                        const next = [...(form.deliverables || [])]
                        next[pIdx] = { ...phase, phase: e.target.value }
                        set("deliverables", next)
                      }}
                      placeholder="Phase Title (e.g. Phase 1 — Digital Design & Simulation)"
                      className={inputCls}
                    />
                    <input
                      value={phase.deadline}
                      onChange={(e) => {
                        const next = [...(form.deliverables || [])]
                        next[pIdx] = { ...phase, deadline: e.target.value }
                        set("deliverables", next)
                      }}
                      placeholder="Deadline (e.g. 30 October 2026, 12:00 PM)"
                      className={inputCls}
                    />
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "deliverables",
                          (form.deliverables || []).filter((_, i) => i !== pIdx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <TextAreaField
                    label="Deliverable Bullet Points (One per line)"
                    rows={4}
                    value={(phase.items || []).join("\n")}
                    onChange={(v) => {
                      const next = [...(form.deliverables || [])]
                      next[pIdx] = {
                        ...phase,
                        items: v.split("\n").filter((line) => line.trim().length > 0),
                      }
                      set("deliverables", next)
                    }}
                    placeholder="Electronic circuit and simulation: Tinkercad circuit..."
                  />
                </div>
              ))}
              <InputField
                label="Deliverables Note"
                value={form.deliverables_note || ""}
                onChange={(v) => set("deliverables_note", v)}
                placeholder="Complete technical specifications and evaluation criteria are provided in the Competition Guidelines."
              />
            </div>

            <div className="border-t border-border pt-6">
              <TextAreaField
                label="Section 8: Final Showcase & Awards"
                rows={4}
                value={form.awards_text || ""}
                onChange={(v) => set("awards_text", v)}
                placeholder="Approximately 10 finalist teams will be selected to participate in on-site preparation..."
              />
            </div>
          </div>
        )}

        {/* TAB 6: REGISTRATION */}
        {sectionTab === "registration" && (
          <div className="space-y-5">
            <TextAreaField
              label="Section 9: Registration Intro Text"
              rows={3}
              value={form.registration_text || ""}
              onChange={(v) => set("registration_text", v)}
              placeholder="Registration is open to eligible student teams from UAE universities..."
            />
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
              <InputField
                label="Registration Deadline Text"
                value={form.registration_deadline || ""}
                onChange={(v) => set("registration_deadline", v)}
                placeholder="21 October 2026, 6:00 PM (UAE time)"
              />
              <InputField
                label="Primary Registration Link (Form / Portal URL)"
                value={form.registration_url || ""}
                onChange={(v) => set("registration_url", v)}
                placeholder="https://..."
              />
              <InputField
                label="Competition / Event Guidelines PDF or Link"
                value={form.guidelines_url || ""}
                onChange={(v) => set("guidelines_url", v)}
                placeholder="https://..."
              />
              <InputField
                label="WhatsApp Community / Group Link"
                value={form.whatsapp_url || ""}
                onChange={(v) => set("whatsapp_url", v)}
                placeholder="https://chat.whatsapp.com/..."
              />
            </div>
            <InputField
              label="Registration Footnote"
              value={form.registration_note || ""}
              onChange={(v) => set("registration_note", v)}
              placeholder="Early registration is recommended as capacity is limited."
            />
          </div>
        )}

        {/* TAB 7: FAQS */}
        {sectionTab === "faqs" && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                Section 10: Frequently Asked Questions
              </h4>
              <button
                type="button"
                onClick={() =>
                  set("faqs", [...(form.faqs || []), { question: "", answer: "" }])
                }
                className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
              >
                <Plus className="h-3.5 w-3.5" /> Add FAQ
              </button>
            </div>
            {(form.faqs || []).map((row, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-border bg-background p-4 space-y-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <input
                    value={row.question}
                    onChange={(e) => {
                      const next = [...(form.faqs || [])]
                      next[idx] = { ...row, question: e.target.value }
                      set("faqs", next)
                    }}
                    placeholder="Question (e.g. Is there a registration fee?)"
                    className={inputCls}
                  />
                  <button
                    type="button"
                    onClick={() =>
                      set(
                        "faqs",
                        (form.faqs || []).filter((_, i) => i !== idx)
                      )
                    }
                    className="text-muted-foreground hover:text-foreground p-1.5"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
                <textarea
                  rows={2}
                  value={row.answer}
                  onChange={(e) => {
                    const next = [...(form.faqs || [])]
                    next[idx] = { ...row, answer: e.target.value }
                    set("faqs", next)
                  }}
                  placeholder="Answer..."
                  className={textareaCls}
                />
              </div>
            ))}
          </div>
        )}

        {/* TAB 8: PARTNERS & CONTACTS */}
        {sectionTab === "partners" && (
          <div className="space-y-8">
            {/* Partners */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 11: Organizers & Supporting Partners
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("partners", [
                      ...(form.partners || []),
                      { name: "", role: "Supporting Partner", logo_url: "" },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Partner
                </button>
              </div>
              {(form.partners || []).map((row, idx) => (
                <div key={idx} className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center">
                  <div className="md:col-span-4">
                    <input
                      value={row.name}
                      onChange={(e) => {
                        const next = [...(form.partners || [])]
                        next[idx] = { ...row, name: e.target.value }
                        set("partners", next)
                      }}
                      placeholder="Organization Name (e.g. UAE Space Agency)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-3">
                    <input
                      value={row.role}
                      onChange={(e) => {
                        const next = [...(form.partners || [])]
                        next[idx] = { ...row, role: e.target.value }
                        set("partners", next)
                      }}
                      placeholder="Role (e.g. Host Institution)"
                      className={inputCls}
                    />
                  </div>
                  <div className="md:col-span-4 flex items-center gap-2">
                    {row.logo_url && (
                      <img
                        src={row.logo_url}
                        alt=""
                        className="h-9 w-9 rounded-lg object-contain bg-background p-1 shrink-0 border border-border"
                      />
                    )}
                    <input
                      value={row.logo_url || ""}
                      onChange={(e) => {
                        const next = [...(form.partners || [])]
                        next[idx] = { ...row, logo_url: e.target.value }
                        set("partners", next)
                      }}
                      placeholder="Optional image/logo URL"
                      className={inputCls}
                    />
                    <label className="cursor-pointer shrink-0 inline-flex items-center gap-1.5 rounded-xl border border-border bg-muted px-3 py-2 text-xs font-semibold text-foreground hover:opacity-90">
                      <Upload className="h-3.5 w-3.5" />
                      <span>Image</span>
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e) => {
                          const f = e.target.files?.[0]
                          if (!f) return
                          try {
                            const res = await uploadWebsiteAsset(f)
                            const next = [...(form.partners || [])]
                            next[idx] = { ...row, logo_url: res.url }
                            set("partners", next)
                            toast.success("Partner image uploaded")
                          } catch (err) {
                            toast.error(getErrorMessage(err, "Upload failed"))
                          }
                        }}
                      />
                    </label>
                  </div>
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "partners",
                          (form.partners || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Contacts */}
            <div className="space-y-3 border-t border-border pt-6">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  Section 12: Contact Persons & Links
                </h4>
                <button
                  type="button"
                  onClick={() =>
                    set("contacts", [
                      ...(form.contacts || []),
                      { name: "", role: "", organization: "", org: "", email: "", phone: "" },
                    ])
                  }
                  className="inline-flex items-center gap-1.5 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Plus className="h-3.5 w-3.5" /> Add Contact Person
                </button>
              </div>
              {(form.contacts || []).map((row, idx) => (
                <div
                  key={idx}
                  className="grid grid-cols-1 gap-3 md:grid-cols-12 items-center rounded-xl border border-border bg-background p-3"
                >
                  <input
                    value={row.name}
                    onChange={(e) => {
                      const next = [...(form.contacts || [])]
                      next[idx] = { ...row, name: e.target.value }
                      set("contacts", next)
                    }}
                    placeholder="Name (e.g. Dr. Jawad Yousaf)"
                    className={cn(inputCls, "md:col-span-3")}
                  />
                  <input
                    value={row.role}
                    onChange={(e) => {
                      const next = [...(form.contacts || [])]
                      next[idx] = { ...row, role: e.target.value }
                      set("contacts", next)
                    }}
                    placeholder="Role / Title"
                    className={cn(inputCls, "md:col-span-3")}
                  />
                  <input
                    value={row.organization ?? row.org ?? ""}
                    onChange={(e) => {
                      const next = [...(form.contacts || [])]
                      next[idx] = { ...row, organization: e.target.value, org: e.target.value }
                      set("contacts", next)
                    }}
                    placeholder="Organization"
                    className={cn(inputCls, "md:col-span-2")}
                  />
                  <input
                    value={row.email}
                    onChange={(e) => {
                      const next = [...(form.contacts || [])]
                      next[idx] = { ...row, email: e.target.value }
                      set("contacts", next)
                    }}
                    placeholder="Email"
                    className={cn(inputCls, "md:col-span-3")}
                  />
                  <div className="md:col-span-1 flex justify-end">
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "contacts",
                          (form.contacts || []).filter((_, i) => i !== idx)
                        )
                      }
                      className="text-muted-foreground hover:text-foreground p-1.5"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Bottom Save Bar */}
        <div className="flex justify-end gap-3 pt-6 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-border bg-background px-5 py-2.5 text-xs font-semibold text-foreground hover:bg-muted transition"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving || !canSave}
            onClick={() =>
              onSave({
                ...rawForm,
                title:
                  (rawForm.title || "").trim() ||
                  String(arContent.title || rawForm.title_ar || "Event"),
              })
            }
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-6 py-2.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50 transition"
          >
            <Save className="h-4 w-4" />
            {saving ? "Saving..." : "Save Event"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ========================================================================== */
/* ADMIN / OPERATIONS EVENTS & MEGA-EVENTS PANEL                              */
/* ========================================================================== */
export function WebsiteEventsPanel() {
  const toast = useToast()
  const qc = useQueryClient()
  const [subTab, setSubTab] = useState<"events" | "mega" | "organizations">("events")

  const megaQuery = useQuery({
    queryKey: ["admin-website-mega-events"],
    queryFn: getAdminMegaEvents,
  })
  const eventsQuery = useQuery({
    queryKey: ["admin-website-events"],
    queryFn: getAdminWebsiteEvents,
  })
  const orgsQuery = useQuery({
    queryKey: ["admin-website-organizations"],
    queryFn: getAdminEventOrganizations,
  })

  // Full-page Event Editor state
  const [editingEvent, setEditingEvent] = useState<WebsiteEvent | null>(null)
  const [creatingEvent, setCreatingEvent] = useState(false)

  // Full-page MegaEvent Editor state
  const [editingMega, setEditingMega] = useState<MegaEvent | null>(null)
  const [creatingMega, setCreatingMega] = useState(false)
  const [megaLangTab, setMegaLangTab] = useState<"en" | "ar">("en")
  const [megaDraft, setMegaDraft] = useState<MegaEventCreateInput>({
    title: "",
    slug: "",
    country: "uae",
    subtitle: "",
    tagline: "",
    date_label: "",
    about_text: "",
    official_note: "",
    official_url: "https://www.worldspaceweek.org",
    is_published: true,
    default_language: "en",
    ar_content: { enabled: false, en_enabled: true },
  })

  // Full-page Create / Edit Organization Account state
  const [creatingOrg, setCreatingOrg] = useState(false)
  const [editingOrg, setEditingOrg] = useState<OrganizationAccountSummary | null>(null)
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [orgResetLink, setOrgResetLink] = useState<{ orgName: string; email: string; url: string } | null>(null)
  const [orgForm, setOrgForm] = useState({
    org_name_latin: "",
    org_name_arabic: "",
    org_type: "university",
    country: "uae",
    city: "Abu Dhabi",
    full_name: "",
    email: "",
    phone: "",
    password: "",
  })

  const saveEventMut = useMutation({
    mutationFn: (payload: WebsiteEventInput) =>
      editingEvent
        ? updateAdminWebsiteEvent(editingEvent.id, payload)
        : createAdminWebsiteEvent(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
      void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      setEditingEvent(null)
      setCreatingEvent(false)
      toast.success("Event saved")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save event")),
  })

  const publishToggleMut = useMutation({
    mutationFn: ({ id, is_published }: { id: string; is_published: boolean }) =>
      togglePublishWebsiteEvent(id, is_published),
    onSuccess: (updated) => {
      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
      toast.success(updated.is_published ? "Event published live!" : "Event unpublished")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Could not update publish status")),
  })

  const deleteEventMut = useMutation({
    mutationFn: (id: string) => deleteAdminWebsiteEvent(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
      toast.success("Event deleted")
    },
  })

  const saveMegaMut = useMutation({
    mutationFn: (payload: MegaEventCreateInput) =>
      editingMega
        ? updateAdminMegaEvent(editingMega.id, payload)
        : createAdminMegaEvent(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
      setEditingMega(null)
      setCreatingMega(false)
      toast.success("Featured Event saved")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save Featured Event")),
  })

  const deleteMegaMut = useMutation({
    mutationFn: (id: string) => deleteAdminMegaEvent(id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
      toast.success("Featured Event deleted")
    },
  })

  const saveOrgMut = useMutation({
    mutationFn: () =>
      editingOrg
        ? updateAdminOrganizationAccount(editingOrg.id, {
            org_name_latin: orgForm.org_name_latin,
            org_name_arabic: orgForm.org_name_arabic,
            org_type: orgForm.org_type,
            country: orgForm.country,
            city: orgForm.city,
            full_name: orgForm.full_name,
            email: orgForm.email || undefined,
            phone: orgForm.phone,
            password: orgForm.password || undefined,
          })
        : createAdminOrganizationAccount(orgForm),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      void qc.invalidateQueries({ queryKey: ["users"] })
      setCreatingOrg(false)
      setEditingOrg(null)
      setOrgForm({
        org_name_latin: "",
        org_name_arabic: "",
        org_type: "university",
        country: "uae",
        city: "Abu Dhabi",
        full_name: "",
        email: "",
        phone: "",
        password: "",
      })
      toast.success(editingOrg ? "Organization updated!" : "Organization account created!")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to save organization account")),
  })

  const deleteOrgMut = useMutation({
    mutationFn: (orgId: string) => deleteAdminOrganizationAccount(orgId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
      void qc.invalidateQueries({ queryKey: ["users"] })
      toast.success("Organization deleted")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to delete organization")),
  })

  const resetOrgLinkMut = useMutation({
    mutationFn: async (org: OrganizationAccountSummary) => {
      const res = await getAdminOrganizationResetLink(org.id)
      return { orgName: org.name_latin, email: res.email, url: res.reset_url }
    },
    onSuccess: (data) => {
      navigator.clipboard?.writeText(data.url).catch(() => {})
      setOrgResetLink(data)
      toast.success("Password reset link generated and copied to clipboard!")
    },
    onError: (err) => toast.error(getErrorMessage(err, "Failed to generate reset link")),
  })

  const megaEvents = megaQuery.data || []
  const events = eventsQuery.data || []
  const organizations = orgsQuery.data || []
  // Partner accounts ONLY (event-host logins, owner_user_id set). Plain CRM
  // school rows auto-created by imports/registrations live in the same table
  // but are just contact attributes — they are deliberately NOT listed here.
  const partnerOrgs = organizations.filter((o) => !!o.owner_user_id)

  if (megaQuery.isLoading || eventsQuery.isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    )
  }

  // 1. FULL-PAGE EVENT VIEW / EDITOR
  if (creatingEvent || editingEvent) {
    return (
      <EventEditorModal
        onClose={() => {
          setCreatingEvent(false)
          setEditingEvent(null)
        }}
        initial={editingEvent ? editingEvent : emptyEventDraft()}
        megaEvents={megaEvents}
        organizations={organizations}
        isAdmin={true}
        saving={saveEventMut.isPending}
        onSave={(payload) => saveEventMut.mutate(payload)}
      />
    )
  }

  // 2. FULL-PAGE FEATURED / MEGA EVENT VIEW
  if (creatingMega || editingMega) {
    const megaAr = (megaDraft.ar_content || {}) as Record<string, any>
    const isMegaAr = megaLangTab === "ar"
    const setMegaArField = (key: string, val: any) =>
      setMegaDraft((p) => ({
        ...p,
        ...(key === "title" ? { title_ar: String(val || "") } : {}),
        ar_content: {
          ...(p.ar_content || {}),
          enabled: true,
          [key]: val,
        },
      }))

    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => {
                setCreatingMega(false)
                setEditingMega(null)
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition"
            >
              <ArrowLeft className="h-4 w-4" />
              Back
            </button>
            <h2 className="text-lg font-bold text-foreground">
              {editingMega ? `Edit Featured Event: ${editingMega.title}` : "Create Featured Event"}
            </h2>
          </div>
          <button
            type="button"
            disabled={saveMegaMut.isPending || !megaDraft.title?.trim()}
            onClick={() => saveMegaMut.mutate(megaDraft)}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saveMegaMut.isPending ? "Saving..." : "Save Featured Event"}
          </button>
        </div>

        {/* Language Configuration Bar for Featured Event */}
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground mr-1">
              Editing Language:
            </span>
            <button
              type="button"
              onClick={() => setMegaLangTab("en")}
              className={cn(
                "rounded-xl px-4 py-2 text-xs font-bold transition cursor-pointer",
                megaLangTab === "en"
                  ? "bg-primary text-primary-foreground shadow"
                  : "border border-border bg-background text-muted-foreground hover:text-foreground"
              )}
            >
              English Version (/en)
            </button>
            <button
              type="button"
              onClick={() => setMegaLangTab("ar")}
              className={cn(
                "font-thmanyah rounded-xl px-4 py-2 text-xs font-bold transition cursor-pointer",
                megaLangTab === "ar"
                  ? "bg-primary text-primary-foreground shadow"
                  : "border border-border bg-background text-muted-foreground hover:text-foreground"
              )}
            >
              النسخة العربية (/ar)
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={megaAr.en_enabled !== false}
                onChange={(e) =>
                  setMegaDraft((p) => ({
                    ...p,
                    ar_content: { ...(p.ar_content || {}), en_enabled: e.target.checked },
                  }))
                }
                className="h-4 w-4 rounded accent-primary"
              />
              <span className="font-semibold text-foreground">Enable English (/en)</span>
            </label>

            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={Boolean(megaAr.enabled)}
                onChange={(e) =>
                  setMegaDraft((p) => ({
                    ...p,
                    ar_content: { ...(p.ar_content || {}), enabled: e.target.checked },
                  }))
                }
                className="h-4 w-4 rounded accent-primary"
              />
              <span className="font-thmanyah font-semibold text-foreground">
                تفعيل النسخة العربية (/ar)
              </span>
            </label>

            <label className="inline-flex items-center gap-2">
              <span className="font-semibold text-muted-foreground">Default Page:</span>
              <select
                value={megaDraft.default_language === "ar" ? "ar" : "en"}
                onChange={(e) =>
                  setMegaDraft((p) => ({ ...p, default_language: e.target.value }))
                }
                className="h-8 rounded-lg border border-border bg-background px-2.5 text-xs font-semibold text-foreground"
              >
                <option value="en">English (/en)</option>
                <option value="ar">Arabic (/ar — العربية)</option>
              </select>
            </label>
          </div>
        </div>

        <div
          dir={isMegaAr ? "rtl" : "ltr"}
          className={cn(
            "rounded-2xl border border-border bg-card p-6 sm:p-8 space-y-5",
            isMegaAr && "font-thmanyah"
          )}
        >
          <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
            <InputField
              label={isMegaAr ? "عنوان الفعالية بالعربية *" : "Title *"}
              value={isMegaAr ? megaAr.title || megaDraft.title_ar || "" : megaDraft.title || ""}
              onChange={(v) =>
                isMegaAr
                  ? setMegaArField("title", v)
                  : setMegaDraft((p) => ({ ...p, title: v }))
              }
              placeholder={
                isMegaAr ? "أسبوع الفضاء العالمي — الإمارات 2026" : "World Space Week UAE 2026"
              }
            />
            <InputField
              label="Slug (Shared for /en and /ar)"
              value={megaDraft.slug || ""}
              onChange={(v) => setMegaDraft((p) => ({ ...p, slug: v }))}
              placeholder="wsw"
            />
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Country
              </span>
              <select
                value={megaDraft.country || "uae"}
                onChange={(e) => setMegaDraft((p) => ({ ...p, country: e.target.value }))}
                className={inputCls}
              >
                {COUNTRIES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <InputField
              label={isMegaAr ? "العنوان الفرعي" : "Subtitle"}
              value={isMegaAr ? megaAr.subtitle || "" : megaDraft.subtitle || ""}
              onChange={(v) =>
                isMegaAr
                  ? setMegaArField("subtitle", v)
                  : setMegaDraft((p) => ({ ...p, subtitle: v }))
              }
              placeholder="One Week. One Ecosystem. Endless Possibilities."
            />
            <InputField
              label={isMegaAr ? "الشعار الوصفي" : "Tagline"}
              value={isMegaAr ? megaAr.tagline || "" : megaDraft.tagline || ""}
              onChange={(v) =>
                isMegaAr
                  ? setMegaArField("tagline", v)
                  : setMegaDraft((p) => ({ ...p, tagline: v }))
              }
              placeholder="Discover. Participate. Connect. Measure Impact."
            />
          </div>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
            <InputField
              label={isMegaAr ? "التاريخ" : "Date Label"}
              value={isMegaAr ? megaAr.date_label || "" : megaDraft.date_label || ""}
              onChange={(v) =>
                isMegaAr
                  ? setMegaArField("date_label", v)
                  : setMegaDraft((p) => ({ ...p, date_label: v }))
              }
              placeholder="October 2026 • Across All 7 Emirates"
            />
            <InputField
              label="Official Website URL"
              value={megaDraft.official_url || ""}
              onChange={(v) => setMegaDraft((p) => ({ ...p, official_url: v }))}
              placeholder="https://www.worldspaceweek.org"
            />
          </div>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            <EventBannerUploader
              bannerUrl={megaDraft.top_banner_url}
              onChange={(url) => setMegaDraft((p) => ({ ...p, top_banner_url: url }))}
              eventTitle={megaDraft.title || "Featured Event"}
              breadcrumb={`EVENTS / ${(megaDraft.country || "UAE").toUpperCase()} / ${(megaDraft.title || "FEATURED EVENT").toUpperCase()}`}
            />
            <HeroBackgroundUploader
              imageUrl={megaDraft.banner_url}
              onChange={(url) => setMegaDraft((p) => ({ ...p, banner_url: url }))}
            />
          </div>
          <TextAreaField
            label={isMegaAr ? "الوصف التعريفي بالفعالية" : "Hero / Overview Description"}
            rows={4}
            value={isMegaAr ? megaAr.about_text || "" : megaDraft.about_text || ""}
            onChange={(v) =>
              isMegaAr
                ? setMegaArField("about_text", v)
                : setMegaDraft((p) => ({ ...p, about_text: v }))
            }
          />
          <TextAreaField
            label={isMegaAr ? "ملاحظة رسمية" : "Official Note / Disclaimer"}
            rows={2}
            value={isMegaAr ? megaAr.official_note || "" : megaDraft.official_note || ""}
            onChange={(v) =>
              isMegaAr
                ? setMegaArField("official_note", v)
                : setMegaDraft((p) => ({ ...p, official_note: v }))
            }
          />
        </div>

        {editingMega && (
          <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <h3 className="text-base font-bold text-foreground">
                  Attached Child Events ({events.filter((e) => e.mega_event_id === editingMega.id).length})
                </h3>
                <p className="text-xs text-muted-foreground">
                  Attach events to appear under this Featured Event landing page, or remove them to make them standalone.
                </p>
              </div>

              <select
                value=""
                onChange={(e) => {
                  const evId = e.target.value
                  if (!evId) return
                  updateAdminWebsiteEvent(evId, { mega_event_id: editingMega.id }).then(() => {
                    void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                    void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                    toast.success("Event attached to Featured Event")
                  })
                }}
                className="h-10 rounded-xl border border-border bg-background px-3.5 text-xs font-semibold text-foreground"
              >
                <option value="">+ Attach Event to {editingMega.title}...</option>
                {events
                  .filter((ev) => ev.mega_event_id !== editingMega.id)
                  .map((ev) => (
                    <option key={ev.id} value={ev.id}>
                      {ev.title} (/{ev.country}/{ev.slug})
                    </option>
                  ))}
              </select>
            </div>

            {events.filter((e) => e.mega_event_id === editingMega.id).length === 0 ? (
              <div className="rounded-xl border border-dashed border-border bg-background p-6 text-center text-xs text-muted-foreground">
                No child events attached yet. Use the dropdown above to attach events.
              </div>
            ) : (
              <div className="space-y-2.5">
                {events
                  .filter((e) => e.mega_event_id === editingMega.id)
                  .map((ev) => (
                    <div
                      key={ev.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-background px-4 py-3"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-foreground">{ev.title}</span>
                          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-mono text-muted-foreground">
                            /{ev.country}/{ev.slug}
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {ev.host_org_name || ev.organization_name || "SpacePoint"} • {ev.date_label || "Date TBA"}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() =>
                          updateAdminWebsiteEvent(ev.id, { mega_event_id: null }).then(() => {
                            void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                            void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                            toast.success("Removed event from Featured Event")
                          })
                        }
                        className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-card px-3 py-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove from Parent
                      </button>
                    </div>
                  ))}
              </div>
            )}
          </div>
        )}
      </div>
    )
  }

  // 3. FULL-PAGE CREATE / EDIT ORGANIZATION ACCOUNT VIEW
  if (creatingOrg || editingOrg) {
    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card p-5">
          <div className="flex items-center gap-4">
            <button
              type="button"
              onClick={() => {
                setCreatingOrg(false)
                setEditingOrg(null)
              }}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted transition"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to Organizations
            </button>
            <h2 className="text-lg font-bold text-foreground">
              {editingOrg
                ? `Edit Organization: ${editingOrg.name_latin}`
                : "Create Partner Organization Account"}
            </h2>
          </div>
          <button
            type="button"
            disabled={
              saveOrgMut.isPending ||
              !orgForm.org_name_latin.trim() ||
              (!editingOrg && (!orgForm.email.trim() || !orgForm.password.trim()))
            }
            onClick={() => saveOrgMut.mutate()}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-xs font-semibold text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Save className="h-4 w-4" />
            {saveOrgMut.isPending ? "Saving..." : editingOrg ? "Save Changes" : "Create Account"}
          </button>
        </div>

        <div className="rounded-2xl border border-border bg-card p-6 sm:p-8 max-w-2xl space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <InputField
              label="Organization Name *"
              value={orgForm.org_name_latin}
              onChange={(v) => setOrgForm((p) => ({ ...p, org_name_latin: v }))}
              placeholder="Abu Dhabi University"
            />
            <InputField
              label="Organization Arabic Name (Optional)"
              value={orgForm.org_name_arabic}
              onChange={(v) => setOrgForm((p) => ({ ...p, org_name_arabic: v }))}
              placeholder="جامعة أبوظبي"
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Organization Type
              </span>
              <select
                value={orgForm.org_type}
                onChange={(e) => setOrgForm((p) => ({ ...p, org_type: e.target.value }))}
                className={inputCls}
              >
                <option value="university">University</option>
                <option value="school">School</option>
                <option value="company">Company</option>
                <option value="government">Government Entity</option>
                <option value="ngo">NGO / Club</option>
                <option value="other">Other</option>
              </select>
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Country
              </span>
              <CountrySelect
                value={orgForm.country}
                onChange={(v) => setOrgForm((p) => ({ ...p, country: v }))}
                valueType="code"
                className={inputCls}
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                City
              </span>
              <CityNameSelect
                country={orgForm.country}
                value={orgForm.city}
                onChange={(v) => setOrgForm((p) => ({ ...p, city: v }))}
                className={inputCls}
              />
            </label>
          </div>
          <InputField
            label="Contact Person Full Name *"
            value={orgForm.full_name}
            onChange={(v) => setOrgForm((p) => ({ ...p, full_name: v }))}
            placeholder="Dr. Jawad Yousaf"
          />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <InputField
              label={editingOrg ? "Login Email" : "Login Email *"}
              type="email"
              value={orgForm.email}
              onChange={(v) => setOrgForm((p) => ({ ...p, email: v }))}
              placeholder="partner@university.ac.ae"
            />
            <InputField
              label="Phone"
              value={orgForm.phone}
              onChange={(v) => setOrgForm((p) => ({ ...p, phone: v }))}
              placeholder="+971 50 000 0000"
            />
          </div>
          <InputField
            label={editingOrg ? "New Password (leave blank to keep current)" : "Initial Password *"}
            type="password"
            value={orgForm.password}
            onChange={(v) => setOrgForm((p) => ({ ...p, password: v }))}
            placeholder="••••••••"
          />
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Sub-navigation */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSubTab("events")}
            className={cn(
              "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition",
              subTab === "events"
                ? "bg-primary text-primary-foreground"
                : "border border-border bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            <CalendarDays className="h-4 w-4" />
            Events ({events.length})
          </button>
          <button
            type="button"
            onClick={() => setSubTab("mega")}
            className={cn(
              "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition",
              subTab === "mega"
                ? "bg-primary text-primary-foreground"
                : "border border-border bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            <Layers className="h-4 w-4" />
            Featured Events ({megaEvents.length})
          </button>
          <button
            type="button"
            onClick={() => setSubTab("organizations")}
            className={cn(
              "inline-flex items-center gap-2 rounded-xl px-4 py-2 text-xs font-semibold transition",
              subTab === "organizations"
                ? "bg-primary text-primary-foreground"
                : "border border-border bg-card text-muted-foreground hover:text-foreground"
            )}
          >
            <Building2 className="h-4 w-4" />
            Partner Organizations ({partnerOrgs.length})
          </button>
        </div>

        <div className="flex items-center gap-2">
          {subTab === "events" && (
            <button
              type="button"
              onClick={() => setCreatingEvent(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              <Plus className="h-4 w-4" /> Create Event
            </button>
          )}
          {subTab === "mega" && (
            <button
              type="button"
              onClick={() => {
                setMegaLangTab("en")
                setMegaDraft({
                  title: "",
                  slug: "",
                  country: "uae",
                  subtitle: "",
                  tagline: "",
                  date_label: "",
                  about_text: "",
                  official_note: "",
                  official_url: "",
                  is_published: true,
                  default_language: "en",
                  ar_content: { enabled: false, en_enabled: true },
                })
                setCreatingMega(true)
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              <Plus className="h-4 w-4" /> Create Featured Event
            </button>
          )}
          {subTab === "organizations" && (
            <button
              type="button"
              onClick={() => setCreatingOrg(true)}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
            >
              <Plus className="h-4 w-4" /> Create Organization Account
            </button>
          )}
        </div>
      </div>

      {/* 1. EVENTS LIST */}
      {subTab === "events" && (
        <div className="space-y-4">
          {events.map((ev) => (
            <div
              key={ev.id}
              className="rounded-2xl border border-border bg-card p-5 flex flex-col lg:flex-row lg:items-center justify-between gap-4"
            >
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold uppercase",
                      ev.is_published
                        ? "bg-primary/20 text-primary"
                        : "bg-muted text-muted-foreground"
                    )}
                  >
                    {ev.is_published ? (
                      <>
                        <CheckCircle2 className="h-3.5 w-3.5" /> Published
                      </>
                    ) : (
                      <>
                        <Clock className="h-3.5 w-3.5" /> Pending / Draft
                      </>
                    )}
                  </span>
                  <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold uppercase text-foreground">
                    /{ev.country}/{ev.slug}
                  </span>
                  {ev.ar_content?.en_enabled !== false && (
                    <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px] font-bold text-foreground">
                      EN{ev.default_language !== "ar" ? " (Default)" : ""}
                    </span>
                  )}
                  {ev.ar_content?.enabled && (
                    <span className="font-thmanyah rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-bold text-primary">
                      AR العربية{ev.default_language === "ar" ? " (Default)" : ""}
                    </span>
                  )}
                  {ev.mega_event_title && (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-semibold text-primary">
                      Parent: {ev.mega_event_title}
                      <button
                        type="button"
                        onClick={() =>
                          updateAdminWebsiteEvent(ev.id, { mega_event_id: null }).then(() => {
                            void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                            void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                            toast.success("Detached from Featured Event")
                          })
                        }
                        title="Remove from Parent Featured Event"
                        className="ml-0.5 rounded-full px-1 hover:bg-primary/25 text-primary"
                      >
                        ×
                      </button>
                    </span>
                  )}
                  {ev.organization_name && (
                    <span className="rounded-full border border-border bg-background px-2.5 py-0.5 text-xs font-semibold text-foreground">
                      Org: {ev.organization_name}
                    </span>
                  )}
                </div>

                <h3 className="text-lg font-bold text-foreground">{ev.title}</h3>
                <p className="text-xs text-muted-foreground">
                  {ev.subtitle || ev.tagline} • {ev.city || ev.country.toUpperCase()} • {ev.date_label || "Date TBA"}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {/* Quick Set Parent Featured Event */}
                <select
                  value={ev.mega_event_id || ""}
                  onChange={(e) =>
                    updateAdminWebsiteEvent(ev.id, {
                      mega_event_id: e.target.value || null,
                    }).then(() => {
                      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                      void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                      toast.success(
                        e.target.value
                          ? "Parent Featured Event assigned"
                          : "Event set as standalone (removed from parent)"
                      )
                    })
                  }
                  className="h-9 rounded-xl border border-border bg-background px-3 text-xs font-medium text-foreground"
                  title="Set Parent Featured Event"
                >
                  <option value="">Parent: None (Standalone)</option>
                  {megaEvents.map((m) => (
                    <option key={m.id} value={m.id}>
                      Parent: {m.title}
                    </option>
                  ))}
                </select>

                {/* Quick Assign Organization */}
                <select
                  value={ev.organization_id || ""}
                  onChange={(e) =>
                    updateAdminWebsiteEvent(ev.id, {
                      organization_id: e.target.value || null,
                    }).then(() => {
                      void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                      void qc.invalidateQueries({ queryKey: ["admin-website-organizations"] })
                      toast.success("Organization assignment updated")
                    })
                  }
                  className="h-9 rounded-xl border border-border bg-background px-3 text-xs font-medium text-foreground"
                  title="Assign to Organization"
                >
                  <option value="">Org: SpacePoint (Unassigned)</option>
                  {organizations.map((o) => (
                    <option key={o.id} value={o.id}>
                      Org: {o.name_latin}
                    </option>
                  ))}
                </select>

                {/* Publish / Unpublish */}
                <button
                  type="button"
                  onClick={() =>
                    publishToggleMut.mutate({ id: ev.id, is_published: !ev.is_published })
                  }
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-xl px-3.5 py-2 text-xs font-semibold transition",
                    ev.is_published
                      ? "border border-border bg-background text-muted-foreground hover:text-foreground"
                      : "bg-primary text-primary-foreground hover:opacity-90"
                  )}
                >
                  {ev.is_published ? (
                    <>
                      <EyeOff className="h-3.5 w-3.5" /> Unpublish
                    </>
                  ) : (
                    <>
                      <Eye className="h-3.5 w-3.5" /> Publish
                    </>
                  )}
                </button>

                <a
                  href={`${WEBSITE_BASE_URL}/events/${ev.country}/${ev.slug}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                >
                  <ExternalLink className="h-3.5 w-3.5" /> View
                </a>

                <button
                  type="button"
                  onClick={() => setEditingEvent(ev)}
                  className="inline-flex items-center gap-1 rounded-xl bg-primary/15 px-3.5 py-2 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                >
                  <Pencil className="h-3.5 w-3.5" /> Open Event
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete event "${ev.title}"?`)) {
                      deleteEventMut.mutate(ev.id)
                    }
                  }}
                  className="rounded-xl border border-border bg-background p-2 text-muted-foreground hover:text-foreground"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 2. FEATURED / MEGA EVENTS LIST */}
      {subTab === "mega" && (
        <div className="space-y-4">
          {megaEvents.map((m) => {
            const attachedEvents = events.filter((ev) => ev.mega_event_id === m.id)
            const availableEvents = events.filter((ev) => ev.mega_event_id !== m.id)
            return (
              <div
                key={m.id}
                className="rounded-2xl border border-border bg-card p-5 space-y-4"
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="rounded-full bg-primary/20 px-2.5 py-0.5 text-xs font-bold uppercase text-primary">
                        Featured Event • /{m.country}/{m.slug}
                      </span>
                      {m.ar_content?.en_enabled !== false && (
                        <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[11px] font-bold text-foreground">
                          EN{m.default_language !== "ar" ? " (Default)" : ""}
                        </span>
                      )}
                      {m.ar_content?.enabled && (
                        <span className="font-thmanyah rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-[11px] font-bold text-primary">
                          AR العربية{m.default_language === "ar" ? " (Default)" : ""}
                        </span>
                      )}
                      <span className="text-xs font-semibold text-muted-foreground">
                        {attachedEvents.length} child event(s)
                      </span>
                    </div>
                    <h3 className="text-lg font-bold text-foreground">{m.title}</h3>
                    <p className="text-xs text-muted-foreground">
                      {m.subtitle} • {m.date_label}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      value=""
                      onChange={(e) => {
                        const evId = e.target.value
                        if (!evId) return
                        updateAdminWebsiteEvent(evId, { mega_event_id: m.id }).then(() => {
                          void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                          void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                          toast.success(`Attached event to ${m.title}`)
                        })
                      }}
                      className="h-9 rounded-xl border border-border bg-background px-3 text-xs font-medium text-foreground"
                    >
                      <option value="">+ Attach Event...</option>
                      {availableEvents.map((ev) => (
                        <option key={ev.id} value={ev.id}>
                          {ev.title} (/{ev.country}/{ev.slug})
                        </option>
                      ))}
                    </select>

                    <a
                      href={`${WEBSITE_BASE_URL}/events/${m.country}/${m.slug}`}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 rounded-xl border border-border bg-background px-3.5 py-2 text-xs font-semibold text-foreground hover:bg-muted"
                    >
                      <ExternalLink className="h-3.5 w-3.5" /> View
                    </a>
                    <button
                      type="button"
                      onClick={() => {
                        setMegaLangTab("en")
                        setEditingMega(m)
                        setMegaDraft({
                          title: m.title,
                          title_ar: m.title_ar,
                          slug: m.slug,
                          country: m.country,
                          subtitle: m.subtitle,
                          tagline: m.tagline,
                          banner_url: m.banner_url,
                          top_banner_url: getUploadedBannerUrl(m.top_banner_url),
                          date_label: m.date_label,
                          about_text: m.about_text,
                          official_note: m.official_note,
                          official_url: m.official_url,
                          is_published: m.is_published,
                          default_language: m.default_language || "en",
                          ar_content: m.ar_content || { enabled: false, en_enabled: true },
                        })
                      }}
                      className="inline-flex items-center gap-1 rounded-xl bg-primary/15 px-3.5 py-2 text-xs font-semibold text-primary hover:bg-primary/25"
                    >
                      <Pencil className="h-3.5 w-3.5" /> Open
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Delete "${m.title}"?`)) {
                          deleteMegaMut.mutate(m.id)
                        }
                      }}
                      className="rounded-xl border border-border bg-background p-2 text-muted-foreground hover:text-foreground"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Attached Child Events list with quick Remove */}
                <div className="border-t border-border/60 pt-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground mr-1">
                      Child Events:
                    </span>
                    {attachedEvents.length === 0 ? (
                      <span className="text-xs text-muted-foreground italic">
                        None attached — use &ldquo;+ Attach Event...&rdquo; to attach events to this Featured Event.
                      </span>
                    ) : (
                      attachedEvents.map((ev) => (
                        <span
                          key={ev.id}
                          className="inline-flex items-center gap-1.5 rounded-xl border border-border bg-background px-3 py-1 text-xs font-medium text-foreground"
                        >
                          <span>{ev.title}</span>
                          <span className="text-[11px] text-muted-foreground">
                            (/{ev.country}/{ev.slug})
                          </span>
                          <button
                            type="button"
                            onClick={() =>
                              updateAdminWebsiteEvent(ev.id, { mega_event_id: null }).then(() => {
                                void qc.invalidateQueries({ queryKey: ["admin-website-events"] })
                                void qc.invalidateQueries({ queryKey: ["admin-website-mega-events"] })
                                toast.success(`Removed "${ev.title}" from ${m.title}`)
                              })
                            }
                            title="Remove from this Featured Event"
                            className="ml-1 rounded-md px-1 text-muted-foreground hover:bg-muted hover:text-foreground font-bold"
                          >
                            ×
                          </button>
                        </span>
                      ))
                    )}
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* 3. PARTNER ORGANIZATIONS LIST */}
      {subTab === "organizations" && (
        <div className="space-y-4">
          {orgResetLink && (
            <div className="rounded-2xl border border-primary/40 bg-primary/10 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="min-w-0 flex-1 space-y-1">
                <p className="text-xs font-bold text-primary uppercase tracking-wider">
                  Password Reset Link Generated — {orgResetLink.orgName} ({orgResetLink.email})
                </p>
                <p className="font-mono text-xs text-foreground break-all select-all">
                  {orgResetLink.url}
                </p>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard?.writeText(orgResetLink.url)
                    toast.success("Copied reset link!")
                  }}
                  className="rounded-xl bg-primary px-3.5 py-2 text-xs font-semibold text-primary-foreground hover:opacity-90"
                >
                  Copy Link
                </button>
                <button
                  type="button"
                  onClick={() => setOrgResetLink(null)}
                  className="rounded-xl border border-border bg-background px-3 py-2 text-xs font-semibold text-muted-foreground hover:text-foreground"
                >
                  Dismiss
                </button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {partnerOrgs.map((org) => (
              <div
                key={org.id}
                className="rounded-2xl border border-border bg-card p-5 flex flex-col justify-between gap-4"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-bold uppercase text-primary">
                      {org.org_type} • {(org.country || "UAE").toUpperCase()}
                      {org.city ? ` • ${org.city}` : ""}
                    </span>
                    <span className="text-xs font-semibold text-muted-foreground">
                      {org.events_count} event(s)
                    </span>
                  </div>
                  <div>
                    <h4 className="text-base font-bold text-foreground">
                      {org.name_latin}
                    </h4>
                    {org.name_arabic && (
                      <p className="text-xs text-muted-foreground">{org.name_arabic}</p>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground space-y-0.5">
                    {org.owner_email ? (
                      <>
                        <p>
                          Contact: <strong className="text-foreground">{org.owner_name}</strong> ({org.owner_email})
                        </p>
                        {org.owner_phone && <p>Phone: {org.owner_phone}</p>}
                      </>
                    ) : (
                      <p className="text-muted-foreground italic">
                        No login user linked yet — click Edit to attach an email & password
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-end gap-2 pt-3 border-t border-border/50">
                  {org.owner_user_id && (
                    <>
                      <button
                        type="button"
                        onClick={() => setProfileUserId(org.owner_user_id!)}
                        className="inline-flex items-center gap-1 rounded-xl border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition"
                      >
                        Profile
                      </button>
                      <button
                        type="button"
                        disabled={resetOrgLinkMut.isPending}
                        onClick={() => resetOrgLinkMut.mutate(org)}
                        className="inline-flex items-center gap-1 rounded-xl bg-primary/15 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/25 transition"
                      >
                        Reset Link
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => {
                      setEditingOrg(org)
                      setOrgForm({
                        org_name_latin: org.name_latin || "",
                        org_name_arabic: org.name_arabic || "",
                        org_type: org.org_type || "university",
                        country: org.country || "uae",
                        city: org.city || "",
                        full_name: org.owner_name || "",
                        email: org.owner_email || "",
                        phone: org.owner_phone || "",
                        password: "",
                      })
                    }}
                    className="inline-flex items-center gap-1 rounded-xl border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground hover:bg-muted transition"
                  >
                    <Pencil className="h-3.5 w-3.5" /> Edit
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (window.confirm(`Delete organization "${org.name_latin}"?`)) {
                        deleteOrgMut.mutate(org.id)
                      }
                    }}
                    className="inline-flex items-center gap-1 rounded-xl border border-border bg-background p-1.5 text-muted-foreground hover:text-foreground transition"
                    title="Delete organization"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
          {partnerOrgs.length === 0 && (
            <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">
                No partner accounts yet — create one above
              </p>
            </div>
          )}
        </div>
      )}

      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}
