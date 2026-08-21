import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { isAxiosError } from "axios"
import { ChevronDown, ChevronUp, Gift, Plus, Users, X } from "lucide-react"
import { PageHeader, EmptyState, Spinner } from "@/components/ui/primitives"
import { Modal, Field, ModalActions, ConfirmDialog } from "@/pages/admin/components/common"
import {
  listInviteCodesApi, createInviteCodeApi, updateInviteCodeApi, deleteInviteCodeApi,
  listInviteCodeGrantsApi, createInviteCodeGrantApi, deleteInviteCodeGrantApi,
  listCoursesApi, listLearningPathsApi,
  type InviteCode,
} from "@/api/lms_admin"

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail
  return fallback
}

/** Student invite codes (2026-08-13) — the gate on LMS signup, ported from
 * Madar where `invitation_codes` doubled as cohort identity ("Fall 2026
 * Batch"). Deliberately separate from the admin-only instructor codes at
 * /instructors/admin/invitations: same table, split by `kind`, so a school's
 * signup code can't also open the instructor application pipeline. */
export default function LmsInviteCodes() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [addOpen, setAddOpen] = useState(false)
  const [editTarget, setEditTarget] = useState<InviteCode | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<InviteCode | null>(null)
  const [actionError, setActionError] = useState("")
  const [grantsOpenId, setGrantsOpenId] = useState<string | null>(null)

  const { data: codes = [], isLoading } = useQuery({
    queryKey: ["lms-admin-invite-codes"],
    queryFn: listInviteCodesApi,
  })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-invite-codes"] })

  const toggleMutation = useMutation({
    mutationFn: (code: InviteCode) => updateInviteCodeApi(code.id, { is_active: !code.is_active }),
    onSuccess: () => { setActionError(""); invalidate() },
    onError: (e) => setActionError(errorDetail(e, "Couldn't update this code")),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteInviteCodeApi(id),
    onSuccess: () => { setActionError(""); setDeleteTarget(null); invalidate() },
    onError: (e) => setActionError(errorDetail(e, "Couldn't delete this code")),
  })

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Invite codes"
        subtitle="Students need one of these to sign up. Each code is a batch — filter students by it."
        action={
          <button
            onClick={() => setAddOpen(true)}
            className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
          >
            <Plus size={14} /> New code
          </button>
        }
      />

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      {isLoading ? (
        <Spinner />
      ) : codes.length === 0 ? (
        <EmptyState
          title="No invite codes yet"
          hint="Create one and share it with a school or cohort — nobody can sign up as a student without one."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {codes.map((c) => (
            <div key={c.id} className="flex flex-col bg-card border border-border rounded-2xl overflow-hidden">
              <div className="flex items-center gap-4 p-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm font-semibold text-foreground">{c.code}</span>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                      c.is_active
                        ? "bg-green-500/15 text-green-600 dark:text-green-400"
                        : "bg-muted text-muted-foreground"
                    }`}>
                      {c.is_active ? "Active" : "Inactive"}
                    </span>
                    {c.label && <span className="text-sm text-muted-foreground">{c.label}</span>}
                  </div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {c.signups} signed up · {c.used_count}/{c.max_uses} uses
                    {c.used_count >= c.max_uses && (
                      <span className="ml-2 text-amber-600 dark:text-amber-400">Limit reached</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  {c.signups > 0 && (
                    <button
                      onClick={() => void navigate({
                        to: "/lms-authoring/students",
                        search: { invite_code: c.code } as never,
                      })}
                      className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                      title="See the students who signed up with this code"
                    >
                      <Users size={13} /> Students
                    </button>
                  )}
                  <button
                    onClick={() => setGrantsOpenId(grantsOpenId === c.id ? null : c.id)}
                    className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted transition-colors"
                    title="Free courses/paths this code's students get"
                  >
                    <Gift size={13} /> Grants
                    {grantsOpenId === c.id ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                  </button>
                  <button
                    onClick={() => toggleMutation.mutate(c)}
                    disabled={toggleMutation.isPending}
                    className="h-8 px-3 rounded-lg text-xs font-medium text-muted-foreground hover:bg-muted transition-colors disabled:opacity-50"
                  >
                    {c.is_active ? "Deactivate" : "Activate"}
                  </button>
                  <button
                    onClick={() => { setActionError(""); setEditTarget(c) }}
                    className="h-8 px-3 rounded-lg text-xs font-medium text-foreground hover:bg-muted transition-colors"
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => { setActionError(""); setDeleteTarget(c) }}
                    className="h-8 px-3 rounded-lg text-xs font-medium text-red-600 hover:bg-red-500/10 transition-colors"
                  >
                    Delete
                  </button>
                </div>
              </div>
              {grantsOpenId === c.id && <GrantsPanel code={c} />}
            </div>
          ))}
        </div>
      )}

      {addOpen && (
        <InviteCodeModal
          onClose={() => setAddOpen(false)}
          onSuccess={() => { invalidate(); setAddOpen(false) }}
        />
      )}
      {editTarget && (
        <InviteCodeModal
          existing={editTarget}
          onClose={() => setEditTarget(null)}
          onSuccess={() => { invalidate(); setEditTarget(null) }}
        />
      )}
      {deleteTarget && (
        <ConfirmDialog
          title={`Delete code "${deleteTarget.code}"?`}
          description={
            deleteTarget.signups > 0
              ? `${deleteTarget.signups} student(s) signed up with this code — it can't be deleted. Deactivate it instead so no new signups use it.`
              : "Nobody has used this code, so it can be removed cleanly."
          }
          confirmLabel="Delete"
          destructive
          pending={deleteMutation.isPending}
          onCancel={() => setDeleteTarget(null)}
          onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
        />
      )}
    </div>
  )
}

/** Free courses/paths a code batch gets, applied immediately to every
 * account that's ever used the code and to every future signup on it
 * (2026-08-21) — the code IS the batch, same string-match the page above
 * already filters students by. Removing a grant only stops it applying
 * going forward; it never revokes access already granted. */
function GrantsPanel({ code }: { code: InviteCode }) {
  const queryClient = useQueryClient()
  const [pickerType, setPickerType] = useState<"course" | "path">("course")
  const [pickerId, setPickerId] = useState("")
  const [error, setError] = useState("")

  const { data: grants = [], isLoading } = useQuery({
    queryKey: ["lms-admin-invite-code-grants", code.id],
    queryFn: () => listInviteCodeGrantsApi(code.id),
  })
  const { data: courses = [] } = useQuery({ queryKey: ["lms-admin-courses"], queryFn: listCoursesApi })
  const { data: paths = [] } = useQuery({ queryKey: ["lms-admin-learning-paths"], queryFn: listLearningPathsApi })
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["lms-admin-invite-code-grants", code.id] })

  const grantedCourseIds = new Set(grants.filter((g) => g.course_id).map((g) => g.course_id))
  const grantedPathIds = new Set(grants.filter((g) => g.learning_path_id).map((g) => g.learning_path_id))
  const availableCourses = courses.filter((c) => !grantedCourseIds.has(c.id))
  const availablePaths = paths.filter((p) => !grantedPathIds.has(p.id))

  const addMutation = useMutation({
    mutationFn: () => createInviteCodeGrantApi(
      code.id, pickerType === "course" ? { course_id: pickerId } : { learning_path_id: pickerId },
    ),
    onSuccess: () => { setError(""); setPickerId(""); invalidate() },
    onError: (e) => setError(isAxiosError(e) && typeof e.response?.data?.detail === "string" ? e.response.data.detail : "Couldn't add that grant"),
  })
  const removeMutation = useMutation({
    mutationFn: (grantId: string) => deleteInviteCodeGrantApi(code.id, grantId),
    onSuccess: invalidate,
  })

  return (
    <div className="flex flex-col gap-3 px-4 pb-4 pt-1 border-t border-border bg-muted/30">
      <p className="text-xs text-muted-foreground">
        Everyone who's used {code.code} — new or existing — gets these for free, no checkout involved.
      </p>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading grants…</p>
      ) : grants.length === 0 ? (
        <p className="text-xs text-muted-foreground">No free courses or paths attached yet.</p>
      ) : (
        <div className="flex flex-col gap-1">
          {grants.map((g) => (
            <div key={g.id} className="flex items-center justify-between gap-2 h-8 px-2 text-sm bg-card border border-border rounded-lg">
              <span className="truncate">
                {g.product_type === "course" ? g.course_title : g.learning_path_title}
                <span className="ml-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {g.product_type === "course" ? "Course" : "Path"}
                </span>
              </span>
              <button
                onClick={() => removeMutation.mutate(g.id)}
                disabled={removeMutation.isPending}
                className="shrink-0 text-muted-foreground hover:text-red-600 transition-colors disabled:opacity-50"
                title="Stop granting this — doesn't revoke access already given"
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <select
          value={pickerType}
          onChange={(e) => { setPickerType(e.target.value as "course" | "path"); setPickerId("") }}
          className="h-9 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="course">Course</option>
          <option value="path">Path</option>
        </select>
        <select
          value={pickerId}
          onChange={(e) => setPickerId(e.target.value)}
          className="flex-1 h-9 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">
            {pickerType === "course" ? "Add a course…" : "Add a path…"}
          </option>
          {(pickerType === "course" ? availableCourses : availablePaths).map((item) => (
            <option key={item.id} value={item.id}>{item.title}</option>
          ))}
        </select>
        <button
          onClick={() => pickerId && addMutation.mutate()}
          disabled={!pickerId || addMutation.isPending}
          className="flex items-center gap-1 h-9 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 transition-colors disabled:opacity-50"
        >
          <Plus size={13} /> Grant
        </button>
      </div>
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  )
}

function InviteCodeModal({ existing, onClose, onSuccess }: {
  existing?: InviteCode; onClose: () => void; onSuccess: () => void
}) {
  const [code, setCode] = useState(existing?.code ?? "")
  const [label, setLabel] = useState(existing?.label ?? "")
  const [maxUses, setMaxUses] = useState(String(existing?.max_uses ?? 30))
  const [error, setError] = useState("")

  // A code that's already been used can't be renamed (the server refuses —
  // students carry the literal string, not a reference), so don't offer it.
  const codeLocked = !!existing && existing.signups > 0

  const mutation = useMutation({
    mutationFn: () => {
      const payload = {
        label: label.trim() || null,
        max_uses: Number(maxUses) || 30,
      }
      return existing
        ? updateInviteCodeApi(existing.id, codeLocked ? payload : { ...payload, code: code.trim().toUpperCase() })
        : createInviteCodeApi({ ...payload, code: code.trim().toUpperCase() })
    },
    onSuccess,
    onError: (e) => setError(errorDetail(e, "Couldn't save this code")),
  })

  return (
    <Modal title={existing ? "Edit invite code" : "New invite code"} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Code">
          <input
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="FALL26"
            autoFocus={!existing}
            disabled={codeLocked}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm font-mono focus:outline-none focus:border-primary transition-colors disabled:opacity-60"
          />
        </Field>
        {codeLocked && (
          <p className="text-xs text-muted-foreground -mt-2">
            {existing!.signups} student(s) already signed up with this code, so it can't be renamed — change the
            batch name instead.
          </p>
        )}
        <Field label="Batch name (optional)">
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Fall 2026 Batch"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Max uses">
          <input
            value={maxUses}
            onChange={(e) => setMaxUses(e.target.value.replace(/[^0-9]/g, ""))}
            inputMode="numeric"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose}
          onConfirm={() => mutation.mutate()}
          loading={mutation.isPending}
          disabled={!code.trim()}
          label={existing ? "Save changes" : "Create code"}
        />
      </div>
    </Modal>
  )
}
