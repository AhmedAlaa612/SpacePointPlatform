import { useMutation, useQuery } from "@tanstack/react-query"
import { fetchPublicCities } from "@/api/lms"
import { previewInternshipLetterApi, type InternshipApproveBody } from "@/api/internship"
import { Button } from "@/components/ui/button"

// Defaults from the reference letter (Amna Khairi's, the example the
// letter template/design was built from) — the same supervisor signs off
// on essentially every internship letter today, so admins shouldn't have
// to retype this every time; supervisor/hours are still editable per
// request. `activity_description` has no form field at all below — it's
// always "research and development" (every internship letter to date),
// so admins never see or touch it.
export const emptyInternshipApprove = (): InternshipApproveBody => ({
  salutation: "", activity_description: "research and development", supervisor_title: "Mr.",
  supervisor_name: "Abdullah AlSalmani", supervisor_email: "abdel.alsalmani@gmail.com",
  supervisor_phone: "+971562987005", hours_per_week: 40,
})

export const isInternshipApproveComplete = (v: InternshipApproveBody) =>
  !!(v.salutation.trim() && v.activity_description.trim() && v.supervisor_title.trim() &&
     v.supervisor_name.trim() && v.supervisor_email.trim() && v.supervisor_phone.trim())

/** Shared internship-letter admin form — used on both the Role Requests
 * review page and the Applications approve/send-to-onboarding actions
 * (HANDOFF_INTERNSHIP.md, all three paths converge on the same
 * InternshipApprove shape). `requestedCityId`/`requestedDurationWeeks`/
 * `requestedStartDate` show as placeholders/context when the applicant
 * already supplied one and admin hasn't overridden it. Pass
 * `showRefNumberOverride={false}` for the onboarding flow, where the ref
 * number is deliberately never pre-set. `internName`/`universityIdNumber`
 * are only used for the Preview button — omit to hide it (e.g. if the
 * caller doesn't have an applicant identity to preview against yet). */
export function InternshipLetterFields({
  value, onChange, requestedCityId, requestedDurationWeeks, requestedStartDate, showRefNumberOverride = true,
  internName, universityIdNumber,
}: {
  value: InternshipApproveBody
  onChange: (next: InternshipApproveBody) => void
  requestedCityId?: string
  requestedDurationWeeks?: number
  requestedStartDate?: string
  showRefNumberOverride?: boolean
  internName?: string
  universityIdNumber?: string
}) {
  const { data: cities = [] } = useQuery({ queryKey: ["public-cities"], queryFn: fetchPublicCities })
  const requestedCityName = cities.find((c) => c.id === requestedCityId)?.name

  const preview = useMutation({
    mutationFn: async () => {
      const blob = await previewInternshipLetterApi({
        ...value, intern_name: internName || "Applicant",
        university_id_number: universityIdNumber, requested_start_date: requestedStartDate,
        requested_duration_weeks: requestedDurationWeeks,
      })
      const url = URL.createObjectURL(blob)
      window.open(url, "_blank")
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    },
    onError: (err: any) => alert(err?.response?.data?.detail || "Failed to render preview."),
  })

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Salutation">
          <select className="input" value={value.salutation}
            onChange={(e) => onChange({ ...value, salutation: e.target.value })}>
            <option value="">Select…</option>
            <option value="Mr.">Mr.</option>
            <option value="Ms.">Ms.</option>
            <option value="Mx.">Mx.</option>
          </select>
        </Field>
        <Field label="City">
          <select className="input" value={value.city_id ?? ""}
            onChange={(e) => onChange({ ...value, city_id: e.target.value || undefined })}>
            <option value="">
              {requestedCityId ? `Use requester's choice (${requestedCityName ?? "unknown city"})` : "Select…"}
            </option>
            {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Duration (weeks)">
          <input className="input" type="number" min={1}
            value={value.duration_weeks ?? requestedDurationWeeks ?? ""}
            onChange={(e) => onChange({ ...value, duration_weeks: e.target.value ? Number(e.target.value) : undefined })} />
        </Field>
        <Field label="Hours / week">
          <input className="input" type="number" min={1}
            value={value.hours_per_week ?? ""}
            onChange={(e) => onChange({ ...value, hours_per_week: e.target.value ? Number(e.target.value) : undefined })} />
        </Field>
      </div>

      {showRefNumberOverride && (
        <Field label="Ref number override (optional — auto-assigned if left blank)">
          <input className="input" type="number" min={1}
            value={value.ref_number_override ?? ""}
            onChange={(e) => onChange({ ...value, ref_number_override: e.target.value ? Number(e.target.value) : undefined })} />
        </Field>
      )}

      <Field label="Start date override">
        {/* Shows the requested date by default so the admin sees what will
            actually be used without having to look it up elsewhere — but
            `value.start_date_override` itself stays unset until the admin
            actually edits this, so the auto-resolve rule below still runs
            normally (e.g. the day-after-approval case) unless they do. */}
        <input className="input" type="date"
          value={value.start_date_override ?? requestedStartDate ?? ""}
          onChange={(e) => onChange({ ...value, start_date_override: e.target.value || undefined })} />
        <p className="text-[11px] text-muted-foreground mt-1">
          {requestedStartDate
            ? `Shown: the requester's own choice. Left as-is: if approved on or before ${requestedStartDate}, that's the start date; if approved after, the start date becomes the day after approval. Change it to override.`
            : "Nothing was requested — leave blank to default to the approval date, or set one to override."}
        </p>
      </Field>

      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mt-1">Supervisor</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Title">
          <select className="input" value={value.supervisor_title}
            onChange={(e) => onChange({ ...value, supervisor_title: e.target.value })}>
            <option value="">Select…</option>
            <option value="Mr.">Mr.</option>
            <option value="Ms.">Ms.</option>
            <option value="Dr.">Dr.</option>
          </select>
        </Field>
        <Field label="Name">
          <input className="input" value={value.supervisor_name}
            onChange={(e) => onChange({ ...value, supervisor_name: e.target.value })} />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Email">
          <input className="input" type="email" value={value.supervisor_email}
            onChange={(e) => onChange({ ...value, supervisor_email: e.target.value })} />
        </Field>
        <Field label="Phone">
          <input className="input" value={value.supervisor_phone}
            onChange={(e) => onChange({ ...value, supervisor_phone: e.target.value })} />
        </Field>
      </div>

      {internName && (
        <Button type="button" variant="outline" className="w-full mt-1"
          onClick={() => preview.mutate()} disabled={preview.isPending}>
          {preview.isPending ? "Rendering preview…" : "Preview Letter"}
        </Button>
      )}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider block mb-1.5">
        {label}
      </label>
      {children}
    </div>
  )
}
