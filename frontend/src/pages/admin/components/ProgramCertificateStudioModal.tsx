import React, { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Award,
  Upload,
  Trash2,
  Check,
  Plus,
  Image as ImageIcon,
  Sliders,
  CheckCircle2,
  FileDown,
  Eye,
} from "lucide-react"
import type {
  Program,
  ProgramCertificateTemplate,
  ProgramCertificateTemplateCreate,
  CertificatePreviewRequest,
} from "@/types/sessions"
import { apiBaseUrl } from "@/api/client"
import {
  listProgramCertificateTemplatesApi,
  createProgramCertificateTemplateApi,
  updateProgramCertificateTemplateApi,
  deleteProgramCertificateTemplateApi,
  setDefaultProgramCertificateTemplateApi,
  setStockDefaultCertificateTemplateApi,
  uploadCertificateBackgroundApi,
  getStockSignatoryInfoApi,
  previewCertificateTemplateApi,
} from "@/api/sessions/programCertificateTemplates"
import { Modal } from "@/pages/admin/components/common"

const COLOR_SWATCHES = [
  { label: "Dark Purple", value: "#9778be" },
  { label: "Deep Violet", value: "#67388f" },
  { label: "Space Gold", value: "#d4af37" },
  { label: "Pure White", value: "#ffffff" },
  { label: "Dark Slate", value: "#1e293b" },
  { label: "Deep Black", value: "#000000" },
]

interface Props {
  program: Program
  onClose: () => void
  onUpdated?: () => void
}

export function ProgramCertificateStudioModal({ program, onClose, onUpdated }: Props) {
  const queryClient = useQueryClient()
  const canvasRef = useRef<HTMLDivElement>(null)
  const [isOpeningPreview, setIsOpeningPreview] = useState(false)

  const { data: templates = [], refetch } = useQuery<ProgramCertificateTemplate[]>({
    queryKey: ["program-certificate-templates", program.id],
    queryFn: () => listProgramCertificateTemplatesApi(program.id),
  })

  // Signatory details from system settings
  const { data: signatoryInfo } = useQuery({
    queryKey: ["stock-signatory-info"],
    queryFn: getStockSignatoryInfoApi,
  })

  // Selected tab: 'stock_dark', 'stock_light', 'new', or template ID
  const [activeTab, setActiveTab] = useState<string>("stock_dark")

  // Draft form state
  const [name, setName] = useState("Custom Certificate Template")
  const [backgroundType, setBackgroundType] = useState<"custom" | "dark" | "light">("custom")
  const [bgFilePath, setBgFilePath] = useState<string | null>(null)
  const [bgFileUrl, setBgFileUrl] = useState<string | null>(null)

  const [nameFontSize, setNameFontSize] = useState(34)
  const [nameY, setNameY] = useState(298)
  const [nameColor, setNameColor] = useState("#9778be")

  const [bodyText, setBodyText] = useState(
    "For successfully completing<br/>{program_name}<br/>{dates}"
  )
  const [bodyFontSize, setBodyFontSize] = useState(20)
  const [bodyY, setBodyY] = useState(260)
  const [bodyColor, setBodyColor] = useState("#9778be")
  const [bodyMaxWidth, setBodyMaxWidth] = useState(600)
  const [bodyAlignment, setBodyAlignment] = useState<"center" | "left" | "right">("center")

  // Signature Block placement (comes from system settings)
  const [showSignature, setShowSignature] = useState(false)
  const [sigY, setSigY] = useState(85)
  const [sigX, setSigX] = useState<number | null>(null)
  const [isCustomX, setIsCustomX] = useState(false)
  const [sigWidth, setSigWidth] = useState(140)
  const [sigHeight, setSigHeight] = useState(50)

  // Sample student name for live testing
  const [testStudentName, setTestStudentName] = useState("Ahmed Mubarak Albalushi")
  const [isUploadingBg, setIsUploadingBg] = useState(false)
  const [isPreviewDownloading, setIsPreviewDownloading] = useState(false)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // When templates load or tab changes, load corresponding template into form
  useEffect(() => {
    if (activeTab === "stock_dark") {
      setName("Stock Dark Default")
      setBackgroundType("dark")
      setBgFilePath(null)
      setBgFileUrl(null)
      setNameFontSize(34)
      setNameY(298)
      setNameColor("#9778be")
      setBodyText("For successfully completing<br/>{program_name}<br/>{dates}")
      setBodyFontSize(20)
      setBodyY(260)
      setBodyColor("#9778be")
      setBodyMaxWidth(600)
      setShowSignature(false)
    } else if (activeTab === "stock_light") {
      setName("Stock Light Default")
      setBackgroundType("light")
      setBgFilePath(null)
      setBgFileUrl(null)
      setNameFontSize(34)
      setNameY(298)
      setNameColor("#67388f")
      setBodyText("For successfully completing<br/>{program_name}<br/>{dates}")
      setBodyFontSize(20)
      setBodyY(260)
      setBodyColor("#67388f")
      setBodyMaxWidth(600)
      setShowSignature(false)
    } else if (activeTab === "new") {
      setName("New Program Certificate")
      setBackgroundType("custom")
      setBgFilePath(null)
      setBgFileUrl(null)
      setNameFontSize(34)
      setNameY(298)
      setNameColor("#9778be")
      setBodyText("For successfully completing<br/>{program_name}<br/>{dates}")
      setBodyFontSize(20)
      setBodyY(260)
      setBodyColor("#9778be")
      setBodyMaxWidth(600)
      setShowSignature(false)
      setSigY(85)
      setSigX(null)
      setIsCustomX(false)
      setSigWidth(140)
      setSigHeight(50)
    } else {
      const existing = templates.find((t) => t.id === activeTab)
      if (existing) {
        setName(existing.name)
        setBackgroundType(existing.background_type)
        setBgFilePath(existing.background_file_path ?? null)
        setBgFileUrl(existing.background_file_url ?? null)
        setNameFontSize(existing.name_font_size)
        setNameY(Number(existing.name_y))
        setNameColor(existing.name_color)
        setBodyText(existing.body_text ?? "For successfully completing<br/>{program_name}<br/>{dates}")
        setBodyFontSize(existing.body_font_size)
        setBodyY(Number(existing.body_y))
        setBodyColor(existing.body_color)
        setBodyMaxWidth(Number(existing.body_max_width))
        setBodyAlignment(existing.body_alignment)
        setShowSignature(existing.show_signature)
        setSigY(Number(existing.signature_y ?? 85))
        setSigWidth(Number(existing.signature_width ?? 140))
        setSigHeight(Number(existing.signature_height ?? 50))
        if (existing.signature_x !== null && existing.signature_x !== undefined) {
          setSigX(Number(existing.signature_x))
          setIsCustomX(true)
        } else {
          setSigX(null)
          setIsCustomX(false)
        }
      }
    }
  }, [activeTab, templates])

  // Current active template row (if editing existing custom template)
  const currentCustomTemplate = templates.find((t) => t.id === activeTab)

  // Is the current view set as auto-send default?
  const isCurrentlyDefault =
    activeTab === "stock_dark"
      ? !program.default_certificate_template_id && !templates.some((t) => t.is_default)
      : activeTab === "stock_light"
      ? false
      : currentCustomTemplate?.is_default ?? false

  // Save / Update mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload: ProgramCertificateTemplateCreate = {
        name,
        is_default: isCurrentlyDefault,
        background_type: backgroundType,
        background_file_path: bgFilePath,
        background_file_url: bgFileUrl,
        name_font_size: nameFontSize,
        name_y: nameY,
        name_color: nameColor,
        body_text: bodyText,
        body_font_size: bodyFontSize,
        body_y: bodyY,
        body_color: bodyColor,
        body_max_width: bodyMaxWidth,
        body_alignment: bodyAlignment,
        show_signature: showSignature,
        signature_image_path: null,
        signature_image_url: null,
        signature_x: isCustomX ? sigX : null,
        signature_y: sigY,
        signature_width: sigWidth,
        signature_height: sigHeight,
      }

      if (currentCustomTemplate) {
        return updateProgramCertificateTemplateApi(program.id, currentCustomTemplate.id, payload)
      } else {
        return createProgramCertificateTemplateApi(program.id, payload)
      }
    },
    onSuccess: (saved) => {
      setSaveSuccess(true)
      setTimeout(() => setSaveSuccess(false), 3000)
      queryClient.invalidateQueries({ queryKey: ["program-certificate-templates", program.id] })
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      setActiveTab(saved.id)
      onUpdated?.()
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => deleteProgramCertificateTemplateApi(program.id, templateId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["program-certificate-templates", program.id] })
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      setActiveTab("stock_dark")
      onUpdated?.()
    },
  })

  // Set default mutation
  const setDefaultMutation = useMutation({
    mutationFn: async (target: "stock_dark" | "stock_light" | string) => {
      if (target === "stock_dark" || target === "stock_light") {
        return setStockDefaultCertificateTemplateApi(
          program.id,
          target === "stock_light" ? "light" : "dark"
        )
      } else {
        return setDefaultProgramCertificateTemplateApi(program.id, target)
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["program-certificate-templates", program.id] })
      queryClient.invalidateQueries({ queryKey: ["sessions-programs"] })
      refetch()
      onUpdated?.()
    },
  })

  // Handle Background Upload
  const handleBackgroundUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setIsUploadingBg(true)
    try {
      const res = await uploadCertificateBackgroundApi(program.id, file)
      setBgFilePath(res.file_path)
      setBgFileUrl(res.file_url)
      setBackgroundType("custom")
    } catch (err) {
      console.error("Failed to upload certificate background", err)
      alert("Failed to upload background image. Please try again.")
    } finally {
      setIsUploadingBg(false)
    }
  }

  // Handle Download Test PDF
  const handleDownloadTestPdf = async () => {
    setIsPreviewDownloading(true)
    try {
      const previewReq: CertificatePreviewRequest = {
        recipient_name: testStudentName || "Student Name",
        program_name: program.name,
        cohort_name: "Cohort Title",
        dates: "12 – 16 October 2026",
        location: "SpacePoint HQ",
        background_type: backgroundType,
        background_file_path: bgFilePath,
        name_font_size: nameFontSize,
        name_y: nameY,
        name_color: nameColor,
        body_text: bodyText,
        body_font_size: bodyFontSize,
        body_y: bodyY,
        body_color: bodyColor,
        body_max_width: bodyMaxWidth,
        body_alignment: bodyAlignment,
        show_signature: showSignature,
        signature_image_path: null,
        signature_x: isCustomX ? sigX : null,
        signature_y: sigY,
        signature_width: sigWidth,
        signature_height: sigHeight,
      }

      const pdfBlob = await previewCertificateTemplateApi(program.id, previewReq)
      const url = URL.createObjectURL(pdfBlob)
      const a = document.createElement("a")
      a.href = url
      a.download = `preview_${program.code}_${name.replace(/[^a-z0-9]+/gi, "_")}.pdf`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error("Failed to download test PDF", err)
      alert("Failed to generate test PDF preview. Please check parameters.")
    } finally {
      setIsPreviewDownloading(false)
    }
  }

  // Handle Open Live Rendered PDF in New Tab
  const handleOpenPdfPreview = async () => {
    setIsOpeningPreview(true)
    try {
      const previewReq: CertificatePreviewRequest = {
        recipient_name: testStudentName || "Student Name",
        program_name: program.name,
        cohort_name: "Cohort Title",
        dates: "12 – 16 October 2026",
        location: "SpacePoint HQ",
        background_type: backgroundType,
        background_file_path: bgFilePath,
        name_font_size: nameFontSize,
        name_y: nameY,
        name_color: nameColor,
        body_text: bodyText,
        body_font_size: bodyFontSize,
        body_y: bodyY,
        body_color: bodyColor,
        body_max_width: bodyMaxWidth,
        body_alignment: bodyAlignment,
        show_signature: showSignature,
        signature_image_path: null,
        signature_x: isCustomX ? sigX : null,
        signature_y: sigY,
        signature_width: sigWidth,
        signature_height: sigHeight,
      }

      const pdfBlob = await previewCertificateTemplateApi(program.id, previewReq)
      const url = URL.createObjectURL(pdfBlob)
      window.open(url, "_blank")
    } catch (err) {
      console.error("Failed to open PDF preview", err)
      alert("Failed to generate PDF preview. Please check parameters.")
    } finally {
      setIsOpeningPreview(false)
    }
  }

  // Formatted preview body text with test values: {program_name} is always the program name,
  // while {cohort} / {cohort_name} is used if explicitly specified.
  const previewBodyLines = (bodyText || "")
    .replace(/\{program_name\}/g, program.name)
    .replace(/\{cohort_name\}/g, "Cohort Title")
    .replace(/\{cohort\}/g, "Cohort Title")
    .replace(/\{dates\}/g, "12 – 16 October 2026")
    .replace(/\{location\}/g, "SpacePoint HQ")
    .split("<br/>")

  // Effective background image URL for canvas
  const effectiveBgUrl = (() => {
    if (backgroundType === "custom" && bgFileUrl) {
      return bgFileUrl.startsWith("http") ? bgFileUrl : `${apiBaseUrl}${bgFileUrl}`
    }
    const theme = backgroundType === "light" || activeTab === "stock_light" ? "light" : "dark"
    return `${apiBaseUrl}/sessions/programs/stock-template-image?theme=${theme}`
  })()


  return (
    <Modal
      title={`Certificate Templates: ${program.name}`}
      onClose={onClose}
      maxWidth="w-[98vw] max-w-[98vw] sm:w-full sm:max-w-7xl p-2.5 sm:p-6 max-h-[96vh] sm:max-h-[90vh]"
    >
      <div className="flex flex-col gap-5 -mt-1">
        {/* Top Header: Template Selector Pills & Actions Bar */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5 pb-2.5 border-b border-border">
          {/* Template Selector Pills (Horizontally scrollable) */}
          <div className="flex items-center gap-1.5 overflow-x-auto max-w-full pb-0.5 scrollbar-none shrink">
            {/* Stock Dark Default */}
            <button
              onClick={() => setActiveTab("stock_dark")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                activeTab === "stock_dark"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <Award size={13} />
              <span>Dark Default</span>
              {!program.default_certificate_template_id && !templates.some((t) => t.is_default) && (
                <span className="ml-1 text-[10px] bg-primary-foreground/20 text-primary-foreground font-semibold px-1.5 py-0.2 rounded-full">
                  Default
                </span>
              )}
            </button>

            {/* Stock Light Default */}
            <button
              onClick={() => setActiveTab("stock_light")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                activeTab === "stock_light"
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
              }`}
            >
              <Award size={13} />
              <span>Light Default</span>
            </button>

            {/* Custom Templates List */}
            {templates.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-colors whitespace-nowrap shrink-0 ${
                  activeTab === t.id
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "bg-muted/60 text-muted-foreground hover:text-foreground hover:bg-muted"
                }`}
              >
                <Award size={13} />
                <span className="whitespace-nowrap">{t.name}</span>
                {t.is_default && (
                  <span className="ml-1 text-[10px] bg-emerald-500 text-white font-semibold px-1.5 py-0.2 rounded-full">
                    Default
                  </span>
                )}
              </button>
            ))}

            {/* + Add Custom Template */}
            <button
              onClick={() => setActiveTab("new")}
              className={`flex items-center gap-1 px-3 py-1.5 rounded-xl text-xs font-medium border border-dashed transition-colors whitespace-nowrap shrink-0 ${
                activeTab === "new"
                  ? "border-primary bg-primary/10 text-primary font-semibold"
                  : "border-border text-muted-foreground hover:text-foreground hover:border-muted-foreground"
              }`}
            >
              <Plus size={13} />
              <span>New Custom</span>
            </button>
          </div>

          {/* Top Actions: Default on Left, Delete & Save on Right */}
          <div className="flex items-center justify-between sm:justify-end gap-2 shrink-0">
            {/* Set as Default (only shown when not currently default) */}
            {!isCurrentlyDefault && activeTab !== "new" && (
              <div>
                <button
                  type="button"
                  onClick={() => setDefaultMutation.mutate(activeTab)}
                  disabled={setDefaultMutation.isPending}
                  className="h-8 px-2.5 sm:px-3 border border-border bg-background hover:bg-muted text-xs font-medium text-foreground rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer whitespace-nowrap shrink-0"
                  title={`Make this template the default for ${program.name}`}
                >
                  <Check size={13} className="text-primary shrink-0" />
                  <span className="hidden sm:inline">
                    {setDefaultMutation.isPending ? "Setting…" : "Set as Default"}
                  </span>
                  <span className="sm:hidden">
                    {setDefaultMutation.isPending ? "Setting…" : "Set Default"}
                  </span>
                </button>
              </div>
            )}

            {/* Delete, Saved Indicator, Save */}
            <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
              {saveSuccess && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                  <CheckCircle2 size={13} className="shrink-0" />
                  <span className="hidden sm:inline">Saved!</span>
                </span>
              )}

              {activeTab !== "stock_dark" &&
                activeTab !== "stock_light" &&
                currentCustomTemplate && (
                  <button
                    type="button"
                    onClick={() => {
                      if (confirm(`Delete the custom template "${currentCustomTemplate.name}"?`)) {
                        deleteMutation.mutate(currentCustomTemplate.id)
                      }
                    }}
                    disabled={deleteMutation.isPending}
                    className="h-8 px-2 sm:px-2.5 flex items-center gap-1 text-xs text-red-600 dark:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors cursor-pointer whitespace-nowrap shrink-0"
                    title="Delete this template"
                  >
                    <Trash2 size={13} className="shrink-0" />
                    <span className="hidden sm:inline">Delete template</span>
                    <span className="sm:hidden">Delete</span>
                  </button>
                )}

              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="h-8 px-3 sm:px-4 bg-primary text-primary-foreground rounded-lg text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50 flex items-center gap-1.5 shadow-sm cursor-pointer whitespace-nowrap shrink-0"
              >
                <span>{saveMutation.isPending ? "Saving…" : "Save"}</span>
                <span className="hidden sm:inline">Template</span>
              </button>
            </div>
          </div>
        </div>

        {/* Studio Grid: Controls on Left (4 cols), Live WYSIWYG Canvas on Right (8 cols) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-3 sm:gap-6">
          {/* Controls Column (4 cols) */}
          <div className="lg:col-span-4 flex flex-col gap-4 lg:max-h-[74vh] lg:overflow-y-auto pr-1">
            {/* Template Name */}
                <div>
                  <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">
                    Template Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Space Race Champion Finalist"
                    className="w-full h-9 px-3 rounded-xl border border-border bg-background text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                  />
                </div>

                {/* Background Image Selection */}
                <div className="border border-border rounded-xl p-3.5 flex flex-col gap-2.5 bg-card">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                      <ImageIcon size={14} className="text-primary" /> Certificate Background
                    </span>
                    <span className="text-[11px] text-muted-foreground">A4 Landscape</span>
                  </div>

                  <div className="grid grid-cols-3 gap-1.5">
                    <button
                      type="button"
                      onClick={() => {
                        setBackgroundType("dark")
                        setBgFilePath(null)
                        setBgFileUrl(null)
                      }}
                      className={`h-8 rounded-lg text-xs font-medium border transition-colors ${
                        backgroundType === "dark" && !bgFileUrl
                          ? "border-primary bg-primary/10 text-primary font-semibold"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Stock Dark
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setBackgroundType("light")
                        setBgFilePath(null)
                        setBgFileUrl(null)
                      }}
                      className={`h-8 rounded-lg text-xs font-medium border transition-colors ${
                        backgroundType === "light" && !bgFileUrl
                          ? "border-primary bg-primary/10 text-primary font-semibold"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      Stock Light
                    </button>
                    <label
                      className={`h-8 rounded-lg text-xs font-medium border flex items-center justify-center gap-1 cursor-pointer transition-colors ${
                        backgroundType === "custom" && bgFileUrl
                          ? "border-primary bg-primary/10 text-primary font-semibold"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      <Upload size={12} />
                      <span>{isUploadingBg ? "Uploading…" : "Custom PNG"}</span>
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp"
                        className="hidden"
                        onChange={handleBackgroundUpload}
                        disabled={isUploadingBg}
                      />
                    </label>
                  </div>

                  {bgFileUrl && (
                    <p className="text-[11px] text-emerald-600 dark:text-emerald-400 truncate">
                      Custom image uploaded
                    </p>
                  )}
                </div>

                {/* Recipient Name Controls */}
                <div className="border border-border rounded-xl p-3.5 flex flex-col gap-3 bg-card">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Sliders size={14} className="text-primary" /> Recipient Name Styling
                  </span>

                  {/* Font size */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>Font Size</span>
                      <span className="font-mono text-foreground">{nameFontSize} pt</span>
                    </div>
                    <input
                      type="range"
                      min="18"
                      max="54"
                      value={nameFontSize}
                      onChange={(e) => setNameFontSize(Number(e.target.value))}
                      className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>

                  {/* Vertical Position (Y) */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>Vertical Position (from bottom)</span>
                      <span className="font-mono text-foreground">{nameY} pt</span>
                    </div>
                    <input
                      type="range"
                      min="180"
                      max="420"
                      value={nameY}
                      onChange={(e) => setNameY(Number(e.target.value))}
                      className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>

                  {/* Color Picker */}
                  <div>
                    <span className="text-xs text-muted-foreground block mb-1.5">Name Color</span>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {COLOR_SWATCHES.map((swatch) => (
                          <button
                            key={swatch.value}
                            type="button"
                            onClick={() => setNameColor(swatch.value)}
                            style={{ backgroundColor: swatch.value }}
                            className={`w-5 h-5 rounded-full border transition-transform ${
                              nameColor.toLowerCase() === swatch.value.toLowerCase()
                                ? "scale-125 border-primary shadow-sm"
                                : "border-border hover:scale-110"
                            }`}
                            title={swatch.label}
                          />
                        ))}
                      </div>
                      <input
                        type="color"
                        value={nameColor}
                        onChange={(e) => setNameColor(e.target.value)}
                        className="w-7 h-7 rounded-lg border border-border bg-transparent cursor-pointer ml-auto"
                        title="Custom color"
                      />
                    </div>
                  </div>
                </div>

                {/* Description Body Controls */}
                <div className="border border-border rounded-xl p-3.5 flex flex-col gap-3 bg-card">
                  <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                    <Sliders size={14} className="text-primary" /> Body Description Styling
                  </span>

                  {/* Body Text Template */}
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-[11px] text-muted-foreground block">
                        Text template (use <code className="text-primary">&lt;br/&gt;</code> for line breaks)
                      </label>
                      <button
                        type="button"
                        onClick={() => setBodyText((prev) => `${prev} {cohort}`)}
                        className="text-[10px] text-primary hover:underline font-medium cursor-pointer"
                        title="Add {cohort} placeholder"
                      >
                        + Insert &#123;cohort&#125;
                      </button>
                    </div>
                    <textarea
                      rows={3}
                      value={bodyText}
                      onChange={(e) => setBodyText(e.target.value)}
                      className="w-full px-3 py-2 rounded-xl border border-border bg-background text-xs font-mono text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                      placeholder="For successfully completing<br/>{program_name}<br/>{dates}"
                    />
                    <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px] text-muted-foreground">
                      <span>Variables:</span>
                      <code className="bg-muted px-1 rounded text-foreground">&#123;program_name&#125;</code>
                      <code className="bg-muted px-1 rounded text-foreground">&#123;cohort&#125;</code>
                      <code className="bg-muted px-1 rounded text-foreground">&#123;dates&#125;</code>
                      <code className="bg-muted px-1 rounded text-foreground">&#123;location&#125;</code>
                    </div>
                  </div>

                  {/* Body Font size */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>Font Size</span>
                      <span className="font-mono text-foreground">{bodyFontSize} pt</span>
                    </div>
                    <input
                      type="range"
                      min="12"
                      max="32"
                      value={bodyFontSize}
                      onChange={(e) => setBodyFontSize(Number(e.target.value))}
                      className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>

                  {/* Body Vertical Position (Y) */}
                  <div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                      <span>Vertical Position (from bottom)</span>
                      <span className="font-mono text-foreground">{bodyY} pt</span>
                    </div>
                    <input
                      type="range"
                      min="140"
                      max="360"
                      value={bodyY}
                      onChange={(e) => setBodyY(Number(e.target.value))}
                      className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>


                  {/* Body Color Picker */}
                  <div>
                    <span className="text-xs text-muted-foreground block mb-1.5">Body Text Color</span>
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {COLOR_SWATCHES.map((swatch) => (
                          <button
                            key={swatch.value}
                            type="button"
                            onClick={() => setBodyColor(swatch.value)}
                            style={{ backgroundColor: swatch.value }}
                            className={`w-5 h-5 rounded-full border transition-transform ${
                              bodyColor.toLowerCase() === swatch.value.toLowerCase()
                                ? "scale-125 border-primary shadow-sm"
                                : "border-border hover:scale-110"
                            }`}
                            title={swatch.label}
                          />
                        ))}
                      </div>
                      <input
                        type="color"
                        value={bodyColor}
                        onChange={(e) => setBodyColor(e.target.value)}
                        className="w-7 h-7 rounded-lg border border-border bg-transparent cursor-pointer ml-auto"
                        title="Custom color"
                      />
                    </div>
                  </div>
                </div>

                {/* Signature Block Controls */}
                <div className="border border-border rounded-xl p-3.5 flex flex-col gap-3 bg-card">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-foreground">
                      Dynamic Signature Block
                    </span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showSignature}
                        onChange={(e) => setShowSignature(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-muted peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-border after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>

                  {showSignature && (
                    <div className="flex flex-col gap-3 pt-2 border-t border-border/60">
                      {/* System Settings Source Card */}
                      <div className="p-2.5 rounded-xl border border-border/80 bg-muted/40 text-xs flex flex-col gap-0.5">
                        <div className="flex items-center justify-between text-muted-foreground mb-1 text-[10px] font-semibold uppercase tracking-wider">
                          <span>From System Settings</span>
                          <span className="text-primary/90 font-medium">Automatic</span>
                        </div>
                        <p className="font-semibold text-foreground tracking-wide break-words">
                          {signatoryInfo?.signatory_name || "ABDULLAH ALSALMANI"}
                        </p>
                        <p className="text-[11px] text-muted-foreground break-words">
                          {signatoryInfo?.signatory_title || "Co-Founder & CEO of SpacePoint"}
                        </p>
                      </div>

                      {/* Placement: Vertical Position (Y) */}
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                          <span>Vertical Position (from bottom)</span>
                          <span className="font-mono text-foreground">{sigY} pt</span>
                        </div>
                        <input
                          type="range"
                          min="30"
                          max="200"
                          value={sigY}
                          onChange={(e) => setSigY(Number(e.target.value))}
                          className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                        />
                      </div>

                      {/* Placement: Horizontal Position (X) */}
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1.5">
                          <span>Horizontal Alignment</span>
                          <div className="flex items-center gap-1 bg-muted/70 p-0.5 rounded-lg border border-border">
                            <button
                              type="button"
                              onClick={() => {
                                setIsCustomX(false)
                                setSigX(null)
                              }}
                              className={`px-2 py-0.5 rounded-md text-[10px] font-medium transition-colors ${
                                !isCustomX
                                  ? "bg-background text-foreground shadow-sm"
                                  : "text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              Centered
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setIsCustomX(true)
                                if (sigX === null) setSigX(Math.round((842 - sigWidth) / 2))
                              }}
                              className={`px-2 py-0.5 rounded-md text-[10px] font-medium transition-colors ${
                                isCustomX
                                  ? "bg-background text-foreground shadow-sm"
                                  : "text-muted-foreground hover:text-foreground"
                              }`}
                            >
                              Custom X
                            </button>
                          </div>
                        </div>
                        {isCustomX && (
                          <div className="mt-2">
                            <div className="flex items-center justify-between text-[11px] text-muted-foreground mb-1">
                              <span>Left Offset (X)</span>
                              <span className="font-mono text-foreground">{sigX ?? 350} pt</span>
                            </div>
                            <input
                              type="range"
                              min="40"
                              max="680"
                              step="5"
                              value={sigX ?? 350}
                              onChange={(e) => setSigX(Number(e.target.value))}
                              className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                            />
                          </div>
                        )}
                      </div>

                      {/* Placement: Width */}
                      <div>
                        <div className="flex items-center justify-between text-xs text-muted-foreground mb-1">
                          <span>Signature Width</span>
                          <span className="font-mono text-foreground">{sigWidth} pt</span>
                        </div>
                        <input
                          type="range"
                          min="80"
                          max="260"
                          value={sigWidth}
                          onChange={(e) => setSigWidth(Number(e.target.value))}
                          className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary"
                        />
                      </div>
                    </div>
                  )}
                </div>

            {/* Test Student Name Input */}
            <div className="p-3 bg-muted/20 border border-border rounded-xl">
              <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">
                Live Test Student Name
              </label>
              <input
                type="text"
                value={testStudentName}
                onChange={(e) => setTestStudentName(e.target.value)}
                placeholder="Test student name (English or Arabic)"
                className="w-full h-8 px-2.5 rounded-lg border border-border bg-background text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              />
            </div>
          </div>

          {/* Canvas & Actions Column (8 cols) */}
          <div className="lg:col-span-8 flex flex-col gap-4">
            {/* Top Toolbar */}
            <div className="flex items-center justify-between flex-wrap gap-2">
              <span className="text-xs font-semibold text-foreground">
                Certificate Preview
              </span>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleOpenPdfPreview}
                  disabled={isOpeningPreview}
                  className="flex items-center gap-1.5 h-8 px-3 rounded-xl border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors disabled:opacity-50"
                  title="Render and open live PDF in a new browser tab"
                >
                  <Eye size={13} className="text-primary" />
                  <span>{isOpeningPreview ? "Loading…" : "Preview PDF"}</span>
                </button>

                <button
                  type="button"
                  onClick={handleDownloadTestPdf}
                  disabled={isPreviewDownloading}
                  className="flex items-center gap-1.5 h-8 px-3 rounded-xl border border-border bg-background hover:bg-muted text-xs font-medium text-foreground transition-colors disabled:opacity-50"
                  title="Generates and downloads pixel-perfect PDF using server ReportLab engine"
                >
                  <FileDown size={13} className="text-primary" />
                  <span>{isPreviewDownloading ? "Generating…" : "Download PDF"}</span>
                </button>
              </div>
            </div>

            {/* WYSIWYG A4 Landscape Canvas Viewport (1:1 Actual, Left-start scrollable) */}
            <div
              className="w-full overflow-x-auto overflow-y-auto max-h-[72vh] rounded-2xl border-2 border-border/80 bg-slate-950/40 p-3 shadow-inner"
            >
              <div className="min-w-fit w-full flex justify-center items-start">
                <div
                  ref={canvasRef}
                  className="relative shrink-0 rounded-xl border border-border/50 shadow-2xl overflow-hidden select-none bg-slate-950"
                  style={{
                    width: "841.89px",
                    height: "595.27px",
                    minWidth: "841.89px",
                    minHeight: "595.27px",
                  }}
                >
                {/* Template Background Image Layer */}
                {effectiveBgUrl ? (
                  <img
                    src={effectiveBgUrl}
                    alt="Certificate Template Background"
                    className="absolute inset-0 w-full h-full object-fill pointer-events-none"
                  />
                ) : (
                  <div className="absolute inset-0 flex flex-col items-center justify-center border-4 border-double border-muted/30 m-4 rounded-xl pointer-events-none">
                    <ImageIcon size={32} className="text-muted-foreground/40 mb-1.5" />
                    <p className="text-xs text-muted-foreground font-medium">
                      Upload a background image on the left panel
                    </p>
                  </div>
                )}

                {/* Recipient Name Preview - Placed by baseline matching ReportLab's drawCentredString */}
                <div
                  className="absolute left-1/2 text-center font-serif font-bold italic transition-all pointer-events-none"
                  style={{
                    top: `${((595.27 - nameY) / 595.27) * 100}%`,
                    transform: "translate(-50%, -75%)",
                    fontSize: `${nameFontSize}px`,
                    fontFamily: '"Times New Roman", Times, Georgia, serif',
                    lineHeight: 1.1,
                    color: nameColor,
                    textShadow: "0 1px 2px rgba(0,0,0,0.3)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {testStudentName || "Student Name"}
                </div>

                {/* Body Description Preview - Starts at body_y and flows downward matching ReportLab's Paragraph.drawOn */}
                <div
                  className="absolute left-1/2 font-serif italic transition-all pointer-events-none flex flex-col items-center"
                  style={{
                    top: `${((595.27 - bodyY) / 595.27) * 100}%`,
                    transform: "translateX(-50%)",
                    width: `${(bodyMaxWidth / 841.89) * 100}%`,
                    fontSize: `${bodyFontSize}px`,
                    fontFamily: '"Times New Roman", Times, Georgia, serif',
                    lineHeight: 1.45,
                    color: bodyColor,
                    textAlign: bodyAlignment,
                    textShadow: "0 1px 2px rgba(0,0,0,0.3)",
                  }}
                >
                  {previewBodyLines.map((line, idx) => (
                    <p key={idx} className="w-full">
                      {line}
                    </p>
                  ))}
                </div>

                {/* Dynamic Signature Preview */}
                {showSignature && (
                  <div
                    className="absolute flex flex-col items-center justify-center pointer-events-none transition-all"
                    style={{
                      bottom: `${(sigY / 595.27) * 100}%`,
                      left: isCustomX && sigX !== null ? `${(sigX / 841.89) * 100}%` : "50%",
                      transform: isCustomX && sigX !== null ? "none" : "translateX(-50%)",
                      width: `${(sigWidth / 841.89) * 100}%`,
                    }}
                  >
                    <img
                      src={`${apiBaseUrl}/sessions/programs/stock-signature-image?theme=${
                        backgroundType === "light" || activeTab === "stock_light" ? "light" : "dark"
                      }`}
                      alt="Signature"
                      className="w-full object-contain mb-1 pointer-events-none"
                      style={{
                        filter: "drop-shadow(0 1px 2px rgba(0,0,0,0.3))",
                      }}
                    />
                    <p
                      className="text-center font-bold uppercase tracking-widest leading-tight whitespace-nowrap"
                      style={{
                        fontSize: "10.5px",
                        fontFamily: "Helvetica, Arial, -apple-system, sans-serif",
                        letterSpacing: "0.12em",
                        color: bodyColor,
                        textShadow: "0 1px 2px rgba(0,0,0,0.4)",
                      }}
                    >
                      {signatoryInfo?.signatory_name || "ABDULLAH ALSALMANI"}
                    </p>
                    <p
                      className="text-center leading-tight mt-0.5 whitespace-nowrap"
                      style={{
                        fontSize: "9px",
                        fontFamily: "Helvetica, Arial, -apple-system, sans-serif",
                        color: bodyColor,
                        opacity: 0.9,
                        textShadow: "0 1px 2px rgba(0,0,0,0.4)",
                      }}
                    >
                      {signatoryInfo?.signatory_title || "Co-Founder & CEO of SpacePoint"}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

            {/* Bottom Actions Row */}
            <div className="flex items-center justify-end pt-2 border-t border-border mt-auto">
              <button
                type="button"
                onClick={onClose}
                className="h-9 px-4 border border-border rounded-xl text-xs font-medium text-foreground hover:bg-muted transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
