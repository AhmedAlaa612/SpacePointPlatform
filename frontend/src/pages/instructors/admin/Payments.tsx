import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useSearch } from "@tanstack/react-router"
import {
  Ban,
  Calendar,
  CalendarCheck,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Download,
  Eye,
  FileCheck2,
  FileSpreadsheet,
  FileText,
  FolderPlus,
  Layers,
  MapPin,
  Pencil,
  Plus,
  Search,
  Send,
  Trash2,
  Upload,
  UserCheck,
  Users,
  Wallet,
  X,
} from "lucide-react"
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import {
  bulkImportConfirmApi,
  bulkImportPreviewApi,
  createBatchApi,
  createLetterApi,
  deleteBatchApi,
  downloadBulkImportTemplateApi,
  generateLetterPdfApi,
  getPaymentsAnalyticsApi,
  ignoreDraftLetterApi,
  ignorePaymentCohortApi,
  listAdminLettersApi,
  listBatchesApi,
  listPaymentCohortsApi,
  markPaidApi,
  paymentsInstructorDropdownApi,
  publishLetterApi,
  updateLetterApi,
  type CompletedCohortPayment,
} from "@/api/instructors/payments_admin"
import { getDeliveryRolesApi } from "@/api/sessions/openings"
import { UserProfileModal } from "@/components/UserProfileModal"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { useToast } from "@/components/ui/toast"
import { cn, getErrorMessage } from "@/lib/utils"
import {
  CohortReviewModal,
  PaymentStatusBadge,
  SettledCohortModal,
  type PaymentBadgeVariant,
} from "@/pages/instructors/admin/components/PaymentCohortModals"
import { PaymentLetterTable } from "@/pages/instructors/admin/components/PaymentLetterTable"
import { PageHeader, Spinner } from "@/pages/instructors/components/common"
import type { PaymentLetter, PaymentLetterStatus } from "@/types/instructors"

export default function InstructorsAdminPayments() {
  const { letterId: searchLetterId, status: searchStatus } = useSearch({ strict: false }) as {
    letterId?: string
    status?: string
  }
  const qc = useQueryClient()
  const toast = useToast()
  const importInputRef = useRef<HTMLInputElement>(null)
  const handledLetterIdRef = useRef<string | null>(null)
  const touchedTimerRef = useRef<number | null>(null)

  // Filters & modals
  const [search, setSearch] = useState("")
  const [batchFilter, setBatchFilter] = useState("all")
  const [analysisUserId, setAnalysisUserId] = useState("")
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  const [manageLetterId, setManageLetterId] = useState<string | null>(null)
  const [reviewCohortId, setReviewCohortId] = useState<string | null>(null)
  const [settledCohortId, setSettledCohortId] = useState<string | null>(null)

  const [batchesOpen, setBatchesOpen] = useState(false)
  const [assignBatchLetterId, setAssignBatchLetterId] = useState<string | null>(null)
  const [newBatchName, setNewBatchName] = useState("")
  const [newBatchDesc, setNewBatchDesc] = useState("")

  const [newLetterOpen, setNewLetterOpen] = useState(false)
  const [selectedInstructor, setSelectedInstructor] = useState("")
  const [selectedBatch, setSelectedBatch] = useState("")

  const [bulkImportOpen, setBulkImportOpen] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importPreview, setImportPreview] = useState<Awaited<ReturnType<typeof bulkImportPreviewApi>> | null>(null)
  const [importBatch, setImportBatch] = useState("")

  const [touchedLetterIds, setTouchedLetterIds] = useState<Set<string>>(() => new Set())

  // Vertical collapsibles
  const [openCohortPending, setOpenCohortPending] = useState(true)
  const [openCohortSettled, setOpenCohortSettled] = useState(false)
  const [openLetterStages, setOpenLetterStages] = useState<Record<PaymentLetterStatus, boolean>>({
    draft: true,
    published: true,
    signed: true,
    paid: false,
  })

  // Queries
  const { data: letters = [], isLoading: loadingLetters } = useQuery({
    queryKey: ["admin-payment-letters"],
    queryFn: () => listAdminLettersApi(),
  })
  const { data: cohorts = [], isLoading: loadingCohorts } = useQuery({
    queryKey: ["admin-payment-cohorts"],
    queryFn: listPaymentCohortsApi,
  })
  const { data: analytics } = useQuery({
    queryKey: ["admin-payment-analytics"],
    queryFn: getPaymentsAnalyticsApi,
  })
  const { data: batches = [] } = useQuery({
    queryKey: ["admin-payment-batches"],
    queryFn: listBatchesApi,
  })
  const { data: instructorOptions = [] } = useQuery({
    queryKey: ["payments-instructor-options"],
    queryFn: paymentsInstructorDropdownApi,
  })
  const { data: deliveryRoles = [] } = useQuery({
    queryKey: ["delivery-roles"],
    queryFn: () => getDeliveryRolesApi(),
  })

  useEffect(() => {
    return () => {
      if (touchedTimerRef.current !== null) {
        window.clearTimeout(touchedTimerRef.current)
      }
    }
  }, [])

  const highlightLetters = (ids: string[]) => {
    if (ids.length === 0) return
    setTouchedLetterIds(new Set(ids))
    if (touchedTimerRef.current !== null) window.clearTimeout(touchedTimerRef.current)
    touchedTimerRef.current = window.setTimeout(() => setTouchedLetterIds(new Set()), 2500)
  }

  const invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["admin-payment-letters"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-cohorts"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-analytics"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-batches"] })
    qc.invalidateQueries({ queryKey: ["admin-payment-todo"] })
    qc.invalidateQueries({ queryKey: ["admin-overview"] })
    qc.invalidateQueries({ queryKey: ["instructor-payment-history"] })
  }

  // Deep-links from Admin Dashboard (?status=, ?letterId=)
  useEffect(() => {
    if (!searchStatus) return
    const normalized = searchStatus === "pending" ? "draft" : searchStatus
    if (normalized === "draft" || normalized === "published" || normalized === "signed" || normalized === "paid") {
      setOpenLetterStages((prev) => ({ ...prev, [normalized]: true }))
    }
  }, [searchStatus])

  useEffect(() => {
    if (!searchLetterId) {
      handledLetterIdRef.current = null
      return
    }
    if (loadingLetters || handledLetterIdRef.current === searchLetterId) return
    const target = letters.find((l) => l.id === searchLetterId)
    if (target) {
      handledLetterIdRef.current = searchLetterId
      setOpenLetterStages((prev) => ({ ...prev, [target.status]: true }))
      setManageLetterId(searchLetterId)
    }
  }, [searchLetterId, letters, loadingLetters])

  // Mutations
  const createLetter = useMutation({
    mutationFn: () =>
      createLetterApi({
        instructor_user_id: selectedInstructor,
        batch_id: selectedBatch || undefined,
      }),
    onSuccess: (created) => {
      invalidateAll()
      setNewLetterOpen(false)
      setSelectedInstructor("")
      setSelectedBatch("")
      setOpenLetterStages((prev) => ({ ...prev, draft: true }))
      setManageLetterId(created.id)
      highlightLetters([created.id])
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create letter")),
  })

  const createBatch = useMutation({
    mutationFn: () =>
      createBatchApi({ name: newBatchName.trim(), description: newBatchDesc.trim() || undefined }),
    onSuccess: async (created) => {
      if (assignBatchLetterId) {
        await updateLetterApi({ id: assignBatchLetterId, batch_id: created.id })
        setAssignBatchLetterId(null)
        setBatchesOpen(false)
      }
      invalidateAll()
      setNewBatchName("")
      setNewBatchDesc("")
      toast.success(`Created batch "${created.name}"`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to create batch")),
  })

  const removeBatch = useMutation({
    mutationFn: deleteBatchApi,
    onSuccess: () => {
      invalidateAll()
      toast.info("Batch removed")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to delete batch")),
  })

  const setLetterBatch = useMutation({
    mutationFn: ({ id, batchId }: { id: string; batchId: string | null }) =>
      updateLetterApi({ id, batch_id: batchId }),
    onSuccess: () => {
      invalidateAll()
      toast.success("Batch updated")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to update batch")),
  })

  const ignoreDraft = useMutation({
    mutationFn: ignoreDraftLetterApi,
    onSuccess: () => {
      invalidateAll()
      setManageLetterId(null)
      toast.info("Draft ignored")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to ignore draft")),
  })

  const generatePdf = useMutation({
    mutationFn: generateLetterPdfApi,
    onSuccess: () => {
      invalidateAll()
      toast.success("PDF generated")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to generate PDF")),
  })

  const publish = useMutation({
    mutationFn: publishLetterApi,
    onSuccess: () => {
      invalidateAll()
      toast.success("Letter published")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to publish letter")),
  })

  const markPaid = useMutation({
    mutationFn: markPaidApi,
    onSuccess: () => {
      invalidateAll()
      toast.success("Marked paid — analytics updated")
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to mark paid")),
  })

  const ignoreCohort = useMutation({
    mutationFn: (cohortId: string) => ignorePaymentCohortApi({ cohortId }),
    onSuccess: (updated) => {
      invalidateAll()
      toast.info(`${updated.name} moved to Settled`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Failed to ignore cohort")),
  })

  const handleBulkPreview = async (file: File) => {
    setImportFile(file)
    try {
      setImportPreview(await bulkImportPreviewApi(file))
    } catch (e: any) {
      toast.error(getErrorMessage(e, "Could not preview Excel file"))
    }
  }

  const confirmBulkImport = useMutation({
    mutationFn: () => bulkImportConfirmApi(importFile!, importBatch || undefined),
    onSuccess: (res) => {
      invalidateAll()
      setBulkImportOpen(false)
      setImportFile(null)
      setImportPreview(null)
      setImportBatch("")
      setOpenLetterStages((prev) => ({ ...prev, draft: true }))
      toast.success(`Imported ${res.created_letters} draft letter(s)`)
    },
    onError: (e: any) => toast.error(getErrorMessage(e, "Bulk import failed")),
  })

  // Derived data & filtering
  const roleNames = useMemo(() => deliveryRoles.map((r) => r.name), [deliveryRoles])
  const batchById = useMemo(() => new Map(batches.map((b) => [b.id, b])), [batches])
  const letterTotal = (l: PaymentLetter) =>
    l.sessions.reduce((s, x) => s + (x.compensation_aed || 0), 0) +
    l.addons.reduce((s, x) => s + (x.amount_aed || 0), 0)

  const q = search.trim().toLowerCase()

  const matchesCohort = (c: CompletedCohortPayment) => {
    if (!q) return true
    if (
      c.name.toLowerCase().includes(q) ||
      c.program_name.toLowerCase().includes(q) ||
      (c.location ?? "").toLowerCase().includes(q)
    ) {
      return true
    }
    return c.instructors.some(
      (i) => i.full_name.toLowerCase().includes(q) || i.role_name.toLowerCase().includes(q),
    )
  }

  const matchesLetter = (l: PaymentLetter) => {
    if (batchFilter === "none" && l.batch_id) return false
    if (batchFilter !== "all" && batchFilter !== "none" && l.batch_id !== batchFilter) return false
    if (!q) return true
    if (
      (l.instructor_name ?? "").toLowerCase().includes(q) ||
      l.reference.toLowerCase().includes(q)
    ) {
      return true
    }
    return l.sessions.some(
      (s) =>
        s.workshop_description.toLowerCase().includes(q) ||
        (s.location ?? "").toLowerCase().includes(q),
    )
  }

  const pendingCohorts = useMemo(
    () => cohorts.filter((c) => c.status === "pending" && matchesCohort(c)),
    [cohorts, q],
  )
  const settledCohorts = useMemo(
    () => cohorts.filter((c) => c.status === "settled" && matchesCohort(c)),
    [cohorts, q],
  )

  const draftLetters = useMemo(
    () => letters.filter((l) => l.status === "draft" && matchesLetter(l)),
    [letters, batchFilter, q],
  )
  const publishedLetters = useMemo(
    () => letters.filter((l) => l.status === "published" && matchesLetter(l)),
    [letters, batchFilter, q],
  )
  const signedLetters = useMemo(
    () => letters.filter((l) => l.status === "signed" && matchesLetter(l)),
    [letters, batchFilter, q],
  )
  const paidLetters = useMemo(
    () => letters.filter((l) => l.status === "paid" && matchesLetter(l)),
    [letters, batchFilter, q],
  )

  if (loadingLetters || loadingCohorts) return <Spinner />

  const reviewCohort = cohorts.find((c) => c.cohort_id === reviewCohortId) ?? null
  const settledCohort = cohorts.find((c) => c.cohort_id === settledCohortId) ?? null
  const manageLetter = letters.find((l) => l.id === manageLetterId) ?? null

  const paidTiles = [
    {
      label: "Total Paid",
      value: `AED ${(analytics?.total_paid_aed ?? 0).toLocaleString()}`,
      icon: Wallet,
    },
    {
      label: "Paid Letters",
      value: analytics?.paid_letters_count ?? 0,
      icon: FileCheck2,
    },
    {
      label: "Paid Sessions",
      value: analytics?.paid_sessions_count ?? 0,
      icon: CalendarCheck,
    },
    {
      label: "Paid Hours",
      value: analytics?.paid_hours_count ?? 0,
      icon: Clock,
    },
  ]

  const letterGroups: {
    status: PaymentLetterStatus
    title: string
    items: PaymentLetter[]
    badgeVariant: PaymentBadgeVariant
  }[] = [
    { status: "draft", title: "Pending Drafts", items: draftLetters, badgeVariant: "draft" },
    { status: "published", title: "Published", items: publishedLetters, badgeVariant: "published" },
    { status: "signed", title: "Signed", items: signedLetters, badgeVariant: "signed" },
    { status: "paid", title: "Paid", items: paidLetters, badgeVariant: "paid" },
  ]

  return (
    <div className="max-w-[1440px] mx-auto flex flex-col gap-6 pb-16">
      <PageHeader title="Payments" />

      {/* Top Executive Row: Paid-Only KPIs + Paid-Only Monthly Bar Chart */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 items-stretch">
        <div className="xl:col-span-6 grid grid-cols-2 gap-3">
          {paidTiles.map((t) => {
            const Icon = t.icon
            return (
              <div
                key={t.label}
                className="sp-subcard rounded-[10px] bg-card p-4 flex items-center justify-between gap-3"
              >
                <div>
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    {t.label}
                  </p>
                  <p className="mt-1 font-display text-2xl font-extrabold text-foreground tabular-nums">
                    {t.value}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-[10px] bg-emerald-600/12 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300 flex items-center justify-center shrink-0">
                  <Icon size={18} />
                </div>
              </div>
            )
          })}
        </div>

        <div className="xl:col-span-6 sp-subcard rounded-[10px] bg-card p-4 flex flex-col justify-between">
          <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
            <span className="text-xs font-extrabold uppercase tracking-wider text-muted-foreground">
              Monthly Paid Payouts (AED)
            </span>
            <PaymentStatusBadge
              variant="paid"
              label={`${analytics?.paid_instructors_count ?? 0} Paid Instructors`}
            />
          </div>

          {(analytics?.monthly_paid ?? []).length === 0 ? (
            <div className="h-[142px] flex items-center justify-center text-xs font-medium text-muted-foreground">
              No paid letters recorded yet
            </div>
          ) : (
            <div className="h-[142px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={analytics!.monthly_paid}
                  margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="currentColor"
                    className="opacity-15"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="month_label"
                    tick={{ fontSize: 11, fill: "currentColor" }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "currentColor" }}
                    axisLine={false}
                    tickLine={false}
                    width={48}
                  />
                  <Tooltip
                    cursor={{ fill: "rgba(101, 63, 132, 0.08)" }}
                    contentStyle={{
                      borderRadius: "10px",
                      border: "1px solid hsl(var(--border))",
                      backgroundColor: "hsl(var(--popover))",
                      color: "hsl(var(--popover-foreground))",
                      fontSize: "12px",
                    }}
                    formatter={(val) => [`AED ${Number(val ?? 0).toLocaleString()}`, "Paid"]}
                  />
                  <Bar dataKey="amount_aed" fill="#653F84" radius={[6, 6, 0, 0]} maxBarSize={44} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* Unified Filter & Action Toolbar */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-3">
        <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 flex-1 min-w-0 flex-wrap">
          <div className="relative flex-1 min-w-[220px]">
            <Search
              size={15}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none"
            />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search cohort, instructor, venue, or reference..."
              className="w-full h-10 pl-10 pr-8 rounded-[10px] text-sm font-medium text-foreground focus:outline-none"
            />
            {search && (
              <button
                type="button"
                onClick={() => setSearch("")}
                aria-label="Clear search"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                <X size={14} />
              </button>
            )}
          </div>

          <select
            value={batchFilter}
            onChange={(e) => setBatchFilter(e.target.value)}
            className="h-10 px-3 sm:w-44 rounded-[10px] text-sm font-medium text-foreground cursor-pointer"
          >
            <option value="all" className="bg-popover text-popover-foreground">
              All batches
            </option>
            <option value="none" className="bg-popover text-popover-foreground">
              No batch
            </option>
            {batches.map((b) => (
              <option key={b.id} value={b.id} className="bg-popover text-popover-foreground">
                {b.name} ({b.letter_count})
              </option>
            ))}
          </select>

          <select
            value={analysisUserId}
            onChange={(e) => {
              const uid = e.target.value
              if (uid) {
                setProfileUserId(uid)
              }
              setAnalysisUserId("")
            }}
            className="h-10 px-3 sm:w-56 rounded-[10px] text-sm font-medium text-foreground cursor-pointer"
            aria-label="Instructor analysis"
          >
            <option value="" className="bg-popover text-popover-foreground">
              Instructor analysis...
            </option>
            {instructorOptions.map((inst) => (
              <option key={inst.id} value={inst.id} className="bg-popover text-popover-foreground">
                {inst.full_name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 flex-wrap shrink-0">
          <Button
            variant="outline"
            size="lg"
            onClick={() => {
              setAssignBatchLetterId(null)
              setBatchesOpen(true)
            }}
            className="h-10 px-3.5 rounded-[10px] border-border text-xs font-semibold"
          >
            <FolderPlus size={15} className="mr-1.5" /> Batches ({batches.length})
          </Button>
          <Button
            variant="outline"
            size="lg"
            onClick={() => setBulkImportOpen(true)}
            className="h-10 px-3.5 rounded-[10px] border-border text-xs font-semibold"
          >
            <FileSpreadsheet size={15} className="mr-1.5" /> Bulk Import
          </Button>
          <Button
            size="lg"
            onClick={() => setNewLetterOpen(true)}
            className="h-10 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
          >
            <Plus size={15} className="mr-1.5" /> New Letter
          </Button>
        </div>
      </div>

      {/* Side-by-Side Pipeline: Left Completed Cohorts | Right Payment Letters */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        {/* LEFT COLUMN: Completed Cohorts */}
        <div className="xl:col-span-5 space-y-4">
          <h2 className="text-base font-extrabold tracking-tight text-foreground px-1">
            Completed Cohorts
          </h2>

          {/* Pending Review Collapsible */}
          <div className="sp-subcard rounded-[10px] bg-card overflow-hidden">
            <button
              type="button"
              onClick={() => setOpenCohortPending((v) => !v)}
              className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-muted/40 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2.5 flex-wrap">
                {openCohortPending ? (
                  <ChevronDown size={17} className="text-muted-foreground shrink-0" />
                ) : (
                  <ChevronRight size={17} className="text-muted-foreground shrink-0" />
                )}
                <span className="text-sm font-extrabold text-foreground">Pending Review</span>
                <PaymentStatusBadge variant="pending" label={String(pendingCohorts.length)} />
              </div>
            </button>

            {openCohortPending && (
              <div className="border-t border-border divide-y divide-border">
                {pendingCohorts.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    No completed cohorts awaiting review
                  </div>
                ) : (
                  pendingCohorts.map((cohort) => {
                    const pendingRows = cohort.instructors.filter((i) => i.outcome === "pending")
                    const expectedTotal = pendingRows.reduce((s, i) => s + (i.total_aed || 0), 0)
                    const missingRateCount = pendingRows.filter(
                      (i) => (i.rate_aed ?? 0) <= 0 && i.total_aed <= 0,
                    ).length

                    return (
                      <div key={cohort.cohort_id} className="p-4 space-y-3">
                        <div className="flex items-start justify-between gap-2">
                          <div className="space-y-1">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h3 className="text-sm font-extrabold text-foreground">
                                {cohort.name}
                              </h3>
                              {missingRateCount > 0 && (
                                <PaymentStatusBadge
                                  variant="missing_rate"
                                  label={`${missingRateCount} rate needed`}
                                />
                              )}
                            </div>
                            <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
                              <span className="inline-flex items-center gap-1">
                                <Layers size={12} /> {cohort.program_name}
                              </span>
                              {cohort.date_range && (
                                <span className="inline-flex items-center gap-1">
                                  <Calendar size={12} /> {cohort.date_range}
                                </span>
                              )}
                              {cohort.location && (
                                <span className="inline-flex items-center gap-1">
                                  <MapPin size={12} /> {cohort.location}
                                </span>
                              )}
                            </div>
                          </div>
                          <span className="text-sm font-extrabold text-foreground tabular-nums shrink-0">
                            AED {expectedTotal.toLocaleString()}
                          </span>
                        </div>

                        {/* Instructor chips */}
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {pendingRows.map((inst) => (
                            <span
                              key={inst.instructor_user_id}
                              className="inline-flex items-center gap-1.5 rounded-[10px] border border-border px-2.5 py-1 text-[11px] font-semibold text-foreground"
                            >
                              <span>{inst.full_name}</span>
                              <span
                                className={cn(
                                  "font-bold",
                                  inst.has_active_draft
                                    ? "text-[#653F84] dark:text-purple-300"
                                    : "text-muted-foreground",
                                )}
                              >
                                {inst.has_active_draft ? "Appends" : "New"}
                              </span>
                            </span>
                          ))}
                        </div>

                        <div className="flex items-center justify-between gap-2 pt-1 flex-wrap">
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Users size={13} /> {pendingRows.length} instructor
                            {pendingRows.length === 1 ? "" : "s"}
                          </span>
                          <div className="flex items-center gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              disabled={ignoreCohort.isPending}
                              onClick={() => ignoreCohort.mutate(cohort.cohort_id)}
                              className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                            >
                              <Ban size={13} className="mr-1" /> Ignore
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => setReviewCohortId(cohort.cohort_id)}
                              className="h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
                            >
                              <Eye size={13} className="mr-1" /> Review &amp; Bill
                            </Button>
                          </div>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>

          {/* Settled Cohorts Collapsible */}
          <div className="sp-subcard rounded-[10px] bg-card overflow-hidden">
            <button
              type="button"
              onClick={() => setOpenCohortSettled((v) => !v)}
              className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-muted/40 transition-colors cursor-pointer"
            >
              <div className="flex items-center gap-2.5 flex-wrap">
                {openCohortSettled ? (
                  <ChevronDown size={17} className="text-muted-foreground shrink-0" />
                ) : (
                  <ChevronRight size={17} className="text-muted-foreground shrink-0" />
                )}
                <span className="text-sm font-extrabold text-foreground">Settled Cohorts</span>
                <PaymentStatusBadge variant="settled" label={String(settledCohorts.length)} />
              </div>
            </button>

            {openCohortSettled && (
              <div className="border-t border-border divide-y divide-border">
                {settledCohorts.length === 0 ? (
                  <div className="p-6 text-center text-sm text-muted-foreground">
                    No settled cohorts yet
                  </div>
                ) : (
                  settledCohorts.map((c) => {
                    const added = c.instructors.filter((i) => i.outcome === "added").length
                    const ignored = c.instructors.filter((i) => i.outcome === "ignored").length
                    const billedAed = c.instructors
                      .filter((i) => i.outcome === "added")
                      .reduce((s, i) => s + (i.total_aed || 0), 0)

                    return (
                      <div
                        key={c.cohort_id}
                        onClick={() => setSettledCohortId(c.cohort_id)}
                        className="p-3.5 flex items-center justify-between gap-3 hover:bg-muted/30 transition-colors cursor-pointer"
                      >
                        <div className="space-y-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-bold text-foreground">{c.name}</span>
                            <PaymentStatusBadge
                              variant={c.settled_outcome ?? "settled"}
                              label={
                                c.settled_outcome === "ignored"
                                  ? "Ignored"
                                  : c.settled_outcome === "partial"
                                    ? `${added} Added / ${ignored} Ignored`
                                    : `${added} Added`
                              }
                            />
                          </div>
                          <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
                            {c.date_range && <span>{c.date_range}</span>}
                            {c.location && <span>{c.location}</span>}
                          </div>
                        </div>

                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-xs font-extrabold tabular-nums">
                            AED {billedAed.toLocaleString()}
                          </span>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation()
                              setSettledCohortId(c.cohort_id)
                            }}
                            className="h-8 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                          >
                            Details
                          </Button>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Payment Letters (4 Vertical Collapsibles) */}
        <div className="xl:col-span-7 space-y-4">
          <h2 className="text-base font-extrabold tracking-tight text-foreground px-1">
            Payment Letters
          </h2>

          {letterGroups.map((group) => {
            const isOpen = openLetterStages[group.status]
            const groupTotal = group.items.reduce((s, l) => s + letterTotal(l), 0)

            return (
              <div key={group.status} className="sp-subcard rounded-[10px] bg-card overflow-hidden">
                <button
                  type="button"
                  onClick={() =>
                    setOpenLetterStages((prev) => ({
                      ...prev,
                      [group.status]: !prev[group.status],
                    }))
                  }
                  className="w-full flex items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-muted/40 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-2.5 flex-wrap">
                    {isOpen ? (
                      <ChevronDown size={17} className="text-muted-foreground shrink-0" />
                    ) : (
                      <ChevronRight size={17} className="text-muted-foreground shrink-0" />
                    )}
                    <span className="text-sm font-extrabold text-foreground">{group.title}</span>
                    <PaymentStatusBadge
                      variant={group.badgeVariant}
                      label={String(group.items.length)}
                    />
                    <span className="text-xs font-bold text-muted-foreground tabular-nums">
                      AED {groupTotal.toLocaleString()}
                    </span>
                  </div>
                </button>

                {isOpen && (
                  <div className="border-t border-border divide-y divide-border">
                    {group.items.length === 0 ? (
                      <div className="p-6 text-center text-sm text-muted-foreground">
                        No {group.title.toLowerCase()}
                      </div>
                    ) : (
                      group.items.map((l) => {
                        const total = letterTotal(l)
                        const isTouched = touchedLetterIds.has(l.id)
                        const locked = l.status === "signed" || l.status === "paid"
                        const pdfHref = l.status === "signed" || l.status === "paid"
                          ? l.signed_pdf_url ?? l.pdf_url
                          : l.pdf_url
                        const batchObj = l.batch_id ? batchById.get(l.batch_id) : undefined

                        return (
                          <div
                            key={l.id}
                            className={cn(
                              "p-4 space-y-3 transition-colors",
                              isTouched && "ring-2 ring-inset ring-[#653F84]",
                            )}
                          >
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                              <div className="flex items-center gap-2 flex-wrap">
                                <button
                                  type="button"
                                  onClick={() => setManageLetterId(l.id)}
                                  className="text-sm font-extrabold text-foreground hover:text-primary transition-colors cursor-pointer text-left"
                                >
                                  {l.instructor_name ?? "Instructor"}
                                </button>
                                <PaymentStatusBadge
                                  variant={l.status}
                                  label={l.status}
                                />
                                <span className="text-xs font-mono text-muted-foreground">
                                  {l.reference}
                                </span>
                                {l.instructor_user_id && (
                                  <button
                                    type="button"
                                    onClick={() => setProfileUserId(l.instructor_user_id!)}
                                    className="inline-flex items-center gap-1 rounded-[10px] border border-border px-2 py-0.5 text-[11px] font-semibold text-muted-foreground hover:text-primary hover:border-primary transition-colors cursor-pointer"
                                  >
                                    <UserCheck size={11} /> Profile
                                  </button>
                                )}
                              </div>

                              <div className="flex items-center gap-2.5 flex-wrap">
                                <select
                                  aria-label={`Batch for ${l.instructor_name ?? l.reference}`}
                                  value={l.batch_id ?? ""}
                                  disabled={locked || setLetterBatch.isPending}
                                  onChange={(e) => {
                                    const val = e.target.value
                                    if (val === "__new__") {
                                      setAssignBatchLetterId(l.id)
                                      setBatchesOpen(true)
                                      return
                                    }
                                    setLetterBatch.mutate({ id: l.id, batchId: val || null })
                                  }}
                                  className="h-8 px-2.5 rounded-[10px] text-xs font-semibold text-foreground cursor-pointer min-w-[126px]"
                                >
                                  <option value="" className="bg-popover text-popover-foreground">
                                    {batchObj ? "No batch" : "No batch"}
                                  </option>
                                  {batches.map((b) => (
                                    <option
                                      key={b.id}
                                      value={b.id}
                                      className="bg-popover text-popover-foreground"
                                    >
                                      {b.name}
                                    </option>
                                  ))}
                                  <option
                                    value="__new__"
                                    className="bg-popover text-popover-foreground font-semibold"
                                  >
                                    + New batch...
                                  </option>
                                </select>

                                <span className="text-sm font-extrabold text-foreground tabular-nums">
                                  AED {total.toLocaleString()}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                {l.sessions.length === 0 ? (
                                  <span className="text-xs text-muted-foreground">
                                    No entries yet
                                  </span>
                                ) : (
                                  l.sessions.map((s) => (
                                    <span
                                      key={s.id}
                                      className="rounded-[10px] border border-border px-2 py-0.5 text-[11px] font-medium text-foreground"
                                    >
                                      {s.workshop_description || s.role}
                                    </span>
                                  ))
                                )}
                                {l.addons.length > 0 && (
                                  <span className="text-xs text-muted-foreground">
                                    +{l.addons.length} add-on{l.addons.length === 1 ? "" : "s"}
                                  </span>
                                )}
                                {l.paid_at && (
                                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                                    Paid {new Date(l.paid_at).toLocaleDateString()}
                                  </span>
                                )}
                              </div>

                              <div className="flex items-center gap-2 flex-wrap">
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setManageLetterId(l.id)}
                                  className="h-8 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                                >
                                  <Pencil size={13} className="mr-1" /> Edit
                                </Button>

                                {!l.pdf_url && l.status === "draft" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={generatePdf.isPending}
                                    onClick={() => generatePdf.mutate(l.id)}
                                    className="h-8 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                                  >
                                    <FileText size={13} className="mr-1" /> Generate PDF
                                  </Button>
                                )}

                                {pdfHref && (
                                  <a href={pdfHref} target="_blank" rel="noreferrer">
                                    <Button
                                      variant="outline"
                                      size="sm"
                                      className="h-8 px-2.5 rounded-[10px] border-border text-xs font-semibold"
                                    >
                                      <Download size={13} className="mr-1" />
                                      {l.status === "signed" || l.status === "paid" ? "Signed PDF" : "Draft PDF"}
                                    </Button>
                                  </a>
                                )}

                                {l.pdf_url && l.status === "draft" && (
                                  <Button
                                    size="sm"
                                    disabled={publish.isPending}
                                    onClick={() => publish.mutate(l.id)}
                                    className="h-8 px-3 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
                                  >
                                    <Send size={13} className="mr-1" /> Publish
                                  </Button>
                                )}

                                {l.status === "signed" && (
                                  <Button
                                    size="sm"
                                    disabled={markPaid.isPending}
                                    onClick={() => markPaid.mutate(l.id)}
                                    className="h-8 px-3 rounded-[10px] bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold"
                                  >
                                    <Check size={13} className="mr-1" /> Mark Paid
                                  </Button>
                                )}

                                {l.status === "draft" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    disabled={ignoreDraft.isPending}
                                    onClick={() => ignoreDraft.mutate(l.id)}
                                    className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600 text-xs font-semibold"
                                  >
                                    <Ban size={13} className="mr-1" /> Ignore
                                  </Button>
                                )}
                              </div>
                            </div>
                          </div>
                        )
                      })
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Modals */}
      <CohortReviewModal
        cohort={reviewCohort}
        batches={batches}
        deliveryRoles={roleNames}
        onClose={() => setReviewCohortId(null)}
        onOpenProfile={(uid) => {
          setReviewCohortId(null)
          setProfileUserId(uid)
        }}
        onSettled={(res) => {
          setOpenLetterStages((prev) => ({ ...prev, draft: true }))
          highlightLetters(res.touched_letter_ids)
        }}
      />

      <SettledCohortModal
        cohort={settledCohort}
        onClose={() => setSettledCohortId(null)}
        onOpenProfile={(uid) => setProfileUserId(uid)}
        onOpenLetter={(lid) => {
          const target = letters.find((x) => x.id === lid)
          if (target) {
            setOpenLetterStages((prev) => ({ ...prev, [target.status]: true }))
          }
          setManageLetterId(lid)
        }}
        onRestored={() => setOpenCohortPending(true)}
      />

      <Dialog open={!!manageLetter} onOpenChange={(open) => !open && setManageLetterId(null)}>
        <DialogContent className="max-w-[95vw] sm:max-w-5xl max-h-[90vh] overflow-y-auto rounded-[10px] p-5 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-lg font-extrabold">
              {manageLetter?.instructor_name} — {manageLetter?.reference}
            </DialogTitle>
          </DialogHeader>
          {manageLetter && (
            <PaymentLetterTable
              letter={manageLetter}
              onIgnoreDraft={() => ignoreDraft.mutate(manageLetter.id)}
            />
          )}
        </DialogContent>
      </Dialog>

      <Dialog
        open={batchesOpen}
        onOpenChange={(open) => {
          if (!open) {
            setBatchesOpen(false)
            setAssignBatchLetterId(null)
          }
        }}
      >
        <DialogContent className="max-w-[95vw] sm:max-w-xl rounded-[10px] p-5 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-lg font-extrabold">Payment Batches</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
              <input
                value={newBatchName}
                onChange={(e) => setNewBatchName(e.target.value)}
                placeholder="Batch name (e.g. Nov 2026)"
                className="h-9 px-3 rounded-[10px] text-sm"
              />
              <input
                value={newBatchDesc}
                onChange={(e) => setNewBatchDesc(e.target.value)}
                placeholder="Description (optional)"
                className="h-9 px-3 rounded-[10px] text-sm"
              />
              <Button
                size="lg"
                disabled={!newBatchName.trim() || createBatch.isPending}
                onClick={() => createBatch.mutate()}
                className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
              >
                <Plus size={14} className="mr-1" /> Create
              </Button>
            </div>

            <div className="divide-y divide-border border-t border-border max-h-72 overflow-y-auto">
              {batches.length === 0 ? (
                <p className="py-6 text-center text-xs text-muted-foreground">No batches yet</p>
              ) : (
                batches.map((b) => (
                  <div key={b.id} className="py-3 flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-bold text-foreground">{b.name}</p>
                      <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                        <span>{b.letter_count} letter{b.letter_count === 1 ? "" : "s"}</span>
                        {b.description && <span>{b.description}</span>}
                      </div>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={removeBatch.isPending}
                      onClick={() => removeBatch.mutate(b.id)}
                      className="h-8 px-2.5 rounded-[10px] border-rose-600/35 text-rose-600"
                    >
                      <Trash2 size={13} />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={newLetterOpen} onOpenChange={setNewLetterOpen}>
        <DialogContent className="max-w-[95vw] sm:max-w-md rounded-[10px] p-5 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-lg font-extrabold">New Payment Letter</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">
                Instructor
              </label>
              <select
                value={selectedInstructor}
                onChange={(e) => setSelectedInstructor(e.target.value)}
                className="w-full h-10 px-3 rounded-[10px] text-sm font-medium"
              >
                <option value="" className="bg-popover text-popover-foreground">
                  Select instructor...
                </option>
                {instructorOptions.map((o) => (
                  <option key={o.id} value={o.id} className="bg-popover text-popover-foreground">
                    {o.full_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground block mb-1.5">
                Batch
              </label>
              <select
                value={selectedBatch}
                onChange={(e) => setSelectedBatch(e.target.value)}
                className="w-full h-10 px-3 rounded-[10px] text-sm font-medium"
              >
                <option value="" className="bg-popover text-popover-foreground">
                  No batch
                </option>
                {batches.map((b) => (
                  <option key={b.id} value={b.id} className="bg-popover text-popover-foreground">
                    {b.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                variant="outline"
                size="lg"
                onClick={() => setNewLetterOpen(false)}
                className="h-9 px-3.5 rounded-[10px] border-border text-xs font-semibold"
              >
                Cancel
              </Button>
              <Button
                size="lg"
                disabled={!selectedInstructor || createLetter.isPending}
                onClick={() => createLetter.mutate()}
                className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
              >
                {createLetter.isPending ? "Creating..." : "Create Letter"}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={bulkImportOpen} onOpenChange={setBulkImportOpen}>
        <DialogContent className="max-w-[95vw] sm:max-w-lg rounded-[10px] p-5 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-lg font-extrabold">Excel Bulk Import</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <Button
                variant="outline"
                size="lg"
                onClick={() => downloadBulkImportTemplateApi()}
                className="h-9 px-3.5 rounded-[10px] border-border text-xs font-semibold"
              >
                <Download size={14} className="mr-1.5" /> Download Template
              </Button>
              <input
                ref={importInputRef}
                type="file"
                accept=".xlsx"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) void handleBulkPreview(f)
                }}
              />
              <Button
                variant="outline"
                size="lg"
                onClick={() => importInputRef.current?.click()}
                className="h-9 px-3.5 rounded-[10px] border-border text-xs font-semibold"
              >
                <Upload size={14} className="mr-1.5" /> Select .xlsx File
              </Button>
            </div>

            {importPreview && (
              <div className="rounded-[10px] border border-border p-3.5 space-y-3 text-xs">
                <div className="flex items-center gap-4 flex-wrap font-semibold text-foreground">
                  <span>{importPreview.instructor_count} instructors</span>
                  <span>{importPreview.session_count} sessions</span>
                  <span>{importPreview.addon_count} add-ons</span>
                </div>
                {importPreview.unmatched_emails.length > 0 && (
                  <p className="text-rose-600 font-semibold">
                    Unmatched emails: {importPreview.unmatched_emails.join(", ")}
                  </p>
                )}
                {importPreview.errors.length > 0 && (
                  <p className="text-rose-600 font-semibold">
                    {importPreview.errors.join("; ")}
                  </p>
                )}
                <div>
                  <label className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">
                    Target Batch
                  </label>
                  <select
                    value={importBatch}
                    onChange={(e) => setImportBatch(e.target.value)}
                    className="w-full h-9 px-3 rounded-[10px] text-xs font-medium"
                  >
                    <option value="" className="bg-popover text-popover-foreground">
                      No batch
                    </option>
                    {batches.map((b) => (
                      <option key={b.id} value={b.id} className="bg-popover text-popover-foreground">
                        {b.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button
                variant="outline"
                size="lg"
                onClick={() => setBulkImportOpen(false)}
                className="h-9 px-3.5 rounded-[10px] border-border text-xs font-semibold"
              >
                Close
              </Button>
              {importPreview && importFile && (
                <Button
                  size="lg"
                  disabled={confirmBulkImport.isPending}
                  onClick={() => confirmBulkImport.mutate()}
                  className="h-9 px-4 rounded-[10px] bg-primary text-primary-foreground text-xs font-bold"
                >
                  {confirmBulkImport.isPending ? "Importing..." : "Confirm Import"}
                </Button>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {profileUserId && (
        <UserProfileModal
          userId={profileUserId}
          onClose={() => setProfileUserId(null)}
          onOpenLetter={(lid) => {
            const target = letters.find((x) => x.id === lid)
            if (target) {
              setOpenLetterStages((prev) => ({ ...prev, [target.status]: true }))
            }
            setManageLetterId(lid)
          }}
        />
      )}
    </div>
  )
}
