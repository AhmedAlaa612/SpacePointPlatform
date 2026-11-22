import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { MapPin, Plus, X } from "lucide-react"

import { getLocationsApi } from "@/api/inventory"
import { createOrgCohortApi, updateOrgCohortApi } from "@/api/organizationPrograms"
import { listProgramVariationsApi } from "@/api/sessions/programs"
import { Button } from "@/components/ui/button"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { QuickCreateLocationModal } from "@/pages/admin/components/QuickCreateLocationModal"
import type { Location } from "@/types/inventory"
import type { ProgramVariation } from "@/types/sessions"

export interface OrgCohortModalProgram {
  id: string
  name: string
  code?: string
  is_org_owned?: boolean
  is_shared_program?: boolean
  can_create_cohort?: boolean
  default_capacity?: number | null
  duration_hours?: number | null
}

export interface OrgCohortModalEditable {
  id: string
  program_id: string
  name: string
  starts_on?: string | null
  ends_on?: string | null
  start_date?: string
  end_date?: string
  location_id?: string | null
  location?: string | null
  capacity?: number | null
  duration_hours?: number | null
  visibility?: "public" | "private"
  is_public?: boolean
  status?: string
  variation_id?: string | null
  checklist_title_override?: string | null
}

interface Props {
  open: boolean
  onClose: () => void
  programs: OrgCohortModalProgram[]
  defaultProgramId?: string
  cohort?: OrgCohortModalEditable | null
  maxStudentsPerCohort?: number | null
  onSuccess: () => void
}

export function OrgCohortModal({
  open,
  onClose,
  programs,
  defaultProgramId,
  cohort,
  maxStudentsPerCohort,
  onSuccess,
}: Props) {
  const qc = useQueryClient()
  const toast = useToast()
  const isEdit = Boolean(cohort)

  const eligiblePrograms = useMemo(() => {
    if (isEdit && cohort) {
      const current = programs.find((p) => p.id === cohort.program_id)
      return current ? [current] : programs
    }
    return programs.filter((p) => p.can_create_cohort !== false)
  }, [programs, isEdit, cohort])

  const [programId, setProgramId] = useState("")
  const [variationId, setVariationId] = useState("")
  const [name, setName] = useState("")
  const [startsOn, setStartsOn] = useState("")
  const [endsOn, setEndsOn] = useState("")
  const [locationId, setLocationId] = useState("")
  const [locationText, setLocationText] = useState("")
  const [capacity, setCapacity] = useState("")
  const [durationHours, setDurationHours] = useState("")
  const [visibility, setVisibility] = useState<"public" | "private">("private")
  const [status, setStatus] = useState("registration_open")
  const [createLocOpen, setCreateLocOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    if (cohort) {
      setProgramId(cohort.program_id)
      setVariationId(cohort.variation_id ?? "")
      setName(cohort.name ?? "")
      setStartsOn(cohort.starts_on ?? cohort.start_date ?? "")
      setEndsOn(cohort.ends_on ?? cohort.end_date ?? "")
      setLocationId(cohort.location_id ?? "")
      setLocationText(cohort.location ?? "")
      setCapacity(cohort.capacity != null ? String(cohort.capacity) : "")
      setDurationHours(cohort.duration_hours != null ? String(cohort.duration_hours) : "")
      setVisibility(
        cohort.visibility ?? (cohort.is_public === false ? "private" : "public"),
      )
      setStatus(cohort.status ?? "registration_open")
    } else {
      const initProg = defaultProgramId || eligiblePrograms[0]?.id || ""
      setProgramId(initProg)
      setVariationId("")
      setName("")
      setStartsOn("")
      setEndsOn("")
      setLocationId("")
      setLocationText("")
      setCapacity("")
      setDurationHours("")
      setVisibility("private")
      setStatus("registration_open")
    }
  }, [open, cohort, defaultProgramId, eligiblePrograms])

  const { data: variations = [] } = useQuery<ProgramVariation[]>({
    queryKey: ["program-variations", programId],
    queryFn: () => listProgramVariationsApi(programId),
    enabled: open && Boolean(programId),
  })

  const visibleVariations = useMemo(
    () => variations.filter((v) => v.is_active || v.id === cohort?.variation_id),
    [variations, cohort?.variation_id],
  )

  useEffect(() => {
    if (!open || isEdit || visibleVariations.length === 0) return
    if (!variationId || !visibleVariations.some((v) => v.id === variationId)) {
      const defVar = visibleVariations.find((v) => v.is_default) ?? visibleVariations[0]
      if (defVar) setVariationId(defVar.id)
    }
  }, [open, isEdit, visibleVariations, variationId])

  const { data: locations = [] } = useQuery<Location[]>({
    queryKey: ["locations"],
    queryFn: () => getLocationsApi(),
    enabled: open,
  })

  const selectedProgram = programs.find((p) => p.id === programId)
  const selectedVariation = visibleVariations.find((v) => v.id === variationId)

  const parsedCapacity = capacity.trim() ? Number(capacity) : null
  const capacityExceeded =
    maxStudentsPerCohort != null &&
    parsedCapacity != null &&
    !Number.isNaN(parsedCapacity) &&
    parsedCapacity > maxStudentsPerCohort

  const mut = useMutation({
    mutationFn: async () => {
      const capVal = capacity.trim() ? Number(capacity) : null
      const durVal = durationHours.trim() ? Number(durationHours) : null
      if (isEdit && cohort) {
        return updateOrgCohortApi(cohort.id, {
          name: name.trim(),
          starts_on: startsOn || null,
          ends_on: endsOn || null,
          start_date: startsOn || undefined,
          end_date: endsOn || undefined,
          location_id: locationId || null,
          location: locationText.trim() || null,
          capacity: capVal,
          duration_hours: durVal,
          visibility,
          is_public: visibility === "public",
          ...(cohort.status !== "completed" ? { status } : {}),
          variation_id: variationId || null,
        })
      }
      return createOrgCohortApi({
        program_id: programId,
        name: name.trim(),
        starts_on: startsOn || null,
        ends_on: endsOn || null,
        start_date: startsOn || undefined,
        end_date: endsOn || undefined,
        location_id: locationId || null,
        location: locationText.trim() || null,
        capacity: capVal,
        duration_hours: durVal,
        visibility,
        is_public: visibility === "public",
        status,
        variation_id: variationId || null,
      })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["org-programs-overview"] })
      qc.invalidateQueries({ queryKey: ["sessions-cohorts"] })
      if (cohort?.id) {
        qc.invalidateQueries({ queryKey: ["org-cohort", cohort.id] })
      }
      toast.success(isEdit ? "Cohort updated" : "Cohort launched")
      onSuccess()
      onClose()
    },
    onError: (err) => {
      toast.error(getErrorMessage(err, isEdit ? "Failed to update cohort" : "Failed to create cohort"))
    },
  })

  if (!open) return null

  const capPlaceholder =
    selectedVariation?.default_capacity ??
    selectedProgram?.default_capacity ??
    maxStudentsPerCohort ??
    30
  const durPlaceholder = selectedVariation?.duration_hours ?? selectedProgram?.duration_hours ?? 2

  const canSubmit = Boolean(programId && name.trim() && !capacityExceeded && !mut.isPending)

  return (
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4 backdrop-blur-sm"
        onClick={onClose}
      >
        <div
          className="w-full max-w-xl max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-background shadow-2xl"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between px-5 py-4 border-b border-border sticky top-0 bg-background z-10">
            <div>
              <h2 className="text-base font-bold text-foreground">
                {isEdit ? "Edit Cohort" : "Launch New Cohort"}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5">
                {isEdit
                  ? "Update dates, location, capacity, and delivery status."
                  : "Inherits schedule days, checklists, role slots, and LMS items from the program defaults."}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <X size={16} />
            </button>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (canSubmit) mut.mutate()
            }}
            className="p-5 space-y-4"
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
              <label className="flex flex-col gap-1 sm:col-span-2">
                <span className="text-xs font-semibold text-muted-foreground">
                  Program <span className="text-destructive">*</span>
                </span>
                <select
                  value={programId}
                  onChange={(e) => {
                    setProgramId(e.target.value)
                    setVariationId("")
                  }}
                  disabled={isEdit || (Boolean(defaultProgramId) && eligiblePrograms.length === 1)}
                  className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground disabled:opacity-60"
                >
                  {eligiblePrograms.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                      {p.code ? ` (${p.code})` : ""}
                      {p.is_shared_program ? " · Shared by SpacePoint" : ""}
                    </option>
                  ))}
                </select>
              </label>

              {visibleVariations.length > 0 && (
                <label className="flex flex-col gap-1 sm:col-span-2">
                  <span className="text-xs font-semibold text-muted-foreground">
                    Program Variation
                  </span>
                  <select
                    value={variationId}
                    onChange={(e) => setVariationId(e.target.value)}
                    className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                  >
                    <option value="">Program Defaults</option>
                    {visibleVariations.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                        {v.is_default ? " (Default)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <label className="flex flex-col gap-1 sm:col-span-2">
                <span className="text-xs font-semibold text-muted-foreground">
                  Cohort Name <span className="text-destructive">*</span>
                </span>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Fall 2026 Robotics — Batch A"
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Start Date</span>
                <input
                  type="date"
                  value={startsOn}
                  onChange={(e) => setStartsOn(e.target.value)}
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">End Date</span>
                <input
                  type="date"
                  value={endsOn}
                  min={startsOn || undefined}
                  onChange={(e) => setEndsOn(e.target.value)}
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                />
              </label>

              <div className="flex flex-col gap-1 sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1">
                    <MapPin size={12} /> Venue / Location
                  </span>
                  <button
                    type="button"
                    onClick={() => setCreateLocOpen(true)}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline cursor-pointer"
                  >
                    <Plus size={12} /> New Location
                  </button>
                </div>
                <select
                  value={locationId}
                  onChange={(e) => {
                    const id = e.target.value
                    setLocationId(id)
                    const match = locations.find((l) => l.id === id)
                    if (match && !locationText) setLocationText(match.name)
                  }}
                  className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                >
                  <option value="">Select a saved venue (optional)</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>
                      {loc.name}
                      {loc.city_name ? ` — ${loc.city_name}` : ""}
                    </option>
                  ))}
                </select>
                {!locationId && (
                  <input
                    type="text"
                    value={locationText}
                    onChange={(e) => setLocationText(e.target.value)}
                    placeholder="Or enter a quick venue label / room notes (optional)"
                    className="mt-1 h-9 rounded-lg border border-border bg-background px-3 text-xs text-foreground"
                  />
                )}
              </div>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">
                  Capacity
                  {maxStudentsPerCohort != null ? ` (max ${maxStudentsPerCohort})` : ""}
                </span>
                <input
                  type="number"
                  min={1}
                  max={maxStudentsPerCohort ?? undefined}
                  value={capacity}
                  onChange={(e) => setCapacity(e.target.value)}
                  placeholder={String(capPlaceholder)}
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                />
                {capacityExceeded && (
                  <span className="text-[11px] text-destructive">
                    Exceeds organization cap of {maxStudentsPerCohort} students.
                  </span>
                )}
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">
                  Session Duration (hrs)
                </span>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  value={durationHours}
                  onChange={(e) => setDurationHours(e.target.value)}
                  placeholder={String(durPlaceholder)}
                  className="h-9 rounded-lg border border-border bg-background px-3 text-sm text-foreground"
                />
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Visibility</span>
                <select
                  value={visibility}
                  onChange={(e) => setVisibility(e.target.value as "public" | "private")}
                  className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                >
                  <option value="public">Public (registration link)</option>
                  <option value="private">Private (invite / desk only)</option>
                </select>
              </label>

              <label className="flex flex-col gap-1">
                <span className="text-xs font-semibold text-muted-foreground">Status</span>
                {cohort?.status === "completed" ? (
                  <div className="h-9 rounded-lg border border-border bg-muted/50 px-3 flex items-center text-sm text-muted-foreground">
                    Completed (locked)
                  </div>
                ) : (
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                    className="h-9 rounded-lg border border-border bg-card px-3 text-sm text-foreground"
                  >
                    <option value="planned">Planned</option>
                    <option value="registration_open">Registration Open</option>
                    <option value="running">Running</option>
                    {isEdit && <option value="cancelled">Cancelled</option>}
                  </select>
                )}
              </label>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <Button type="button" variant="outline" size="sm" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" size="sm" disabled={!canSubmit}>
                {mut.isPending
                  ? isEdit
                    ? "Saving..."
                    : "Launching..."
                  : isEdit
                    ? "Save Changes"
                    : "Launch Cohort"}
              </Button>
            </div>
          </form>
        </div>
      </div>

      {createLocOpen && (
        <QuickCreateLocationModal
          onClose={() => setCreateLocOpen(false)}
          onCreated={(loc) => {
            setLocationId(loc.id)
            setLocationText(loc.name)
            qc.invalidateQueries({ queryKey: ["locations"] })
          }}
        />
      )}
    </>
  )
}
