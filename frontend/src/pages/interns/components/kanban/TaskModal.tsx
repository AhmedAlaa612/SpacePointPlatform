import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { ExternalLink, Clock, Trash2, Network, ChevronDown, ChevronUp, Pencil, Plus, X as XIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import type { BoardCard, User } from "@/types/interns"
import { useAuth } from "@/context/AuthContext"
import {
  updateLeaderTaskApi, deleteLeaderTaskApi, leaderReviewSubmissionApi,
  updateInternTaskStatusApi, submitTaskWorkApi,
  assignLeaderTaskApi, unassignLeaderTaskApi,
} from "@/api/interns/tasks"
import { getLeaderTeamMembersApi } from "@/api/interns/teams"

interface Props {
  card: BoardCard | null
  open: boolean
  onClose: () => void
  tasksKey: string[]
}

function AssigneeRow({ user }: { user: User }) {
  const initials = user.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-[#d6c7e1] text-[#643f83] text-xs font-semibold flex items-center justify-center flex-shrink-0">
          {initials}
        </div>
        <div>
          <p className="text-sm font-medium text-black">{user.full_name}</p>
          <p className="text-xs text-gray-400">{user.email}</p>
        </div>
      </div>
      {user.phone && (
        <a href={`https://wa.me/${user.phone.replace(/\D/g, "")}`}
          target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}
          className="flex items-center gap-1.5 text-xs text-[#25d366] hover:text-[#1da851] font-medium transition-colors">
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
          </svg>
          <span className="hidden sm:inline">WhatsApp</span>
        </a>
      )}
    </div>
  )
}

export default function TaskModal({ card, open, onClose, tasksKey }: Props) {
  const { currentUser } = useAuth()
  const queryClient     = useQueryClient()
  const navigate        = useNavigate()
  const isIntern  = currentUser?.role === "intern"
  const isLeader  = currentUser?.role === "leader"

  const [view,           setView]           = useState<"detail" | "edit" | "submit" | "review">("detail")
  const [scopeOpen,      setScopeOpen]      = useState(false)
  const [submitLink,     setSubmitLink]     = useState("")
  const [submitNote,     setSubmitNote]     = useState("")
  const [actualTime,     setActualTime]     = useState("")
  const [reviewScore,    setReviewScore]    = useState("")
  const [reviewComment,  setReviewComment]  = useState("")
  const [selectedSubId,  setSelectedSubId]  = useState<string | null>(null)

  // edit fields
  const [editTitle,    setEditTitle]    = useState("")
  const [editDesc,     setEditDesc]     = useState("")
  const [editDue,      setEditDue]      = useState("")
  const [editExpected, setEditExpected] = useState("")

  const resetClose = () => {
    setView("detail")
    setSubmitLink(""); setSubmitNote(""); setActualTime("")
    setReviewScore(""); setReviewComment(""); setSelectedSubId(null)
    onClose()
  }

  const openEdit = () => {
    setEditTitle(card?.title ?? "")
    setEditDesc(card?.description ?? "")
    setEditDue(card?.due_date ? card.due_date.split("T")[0] : "")
    setEditExpected(card?.expected_time != null ? String(card.expected_time) : "")
    setView("edit")
  }

  const startMutation = useMutation({
    mutationFn: () => isIntern
      ? updateInternTaskStatusApi(card!.id, "in_progress")
      : updateLeaderTaskApi(card!.id, { status: "in_progress" }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); resetClose() },
  })

  const submitMutation = useMutation({
    mutationFn: () => submitTaskWorkApi(card!.id, {
      link: submitLink,
      note: submitNote || undefined,
      actual_time: actualTime ? Number(actualTime) : undefined,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); resetClose() },
  })

  const reviewMutation = useMutation({
    mutationFn: () => leaderReviewSubmissionApi(selectedSubId!, {
      score: Number(reviewScore) || 0,
      review_comment: reviewComment,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); resetClose() },
  })

  const updateStatusMutation = useMutation({
    mutationFn: (status: string) => updateLeaderTaskApi(card!.id, { status }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); resetClose() },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteLeaderTaskApi(card!.id),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); resetClose() },
  })

  const editMutation = useMutation({
    mutationFn: () => updateLeaderTaskApi(card!.id, {
      title:         editTitle.trim() || undefined,
      description:   editDesc.trim()  || undefined,
      due_date:      editDue           ? new Date(editDue).toISOString() : undefined,
      expected_time: editExpected      ? Number(editExpected) : undefined,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); setView("detail") },
  })

  const assignMutation = useMutation({
    mutationFn: (userId: string) => assignLeaderTaskApi(card!.id, [userId]),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
  })

  const unassignMutation = useMutation({
    mutationFn: (userId: string) => unassignLeaderTaskApi(card!.id, userId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
  })

  // team members for assign picker
  const { data: teamMembers = [] } = useQuery<User[]>({
    queryKey: ["leader", "team", "members"],
    queryFn: getLeaderTeamMembersApi,
    enabled: isLeader && view === "edit",
  })

  if (!card) return null

  const pendingSubs = card.submissions?.filter((s) => s.status === "submitted") ?? []
  const formattedDue = card.due_date
    ? new Date(card.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : null

  return (
    <Dialog open={open} onOpenChange={resetClose}>
      <DialogContent className="max-w-md w-full bg-white border border-gray-100 shadow-xl rounded-2xl p-0 overflow-hidden">
        <div className="p-6">
          <DialogHeader>
            {/* Epic / module context */}
            {(card.epic_title || card.module_title) && (
              <div className="flex items-center gap-1.5 mb-1">
                {card.epic_title && (
                  <span className="text-[10px] font-semibold text-[#643f83] bg-[#d6c7e1]/40 px-2 py-0.5 rounded-full">
                    {card.epic_title}
                  </span>
                )}
                {card.module_title && card.module_title !== "General" && (
                  <span className="text-[10px] text-gray-400">{card.module_title}</span>
                )}
              </div>
            )}
            <div className="flex items-start justify-between gap-2">
              <DialogTitle className="text-base font-semibold text-black leading-snug pr-2">
                {card.title}
              </DialogTitle>
              <div className="flex items-center gap-1 flex-shrink-0">
                {card.epic_id && (
                  <button
                    onClick={() => navigate({ to: "/interns/mind-map/$epicId", params: { epicId: card.epic_id! } })}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-[#643f83] hover:bg-[#d6c7e1]/30 transition-colors"
                    title="View epic mind map"
                  >
                    <Network size={14} />
                  </button>
                )}
                {isLeader && view === "detail" && (
                  <button onClick={openEdit}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-black hover:bg-gray-100 transition-colors">
                    <Pencil size={14} />
                  </button>
                )}
                {isLeader && (
                  <button
                    onClick={() => { if (confirm(`Delete "${card.title}"?`)) deleteMutation.mutate() }}
                    disabled={deleteMutation.isPending}
                    className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            </div>
          </DialogHeader>

          {/* ── Detail view ─────────────────────────────────────────── */}
          {view === "detail" && (
            <div className="mt-4 flex flex-col gap-4">
              {/* Module scope — collapsible context */}
              {(() => {
                const isGeneral = !card.module_title || card.module_title === "General"
                const scopeText = card.module_description
                  ?? (isGeneral ? (card.epic_description ?? null) : null)
                if (!scopeText) return null
                const label = isGeneral ? "Epic scope" : `${card.module_title} — scope`
                return (
                  <div className="border border-[#d6c7e1] rounded-xl overflow-hidden">
                    <button
                      onClick={() => setScopeOpen((o) => !o)}
                      className="w-full flex items-center justify-between px-3.5 py-2.5 bg-[#f5f0fa] text-[#643f83] hover:bg-[#ede5f5] transition-colors"
                    >
                      <span className="text-[10px] font-bold uppercase tracking-widest">{label}</span>
                      {scopeOpen ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                    </button>
                    {scopeOpen && (
                      <div className="px-3.5 py-3 bg-white">
                        <p className="text-xs text-gray-600 leading-relaxed whitespace-pre-wrap">{scopeText}</p>
                      </div>
                    )}
                  </div>
                )
              })()}

              {card.description && (
                <p className="text-sm text-gray-600 leading-relaxed">{card.description}</p>
              )}

              <div className="flex flex-wrap gap-2">
                {formattedDue && (
                  <span className="flex items-center gap-1.5 text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-lg">
                    <Clock size={11} /> Due {formattedDue}
                  </span>
                )}
                {card.expected_time != null && (
                  <span className="text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-lg">
                    Expected {card.expected_time}h
                  </span>
                )}
                {card.actual_time != null && (
                  <span className="text-xs text-gray-500 bg-gray-100 px-2.5 py-1 rounded-lg">
                    Actual {card.actual_time}h
                  </span>
                )}
              </div>

              {/* Assignees */}
              {card.assignees.length > 0 && (
                <div>
                  <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-1">Assigned to</p>
                  <div className="divide-y divide-gray-50">
                    {card.assignees.map((u) => <AssigneeRow key={u.id} user={u} />)}
                  </div>
                </div>
              )}

              {/* Submissions */}
              {card.submissions.length > 0 && (
                <div className="flex flex-col gap-2">
                  <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                    Submissions ({card.submissions.length})
                  </p>
                  {[...card.submissions].reverse().map((sub, i) => (
                    <div key={sub.id} className={cn(
                      "rounded-xl p-3 border",
                      i === 0 ? "bg-gray-50 border-gray-200" : "bg-white border-gray-100 opacity-70"
                    )}>
                      <div className="flex items-center justify-between mb-1.5">
                        {i === 0
                          ? <p className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Latest</p>
                          : <span />}
                        {sub.submitter_name && (
                          <span className="text-[10px] font-medium text-gray-500">by {sub.submitter_name}</span>
                        )}
                      </div>
                      <a href={sub.link} target="_blank" rel="noreferrer"
                        className="flex items-center gap-1.5 text-sm text-[#643f83] hover:underline">
                        <ExternalLink size={13} />{sub.link}
                      </a>
                      {sub.note && <p className="text-xs text-gray-500 mt-1">{sub.note}</p>}
                      <div className="flex items-center justify-between mt-2">
                        <span className={cn(
                          "text-[10px] font-semibold px-2 py-0.5 rounded-full",
                          sub.status === "reviewed" ? "bg-black text-white" : "bg-[#d6c7e1] text-[#643f83]"
                        )}>
                          {sub.status === "reviewed" ? "Reviewed" : "Pending review"}
                        </span>
                        <div className="flex items-center gap-2">
                          {sub.score != null && (
                            <span className="text-xs font-semibold text-black">{sub.score}/100</span>
                          )}
                          <span className="text-[10px] text-gray-400">
                            {new Date(sub.submitted_at).toLocaleDateString()}
                          </span>
                        </div>
                      </div>
                      {sub.review_comment && (
                        <p className="text-xs text-gray-500 mt-1.5 italic">"{sub.review_comment}"</p>
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-col gap-2 pt-1">
                {/* Intern */}
                {isIntern && card.status === "todo" && (
                  <button onClick={() => startMutation.mutate()} disabled={startMutation.isPending}
                    className="w-full h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                    {startMutation.isPending ? "Updating…" : "Start working"}
                  </button>
                )}
                {isIntern && card.status === "in_progress" && (
                  <button onClick={() => setView("submit")}
                    className="w-full h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors">
                    Submit work
                  </button>
                )}

                {/* Leader: review */}
                {isLeader && pendingSubs.length > 0 && (
                  <button onClick={() => {
                    const latest = [...pendingSubs].sort((a, b) =>
                      new Date(b.submitted_at).getTime() - new Date(a.submitted_at).getTime()
                    )[0]
                    setSelectedSubId(latest.id)
                    setView("review")
                  }}
                    className="w-full h-10 border border-black text-black rounded-xl text-sm font-medium hover:bg-gray-50 transition-colors">
                    Review submission ({pendingSubs.length})
                  </button>
                )}

                {/* Leader: status buttons */}
                {isLeader && (
                  <div className="flex gap-2">
                    {card.status !== "in_progress" && (
                      <button onClick={() => updateStatusMutation.mutate("in_progress")}
                        disabled={updateStatusMutation.isPending}
                        className="flex-1 h-9 border border-[#643f83] text-[#643f83] rounded-xl text-xs font-medium hover:bg-[#d6c7e1]/30 transition-colors disabled:opacity-50">
                        Mark in progress
                      </button>
                    )}
                    {card.status !== "done" && (
                      <button onClick={() => updateStatusMutation.mutate("done")}
                        disabled={updateStatusMutation.isPending}
                        className="flex-1 h-9 bg-black text-white rounded-xl text-xs font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                        Mark done
                      </button>
                    )}
                    {card.status !== "todo" && (
                      <button onClick={() => updateStatusMutation.mutate("todo")}
                        disabled={updateStatusMutation.isPending}
                        className="flex-1 h-9 border border-gray-200 text-gray-600 rounded-xl text-xs font-medium hover:bg-gray-50 transition-colors disabled:opacity-50">
                        Reopen
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Edit view (leader only) ──────────────────────────────── */}
          {view === "edit" && (
            <div className="mt-4 flex flex-col gap-4">
              {/* title */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Title</label>
                <input value={editTitle} onChange={(e) => setEditTitle(e.target.value)}
                  className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
              </div>
              {/* description */}
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">Description</label>
                <textarea value={editDesc} onChange={(e) => setEditDesc(e.target.value)}
                  rows={3} placeholder="Optional"
                  className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
              </div>
              {/* due date + expected time */}
              <div className="flex gap-3">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">Deadline</label>
                  <input type="date" value={editDue} onChange={(e) => setEditDue(e.target.value)}
                    className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
                </div>
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-500 mb-1.5">Expected (h)</label>
                  <input type="number" min="0" step="0.5" value={editExpected} onChange={(e) => setEditExpected(e.target.value)}
                    placeholder="e.g. 3"
                    className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
                </div>
              </div>

              {/* assignees */}
              <div>
                <p className="text-xs font-medium text-gray-500 mb-2">Assignees</p>
                {/* current */}
                {card.assignees.length > 0 && (
                  <div className="flex flex-col gap-1.5 mb-3">
                    {card.assignees.map((u) => (
                      <div key={u.id} className="flex items-center justify-between px-3 py-2 bg-gray-50 rounded-xl">
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-[#d6c7e1] text-[#643f83] text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                            {u.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                          </div>
                          <span className="text-sm font-medium text-black">{u.full_name}</span>
                        </div>
                        <button onClick={() => unassignMutation.mutate(u.id)}
                          disabled={unassignMutation.isPending}
                          className="p-1 rounded-lg text-gray-400 hover:text-red-500 transition-colors disabled:opacity-50">
                          <XIcon size={13} />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                {/* add from team */}
                {teamMembers.filter((m) => !card.assignees.find((a) => a.id === m.id)).length > 0 && (
                  <div className="flex flex-col gap-1.5">
                    <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">Add from team</p>
                    {teamMembers
                      .filter((m) => !card.assignees.find((a) => a.id === m.id))
                      .map((m) => (
                        <button key={m.id} onClick={() => assignMutation.mutate(m.id)}
                          disabled={assignMutation.isPending}
                          className="flex items-center justify-between px-3 py-2 border border-dashed border-gray-200 rounded-xl hover:border-black hover:bg-gray-50 transition-all disabled:opacity-50">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-full bg-gray-100 text-gray-500 text-[10px] font-bold flex items-center justify-center flex-shrink-0">
                              {m.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                            </div>
                            <span className="text-sm text-gray-600">{m.full_name}</span>
                          </div>
                          <Plus size={13} className="text-gray-400" />
                        </button>
                      ))}
                  </div>
                )}
              </div>

              <div className="flex gap-2 pt-1">
                <button onClick={() => setView("detail")}
                  className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
                <button onClick={() => editMutation.mutate()}
                  disabled={!editTitle.trim() || editMutation.isPending}
                  className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                  {editMutation.isPending ? "Saving…" : "Save changes"}
                </button>
              </div>
            </div>
          )}

          {/* ── Submit view ──────────────────────────────────────────── */}
          {view === "submit" && (
            <div className="mt-4 flex flex-col gap-3">
              <p className="text-sm text-gray-500">Paste a link to your work</p>
              <input value={submitLink} onChange={(e) => setSubmitLink(e.target.value)}
                placeholder="https://…"
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
              <textarea value={submitNote} onChange={(e) => setSubmitNote(e.target.value)}
                placeholder="Add a note (optional)" rows={3}
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
              <div>
                <label className="block text-xs font-medium text-gray-500 mb-1.5">
                  Time spent (hours)
                  {card.expected_time != null && (
                    <span className="text-gray-400 font-normal"> · expected {card.expected_time}h</span>
                  )}
                </label>
                <input type="number" min="0" step="0.5" value={actualTime}
                  onChange={(e) => setActualTime(e.target.value)} placeholder="e.g. 2.5"
                  className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
              </div>
              <div className="flex gap-2 pt-1">
                <button onClick={() => setView("detail")}
                  className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                  Back
                </button>
                <button onClick={() => submitMutation.mutate()}
                  disabled={!submitLink.trim() || submitMutation.isPending}
                  className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                  {submitMutation.isPending ? "Submitting…" : "Submit"}
                </button>
              </div>
            </div>
          )}

          {/* ── Review view ──────────────────────────────────────────── */}
          {view === "review" && selectedSubId && (() => {
            const sub = card.submissions.find((s) => s.id === selectedSubId)
            if (!sub) return null
            return (
              <div className="mt-4 flex flex-col gap-3">
                <div className="bg-gray-50 rounded-xl p-3">
                  <a href={sub.link} target="_blank" rel="noreferrer"
                    className="flex items-center gap-1.5 text-sm text-[#643f83] hover:underline">
                    <ExternalLink size={13} />{sub.link}
                  </a>
                  {sub.note && <p className="text-xs text-gray-500 mt-1">{sub.note}</p>}
                </div>
                <input type="number" value={reviewScore} onChange={(e) => setReviewScore(e.target.value)}
                  placeholder="Score (0–100)" min={0} max={100}
                  className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
                <textarea value={reviewComment} onChange={(e) => setReviewComment(e.target.value)}
                  placeholder="Feedback…" rows={3}
                  className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
                <div className="flex gap-2 pt-1">
                  <button onClick={() => setView("detail")}
                    className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                    Back
                  </button>
                  <button onClick={() => reviewMutation.mutate()}
                    disabled={!reviewComment.trim() || reviewMutation.isPending}
                    className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                    {reviewMutation.isPending ? "Saving…" : "Submit review"}
                  </button>
                </div>
              </div>
            )
          })()}
        </div>
      </DialogContent>
    </Dialog>
  )
}
