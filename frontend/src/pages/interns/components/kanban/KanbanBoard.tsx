import { useState } from "react"
import { createPortal } from "react-dom"
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors, useDroppable, useDraggable,
} from "@dnd-kit/core"
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core"
import { CSS } from "@dnd-kit/utilities"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Lightbulb, MessageSquare, ArrowLeft, ChevronRight, Network, Layers, Info } from "lucide-react"
import { useNavigate } from "@tanstack/react-router"
import ManageModulesModal from "@/pages/interns/components/ManageModulesModal"
import ProposalDetailDialog from "@/pages/interns/components/ProposalDetailDialog"
import Column from "./Column"
import TaskCard from "./TaskCard"
import TaskModal from "./TaskModal"
import CreateTaskModal from "./CreateSubtaskModal"
import EpicDetailModal from "./EpicDetailModal"
import type { BoardCard, Task, Epic, Project, Proposal, WorkStatus } from "@/types/interns"
import { useAuth } from "@/context/AuthContext"
import { getLeaderTasksApi, getInternTasksApi, updateLeaderTaskApi, updateInternTaskStatusApi, submitTaskWorkApi } from "@/api/interns/tasks"
import { getLeaderEpicsApi, updateLeaderEpicApi } from "@/api/interns/epics"
import { getLeaderProjectsApi, getInternProjectsApi } from "@/api/interns/projects"
import { createProposalApi, getLeaderAllProposalsApi, getInternProposalsApi, reviewProposalApi } from "@/api/interns/proposals"
import { cn } from "@/lib/utils"

const COLUMNS: { title: string; status: WorkStatus }[] = [
  { title: "To do",       status: "todo" },
  { title: "In progress", status: "in_progress" },
  { title: "Done",        status: "done" },
]

const STATUS_STYLE: Record<WorkStatus, { dot: string; badge: string }> = {
  todo:        { dot: "bg-gray-300",  badge: "bg-gray-100 text-gray-500" },
  in_progress: { dot: "bg-[#a880ff]", badge: "bg-[#d6c7e1] text-[#643f83]" },
  done:        { dot: "bg-black",     badge: "bg-black text-white" },
}

export default function KanbanBoard() {
  const { currentUser } = useAuth()
  const queryClient     = useQueryClient()
  const isIntern  = currentUser?.role === "intern"
  const isLeader  = currentUser?.role === "leader"
  const role      = currentUser?.role ?? "intern"
  const tasksKey  = ["tasks", role]

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  const [activeCard,    setActiveCard]    = useState<BoardCard | null>(null)
  const [dragEpic,      setDragEpic]      = useState<Epic | null>(null)
  const [selectedCard,  setSelectedCard]  = useState<BoardCard | null>(null)
  const [pendingDrop,   setPendingDrop]   = useState<BoardCard | null>(null)
  const [createOpen,    setCreateOpen]    = useState(false)
  const [proposeOpen,        setProposeOpen]        = useState(false)
  const [proposalsOpen,      setProposalsOpen]      = useState(false)
  const [myProposalsOpen,    setMyProposalsOpen]    = useState(false)
  const [seenProposalIds,   setSeenProposalIds]    = useState<Set<string>>(
    () => new Set(JSON.parse(localStorage.getItem(`seen_proposals_${currentUser?.id}`) ?? "[]"))
  )
  const [boardEpic,     setBoardEpic]     = useState<Epic | null>(null)   // leader drill-down
  const [modulesOpen,   setModulesOpen]   = useState(false)

  // ── data ────────────────────────────────────────────────────────────────────
  const { data: tasks = [], isLoading } = useQuery<Task[]>({
    queryKey: tasksKey,
    queryFn: isIntern ? getInternTasksApi : getLeaderTasksApi,
    enabled: !!currentUser,
  })

  const { data: projects = [] } = useQuery<Project[]>({
    queryKey: ["projects", role],
    queryFn: isIntern ? getInternProjectsApi : getLeaderProjectsApi,
    enabled: !!currentUser,
  })

  const { data: epics = [] } = useQuery<Epic[]>({
    queryKey: ["epics", "leader"],
    queryFn: getLeaderEpicsApi,
    enabled: isLeader,
  })

  const { data: leaderProposals = [] } = useQuery<Proposal[]>({
    queryKey: ["proposals", "leader"],
    queryFn: getLeaderAllProposalsApi,
    enabled: isLeader,
  })

  const { data: internProposals = [] } = useQuery<Proposal[]>({
    queryKey: ["proposals", "intern"],
    queryFn: getInternProposalsApi,
    enabled: isIntern,
    refetchInterval: 30_000,
  })

  const pendingProposals = leaderProposals.filter((p) => p.status === "pending")
  const projectName = (id: string | null) => (id ? projects.find((p) => p.id === id)?.title ?? null : null)

  const taskToCard = (t: Task): BoardCard => ({
    id:                 t.id,
    title:              t.title,
    epic_id:            t.epic_id            ?? null,
    epic_title:         t.epic_title         ?? null,
    epic_description:   t.epic_description   ?? null,
    module_title:       t.module_title       ?? null,
    module_description: t.module_description ?? null,
    project_title:      projectName(t.project_id ?? null),
    status:             t.status,
    due_date:           t.due_date,
    description:        t.description,
    expected_time:      t.expected_time ? Number(t.expected_time) : null,
    actual_time:        t.actual_time   ? Number(t.actual_time)   : null,
    assignees:          t.assignees,
    submissions:        t.submissions,
  })

  // Leader in epic-list mode shows epics; otherwise the board shows task cards
  const leaderEpicMode = isLeader && !boardEpic
  const visibleTasks   = isLeader && boardEpic ? tasks.filter((t) => t.epic_id === boardEpic.id) : tasks
  const cards          = visibleTasks.map(taskToCard)

  // ── task move (optimistic) ───────────────────────────────────────────────────
  const moveMutation = useMutation({
    mutationFn: ({ id, newStatus }: { id: string; newStatus: WorkStatus }) =>
      isIntern ? updateInternTaskStatusApi(id, newStatus) : updateLeaderTaskApi(id, { status: newStatus }),
    onMutate: async ({ id, newStatus }) => {
      await queryClient.cancelQueries({ queryKey: tasksKey })
      const previous = queryClient.getQueryData<Task[]>(tasksKey)
      queryClient.setQueryData<Task[]>(tasksKey, (old = []) =>
        old.map((t) => (t.id === id ? { ...t, status: newStatus } : t))
      )
      return { previous }
    },
    onError: (_e, _v, ctx) => { if (ctx?.previous) queryClient.setQueryData(tasksKey, ctx.previous) },
    onSettled: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
  })

  // ── epic move (leader, optimistic) ───────────────────────────────────────────
  const moveEpicMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: WorkStatus }) => updateLeaderEpicApi(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["epics", "leader"] })
      const previous = queryClient.getQueryData<Epic[]>(["epics", "leader"])
      queryClient.setQueryData<Epic[]>(["epics", "leader"], (old = []) =>
        old.map((e) => (e.id === id ? { ...e, status } : e))
      )
      return { previous }
    },
    onError: (_e, _v, ctx) => { if (ctx?.previous) queryClient.setQueryData(["epics", "leader"], ctx.previous) },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["epics", "leader"] }),
  })

  // ── dnd handlers ──────────────────────────────────────────────────────────────
  const handleDragStart = (event: DragStartEvent) => {
    const id = String(event.active.id)
    if (leaderEpicMode) setDragEpic(epics.find((e) => e.id === id) ?? null)
    else setActiveCard(cards.find((c) => c.id === id) ?? null)
  }

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    setActiveCard(null)
    setDragEpic(null)
    if (!over) return
    const newStatus = String(over.id) as WorkStatus
    if (!["todo", "in_progress", "done"].includes(newStatus)) return
    const id = String(active.id)

    if (leaderEpicMode) {
      const epic = epics.find((e) => e.id === id)
      if (!epic || epic.status === newStatus) return
      moveEpicMutation.mutate({ id, status: newStatus })
      return
    }

    const card = cards.find((c) => c.id === id)
    if (!card || card.status === newStatus) return
    if (newStatus === "done" && isIntern) { setPendingDrop(card); return }   // intern submits on done
    moveMutation.mutate({ id, newStatus })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-xl font-bold text-black tracking-tight">Task Board</h1>
          <p className="text-sm text-gray-400 mt-0.5">
            {leaderEpicMode
              ? `${epics.length} epic${epics.length !== 1 ? "s" : ""}`
              : `${cards.length} task${cards.length !== 1 ? "s" : ""}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isIntern && (
            <>
              <button onClick={() => {
                  setMyProposalsOpen(true)
                  // mark all currently reviewed proposals as seen
                  const reviewedIds = internProposals
                    .filter((p) => p.status !== "pending")
                    .map((p) => p.id)
                  const next = new Set([...seenProposalIds, ...reviewedIds])
                  setSeenProposalIds(next)
                  localStorage.setItem(`seen_proposals_${currentUser?.id}`, JSON.stringify([...next]))
                }}
                className="relative flex items-center gap-1.5 h-9 px-4 border border-gray-200 text-sm font-medium rounded-xl text-gray-700 hover:bg-gray-50 transition-colors">
                <MessageSquare size={14} /> My proposals
                {internProposals.filter((p) => p.status !== "pending" && !seenProposalIds.has(p.id)).length > 0 && (
                  <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-[#a880ff] text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                    {internProposals.filter((p) => p.status !== "pending" && !seenProposalIds.has(p.id)).length}
                  </span>
                )}
              </button>
              <button onClick={() => setProposeOpen(true)}
                className="flex items-center gap-1.5 h-9 px-4 border border-gray-200 text-sm font-medium rounded-xl text-gray-700 hover:bg-gray-50 transition-colors">
                <Lightbulb size={14} /> Propose idea
              </button>
            </>
          )}
          {isLeader && (
            <button onClick={() => setProposalsOpen(true)}
              className="relative flex items-center gap-1.5 h-9 px-4 border border-gray-200 text-sm font-medium rounded-xl text-gray-700 hover:bg-gray-50 transition-colors">
              <MessageSquare size={14} /> Proposals
              {pendingProposals.length > 0 && (
                <span className="absolute -top-1.5 -right-1.5 w-4 h-4 bg-[#a880ff] text-white text-[9px] font-bold rounded-full flex items-center justify-center">
                  {pendingProposals.length}
                </span>
              )}
            </button>
          )}
          {isLeader && (
            <button onClick={() => setCreateOpen(true)}
              className="h-9 px-4 bg-black text-white text-sm font-medium rounded-xl hover:bg-gray-900 transition-colors">
              + New task
            </button>
          )}
        </div>
      </div>

      {/* ── Leader breadcrumb (inside an epic) ─────────────────────────────── */}
      {isLeader && boardEpic && (
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <button onClick={() => setBoardEpic(null)}
            className="flex items-center gap-2 text-xs font-semibold text-gray-400 uppercase tracking-wider hover:text-black transition-colors w-fit">
            <ArrowLeft size={13} /> Epics
            <span className="text-gray-300">/</span>
            <span className="normal-case tracking-normal text-black">{boardEpic.title}</span>
          </button>
          <button onClick={() => setModulesOpen(true)}
            className="flex items-center gap-1.5 h-8 px-3 border border-gray-200 text-gray-500 text-xs font-medium rounded-lg hover:border-black hover:text-black transition-colors">
            <Layers size={12} /> Modules
          </button>
        </div>
      )}

      {/* ── Board ──────────────────────────────────────────────────────────── */}
      <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {leaderEpicMode
            ? COLUMNS.map((col) => (
                <EpicColumn
                  key={col.status}
                  title={col.title} status={col.status}
                  epics={epics.filter((e) => (e.status ?? "todo") === col.status)}
                  tasks={tasks}
                  projectName={projectName}
                  onEpicClick={setBoardEpic}
                />
              ))
            : COLUMNS.map((col) => (
                <Column
                  key={col.status}
                  title={col.title} status={col.status}
                  cards={cards.filter((c) => c.status === col.status)}
                  onCardClick={setSelectedCard}
                />
              ))}
        </div>
        <DragOverlay>
          {activeCard && <TaskCard card={activeCard} onClick={() => {}} />}
          {dragEpic && (
            <EpicCard
              epic={dragEpic}
              taskCount={tasks.filter((t) => t.epic_id === dragEpic.id).length}
              doneCount={tasks.filter((t) => t.epic_id === dragEpic.id && t.status === "done").length}
              projectName={projectName(dragEpic.project_id)}
              onClick={() => {}} isDragOverlay
            />
          )}
        </DragOverlay>
      </DndContext>

      {/* Intern drag-to-done submit dialog */}
      {pendingDrop && (
        <SubmitDialog card={pendingDrop} tasksKey={tasksKey} onDone={() => setPendingDrop(null)} />
      )}

      <TaskModal
        card={selectedCard}
        open={!!selectedCard}
        onClose={() => setSelectedCard(null)}
        tasksKey={tasksKey}
      />

      {isLeader && createOpen && (
        <CreateTaskModal open={createOpen} onClose={() => setCreateOpen(false)} tasksKey={tasksKey} />
      )}

      {isIntern && proposeOpen && (
        <CreateProposalModal tasks={tasks} onClose={() => setProposeOpen(false)} />
      )}

      {isLeader && proposalsOpen && (
        <LeaderProposalsModal
          proposals={leaderProposals}
          onClose={() => setProposalsOpen(false)}
          onRefresh={() => queryClient.invalidateQueries({ queryKey: ["proposals", "leader"] })}
        />
      )}

      {isLeader && modulesOpen && boardEpic && (
        <ManageModulesModal
          epic={boardEpic}
          role="leader"
          onClose={() => setModulesOpen(false)}
        />
      )}

      {isIntern && myProposalsOpen && (
        <InternProposalsModal
          proposals={internProposals}
          onClose={() => setMyProposalsOpen(false)}
        />
      )}
    </div>
  )
}

/* ── Epic column (leader drill-down level 1) ─────────────────────────────── */
function EpicColumn({ title, status, epics, tasks, projectName, onEpicClick }: {
  title: string; status: WorkStatus; epics: Epic[]; tasks: Task[]
  projectName: (id: string | null) => string | null
  onEpicClick: (e: Epic) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const s = STATUS_STYLE[status]
  return (
    <div ref={setNodeRef} className={cn(
      "flex flex-col gap-3 rounded-2xl border p-4 min-h-[360px] transition-colors",
      isOver ? "border-[#a880ff] bg-[#a880ff]/5" : "border-gray-100 bg-gray-50/50"
    )}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full", s.dot)} />
          <span className="text-xs font-semibold text-black uppercase tracking-widest">{title}</span>
        </div>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", s.badge)}>{epics.length}</span>
      </div>
      <div className="flex flex-col gap-2 flex-1">
        {epics.map((epic) => (
          <EpicCard
            key={epic.id} epic={epic}
            taskCount={tasks.filter((t) => t.epic_id === epic.id).length}
            doneCount={tasks.filter((t) => t.epic_id === epic.id && t.status === "done").length}
            projectName={projectName(epic.project_id)}
            onClick={() => onEpicClick(epic)}
          />
        ))}
      </div>
      {epics.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-300">No epics</p>
        </div>
      )}
    </div>
  )
}

function EpicCard({ epic, taskCount, doneCount, projectName, onClick, isDragOverlay }: {
  epic: Epic; taskCount: number; doneCount: number; projectName: string | null
  onClick: () => void; isDragOverlay?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: epic.id })
  const navigate = useNavigate()
  const [detailOpen, setDetailOpen] = useState(false)
  return (
    <>
      <div
        ref={setNodeRef}
        style={{ transform: CSS.Translate.toString(transform), opacity: isDragging && !isDragOverlay ? 0.4 : 1 }}
        {...attributes} {...listeners}
        onClick={onClick}
        className={cn(
          "bg-white border-2 border-[#643f83] rounded-xl p-3 cursor-pointer select-none transition-all hover:shadow-md",
          isDragging && !isDragOverlay && "shadow-lg"
        )}
      >
        <div className="flex items-start justify-between gap-2 mb-0.5">
          <div className="min-w-0">
            <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Epic</span>
            <p className="text-sm font-semibold text-black leading-snug">{epic.title}</p>
          </div>
          <ChevronRight size={14} className="text-gray-300 flex-shrink-0 mt-0.5" />
        </div>
        {projectName && <p className="text-[11px] text-gray-500 mb-1">{projectName}</p>}
        {epic.description && (
          <p className="text-[11px] text-gray-400 leading-relaxed line-clamp-2 mb-1">{epic.description}</p>
        )}
        <div className="flex items-center justify-between mt-1">
          <span className="text-[10px] text-gray-400">
            {doneCount}/{taskCount} task{taskCount !== 1 ? "s" : ""} done
          </span>
          <div className="flex items-center gap-2">
            <button
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); setDetailOpen(true) }}
              className="flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-[#643f83] transition-colors"
              title="View details"
            >
              <Info size={11} /> Details
            </button>
            <button
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); navigate({ to: "/interns/mind-map/$epicId", params: { epicId: epic.id } }) }}
              className="flex items-center gap-1 text-[10px] font-medium text-[#643f83] hover:text-[#4a2d63] transition-colors"
            >
              <Network size={11} /> Mind map
            </button>
          </div>
        </div>
      </div>
      <EpicDetailModal
        epic={epic}
        projectName={projectName ?? ""}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </>
  )
}

/* ── Intern drag-to-done submit dialog ───────────────────────────────────── */
function SubmitDialog({ card, tasksKey, onDone }: { card: BoardCard; tasksKey: string[]; onDone: () => void }) {
  const queryClient = useQueryClient()
  const [link,       setLink]       = useState("")
  const [note,       setNote]       = useState("")
  const [actualTime, setActualTime] = useState("")

  const mutation = useMutation({
    mutationFn: () => submitTaskWorkApi(card.id, {
      link,
      note: note || undefined,
      actual_time: actualTime ? Number(actualTime) : undefined,
    }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: tasksKey }); onDone() },
  })

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl p-6 flex flex-col gap-4 shadow-2xl">
        <div>
          <p className="text-base font-semibold text-black">Submit work</p>
          <p className="text-sm text-gray-500 mt-0.5">{card.title}</p>
        </div>
        <input value={link} onChange={(e) => setLink(e.target.value)}
          placeholder="Link (GitHub, Figma, Drive…)" autoFocus
          className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
        <textarea value={note} onChange={(e) => setNote(e.target.value)}
          placeholder="Note (optional)" rows={2}
          className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1.5">
            Time spent (hours)
            {card.expected_time && <span className="text-gray-400 font-normal"> · expected {card.expected_time}h</span>}
          </label>
          <input type="number" min="0" step="0.5" value={actualTime} onChange={(e) => setActualTime(e.target.value)}
            placeholder="e.g. 2.5"
            className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
        </div>
        <div className="flex gap-2">
          <button onClick={onDone}
            className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
            Cancel
          </button>
          <button onClick={() => mutation.mutate()}
            disabled={!link.trim() || mutation.isPending}
            className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
            {mutation.isPending ? "Submitting…" : "Submit"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Intern: propose idea modal ──────────────────────────────────────────── */
function CreateProposalModal({ tasks, onClose }: { tasks: Task[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const epics = tasks
    .filter((t) => t.epic_id && t.epic_title)
    .reduce((acc, t) => {
      if (!acc.find((e) => e.id === t.epic_id)) acc.push({ id: t.epic_id!, title: t.epic_title! })
      return acc
    }, [] as { id: string; title: string }[])

  const [epicId,      setEpicId]      = useState(epics[0]?.id ?? "")
  const [title,       setTitle]       = useState("")
  const [description, setDescription] = useState("")
  const [error,       setError]       = useState("")

  const mutation = useMutation({
    mutationFn: () => createProposalApi(epicId, { title, description: description || undefined }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["proposals"] }); onClose() },
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to submit proposal"),
  })

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white rounded-2xl p-6 flex flex-col gap-4 shadow-2xl">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-base font-semibold text-black">Propose an idea</p>
            <p className="text-xs text-gray-400 mt-0.5">Your leader will review it</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors">
            <X size={16} />
          </button>
        </div>

        {epics.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-4">
            You need to be assigned to a task before you can propose ideas.
          </p>
        ) : (
          <>
            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1.5">Epic</label>
              <select value={epicId} onChange={(e) => setEpicId(e.target.value)}
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm bg-white focus:outline-none focus:border-black transition-colors">
                {epics.map((e) => <option key={e.id} value={e.id}>{e.title}</option>)}
              </select>
            </div>
            <input value={title} onChange={(e) => setTitle(e.target.value)}
              placeholder="What's your idea?" autoFocus
              className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
            <textarea value={description} onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe it in more detail (optional)" rows={3}
              className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors" />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <div className="flex gap-2">
              <button onClick={onClose}
                className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                Cancel
              </button>
              <button onClick={() => mutation.mutate()}
                disabled={!title.trim() || !epicId || mutation.isPending}
                className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                {mutation.isPending ? "Submitting…" : "Submit proposal"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

/* ── Leader: proposals review modal ─────────────────────────────────────── */
function LeaderProposalsModal({ proposals, onClose, onRefresh }: {
  proposals: Proposal[]; onClose: () => void; onRefresh: () => void
}) {
  const [selected, setSelected] = useState<Proposal | null>(null)

  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => reviewProposalApi(id, { status }, "leader"),
    onSuccess: () => { onRefresh(); setSelected(null) },
  })

  const pending  = proposals.filter((p) => p.status === "pending")
  const reviewed = proposals.filter((p) => p.status !== "pending")

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
            <div>
              <p className="text-base font-semibold text-black">Proposals</p>
              <p className="text-xs text-gray-400 mt-0.5">{pending.length} pending · {reviewed.length} reviewed</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors">
              <X size={16} />
            </button>
          </div>

          <div className="overflow-y-auto flex-1 p-4 flex flex-col gap-3">
            {proposals.length === 0 && (
              <div className="flex items-center justify-center h-28">
                <p className="text-sm text-gray-400">No proposals yet from your team</p>
              </div>
            )}

            {pending.length > 0 && (
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Pending</p>
            )}
            {pending.map((p) => (
              <button key={p.id} onClick={() => setSelected(p)}
                className="w-full text-left flex flex-col gap-1.5 p-3.5 border border-[#d6c7e1] rounded-xl bg-[#d6c7e1]/10 hover:bg-[#d6c7e1]/20 transition-colors">
                <p className="text-sm font-semibold text-black">{p.title}</p>
                {p.description && <p className="text-xs text-gray-500 line-clamp-2">{p.description}</p>}
                <p className="text-[11px] text-gray-400">by {p.proposer_name ?? "Unknown"} · tap to review</p>
              </button>
            ))}

            {reviewed.length > 0 && (
              <>
                <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mt-2">Reviewed</p>
                {reviewed.map((p) => (
                  <button key={p.id} onClick={() => setSelected(p)}
                    className="w-full text-left flex items-start justify-between gap-2 p-3.5 border border-gray-100 rounded-xl opacity-70 hover:opacity-100 hover:bg-gray-50 transition-all">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-black truncate">{p.title}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">by {p.proposer_name ?? "Unknown"}</p>
                    </div>
                    <span className={cn(
                      "text-[10px] font-semibold px-2 py-0.5 rounded-full flex-shrink-0",
                      p.status === "accepted" ? "bg-black text-white" : "bg-gray-100 text-gray-400"
                    )}>
                      {p.status}
                    </span>
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      {selected && (
        <ProposalDetailDialog
          proposal={selected}
          onClose={() => setSelected(null)}
          onAccept={selected.status === "pending" ? () => reviewMutation.mutate({ id: selected.id, status: "accepted" }) : undefined}
          onReject={selected.status === "pending" ? () => reviewMutation.mutate({ id: selected.id, status: "rejected" }) : undefined}
          isPending={reviewMutation.isPending}
        />
      )}
    </>
  )
}

/* ── Intern: view my proposals modal ─────────────────────────────────────── */
function InternProposalsModal({ proposals, onClose }: {
  proposals: Proposal[]; onClose: () => void
}) {
  const [selected, setSelected] = useState<Proposal | null>(null)

  const pending  = proposals.filter((p) => p.status === "pending")
  const reviewed = proposals.filter((p) => p.status !== "pending")

  return createPortal(
    <>
      <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
        <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl flex flex-col max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-gray-100 flex-shrink-0">
            <div>
              <p className="text-base font-semibold text-black">My Proposals</p>
              <p className="text-xs text-gray-400 mt-0.5">{pending.length} pending · {reviewed.length} reviewed</p>
            </div>
            <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-black transition-colors">
              <X size={16} />
            </button>
          </div>

          <div className="overflow-y-auto flex-1 p-4 flex flex-col gap-3">
            {proposals.length === 0 && (
              <div className="flex items-center justify-center h-28">
                <p className="text-sm text-gray-400">You haven't submitted any proposals yet</p>
              </div>
            )}

            {pending.length > 0 && (
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Pending review</p>
            )}
            {pending.map((p) => (
              <button key={p.id} onClick={() => setSelected(p)}
                className="w-full text-left flex flex-col gap-1.5 p-3.5 border border-[#d6c7e1] rounded-xl bg-[#d6c7e1]/10 hover:bg-[#d6c7e1]/20 transition-colors">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-black truncate">{p.title}</p>
                  <span className="text-[10px] font-semibold px-2.5 py-1 rounded-full bg-[#d6c7e1] text-[#643f83] flex-shrink-0">pending</span>
                </div>
                {p.description && <p className="text-xs text-gray-500 line-clamp-2">{p.description}</p>}
                <p className="text-[11px] text-gray-400">
                  {new Date(p.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                </p>
              </button>
            ))}

            {reviewed.length > 0 && (
              <>
                <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mt-1">Reviewed</p>
                {reviewed.map((p) => (
                  <button key={p.id} onClick={() => setSelected(p)}
                    className={cn(
                      "w-full text-left flex items-start justify-between gap-2 p-3.5 rounded-xl border transition-all hover:shadow-sm",
                      p.status === "accepted"
                        ? "border-green-200 bg-green-50/60 hover:bg-green-50"
                        : "border-red-100 bg-red-50/40 hover:bg-red-50/60"
                    )}>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-black truncate">{p.title}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">
                        {new Date(p.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                      </p>
                    </div>
                    <span className={cn(
                      "text-[10px] font-semibold px-2.5 py-1 rounded-full flex-shrink-0",
                      p.status === "accepted" ? "bg-black text-white" : "bg-red-100 text-red-500"
                    )}>
                      {p.status}
                    </span>
                  </button>
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      {selected && (
        <ProposalDetailDialog
          proposal={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </>,
    document.body
  )
}
