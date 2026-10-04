import { useState, useMemo, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Search,
  RotateCcw,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Cpu,
  Sparkles,
  Save,
  Check,
  Ban,
  Radio,
  Zap,
  Box,
  Thermometer,
  Sliders,
} from "lucide-react"
import { EmptyState, Spinner } from "@/components/ui/primitives"
import { useToast } from "@/components/ui/toast"
import {
  getCohortComponentsApi,
  getProgramComponentsApi,
  resetCohortComponentsApi,
  resetProgramComponentsApi,
  updateCohortComponentsApi,
  updateProgramComponentsApi,
  type ComponentConfigOut,
  type ComponentItemSummary,
} from "@/api/lmsComponentConfig"
import {
  listAdminCustomComponents,
  type AdminCustomComponent,
} from "@/api/missionsLibrary"

interface LmsComponentConfigPanelProps {
  ownerType: "program" | "cohort"
  ownerId: string
  isStaff: boolean
}

const SUBSYSTEM_ICONS: Record<string, typeof Cpu> = {
  ADCS: Sliders,
  CDHS: Cpu,
  COMMS: Radio,
  EPS: Zap,
  Payload: Sparkles,
  Structure: Box,
  Thermal: Thermometer,
}

export function LmsComponentConfigPanel({
  ownerType,
  ownerId,
  isStaff,
}: LmsComponentConfigPanelProps) {
  const queryClient = useQueryClient()
  const toast = useToast()

  const queryKey = ["lms-component-config", ownerType, ownerId]
  const isInstructor = !isStaff

  const {
    data: config,
    isLoading,
    isError,
    error,
  } = useQuery<ComponentConfigOut>({
    queryKey,
    queryFn: () =>
      ownerType === "program"
        ? getProgramComponentsApi(ownerId)
        : getCohortComponentsApi(ownerId, isInstructor),
  })

  // Local draft state
  const [disabledSubsystems, setDisabledSubsystems] = useState<Set<string>>(new Set())
  const [disabledTags, setDisabledTags] = useState<Set<string>>(new Set())
  const [disabledComponentIds, setDisabledComponentIds] = useState<Set<string>>(new Set())

  // UI view state
  const [searchQuery, setSearchQuery] = useState("")
  const [collapsedSubsystems, setCollapsedSubsystems] = useState<Set<string>>(new Set())
  // System catalog vs student-built custom components in this cohort/program.
  const [componentView, setComponentView] = useState<"system" | "custom">("system")

  const { data: cohortCustoms = [], isLoading: customsLoading } = useQuery<AdminCustomComponent[]>({
    queryKey: ["lms-component-config-customs", ownerType, ownerId],
    queryFn: () =>
      ownerType === "cohort"
        ? listAdminCustomComponents({ cohort_id: ownerId })
        : listAdminCustomComponents(),
  })

  const filteredCustoms = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return cohortCustoms
    return cohortCustoms.filter(
      (c) =>
        c.component_name.toLowerCase().includes(q) ||
        c.subsystem.toLowerCase().includes(q) ||
        (c.student_name && c.student_name.toLowerCase().includes(q)) ||
        (c.student_email && c.student_email.toLowerCase().includes(q)) ||
        (c.team_name && c.team_name.toLowerCase().includes(q)) ||
        (c.mission_title && c.mission_title.toLowerCase().includes(q)) ||
        (c.cohort_name && c.cohort_name.toLowerCase().includes(q)) ||
        (c.program_name && c.program_name.toLowerCase().includes(q))
    )
  }, [cohortCustoms, searchQuery])

  // Sync draft once per owner — never on background refetch, otherwise an
  // unsaved toggle (e.g. block customs) gets silently wiped back to Allowed.
  const configKey = `${ownerType}:${ownerId}`
  const syncedKeyRef = useRef("")
  useEffect(() => {
    if (config && syncedKeyRef.current !== configKey) {
      syncedKeyRef.current = configKey
      setDisabledSubsystems(new Set(config.disabled_subsystems || []))
      setDisabledTags(new Set(config.disabled_tags || []))
      setDisabledComponentIds(new Set(config.disabled_component_ids || []))
    }
  }, [config, configKey])
  const applyServerConfig = (next: ComponentConfigOut) => {
    queryClient.setQueryData(queryKey, next)
    setDisabledSubsystems(new Set(next.disabled_subsystems || []))
    setDisabledTags(new Set(next.disabled_tags || []))
    setDisabledComponentIds(new Set(next.disabled_component_ids || []))
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const payload = {
        disabled_subsystems: Array.from(disabledSubsystems),
        disabled_tags: Array.from(disabledTags),
        disabled_component_ids: Array.from(disabledComponentIds),
      }
      return ownerType === "program"
        ? updateProgramComponentsApi(ownerId, payload)
        : updateCohortComponentsApi(ownerId, payload, isInstructor)
    },
    onSuccess: (updated) => {
      applyServerConfig(updated)
      toast.success(
        ownerType === "program"
          ? "Program component defaults saved."
          : "Cohort component overrides saved."
      )
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to save component configuration.")
    },
  })

  // Immediate save for the allow/block toggle — it must not depend on the
  // main Save bar, otherwise a background refetch wipes it back to Allowed.
  const [customSaving, setCustomSaving] = useState(false)

  const resetMutation = useMutation({
    mutationFn: async () => {
      return ownerType === "program"
        ? resetProgramComponentsApi(ownerId)
        : resetCohortComponentsApi(ownerId, isInstructor)
    },
    onSuccess: (updated) => {
      applyServerConfig(updated)
      toast.success(
        ownerType === "program"
          ? "Reset program component defaults to enabled."
          : "Reset cohort to inherit program defaults."
      )
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.detail || "Failed to reset component configuration.")
    },
  })

  // Detect unsaved draft edits
  const hasUnsavedChanges = useMemo(() => {
    if (!config) return false

    const origSubs = new Set(config.disabled_subsystems || [])
    const origTags = new Set(config.disabled_tags || [])
    const origIds = new Set(config.disabled_component_ids || [])

    if (disabledSubsystems.size !== origSubs.size) return true
    for (const s of disabledSubsystems) if (!origSubs.has(s)) return true

    if (disabledTags.size !== origTags.size) return true
    for (const t of disabledTags) if (!origTags.has(t)) return true

    if (disabledComponentIds.size !== origIds.size) return true
    for (const id of disabledComponentIds) if (!origIds.has(id)) return true

    return false
  }, [config, disabledSubsystems, disabledTags, disabledComponentIds])

  // Group components by subsystem
  const groupedComponents = useMemo(() => {
    if (!config) return {}
    const map: Record<string, ComponentItemSummary[]> = {}

    // First ensure every available subsystem has an entry
    for (const sub of config.available_subsystems || []) {
      map[sub] = []
    }

    // Populate components matching search query
    const q = searchQuery.trim().toLowerCase()
    for (const comp of config.components || []) {
      if (
        q &&
        !comp.component_name.toLowerCase().includes(q) &&
        !comp.subsystem.toLowerCase().includes(q) &&
        !(comp.component_code && comp.component_code.toLowerCase().includes(q)) &&
        !(comp.tag && comp.tag.toLowerCase().includes(q)) &&
        !(comp.example_role && comp.example_role.toLowerCase().includes(q))
      ) {
        continue
      }

      if (!map[comp.subsystem]) {
        map[comp.subsystem] = []
      }
      map[comp.subsystem].push(comp)
    }

    return map
  }, [config, searchQuery])

  // Check whether an individual component is effectively enabled
  const isComponentEffectivelyEnabled = (comp: ComponentItemSummary) => {
    if (disabledSubsystems.has(comp.subsystem)) return false
    if (comp.tag && disabledTags.has(comp.tag)) return false
    if (disabledComponentIds.has(comp.id)) return false
    return true
  }

  // Calculate live counts
  const liveStats = useMemo(() => {
    if (!config) return { enabledCount: 0, totalCount: 0, activeSubs: 0, activeTags: 0 }
    let enabledCount = 0
    for (const c of config.components || []) {
      if (isComponentEffectivelyEnabled(c)) enabledCount++
    }
    const totalSubs = config.available_subsystems?.length || 0
    const activeSubs = totalSubs - disabledSubsystems.size
    const totalTags = config.available_tags?.length || 0
    const activeTags = totalTags - disabledTags.size

    return {
      enabledCount,
      totalCount: config.components?.length || 0,
      activeSubs,
      totalSubs,
      activeTags,
      totalTags,
    }
  }, [config, disabledSubsystems, disabledTags, disabledComponentIds])

  // Subsystem toggle handler
  const handleToggleSubsystem = (subsystem: string) => {
    setDisabledSubsystems((prev) => {
      const next = new Set(prev)
      if (next.has(subsystem)) {
        next.delete(subsystem)
      } else {
        next.add(subsystem)
      }
      return next
    })
  }

  // Tag toggle handler
  const handleToggleTag = (tag: string) => {
    setDisabledTags((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) {
        next.delete(tag)
      } else {
        next.add(tag)
      }
      return next
    })
  }

  // Single component toggle handler
  const handleToggleComponent = (comp: ComponentItemSummary) => {
    // If subsystem or tag is disabled, we can't enable this item alone without enabling the parent
    if (disabledSubsystems.has(comp.subsystem)) {
      toast.error(`Enable the ${comp.subsystem} category first to activate this component.`)
      return
    }
    if (comp.tag && disabledTags.has(comp.tag)) {
      toast.error(`Enable the ${comp.tag} kit filter first to activate this component.`)
      return
    }

    setDisabledComponentIds((prev) => {
      const next = new Set(prev)
      if (next.has(comp.id)) {
        next.delete(comp.id)
      } else {
        next.add(comp.id)
      }
      return next
    })
  }

  const handleToggleCollapse = (subsystem: string) => {
    setCollapsedSubsystems((prev) => {
      const next = new Set(prev)
      if (next.has(subsystem)) {
        next.delete(subsystem)
      } else {
        next.add(subsystem)
      }
      return next
    })
  }

  const handleEnableAll = () => {
    setDisabledSubsystems(new Set())
    setDisabledTags(new Set())
    setDisabledComponentIds(new Set())
  }

  const handleDisableAll = () => {
    if (!config) return
    setDisabledSubsystems(new Set(config.available_subsystems || []))
  }

  const handleDiscardChanges = () => {
    if (!config) return
    setDisabledSubsystems(new Set(config.disabled_subsystems || []))
    setDisabledTags(new Set(config.disabled_tags || []))
    setDisabledComponentIds(new Set(config.disabled_component_ids || []))
  }

  if (isLoading) {
    return (
      <div className="py-12 flex justify-center items-center">
        <Spinner />
      </div>
    )
  }

  if (isError || !config) {
    return (
      <EmptyState
        title="Unable to load components"
        hint={(error as any)?.message || "Check your connection and permissions."}
      />
    )
  }

  return (
    <div className="flex flex-col gap-5 w-full max-w-7xl mx-auto pb-12">
      {/* ── 1. Inheritance Status Banner ─────────────────────────────────── */}
      {ownerType === "cohort" ? (
        config.is_inherited ? (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-sky-500/30 bg-sky-500/10 text-sky-950 dark:text-sky-200">
            <div className="min-w-0">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm sm:text-base">
                    Inheriting Program Default Template
                  </span>
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-sky-500/20 text-sky-700 dark:text-sky-300">
                    Auto-Synced
                  </span>
                </div>
                <p className="text-xs sm:text-sm text-sky-800/80 dark:text-sky-300/80 mt-0.5">
                  Components below reflect the program default. Saving any toggle here will create a
                  dedicated cohort override.
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-950 dark:text-amber-200">
            <div className="min-w-0">
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-semibold text-sm sm:text-base">
                    Custom Cohort Override Active
                  </span>
                  <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-amber-500/20 text-amber-700 dark:text-amber-300">
                    Custom Rules
                  </span>
                </div>
                <p className="text-xs sm:text-sm text-amber-800/80 dark:text-amber-300/80 mt-0.5">
                  This cohort has custom component availability rules overriding the program
                  template.
                </p>
              </div>
            </div>
            <button
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}
              className="min-h-[44px] px-3.5 py-2 text-xs sm:text-sm font-medium rounded-lg border border-amber-600/30 bg-card hover:bg-accent text-foreground transition-colors flex items-center gap-2 shrink-0 cursor-pointer self-stretch sm:self-auto justify-center"
            >
              {resetMutation.isPending ? (
                <Spinner />
              ) : (
                <RotateCcw className="w-4 h-4 text-amber-600 dark:text-amber-400" />
              )}
              <span>Reset to Program Default</span>
            </button>
          </div>
        )
      ) : (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl border border-border bg-card text-foreground">
          <div className="min-w-0">
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-semibold text-sm sm:text-base">
                  Program Component Master Template
                </span>
                <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-muted text-muted-foreground">
                  Default Baseline
                </span>
              </div>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                Baseline component catalog for all cohorts under this program. Cohorts inherit this
                unless customized.
              </p>
            </div>
          </div>
          {config.has_override && (
            <button
              onClick={() => resetMutation.mutate()}
              disabled={resetMutation.isPending}
              className="min-h-[44px] px-3.5 py-2 text-xs sm:text-sm font-medium rounded-lg border border-border bg-card hover:bg-accent text-foreground transition-colors flex items-center gap-2 shrink-0 cursor-pointer self-stretch sm:self-auto justify-center"
            >
              {resetMutation.isPending ? <Spinner /> : <RotateCcw className="w-4 h-4" />}
              <span>Reset All to Enabled</span>
            </button>
          )}
        </div>
      )}

      {/* ── 1b. Custom components availability (text only, no icons) ─── */}
      {(() => {
        const customAllowed = ![...disabledTags].some((t) => t.toLowerCase() === "custom")
        const toggleCustomAllowed = async () => {
          if (customSaving || !config) return
          const next = new Set(disabledTags)
          const existing = [...next].find((t) => t.toLowerCase() === "custom")
          if (existing) {
            next.delete(existing)
          } else {
            const canonical =
              config?.available_tags?.find((t) => t.toLowerCase() === "custom") ?? "Custom"
            next.add(canonical)
          }
          const prevTags = disabledTags
          setDisabledTags(next)
          setCustomSaving(true)
          try {
            const payload = {
              disabled_subsystems: Array.from(disabledSubsystems),
              disabled_tags: Array.from(next),
              disabled_component_ids: Array.from(disabledComponentIds),
            }
            const updated =
              ownerType === "program"
                ? await updateProgramComponentsApi(ownerId, payload)
                : await updateCohortComponentsApi(ownerId, payload, isInstructor)
            applyServerConfig(updated)
            toast.success(
              existing
                ? "Custom components allowed."
                : "Custom components blocked."
            )
          } catch (err: any) {
            setDisabledTags(prevTags)
            toast.error(err?.response?.data?.detail || "Failed to save component configuration.")
          } finally {
            setCustomSaving(false)
          }
        }
        return (
          <div className="bg-card border border-border rounded-xl p-3 sm:p-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm sm:text-base font-bold text-foreground">
                Custom components {customAllowed ? "allowed" : "blocked"}
              </p>
              <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
                {ownerType === "cohort"
                  ? customAllowed
                    ? "Students in this cohort can build their own custom components inside the design mission."
                    : "Students in this cohort cannot create or add custom components — the student picker blocks them."
                  : customAllowed
                    ? "Cohorts under this program allow custom components unless a cohort overrides this."
                    : "Cohorts under this program block custom components unless a cohort overrides this."}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void toggleCustomAllowed()}
              disabled={customSaving}
              className={`min-h-[44px] min-w-[110px] px-4 py-2 rounded-xl font-medium text-xs sm:text-sm flex items-center justify-center transition-all cursor-pointer border self-stretch sm:self-auto ${
                customAllowed
                  ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25"
                  : "bg-muted border-border text-muted-foreground hover:bg-muted/80"
              } ${customSaving ? "opacity-60 cursor-wait" : ""}`}
            >
              <span>{customSaving ? "Saving…" : customAllowed ? "Allowed — tap to block" : "Blocked — tap to allow"}</span>
            </button>
          </div>
        )
      })()}

      {/* ── 1c. System vs student custom view toggle ───────────────────── */}
      <div className="flex gap-1 border-b border-border overflow-x-auto">
        {(["system", "custom"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setComponentView(t)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors cursor-pointer shrink-0 whitespace-nowrap ${
              componentView === t ? "border-primary text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}
          >
            {t === "system"
              ? "System components"
              : `Custom components (${cohortCustoms.length})`}
          </button>
        ))}
      </div>

      {componentView === "system" ? (
      <>
      {/* ── 2. Metric Counters & Sticky Action Bar ──────────────────────── */}
      <div className="bg-card border border-border rounded-xl p-3 sm:p-4 flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
        <div className="grid grid-cols-3 gap-2 sm:gap-4 divide-x divide-border">
          <div className="flex flex-col px-1 sm:px-2">
            <span className="text-[11px] sm:text-xs text-muted-foreground uppercase tracking-wider">
              Components
            </span>
            <div className="text-base sm:text-xl font-bold mt-0.5">
              <span className="text-primary">{liveStats.enabledCount}</span>
              <span className="text-muted-foreground font-normal text-xs sm:text-sm">
                {" "}
                / {liveStats.totalCount}
              </span>
            </div>
          </div>
          <div className="flex flex-col pl-3 sm:pl-4">
            <span className="text-[11px] sm:text-xs text-muted-foreground uppercase tracking-wider">
              Subsystems
            </span>
            <div className="text-base sm:text-xl font-bold mt-0.5">
              <span className="text-foreground">{liveStats.activeSubs}</span>
              <span className="text-muted-foreground font-normal text-xs sm:text-sm">
                {" "}
                / {liveStats.totalSubs}
              </span>
            </div>
          </div>
          <div className="flex flex-col pl-3 sm:pl-4">
            <span className="text-[11px] sm:text-xs text-muted-foreground uppercase tracking-wider">
              Kits / Tags
            </span>
            <div className="text-base sm:text-xl font-bold mt-0.5">
              <span className="text-foreground">{liveStats.activeTags}</span>
              <span className="text-muted-foreground font-normal text-xs sm:text-sm">
                {" "}
                / {liveStats.totalTags}
              </span>
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2 self-end md:self-auto w-full md:w-auto">
          {hasUnsavedChanges && (
            <button
              onClick={handleDiscardChanges}
              disabled={saveMutation.isPending}
              className="min-h-[44px] flex-1 md:flex-initial px-3 py-2 text-xs sm:text-sm font-medium rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground transition-colors cursor-pointer text-center"
            >
              Revert
            </button>
          )}
          <button
            onClick={() => saveMutation.mutate()}
            disabled={!hasUnsavedChanges || saveMutation.isPending}
            className={`min-h-[44px] flex-1 md:flex-initial px-4 py-2 text-xs sm:text-sm font-medium rounded-lg transition-all flex items-center justify-center gap-2 cursor-pointer ${
              hasUnsavedChanges
                ? "bg-primary text-primary-foreground shadow-md hover:bg-primary/90"
                : "bg-muted text-muted-foreground opacity-60 cursor-not-allowed"
            }`}
          >
            {saveMutation.isPending ? <Spinner /> : <Save className="w-4 h-4" />}
            <span>{hasUnsavedChanges ? "Save Changes" : "Saved"}</span>
          </button>
        </div>
      </div>

      {/* ── 3. Filters & Quick Toggles ──────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        {/* Search & Bulk buttons */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search components by title, code, role, or specs…"
              className="w-full min-h-[44px] pl-9 pr-3 text-sm bg-card border border-border rounded-xl focus:outline-none focus:border-primary transition-colors text-foreground placeholder:text-muted-foreground"
            />
          </div>

          <div className="flex items-center gap-2 self-stretch sm:self-auto">
            <button
              onClick={handleEnableAll}
              className="min-h-[44px] flex-1 sm:flex-initial px-3 py-2 text-xs font-medium rounded-lg border border-border bg-card hover:bg-accent text-foreground transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              <span>Enable All</span>
            </button>
            <button
              onClick={handleDisableAll}
              className="min-h-[44px] flex-1 sm:flex-initial px-3 py-2 text-xs font-medium rounded-lg border border-border bg-card hover:bg-accent text-foreground transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <Ban className="w-3.5 h-3.5 text-rose-500" />
              <span>Disable All</span>
            </button>
          </div>
        </div>

        {/* Hardware Kit / Tag quick filters */}
        {config.available_tags && config.available_tags.length > 0 && (
          <div className="flex items-center gap-2 flex-wrap pt-1">
            <span className="text-xs font-medium text-muted-foreground flex items-center gap-1 mr-1">
              <span>Kit Quick Toggles:</span>
            </span>
            {config.available_tags.map((tag) => {
              const isTagDisabled = disabledTags.has(tag)
              return (
                <button
                  key={tag}
                  onClick={() => handleToggleTag(tag)}
                  className={`min-h-[40px] px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 transition-colors cursor-pointer border ${
                    isTagDisabled
                      ? "bg-muted/50 border-border text-muted-foreground line-through opacity-70"
                      : "bg-primary/10 border-primary/30 text-primary hover:bg-primary/20"
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full ${
                      isTagDisabled ? "bg-muted-foreground/50" : "bg-emerald-500"
                    }`}
                  />
                  <span>{tag}</span>
                  <span className="text-[10px] uppercase font-bold opacity-80">
                    {isTagDisabled ? "Off" : "On"}
                  </span>
                </button>
              )
            })}
          </div>
        )}
      </div>

      {/* ── 4. Subsystem Categories & Component Cards ───────────────────── */}
      <div className="flex flex-col gap-4 mt-2">
        {config.available_subsystems?.map((subsystem) => {
          const isCategoryDisabled = disabledSubsystems.has(subsystem)
          const isCollapsed = collapsedSubsystems.has(subsystem)
          const items = groupedComponents[subsystem] || []
          const Icon = SUBSYSTEM_ICONS[subsystem] || Cpu

          // Calculate active items in this category
          const categoryTotal =
            config.components?.filter((c) => c.subsystem === subsystem).length || 0
          const categoryEnabled = isCategoryDisabled
            ? 0
            : config.components?.filter(
                (c) => c.subsystem === subsystem && isComponentEffectivelyEnabled(c)
              ).length || 0

          return (
            <div
              key={subsystem}
              className={`rounded-2xl border transition-all overflow-hidden ${
                isCategoryDisabled
                  ? "border-border/60 bg-muted/20 opacity-80"
                  : "border-border bg-card shadow-sm"
              }`}
            >
              {/* Category Header */}
              <div className="p-3 sm:p-4 flex items-center justify-between gap-3 bg-card/60 backdrop-blur-sm border-b border-border/60">
                <div
                  className="flex items-center gap-3 flex-1 min-w-0 cursor-pointer select-none"
                  onClick={() => handleToggleCollapse(subsystem)}
                >
                  <div
                    className={`p-2 rounded-xl shrink-0 transition-colors ${
                      isCategoryDisabled
                        ? "bg-muted text-muted-foreground"
                        : "bg-primary/10 text-primary"
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h3
                        className={`text-sm sm:text-base font-bold ${
                          isCategoryDisabled ? "text-muted-foreground line-through" : "text-foreground"
                        }`}
                      >
                        {subsystem}
                      </h3>
                      <span
                        className={`px-2 py-0.5 text-[11px] font-semibold rounded-md ${
                          isCategoryDisabled
                            ? "bg-rose-500/10 text-rose-600 dark:text-rose-400"
                            : "bg-muted text-muted-foreground"
                        }`}
                      >
                        {isCategoryDisabled
                          ? "Disabled"
                          : `${categoryEnabled}/${categoryTotal} active`}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">
                      {isCategoryDisabled
                        ? "Entire subsystem category is turned off for this cohort/program."
                        : `Manage individual component availability in ${subsystem}.`}
                    </p>
                  </div>
                </div>

                {/* Master Category Toggle & Expand Chevron */}
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handleToggleSubsystem(subsystem)
                    }}
                    title={
                      isCategoryDisabled
                        ? `Enable ${subsystem} subsystem`
                        : `Disable ${subsystem} subsystem`
                    }
                    className={`min-h-[44px] min-w-[48px] px-3 py-1.5 rounded-xl font-medium text-xs flex items-center gap-1.5 transition-all cursor-pointer border ${
                      isCategoryDisabled
                        ? "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20"
                        : "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20"
                    }`}
                  >
                    {isCategoryDisabled ? (
                      <>
                        <Ban className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Disabled</span>
                      </>
                    ) : (
                      <>
                        <Check className="w-3.5 h-3.5" />
                        <span className="hidden sm:inline">Active</span>
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => handleToggleCollapse(subsystem)}
                    className="min-h-[44px] min-w-[44px] flex items-center justify-center rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors cursor-pointer"
                  >
                    {isCollapsed ? (
                      <ChevronDown className="w-5 h-5" />
                    ) : (
                      <ChevronUp className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>

              {/* Category Body */}
              {!isCollapsed && (
                <div className="p-3 sm:p-4">
                  {isCategoryDisabled ? (
                    <div className="py-4 px-3 text-center bg-muted/40 rounded-xl border border-dashed border-border text-xs sm:text-sm text-muted-foreground">
                      The entire <strong>{subsystem}</strong> subsystem category is disabled.
                      Students in this cohort will not see these items or the {subsystem} tab in
                      their Mission Design library.
                    </div>
                  ) : items.length === 0 ? (
                    <div className="py-6 text-center text-xs sm:text-sm text-muted-foreground">
                      No components found matching &ldquo;{searchQuery}&rdquo; in {subsystem}.
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                      {items.map((comp) => {
                        const isEnabled = isComponentEffectivelyEnabled(comp)
                        const isTagBlocked = Boolean(comp.tag && disabledTags.has(comp.tag))

                        return (
                          <div
                            key={comp.id}
                            className={`flex flex-col justify-between p-3.5 rounded-xl border transition-all ${
                              isEnabled
                                ? "bg-card border-border hover:border-primary/40 shadow-xs"
                                : "bg-muted/30 border-border/50 opacity-75"
                            }`}
                          >
                            <div className="flex items-start gap-3">
                              {/* Component Thumbnail or Icon */}
                              <div className="w-12 h-12 rounded-lg bg-muted border border-border shrink-0 flex items-center justify-center overflow-hidden">
                                {comp.image_url ? (
                                  <img
                                    src={comp.image_url}
                                    alt={comp.component_name}
                                    className="w-full h-full object-cover"
                                  />
                                ) : (
                                  <Icon className="w-6 h-6 text-muted-foreground/60" />
                                )}
                              </div>

                              {/* Title & Metadata */}
                              <div className="min-w-0 flex-1">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <span
                                    className={`font-semibold text-xs sm:text-sm truncate ${
                                      isEnabled ? "text-foreground" : "text-muted-foreground line-through"
                                    }`}
                                    title={comp.component_name}
                                  >
                                    {comp.component_name}
                                  </span>
                                  {comp.component_code && (
                                    <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-muted text-muted-foreground">
                                      {comp.component_code}
                                    </span>
                                  )}
                                </div>

                                {comp.tag && (
                                  <div className="mt-1">
                                    <span
                                      className={`px-2 py-0.5 text-[10px] font-medium rounded-full ${
                                        isTagBlocked
                                          ? "bg-rose-500/10 text-rose-600 dark:text-rose-400 line-through"
                                          : "bg-primary/10 text-primary"
                                      }`}
                                    >
                                      {comp.tag}
                                      {isTagBlocked && " (Kit Disabled)"}
                                    </span>
                                  </div>
                                )}

                                {comp.example_role && (
                                  <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1">
                                    {comp.example_role}
                                  </p>
                                )}
                              </div>
                            </div>

                            {/* Card Specs and Toggle Footer */}
                            <div className="mt-3 pt-2.5 border-t border-border/60 flex items-center justify-between gap-2">
                              <div className="flex items-center gap-2 text-[11px] text-muted-foreground flex-wrap">
                                {comp.scaled_mass_g != null && (
                                  <span>{comp.scaled_mass_g}g</span>
                                )}
                                {comp.voltage_v != null && <span>{comp.voltage_v}V</span>}
                                {comp.assumed_cost_usd != null && (
                                  <span>${comp.assumed_cost_usd}</span>
                                )}
                              </div>

                              {/* Interactive Touch-friendly Switch Button */}
                              <button
                                type="button"
                                onClick={() => handleToggleComponent(comp)}
                                disabled={isTagBlocked}
                                className={`min-h-[44px] min-w-[70px] px-3 py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-colors cursor-pointer border ${
                                  isTagBlocked
                                    ? "bg-muted text-muted-foreground opacity-50 cursor-not-allowed border-transparent"
                                    : isEnabled
                                    ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/25"
                                    : "bg-muted border-border text-muted-foreground hover:bg-muted/80"
                                }`}
                              >
                                {isTagBlocked ? (
                                  <span>Kit Off</span>
                                ) : isEnabled ? (
                                  <>
                                    <Check className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
                                    <span>Active</span>
                                  </>
                                ) : (
                                  <>
                                    <Ban className="w-3.5 h-3.5 text-muted-foreground" />
                                    <span>Off</span>
                                  </>
                                )}
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
        })}
      </div>
      </>
      ) : (
      <div className="flex flex-col gap-3">
        <div className="relative flex-1">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search custom components by name, owner, team, or mission…"
            className="w-full min-h-[44px] pl-9 pr-3 text-sm bg-card border border-border rounded-xl focus:outline-none focus:border-primary transition-colors text-foreground placeholder:text-muted-foreground"
          />
        </div>
        {customsLoading ? (
          <div className="py-12 flex justify-center items-center">
            <Spinner />
          </div>
        ) : filteredCustoms.length === 0 ? (
          <div className="py-6 text-center text-xs sm:text-sm text-muted-foreground">
            {cohortCustoms.length === 0
              ? ownerType === "cohort"
                ? "No student-built custom components in this cohort yet — including observer test accounts."
                : "No student-built custom components yet — including observer test accounts."
              : `No custom components match "${searchQuery}".`}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {filteredCustoms.map((c) => (
              <div key={c.id} className="rounded-2xl border border-border bg-card p-3.5 sm:p-4 flex flex-col gap-2">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="w-12 h-12 rounded-lg bg-muted border border-border shrink-0 flex items-center justify-center overflow-hidden">
                    {c.image_url ? (
                      <img src={c.image_url} alt={c.component_name} className="w-full h-full object-cover" />
                    ) : (
                      <Cpu className="w-6 h-6 text-muted-foreground/60" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-semibold text-xs sm:text-sm text-foreground truncate" title={c.component_name}>
                        {c.component_name}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-violet-500/15 text-violet-600 dark:text-violet-400">
                        Custom
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-muted text-muted-foreground">
                        {c.subsystem}
                      </span>
                      {!c.is_active && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide bg-muted text-muted-foreground">
                          Retired
                        </span>
                      )}
                    </div>
                    {c.purpose_function && (
                      <p className="text-[11px] text-muted-foreground line-clamp-2 mt-1">{c.purpose_function}</p>
                    )}
                    <p className="text-[11px] text-muted-foreground mt-1">
                      {`${c.mass_g ?? 0}g · ${c.voltage_v ?? 0}V/${c.current_ma ?? 0}mA · ${c.power_computed_mw ?? 0}mW · ${c.cost_aed ?? 0} AED`}
                    </p>
                    <p className="text-[10px] text-muted-foreground mt-1">
                      Owner: {c.student_name || "(deleted user)"}{c.student_email ? ` · ${c.student_email}` : ""}
                      {c.team_name && ` · team ${c.team_name}`}
                    </p>
                    <p className="text-[10px] text-muted-foreground">
                      {[c.program_code || c.program_name, c.cohort_name].filter(Boolean).join(" — ") || "No cohort"}
                      {c.mission_title && ` · ${c.mission_title}`}
                      {c.created_at && ` · built ${new Date(c.created_at).toLocaleDateString()}`}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      )}
    </div>
  )
}
