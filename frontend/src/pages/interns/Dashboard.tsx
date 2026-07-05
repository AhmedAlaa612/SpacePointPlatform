import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  DndContext, DragOverlay, PointerSensor, useSensor, useSensors, useDroppable, useDraggable,
} from "@dnd-kit/core"
import type { DragEndEvent, DragStartEvent } from "@dnd-kit/core"
import { CSS } from "@dnd-kit/utilities"
import {
  Plus, X, Pencil, Clock, ExternalLink, ChevronRight, Trash2, Check, RotateCcw, ArrowLeft, Users, Network, Layers, Info,
} from "lucide-react"
import KanbanBoard from "@/pages/interns/components/kanban/KanbanBoard"
import EpicDetailModal from "@/pages/interns/components/kanban/EpicDetailModal"
import ManageModulesModal from "@/pages/interns/components/ManageModulesModal"
import ProposalDetailDialog from "@/pages/interns/components/ProposalDetailDialog"
import { useAuth } from "@/context/AuthContext"
import type { Project, ProjectStatus, Task, Team, WorkStatus, Epic, Proposal } from "@/types/interns"
import { getProjectsApi, createProjectApi, updateProjectApi, deleteProjectApi } from "@/api/interns/projects"
import { getAllTasksApi, createAdminTaskApi, updateTaskApi, deleteTaskApi, adminReviewSubmissionApi } from "@/api/interns/tasks"
import { getAllEpicsApi, getProjectEpicsApi, createEpicApi, deleteEpicApi, updateEpicApi } from "@/api/interns/epics"
import { getEpicProposalsApi, reviewProposalApi } from "@/api/interns/proposals"
import { getTeamsApi } from "@/api/interns/teams"
import { cn } from "@/lib/utils"

/* ── styling ─────────────────────────────────────────────────────────── */
const TASK_STATUS: Record<WorkStatus, { dot: string; badge: string }> = {
  todo:        { dot: "bg-gray-300 dark:bg-muted-foreground",  badge: "bg-gray-100 text-gray-500 dark:bg-muted dark:text-muted-foreground" },
  in_progress: { dot: "bg-[#a880ff]", badge: "bg-[#d6c7e1] text-[#643f83] dark:bg-[#d6c7e1]/10 dark:text-[#d6c7e1]" },
  done:        { dot: "bg-black dark:bg-[#d6c7e1]",     badge: "bg-black text-white dark:bg-[#d6c7e1] dark:text-[#643f83]" },
}

const PROJ_COL: Record<string, { label: string; dot: string; badge: string; id: string }> = {
  active:    { label: "Active",       dot: "bg-[#a880ff]", badge: "bg-[#d6c7e1] text-[#643f83]", id: "proj_active" },
  completed: { label: "Done",        dot: "bg-black",     badge: "bg-black text-white",           id: "proj_completed" },
}

const TASK_COLS: { title: string; status: WorkStatus }[] = [
  { title: "To do",       status: "todo" },
  { title: "In progress", status: "in_progress" },
  { title: "Done",        status: "done" },
]

/* ================================================================== */
/* Entry point                                                         */
/* ================================================================== */
export default function Dashboard() {
  const { currentUser } = useAuth()
  if (!currentUser) return null
  if (currentUser.role === "admin") return <AdminDashboard />
  return <KanbanBoard />
}

/* ================================================================== */
/* Admin dashboard                                                     */
/* ================================================================== */
function AdminDashboard() {
  const queryClient = useQueryClient()

  /* modal / selection state */
  const [selectedTask,      setSelectedTask]      = useState<Task | null>(null)
  const [activeProject,     setActiveProject]     = useState<Project | null>(null)
  const [createProjectOpen, setCreateProjectOpen] = useState(false)

  /* board drill-down: null = epic view, set = that epic's task view */
  const [boardEpic, setBoardEpic] = useState<Epic | null>(null)

  /* drag state — separate for projects / epics / tasks */
  const [dragProject, setDragProject] = useState<Project | null>(null)
  const [dragEpic,    setDragEpic]    = useState<Epic | null>(null)
  const [dragTask,    setDragTask]    = useState<Task | null>(null)
  const [projectFilter, setProjectFilter] = useState("all")

  /* data */
  const { data: tasks    = [], isLoading } = useQuery<Task[]>({    queryKey: ["tasks", "admin"], queryFn: getAllTasksApi })
  const { data: projects = [] }            = useQuery<Project[]>({ queryKey: ["projects"],       queryFn: getProjectsApi })
  const { data: allEpics = [] }            = useQuery<Epic[]>({    queryKey: ["epics", "all"],   queryFn: getAllEpicsApi })

  /* sensors */
  const projSensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))
  const taskSensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }))

  /* ── project move mutation ─────────────────────────────────────── */
  const moveProjectMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: ProjectStatus }) =>
      updateProjectApi(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["projects"] })
      const prev = queryClient.getQueryData<Project[]>(["projects"])
      queryClient.setQueryData<Project[]>(["projects"], (old) =>
        (old ?? []).map((p) => (p.id === id ? { ...p, status } : p))
      )
      return { prev }
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) queryClient.setQueryData(["projects"], ctx.prev) },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["projects"] }),
  })

  /* ── delete project mutation ──────────────────────────────────── */
  const deleteProjectMutation = useMutation({
    mutationFn: (id: string) => deleteProjectApi(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] })
      queryClient.invalidateQueries({ queryKey: ["tasks", "admin"] })
      setActiveProject(null)
    },
  })

  /* ── task move mutation ────────────────────────────────────────── */
  const moveTaskMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: WorkStatus }) => updateTaskApi(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["tasks", "admin"] })
      const prev = queryClient.getQueryData<Task[]>(["tasks", "admin"])
      queryClient.setQueryData<Task[]>(["tasks", "admin"], (old) =>
        (old ?? []).map((t) => (t.id === id ? { ...t, status } : t))
      )
      return { prev }
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) queryClient.setQueryData(["tasks", "admin"], ctx.prev) },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["tasks", "admin"] }),
  })

  /* ── epic move mutation ────────────────────────────────────────── */
  const moveEpicMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: WorkStatus }) => updateEpicApi(id, { status }),
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ["epics", "all"] })
      const prev = queryClient.getQueryData<Epic[]>(["epics", "all"])
      queryClient.setQueryData<Epic[]>(["epics", "all"], (old) =>
        (old ?? []).map((e) => (e.id === id ? { ...e, status } : e))
      )
      return { prev }
    },
    onError: (_e, _v, ctx) => { if (ctx?.prev) queryClient.setQueryData(["epics", "all"], ctx.prev) },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["epics"] }),
  })

  /* helpers */
  const projectName = (id: string) => projects.find((p) => p.id === id)?.title ?? "—"

  const activeProjects    = projects.filter((p) => (p.status ?? "active") === "active")
  const completedProjects = projects.filter((p) => (p.status ?? "active") === "completed")
  const filteredEpics     = projectFilter === "all" ? allEpics : allEpics.filter((e) => e.project_id === projectFilter)
  const boardEpicTasks    = boardEpic ? tasks.filter((t) => t.epic_id === boardEpic.id) : []

  /* ── project dnd handlers ──────────────────────────────────────── */
  const onProjDragStart = (e: DragStartEvent) =>
    setDragProject(projects.find((p) => p.id === String(e.active.id)) ?? null)

  const onProjDragEnd = (e: DragEndEvent) => {
    setDragProject(null)
    const { active, over } = e
    if (!over) return
    const colId = String(over.id)
    const newStatus: ProjectStatus = colId === "proj_completed" ? "completed" : "active"
    const proj = projects.find((p) => p.id === String(active.id))
    if (!proj || proj.status === newStatus) return
    moveProjectMutation.mutate({ id: proj.id, status: newStatus })
  }

  /* ── epic dnd handlers ─────────────────────────────────────────── */
  const onEpicDragStart = (e: DragStartEvent) =>
    setDragEpic(allEpics.find((ep) => ep.id === String(e.active.id)) ?? null)

  const onEpicDragEnd = (e: DragEndEvent) => {
    setDragEpic(null)
    const { active, over } = e
    if (!over) return
    const ns = String(over.id) as WorkStatus
    if (!["todo", "in_progress", "done"].includes(ns)) return
    const epic = allEpics.find((ep) => ep.id === String(active.id))
    if (!epic || epic.status === ns) return
    moveEpicMutation.mutate({ id: epic.id, status: ns })
  }

  /* ── task dnd handlers ─────────────────────────────────────────── */
  const onTaskDragStart = (e: DragStartEvent) =>
    setDragTask(tasks.find((t) => t.id === String(e.active.id)) ?? null)

  const onTaskDragEnd = (e: DragEndEvent) => {
    setDragTask(null)
    const { active, over } = e
    if (!over) return
    const ns = String(over.id) as WorkStatus
    if (!["todo", "in_progress", "done"].includes(ns)) return
    const task = tasks.find((t) => t.id === String(active.id))
    if (!task || task.status === ns) return
    moveTaskMutation.mutate({ id: task.id, status: ns })
  }

  if (isLoading) return <PageSpinner />

  return (
    <div className="flex flex-col gap-10">

      {/* ── Page header ──────────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-bold text-foreground tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            {projects.length} project{projects.length !== 1 ? "s" : ""} · {allEpics.length} epic{allEpics.length !== 1 ? "s" : ""}
          </p>
        </div>
        <button
          onClick={() => setCreateProjectOpen(true)}
          className="flex items-center gap-1.5 h-9 px-4 bg-primary text-primary-foreground text-sm font-medium rounded-xl hover:opacity-90 transition-colors"
        >
          <Plus size={14} /> New project
        </button>
      </div>

      {/* ── Projects kanban (draggable) ───────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Projects</p>

        <DndContext sensors={projSensors} onDragStart={onProjDragStart} onDragEnd={onProjDragEnd}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <ProjectColumn
              colKey="active"
              projects={activeProjects}
              epicCounts={allEpics}
              onManage={setActiveProject}
            />
            <ProjectColumn
              colKey="completed"
              projects={completedProjects}
              epicCounts={allEpics}
              onManage={setActiveProject}
            />
          </div>

          <DragOverlay>
            {dragProject && <ProjectCardOverlay project={dragProject} />}
          </DragOverlay>
        </DndContext>
      </section>

      {/* ── Epic / task drill-down board ─────────────────────────────── */}
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          {boardEpic ? (
            <button
              onClick={() => setBoardEpic(null)}
              className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider hover:text-foreground transition-colors"
            >
              <ArrowLeft size={13} /> Epics
              <span className="text-muted-foreground/60">/</span>
              <span className="normal-case tracking-normal text-foreground">{boardEpic.title}</span>
            </button>
          ) : (
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Epics
              {projectFilter !== "all" && (
                <span className="ml-2 font-normal normal-case text-muted-foreground">· {projectName(projectFilter)}</span>
              )}
            </p>
          )}

          {!boardEpic && (
            <div className="relative">
              <select
                value={projectFilter}
                onChange={(e) => setProjectFilter(e.target.value)}
                className="h-8 pl-3 pr-8 text-xs border border-border rounded-lg bg-card text-foreground focus:outline-none focus:border-primary transition-colors appearance-none cursor-pointer"
              >
                <option value="all">All projects</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id} className="bg-card text-foreground">{p.title}</option>
                ))}
              </select>
              <ChevronRight size={10} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none rotate-90" />
            </div>
          )}
        </div>

        {boardEpic ? (
          /* ── Task level (drilled into an epic) ───────────────────── */
          <DndContext sensors={taskSensors} onDragStart={onTaskDragStart} onDragEnd={onTaskDragEnd}>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {TASK_COLS.map((col) => (
                <AdminTaskColumn
                  key={col.status}
                  title={col.title} status={col.status}
                  tasks={boardEpicTasks.filter((t) => t.status === col.status)}
                  projectName={projectName}
                  onTaskClick={setSelectedTask}
                />
              ))}
            </div>
            <DragOverlay>
              {dragTask && (
                <AdminTaskCard
                  task={dragTask}
                  projectName={projectName(dragTask.project_id ?? "")}
                  onClick={() => {}} isDragOverlay
                />
              )}
            </DragOverlay>
          </DndContext>
        ) : (
          /* ── Epic level ──────────────────────────────────────────── */
          <DndContext sensors={taskSensors} onDragStart={onEpicDragStart} onDragEnd={onEpicDragEnd}>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              {TASK_COLS.map((col) => (
                <AdminEpicColumn
                  key={col.status}
                  title={col.title} status={col.status}
                  epics={filteredEpics.filter((e) => (e.status ?? "todo") === col.status)}
                  tasks={tasks}
                  projectName={projectName}
                  onEpicClick={setBoardEpic}
                />
              ))}
            </div>
            <DragOverlay>
              {dragEpic && (
                <AdminEpicCard
                  epic={dragEpic}
                  taskCount={tasks.filter((t) => t.epic_id === dragEpic.id).length}
                  doneCount={tasks.filter((t) => t.epic_id === dragEpic.id && t.status === "done").length}
                  projectName={projectName(dragEpic.project_id)}
                  onClick={() => {}} isDragOverlay
                />
              )}
            </DragOverlay>
          </DndContext>
        )}
      </section>

      {/* ── Project manage panel ─────────────────────────────────────── */}
      {activeProject && (
        <ProjectTasksPanel
          project={activeProject}
          tasks={tasks.filter((t) => t.project_id === activeProject.id)}
          onTaskClick={setSelectedTask}
          onClose={() => setActiveProject(null)}
          onTaskCreated={() => queryClient.invalidateQueries({ queryKey: ["tasks", "admin"] })}
          onToggleStatus={() =>
            moveProjectMutation.mutate({
              id: activeProject.id,
              status: (activeProject.status ?? "active") === "active" ? "completed" : "active",
            })
          }
          onDelete={() => {
            if (confirm(`Delete "${activeProject.title}" and all its tasks?`))
              deleteProjectMutation.mutate(activeProject.id)
          }}
        />
      )}

      {/* ── Task detail modal ─────────────────────────────────────────── */}
      {selectedTask && (
        <AdminTaskModal
          key={selectedTask.id}
          task={selectedTask}
          projectName={projectName(selectedTask.project_id ?? "")}
          elevated={!!activeProject}
          onClose={() => setSelectedTask(null)}
          onSaved={(updated) => {
            queryClient.setQueryData<Task[]>(["tasks", "admin"], (old) =>
              (old ?? []).map((t) => (t.id === updated.id ? updated : t))
            )
            setSelectedTask(updated)
          }}
          onDeleted={(id) => {
            queryClient.setQueryData<Task[]>(["tasks", "admin"], (old) =>
              (old ?? []).filter((t) => t.id !== id)
            )
            setSelectedTask(null)
          }}
        />
      )}

      {/* ── Create project modal ─────────────────────────────────────── */}
      {createProjectOpen && (
        <CreateProjectModal
          onClose={() => setCreateProjectOpen(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ["projects"] })
            setCreateProjectOpen(false)
          }}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Project column — useDroppable + scrollable card list               */
/* ================================================================== */
function ProjectColumn({ colKey, projects, epicCounts, onManage }: {
  colKey: "active" | "completed"
  projects: Project[]
  epicCounts: Epic[]
  onManage: (p: Project) => void
}) {
  const col = PROJ_COL[colKey]
  const { setNodeRef, isOver } = useDroppable({ id: col.id })

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "flex flex-col rounded-2xl border p-4 transition-colors",
        isOver
          ? "border-[#a880ff] bg-[#a880ff]/5"
          : colKey === "active"
            ? "border-border bg-muted/20"
            : "border-border bg-muted/40 dark:bg-card/30"
      )}
    >
      {/* Column header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full", col.dot)} />
          <span className="text-xs font-semibold text-foreground uppercase tracking-widest">{col.label}</span>
        </div>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", col.badge)}>
          {projects.length}
        </span>
      </div>

      {/* Scrollable card list */}
      <div className="flex flex-col gap-2 overflow-y-auto max-h-[320px] pr-0.5">
        {projects.map((p) => (
          <ProjectCard
            key={p.id}
            project={p}
            epicCount={epicCounts.filter((e) => e.project_id === p.id).length}
            onManage={() => onManage(p)}
          />
        ))}
        {projects.length === 0 && (
          <div className="flex items-center justify-center h-16">
            <p className="text-xs text-gray-300">Drop here</p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ── Project card — useDraggable ─────────────────────────────────────── */
function ProjectCard({ project, epicCount, onManage }: {
  project: Project; epicCount: number; onManage: () => void
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: project.id })
  const navigate = useNavigate()
  const isDone = (project.status ?? "active") === "completed"
  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), opacity: isDragging ? 0.4 : 1 }}
      {...attributes} {...listeners}
      className={cn(
        "bg-card border border-border rounded-xl p-3.5 select-none transition-all cursor-grab active:cursor-grabbing hover:border-muted-foreground/30 hover:shadow-sm",
        isDragging && "shadow-lg"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="min-w-0">
          <p className={cn("text-sm font-semibold leading-snug truncate", isDone ? "text-muted-foreground line-through" : "text-foreground")}>
            {project.title}
          </p>
          {project.description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{project.description}</p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between">
        <span className="text-[11px] text-gray-400">
          {epicCount} epic{epicCount !== 1 ? "s" : ""}
        </span>
        <div className="flex items-center gap-3" onPointerDown={(e) => e.stopPropagation()}>
          <button
            onClick={(e) => { e.stopPropagation(); navigate({ to: "/interns/mind-map/project/$projectId", params: { projectId: project.id } }) }}
            className="flex items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-primary transition-colors"
          >
            <Network size={10} /> Map
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onManage() }}
            className="flex items-center gap-1 text-[11px] font-semibold text-[#643f83] dark:text-snuff hover:opacity-80 transition-colors"
          >
            Manage <ChevronRight size={10} />
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Drag overlay (lightweight copy, no dnd hooks) ───────────────────── */
function ProjectCardOverlay({ project }: { project: Project }) {
  return (
    <div className="bg-card border-2 border-[#a880ff] rounded-xl p-3.5 shadow-xl rotate-1 cursor-grabbing">
      <p className="text-sm font-semibold text-foreground leading-snug truncate">{project.title}</p>
    </div>
  )
}

/* ================================================================== */
/* Project manage panel — two screens: epics list → epic tasks          */
/* ================================================================== */
function ProjectTasksPanel({ project, tasks, onTaskClick, onClose, onTaskCreated, onToggleStatus, onDelete }: {
  project: Project; tasks: Task[]
  onTaskClick: (t: Task) => void; onClose: () => void; onTaskCreated: () => void
  onToggleStatus: () => void; onDelete: () => void
}) {
  const queryClient      = useQueryClient()
  const navigate         = useNavigate()
  const [activeEpic,      setActiveEpic]      = useState<Epic | null>(null)
  const [activeTab,       setActiveTab]       = useState<"tasks" | "proposals">("tasks")
  const [createEpicOpen,  setCreateEpicOpen]  = useState(false)
  const [createTaskOpen,  setCreateTaskOpen]  = useState(false)
  const [manageModulesOpen, setManageModulesOpen] = useState(false)
  const [prefillProposal, setPrefillProposal] = useState<{ title: string; description: string } | null>(null)
  const [selectedProposal, setSelectedProposal] = useState<Proposal | null>(null)
  const isDone = (project.status ?? "active") === "completed"

  const { data: epics = [], isLoading: epicsLoading } = useQuery<Epic[]>({
    queryKey: ["epics", project.id],
    queryFn: () => getProjectEpicsApi(project.id),
  })

  const deleteEpicMutation = useMutation({
    mutationFn: (epicId: string) => deleteEpicApi(epicId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["epics"] })
      queryClient.invalidateQueries({ queryKey: ["tasks", "admin"] })
      setActiveEpic(null)
    },
  })

  const updateEpicStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => updateEpicApi(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["epics", project.id] }),
  })

  const { data: proposals = [] } = useQuery<Proposal[]>({
    queryKey: ["proposals", activeEpic?.id],
    queryFn: () => getEpicProposalsApi(activeEpic!.id, "admin"),
    enabled: !!activeEpic,
  })

  const reviewProposalMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      reviewProposalApi(id, { status }, "admin"),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["proposals", activeEpic?.id] }),
  })

  const pendingCount = proposals.filter((p) => p.status === "pending").length

  /* tasks for the currently selected epic */
  const epicTasks = activeEpic
    ? tasks.filter((t) => t.epic_id === activeEpic.id)
    : []

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md bg-card border border-border rounded-2xl shadow-2xl flex flex-col max-h-[85vh] overflow-hidden text-foreground">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-2 px-4 sm:px-6 pt-5 pb-4 border-b border-border flex-shrink-0">
          {activeEpic ? (
            /* Screen 2 header — epic tasks */
            <div className="w-full flex flex-col gap-3">
              {/* Row 1: back + title + close */}
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <button onClick={() => { setActiveEpic(null); setActiveTab("tasks") }}
                    className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
                    <ArrowLeft size={15} />
                  </button>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">{activeEpic.title}</p>
                    <p className="text-xs text-muted-foreground">{epicTasks.length} task{epicTasks.length !== 1 ? "s" : ""}</p>
                  </div>
                </div>
                <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
                  <X size={16} />
                </button>
              </div>
              {/* Row 2: actions */}
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={() => navigate({ to: "/interns/mind-map/$epicId", params: { epicId: activeEpic.id } })}
                  className="flex items-center gap-1.5 h-8 px-3 border border-border text-muted-foreground text-xs font-medium rounded-lg hover:border-foreground hover:text-foreground transition-colors bg-card"
                  title="View mind map"
                >
                  <Network size={12} /> Mind map
                </button>
                <button
                  onClick={() => setCreateTaskOpen(true)}
                  className="flex items-center gap-1.5 h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:opacity-90 transition-colors"
                >
                  <Plus size={12} /> Add task
                </button>
                <button
                  onClick={() => setManageModulesOpen(true)}
                  className="flex items-center gap-1.5 h-8 px-3 border border-border text-muted-foreground text-xs font-medium rounded-lg hover:border-foreground hover:text-foreground transition-colors bg-card"
                >
                  <Layers size={12} /> Modules
                </button>
                <button
                  onClick={() => {
                    const isDoneEpic = activeEpic.status === "done"
                    updateEpicStatusMutation.mutate({
                      id: activeEpic.id,
                      status: isDoneEpic ? "todo" : "done",
                    })
                    setActiveEpic({ ...activeEpic, status: isDoneEpic ? "todo" : "done" })
                  }}
                  className={cn(
                    "flex items-center gap-1 h-8 px-3 text-xs font-medium rounded-lg border transition-colors bg-card",
                    activeEpic.status === "done"
                      ? "border-border text-muted-foreground hover:border-foreground hover:text-foreground"
                      : "border-border text-muted-foreground hover:border-foreground hover:bg-primary hover:text-primary-foreground"
                  )}
                >
                  {activeEpic.status === "done" ? <RotateCcw size={11} /> : <Check size={11} />}
                  {activeEpic.status === "done" ? "Reopen" : "Mark done"}
                </button>
                <button
                  onClick={() => { if (confirm(`Delete epic "${activeEpic.title}" and all its tasks?`)) deleteEpicMutation.mutate(activeEpic.id) }}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors ml-auto"
                  title="Delete epic"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ) : (
            /* Screen 1 header — epics list */
            <div className="w-full flex flex-col gap-3">
              {/* Row 1: title + close */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-base font-semibold text-foreground break-words">{project.title}</p>
                  {project.description && (
                    <p className="text-xs text-muted-foreground mt-0.5 break-words line-clamp-2">{project.description}</p>
                  )}
                  <p className="text-xs text-muted-foreground mt-0.5">{epics.length} epic{epics.length !== 1 ? "s" : ""} · {tasks.length} task{tasks.length !== 1 ? "s" : ""}</p>
                </div>
                <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
                  <X size={16} />
                </button>
              </div>
              {/* Row 2: actions */}
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={onToggleStatus}
                  className={cn(
                    "flex items-center gap-1 h-8 px-3 text-xs font-medium rounded-lg border transition-colors bg-card",
                    isDone
                      ? "border-border text-muted-foreground hover:border-foreground hover:text-foreground"
                      : "border-border text-muted-foreground hover:border-foreground hover:bg-primary hover:text-primary-foreground"
                  )}
                >
                  {isDone ? <RotateCcw size={11} /> : <Check size={11} />}
                  {isDone ? "Reopen" : "Mark done"}
                </button>
                <button
                  onClick={() => setCreateEpicOpen(true)}
                  className="flex items-center gap-1.5 h-8 px-3 bg-primary text-primary-foreground text-xs font-medium rounded-xl hover:opacity-90 transition-colors"
                >
                  <Plus size={12} /> Add epic
                </button>
                <button
                  onClick={() => navigate({ to: "/interns/mind-map/project/$projectId", params: { projectId: project.id } })}
                  className="flex items-center gap-1.5 h-8 px-3 border border-border text-muted-foreground text-xs font-medium rounded-lg hover:border-foreground hover:text-foreground transition-colors bg-card"
                >
                  <Network size={12} /> Project map
                </button>
                <button onClick={onDelete}
                  className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors ml-auto" title="Delete project">
                  <Trash2 size={15} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Tab bar (only shown in epic view) ──────────────────────── */}
        {activeEpic && (
          <div className="flex border-b border-border px-6 flex-shrink-0">
            {(["tasks", "proposals"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={cn(
                  "px-4 py-2.5 text-xs font-semibold capitalize border-b-2 -mb-px transition-colors",
                  activeTab === tab
                    ? "border-primary text-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}>
                {tab}
                {tab === "proposals" && pendingCount > 0 && (
                  <span className="ml-1.5 text-[9px] font-bold bg-[#a880ff] text-white px-1.5 py-0.5 rounded-full">
                    {pendingCount}
                  </span>
                )}
              </button>
            ))}
          </div>
        )}

        {/* ── Body ───────────────────────────────────────────────────── */}
        <div className="overflow-y-auto flex-1 p-4 flex flex-col gap-2">

          {/* Screen 1 — epics list */}
          {!activeEpic && (
            epicsLoading ? (
              <div className="flex items-center justify-center h-24">
                <div className="w-5 h-5 border-2 border-gray-300 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : epics.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-28 gap-3">
                <p className="text-sm text-muted-foreground">No epics yet — add one to get started</p>
                <button onClick={() => setCreateEpicOpen(true)}
                  className="flex items-center gap-1.5 h-8 px-4 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:border-foreground hover:text-foreground transition-colors">
                  <Plus size={12} /> Add the first epic
                </button>
              </div>
            ) : (
              epics.map((epic) => {
                const epicTaskCount   = tasks.filter((t) => t.epic_id === epic.id).length
                const doneCount       = tasks.filter((t) => t.epic_id === epic.id && t.status === "done").length
                const statusStyle     = TASK_STATUS[epic.status as WorkStatus] ?? TASK_STATUS.todo
                return (
                  <button key={epic.id} onClick={() => { setActiveEpic(epic); setActiveTab("tasks") }}
                    className="w-full text-left flex items-center gap-3 p-3.5 border border-border bg-card rounded-xl hover:border-muted-foreground/30 hover:bg-muted/40 transition-all group">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-semibold text-foreground truncate">{epic.title}</p>
                      <div className="flex items-center gap-2 mt-1">
                        <span className="text-[11px] text-muted-foreground">
                          {doneCount}/{epicTaskCount} task{epicTaskCount !== 1 ? "s" : ""} done
                        </span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", statusStyle.badge)}>
                        {epic.status.replace("_", " ")}
                      </span>
                      <ChevronRight size={13} className="text-muted-foreground group-hover:text-foreground transition-colors" />
                    </div>
                  </button>
                )
              })
            )
          )}

          {/* Screen 2 — tasks tab */}
          {activeEpic && activeTab === "tasks" && (
            epicTasks.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-28 gap-3">
                <p className="text-sm text-muted-foreground">No tasks in this epic yet</p>
                <button onClick={() => setCreateTaskOpen(true)}
                  className="flex items-center gap-1.5 h-8 px-4 border border-dashed border-border rounded-xl text-xs font-medium text-muted-foreground hover:border-foreground hover:text-foreground transition-colors">
                  <Plus size={12} /> Add the first task
                </button>
              </div>
            ) : (
              epicTasks.map((task) => {
                const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== "done"
                return (
                  <button key={task.id} onClick={() => onTaskClick(task)}
                    className="w-full text-left flex items-center gap-3 p-3.5 border border-border bg-card rounded-xl hover:border-muted-foreground/30 hover:bg-muted/40 transition-all group">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{task.title}</p>
                      <div className="flex items-center gap-2 mt-1 flex-wrap">
                        {task.assignees.length > 0 && (
                          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                            <Users size={9} /> {task.assignees.map(a => a.full_name.split(" ")[0]).join(", ")}
                          </span>
                        )}
                        {task.due_date && (
                          <span className={cn("flex items-center gap-1 text-[11px]", isOverdue ? "text-red-400" : "text-muted-foreground")}>
                            <Clock size={9} />
                            {new Date(task.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <span className={cn("text-[10px] font-semibold px-2 py-0.5 rounded-full", TASK_STATUS[task.status].badge)}>
                        {task.status.replace("_", " ")}
                      </span>
                      <ChevronRight size={13} className="text-muted-foreground group-hover:text-foreground transition-colors" />
                    </div>
                  </button>
                )
              })
            )
          )}

          {/* Screen 2 — proposals tab */}
          {activeEpic && activeTab === "proposals" && (
            proposals.length === 0 ? (
              <div className="flex items-center justify-center h-28">
                <p className="text-sm text-muted-foreground">No proposals yet for this epic</p>
              </div>
            ) : (
              proposals.map((p) => (
                <button key={p.id} onClick={() => setSelectedProposal(p)}
                  className={cn(
                    "w-full text-left flex flex-col gap-2 p-4 rounded-xl border transition-all",
                    p.status === "pending"
                      ? "bg-card border-border shadow-sm hover:shadow-md hover:border-muted-foreground/30"
                      : "bg-muted/30 border-border opacity-70 hover:opacity-100 hover:bg-card"
                  )}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn(
                      "text-[10px] font-semibold px-2.5 py-1 rounded-full",
                      p.status === "pending"  ? "bg-[#d6c7e1] text-[#643f83]" :
                      p.status === "accepted" ? "bg-foreground text-background" :
                      "bg-muted text-muted-foreground"
                    )}>
                      {p.status}
                    </span>
                    <p className="text-[11px] text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </p>
                  </div>
                  <p className="text-sm font-semibold text-foreground leading-snug">{p.title}</p>
                  {p.description && (
                    <p className="text-xs text-muted-foreground line-clamp-2">{p.description}</p>
                  )}
                  <p className="text-[11px] text-muted-foreground">by {p.proposer_name ?? "Unknown"} · tap to review</p>
                </button>
              ))
            )
          )}
        </div>
      </div>

      {/* Create epic modal */}
      {createEpicOpen && (
        <CreateEpicModal
          project={project}
          onClose={() => setCreateEpicOpen(false)}
          onCreated={() => {
            setCreateEpicOpen(false)
            queryClient.invalidateQueries({ queryKey: ["epics"] })
          }}
        />
      )}

      {/* Manage modules modal */}
      {manageModulesOpen && activeEpic && (
        <ManageModulesModal
          epic={activeEpic}
          role="admin"
          onClose={() => setManageModulesOpen(false)}
        />
      )}

      {/* Create task modal — pre-scoped to selected epic */}
      {createTaskOpen && activeEpic && (
        <CreateTaskForEpicModal
          epic={activeEpic}
          prefillTitle={prefillProposal?.title}
          prefillDescription={prefillProposal?.description}
          onClose={() => { setCreateTaskOpen(false); setPrefillProposal(null) }}
          onCreated={() => {
            setCreateTaskOpen(false)
            setPrefillProposal(null)
            onTaskCreated()
          }}
        />
      )}

      {/* Proposal detail dialog */}
      {selectedProposal && (
        <ProposalDetailDialog
          proposal={selectedProposal}
          onClose={() => setSelectedProposal(null)}
          acceptLabel="Accept + Create task"
          onAccept={selectedProposal.status === "pending" ? () => {
            reviewProposalMutation.mutate({ id: selectedProposal.id, status: "accepted" })
            setPrefillProposal({ title: selectedProposal.title, description: selectedProposal.description ?? "" })
            setCreateTaskOpen(true)
            setSelectedProposal(null)
          } : undefined}
          onReject={selectedProposal.status === "pending" ? () => {
            reviewProposalMutation.mutate({ id: selectedProposal.id, status: "rejected" })
            setSelectedProposal(null)
          } : undefined}
          isPending={reviewProposalMutation.isPending}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Create epic modal                                                   */
/* ================================================================== */
function CreateEpicModal({ project, onClose, onCreated }: {
  project: Project; onClose: () => void; onCreated: () => void
}) {
  const { data: teams = [] } = useQuery<Team[]>({ queryKey: ["teams"], queryFn: getTeamsApi })
  const [title,       setTitle]       = useState("")
  const [description, setDescription] = useState("")
  const [teamId,      setTeamId]      = useState("")
  const [error,       setError]       = useState("")

  const mutation = useMutation({
    mutationFn: () => createEpicApi(project.id, { title, description: description || undefined, team_id: teamId }),
    onSuccess: onCreated,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create epic"),
  })

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl text-foreground">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">New epic</p>
            <p className="text-xs text-muted-foreground mt-0.5">{project.title}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Epic title" autoFocus
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)" rows={2}
          className="w-full px-3 py-2.5 border border-border bg-card text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors" />
        <div>
          <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Assign to team *</label>
          <select value={teamId} onChange={(e) => setTeamId(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors">
            <option value="">Select team…</option>
            {teams.map((t) => <option key={t.id} value={t.id} className="bg-card text-foreground">{t.name}</option>)}
          </select>
        </div>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            Cancel
          </button>
          <button onClick={() => mutation.mutate()} disabled={!title.trim() || !teamId || mutation.isPending}
            className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
            {mutation.isPending ? "Creating…" : "Create epic"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ================================================================== */
/* Create task for a specific epic (no epic picker needed)             */
/* ================================================================== */
function CreateTaskForEpicModal({ epic, onClose, onCreated, prefillTitle, prefillDescription }: {
  epic: Epic; onClose: () => void; onCreated: () => void
  prefillTitle?: string; prefillDescription?: string
}) {
  const modules = epic.modules ?? []
  const [moduleId,     setModuleId]     = useState(modules[0]?.id ?? "")
  const [title,        setTitle]        = useState(prefillTitle ?? "")
  const [description,  setDescription]  = useState(prefillDescription ?? "")
  const [dueDate,      setDueDate]      = useState("")
  const [expectedTime, setExpectedTime] = useState("")
  const [error,        setError]        = useState("")
  const targetModule = modules.find((m) => m.id === moduleId) ?? modules[0]

  const mutation = useMutation({
    mutationFn: () => {
      if (!targetModule) throw new Error("No module found for this epic")
      return createAdminTaskApi(targetModule.id, {
        title,
        description: description || undefined,
        due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
        expected_time: expectedTime ? Number(expectedTime) : undefined,
      })
    },
    onSuccess: onCreated,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create task"),
  })

  return (
    <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl text-foreground">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-base font-semibold text-foreground">New task</p>
            <p className="text-xs text-muted-foreground mt-0.5">{epic.title}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>
        {modules.length > 1 && (
          <div>
            <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Module</label>
            <select value={targetModule?.id ?? ""} onChange={(e) => setModuleId(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors">
              {modules.map((m) => <option key={m.id} value={m.id} className="bg-card text-foreground">{m.title}</option>)}
            </select>
          </div>
        )}
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task title" autoFocus
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)" rows={2}
          className="w-full px-3 py-2.5 border border-border bg-card text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors" />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Due date</label>
            <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
              className="w-full h-9 px-2.5 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors" />
          </div>
          <div>
            <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Expected hours</label>
            <input type="number" min="0" step="0.5" value={expectedTime} onChange={(e) => setExpectedTime(e.target.value)}
              placeholder="e.g. 3"
              className="w-full h-9 px-2.5 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary transition-colors" />
          </div>
        </div>
        {!targetModule && <p className="text-xs text-amber-500">This epic has no modules yet.</p>}
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            Cancel
          </button>
          <button onClick={() => mutation.mutate()} disabled={!title.trim() || !targetModule || mutation.isPending}
            className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
            {mutation.isPending ? "Creating…" : "Create task"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ================================================================== */
/* Admin epic column + card (drill-down level 1)                       */
/* ================================================================== */
function AdminEpicColumn({ title, status, epics, tasks, projectName, onEpicClick }: {
  title: string; status: WorkStatus; epics: Epic[]; tasks: Task[]
  projectName: (id: string) => string
  onEpicClick: (e: Epic) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const s = TASK_STATUS[status]
  return (
    <div ref={setNodeRef} className={cn(
      "flex flex-col gap-3 rounded-2xl border p-4 min-h-[360px] transition-colors",
      isOver ? "border-[#a880ff] bg-[#a880ff]/5" : "border-border bg-muted/20"
    )}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full", s.dot)} />
          <span className="text-xs font-semibold text-foreground uppercase tracking-widest">{title}</span>
        </div>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", s.badge)}>{epics.length}</span>
      </div>
      <div className="flex flex-col gap-2 flex-1">
        {epics.map((epic) => (
          <AdminEpicCard
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
          <p className="text-xs text-gray-300">Drop here</p>
        </div>
      )}
    </div>
  )
}

function AdminEpicCard({ epic, taskCount, doneCount, projectName, onClick, isDragOverlay }: {
  epic: Epic; taskCount: number; doneCount: number; projectName: string
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
          "bg-card border-2 border-[#643f83] rounded-xl p-3 cursor-pointer select-none transition-all hover:shadow-md",
          isDragging && !isDragOverlay && "shadow-lg"
        )}
      >
        <div className="flex items-start justify-between gap-2 mb-0.5">
          <div className="min-w-0">
            <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Epic</span>
            <p className="text-sm font-semibold text-foreground leading-snug">{epic.title}</p>
          </div>
          <ChevronRight size={14} className="text-muted-foreground flex-shrink-0 mt-0.5" />
        </div>
        <p className="text-[11px] text-muted-foreground mb-1">{projectName}</p>
        {epic.description && (
          <p className="text-[11px] text-muted-foreground leading-relaxed line-clamp-2 mb-1">{epic.description}</p>
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
        projectName={projectName}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
      />
    </>
  )
}

/* ================================================================== */
/* Admin task column (useDroppable)                                    */
/* ================================================================== */
function AdminTaskColumn({ title, status, tasks, projectName, onTaskClick }: {
  title: string; status: WorkStatus; tasks: Task[]
  projectName: (id: string) => string
  onTaskClick: (t: Task) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id: status })
  const s = TASK_STATUS[status]
  return (
    <div ref={setNodeRef} className={cn(
      "flex flex-col gap-3 rounded-2xl border p-4 min-h-[360px] transition-colors",
      isOver ? "border-[#a880ff] bg-[#a880ff]/5" : "border-border bg-muted/20"
    )}>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className={cn("w-2 h-2 rounded-full", s.dot)} />
          <span className="text-xs font-semibold text-foreground uppercase tracking-widest">{title}</span>
        </div>
        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", s.badge)}>{tasks.length}</span>
      </div>
      <div className="flex flex-col gap-2 flex-1">
        {tasks.map((task) => (
          <AdminTaskCard
            key={task.id} task={task}
            projectName={projectName(task.project_id ?? "")}
            onClick={() => onTaskClick(task)}
          />
        ))}
      </div>
      {tasks.length === 0 && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-300">Drop here</p>
        </div>
      )}
    </div>
  )
}

/* ── Admin task card (useDraggable) ──────────────────────────────────── */
function AdminTaskCard({ task, projectName, onClick, isDragOverlay }: {
  task: Task; projectName: string
  onClick: () => void; isDragOverlay?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: task.id })
  const due = task.due_date ? new Date(task.due_date) : null
  const isOverdue = due && due < new Date() && task.status !== "done"

  return (
    <div
      ref={setNodeRef}
      style={{ transform: CSS.Translate.toString(transform), opacity: isDragging && !isDragOverlay ? 0.4 : 1 }}
      {...attributes} {...listeners}
      onClick={onClick}
      className={cn(
        "bg-card border border-border rounded-xl p-3 cursor-pointer select-none transition-all hover:shadow-md hover:border-muted-foreground/30",
        isDragging && !isDragOverlay && "shadow-lg"
      )}
    >
      <div className="flex items-start justify-between gap-2 mb-0.5">
        <p className="text-sm font-semibold text-foreground leading-snug flex-1">{task.title}</p>
        <button
          onClick={(e) => { e.stopPropagation(); onClick() }}
          className="p-1 rounded text-muted-foreground hover:text-foreground flex-shrink-0 transition-colors"
        >
          <Pencil size={11} />
        </button>
      </div>
      <p className="text-[11px] text-muted-foreground mb-2">
        {task.epic_title ? `${task.epic_title} · ` : ""}{projectName}
      </p>
      {due && (
        <div className={cn("flex items-center gap-1 text-[11px]", isOverdue ? "text-red-500" : "text-gray-400")}>
          <Clock size={10} />
          <span>{due.toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Admin task modal                                                    */
/* ================================================================== */
function AdminTaskModal({ task, projectName, onClose, onSaved, onDeleted, elevated = false }: {
  task: Task; projectName: string
  onClose: () => void; onSaved: (t: Task) => void; onDeleted: (id: string) => void
  elevated?: boolean
}) {
  const queryClient = useQueryClient()
  const [editing, setEditing]         = useState(false)
  const [title, setTitle]             = useState(task.title)
  const [description, setDescription] = useState(task.description ?? "")
  const [dueDate, setDueDate]         = useState(task.due_date ? task.due_date.slice(0, 10) : "")

  const saveMutation = useMutation({
    mutationFn: () => updateTaskApi(task.id, {
      title,
      description: description || undefined,
      due_date: dueDate ? new Date(dueDate).toISOString() : undefined,
    }),
    onSuccess: (updated) => { onSaved(updated); setEditing(false) },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteTaskApi(task.id),
    onSuccess: () => onDeleted(task.id),
  })

  const reviewMutation = useMutation({
    mutationFn: ({ subId, score, comment }: { subId: string; score: number; comment: string }) =>
      adminReviewSubmissionApi(subId, { score, review_comment: comment }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tasks", "admin"] })
      onClose()
    },
  })

  return (
    <div className={cn(
      "fixed inset-0 bg-black/40 flex items-center justify-center p-4",
      elevated ? "z-[60]" : "z-50"
    )}>
      <div className="w-full max-w-lg bg-card border border-border rounded-2xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden text-foreground">

        <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-border flex-shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded bg-foreground text-background">Task</span>
            {!editing && (
              <button onClick={() => setEditing(true)}
                className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors">
                <Pencil size={13} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => { if (confirm("Delete this task?")) deleteMutation.mutate() }}
              disabled={deleteMutation.isPending}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-colors disabled:opacity-50"
            >
              <Trash2 size={14} />
            </button>
            <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
              <X size={16} />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto flex-1 px-6 py-5 flex flex-col gap-6">
          {editing ? (
            <div className="flex flex-col gap-3">
              <LabeledField label="Title">
                <input value={title} onChange={(e) => setTitle(e.target.value)} autoFocus
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
              </LabeledField>
              <LabeledField label="Description">
                <textarea value={description} onChange={(e) => setDescription(e.target.value)}
                  rows={3} className="w-full px-3 py-2.5 border border-border bg-card text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors" />
              </LabeledField>
              <LabeledField label="Due date">
                <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)}
                  className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
              </LabeledField>
              <div className="flex gap-2">
                <button onClick={() => setEditing(false)}
                  className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
                  Cancel
                </button>
                <button onClick={() => saveMutation.mutate()}
                  disabled={!title.trim() || saveMutation.isPending}
                  className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
                  {saveMutation.isPending ? "Saving…" : "Save changes"}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              {task.epic_title && (
                <span className="text-[10px] font-semibold text-[#643f83] bg-[#d6c7e1]/40 px-2 py-0.5 rounded-full w-fit">
                  {task.epic_title}
                </span>
              )}
              <h2 className="text-base font-semibold text-foreground">{task.title}</h2>
              {task.description && (
                <p className="text-sm text-muted-foreground leading-relaxed">{task.description}</p>
              )}
              <div className="flex flex-wrap gap-2">
                <span className="text-xs text-muted-foreground bg-muted px-2.5 py-1 rounded-lg">{projectName}</span>
                {task.due_date && (
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground bg-muted px-2.5 py-1 rounded-lg">
                    <Clock size={11} />
                    {new Date(task.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                  </span>
                )}
                {task.expected_time != null && (
                  <span className="text-xs text-muted-foreground bg-muted px-2.5 py-1 rounded-lg">
                    Expected {task.expected_time}h
                  </span>
                )}
                {task.actual_time != null && (
                  <span className="text-xs text-muted-foreground bg-muted px-2.5 py-1 rounded-lg">
                    Actual {task.actual_time}h
                  </span>
                )}
                <span className={cn("text-xs font-medium px-2.5 py-1 rounded-lg", TASK_STATUS[task.status].badge)}>
                  {task.status.replace("_", " ")}
                </span>
              </div>
            </div>
          )}

          {/* Assignees */}
          {task.assignees?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">Assigned to</p>
              <div className="flex flex-wrap gap-2">
                {task.assignees.map((u) => (
                  <div key={u.id} className="flex items-center gap-1.5 bg-[#d6c7e1]/40 text-[#643f83] rounded-full px-2.5 py-1">
                    <div className="w-5 h-5 rounded-full bg-[#643f83] text-white text-[9px] font-bold flex items-center justify-center flex-shrink-0">
                      {u.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2).toUpperCase()}
                    </div>
                    <span className="text-xs font-medium">{u.full_name}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Submissions */}
          {task.submissions?.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                Submissions ({task.submissions.length})
              </p>
              <div className="flex flex-col gap-2">
                {[...task.submissions].reverse().map((sub, i) => (
                  <AdminSubmissionRow
                    key={sub.id} sub={sub} isLatest={i === 0}
                    onReview={(score, comment) => reviewMutation.mutate({ subId: sub.id, score, comment })}
                    reviewing={reviewMutation.isPending}
                  />
                ))}
              </div>
            </div>
          )}
          {task.submissions?.length === 0 && (
            <p className="text-sm text-muted-foreground italic">No submissions yet</p>
          )}
        </div>
      </div>
    </div>
  )
}

function AdminSubmissionRow({ sub, isLatest, onReview, reviewing }: {
  sub: { id: string; link: string; note: string | null; status: string; score: number | null; review_comment: string | null; submitted_at: string; submitter_name: string | null }
  isLatest: boolean; onReview: (score: number, comment: string) => void; reviewing: boolean
}) {
  const [showReview, setShowReview] = useState(false)
  const [score, setScore]           = useState("")
  const [comment, setComment]       = useState("")

  return (
    <div className={cn("rounded-xl p-3 border text-xs", isLatest ? "bg-muted/50 border-border" : "bg-card border-border opacity-70")}>
      <div className="flex items-center justify-between mb-1.5">
        {isLatest ? <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Latest</span> : <span />}
        {sub.submitter_name && <span className="text-[10px] text-muted-foreground">by {sub.submitter_name}</span>}
      </div>
      <a href={sub.link} target="_blank" rel="noreferrer"
        className="flex items-center gap-1 text-[#643f83] dark:text-snuff hover:underline">
        <ExternalLink size={10} className="flex-shrink-0" />
        <span className="truncate">{sub.link}</span>
      </a>
      {sub.note && <p className="text-muted-foreground mt-1 italic">{sub.note}</p>}
      <div className="flex items-center justify-between mt-1.5">
        <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded-full",
          sub.status === "reviewed" ? "bg-foreground text-background" : "bg-[#d6c7e1] text-[#643f83]")}>
          {sub.status === "reviewed" ? "Reviewed" : "Pending"}
        </span>
        <div className="flex items-center gap-2">
          {sub.score != null && <span className="font-semibold text-foreground">{sub.score}/100</span>}
          <span className="text-muted-foreground">{new Date(sub.submitted_at).toLocaleDateString()}</span>
        </div>
      </div>
      {sub.review_comment && <p className="text-muted-foreground mt-1 italic">"{sub.review_comment}"</p>}
      {isLatest && sub.status !== "reviewed" && (
        showReview ? (
          <div className="mt-2 flex flex-col gap-1.5">
            <input type="number" min={0} max={100} value={score} onChange={(e) => setScore(e.target.value)}
              placeholder="Score (0–100)"
              className="w-full h-8 px-2 border border-border bg-card text-foreground rounded-lg text-xs focus:outline-none focus:border-primary" />
            <textarea value={comment} onChange={(e) => setComment(e.target.value)}
              placeholder="Feedback…" rows={2}
              className="w-full px-2 py-1.5 border border-border bg-card text-foreground rounded-lg text-xs resize-none focus:outline-none focus:border-primary" />
            <div className="flex gap-1.5">
              <button onClick={() => setShowReview(false)}
                className="flex-1 h-7 border border-border rounded-lg text-[11px] font-medium text-muted-foreground hover:bg-muted bg-card">
                Cancel
              </button>
              <button
                onClick={() => onReview(Number(score) || 0, comment)}
                disabled={!comment.trim() || reviewing}
                className="flex-1 h-7 bg-primary text-primary-foreground rounded-lg text-[11px] font-medium hover:opacity-90 disabled:opacity-50">
                {reviewing ? "…" : "Submit review"}
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => setShowReview(true)}
            className="mt-2 w-full h-7 border border-border bg-card rounded-lg text-[11px] font-medium text-muted-foreground hover:bg-muted">
            Review
          </button>
        )
      )}
    </div>
  )
}

/* ================================================================== */
/* Create project modal                                                */
/* ================================================================== */
function CreateProjectModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [title,       setTitle]       = useState("")
  const [description, setDescription] = useState("")
  const [error,       setError]       = useState("")

  const mutation = useMutation({
    mutationFn: () => createProjectApi({ title, description: description || undefined }),
    onSuccess: onCreated,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create project"),
  })

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl text-foreground">
        <div className="flex items-center justify-between">
          <p className="text-base font-semibold text-foreground">New project</p>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors">
            <X size={16} />
          </button>
        </div>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Project title" autoFocus
          onKeyDown={(e) => { if (e.key === "Enter" && title.trim()) mutation.mutate() }}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
        <textarea value={description} onChange={(e) => setDescription(e.target.value)}
          placeholder="Description (optional)" rows={2}
          className="w-full px-3 py-2.5 border border-border bg-card text-foreground rounded-xl text-sm resize-none focus:outline-none focus:border-primary transition-colors" />
        {error && <p className="text-xs text-red-500">{error}</p>}
        <div className="flex gap-2">
          <button onClick={onClose}
            className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
            Cancel
          </button>
          <button onClick={() => mutation.mutate()} disabled={!title.trim() || mutation.isPending}
            className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
            {mutation.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── helpers ─────────────────────────────────────────────────────────── */
function LabeledField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">{label}</label>
      {children}
    </div>
  )
}

function PageSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  )
}
