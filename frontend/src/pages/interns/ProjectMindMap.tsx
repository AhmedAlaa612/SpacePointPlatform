import { useState, useCallback, useEffect, useRef } from "react"
import { useParams, useNavigate } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  type Node, type Edge,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { ArrowLeft, X, Pencil, Check, Save } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/context/AuthContext"
import type { Epic, WorkStatus } from "@/types/interns"
import { getProjectApi } from "@/api/interns/projects"
import { getProjectEpicsApi } from "@/api/interns/epics"
import { getTaskNoteApi, updateTaskNoteApi } from "@/api/interns/mindmap"
import { updateModuleApi } from "@/api/interns/modules"
import { STATUS, projectMapNodeTypes as nodeTypes } from "@/pages/interns/components/mindmap/SharedNodes"

// â”€â”€ Auto-layout constants â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
const TASK_W   = 200
const TASK_GAP = 30
const MOD_GAP  = 50
const EPIC_GAP = 100

const ROW_EPIC = 280
const ROW_MOD  = 220
const ROW_TASK = 190

function buildProjectGraph(
  projectId: string,
  projectTitle: string,
  projectDescription: string | null,
  epics: Epic[],
  saved: Record<string, { x: number; y: number }>
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []

  const epicMetas = epics.map((epic) => {
    const modWidths = epic.modules.map((mod) => {
      const tc = Math.max(1, mod.tasks.length)
      return tc * (TASK_W + TASK_GAP) - TASK_GAP
    })
    const totalMod = modWidths.length > 0
      ? modWidths.reduce((a, b) => a + b + MOD_GAP, 0) - MOD_GAP
      : TASK_W
    return { epic, modWidths, totalWidth: Math.max(220, totalMod) }
  })

  const totalWidth = epicMetas.length > 0
    ? epicMetas.reduce((a, b) => a + b.totalWidth + EPIC_GAP, 0) - EPIC_GAP
    : 400

  const totalTasks = epics.reduce((a, e) => a + e.modules.reduce((b, m) => b + m.tasks.length, 0), 0)

  nodes.push({
    id: `project-${projectId}`,
    type: "projectNode",
    position: saved[`project-${projectId}`] ?? { x: totalWidth / 2 - 130, y: 0 },
    data: { label: projectTitle, description: projectDescription, epicCount: epics.length, taskCount: totalTasks },
  })

  let epicX = 0
  for (const { epic, modWidths, totalWidth: epicW } of epicMetas) {
    const epicCx = epicX + epicW / 2 - 110

    nodes.push({
      id: `epic-${epic.id}`,
      type: "epicNode",
      position: saved[`epic-${epic.id}`] ?? { x: epicCx, y: ROW_EPIC },
      data: { label: epic.title, status: epic.status, description: epic.description ?? null, team_name: epic.team_name ?? null, leader_name: epic.leader_name ?? null },
    })
    edges.push({
      id: `e-proj-${epic.id}`,
      source: `project-${projectId}`,
      target: `epic-${epic.id}`,
      type: "smoothstep",
      style: { stroke: "#643f83", strokeWidth: 2 },
    })

    let modX = epicX
    for (let mi = 0; mi < epic.modules.length; mi++) {
      const mod = epic.modules[mi]
      const mw  = modWidths[mi]
      const modCx = modX + mw / 2 - 90

      nodes.push({
        id: `module-${mod.id}`,
        type: "moduleNode",
        position: saved[`module-${mod.id}`] ?? { x: modCx, y: ROW_EPIC + ROW_MOD },
        data: { label: mod.title, moduleId: mod.id, description: mod.description ?? null },
      })
      edges.push({
        id: `e-epic-mod-${mod.id}`,
        source: `epic-${epic.id}`,
        target: `module-${mod.id}`,
        type: "smoothstep",
        style: { stroke: "#643f83", strokeWidth: 2 },
      })

      const totalTaskW = mod.tasks.length > 0
        ? mod.tasks.length * (TASK_W + TASK_GAP) - TASK_GAP : 0
      let taskX = modX + mw / 2 - totalTaskW / 2 - 85

      for (const task of mod.tasks) {
        nodes.push({
          id: `task-${task.id}`,
          type: "taskNode",
          position: saved[`task-${task.id}`] ?? { x: taskX, y: ROW_EPIC + ROW_MOD + ROW_TASK },
          data: { label: task.title, status: task.status, assigneeCount: task.assignee_count, assignees: task.assignees ?? [], taskId: task.id },
        })
        edges.push({
          id: `e-mod-task-${task.id}`,
          source: `module-${mod.id}`,
          target: `task-${task.id}`,
          type: "smoothstep",
          style: { stroke: "#d6c7e1", strokeWidth: 1.5 },
        })
        taskX += TASK_W + TASK_GAP
      }

      modX += mw + MOD_GAP
    }

    epicX += epicW + EPIC_GAP
  }

  return { nodes, edges }
}

// â”€â”€ Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function ProjectMindMap() {
  const { projectId }   = useParams({ strict: false }) as { projectId: string }
  const navigate        = useNavigate()
  const { currentUser } = useAuth()
  const queryClient     = useQueryClient()
  const role            = (currentUser?.role ?? "admin") as "admin" | "leader" | "intern"
  const canEdit         = role !== "intern"
  const saveTimer       = useRef<ReturnType<typeof setTimeout> | null>(null)
  const STORAGE_KEY     = `project-map-${projectId}`

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [initialised, setInitialised]    = useState(false)

  // side panel state â€” mirrors MindMap.tsx pattern
  const [selectedTask,   setSelectedTask]   = useState<{ id: string; title: string; status: string } | null>(null)
  const [selectedModule, setSelectedModule] = useState<{ id: string; title: string; description: string | null } | null>(null)
  const [selectedEpic,   setSelectedEpic]   = useState<{ title: string; description: string | null; status: string } | null>(null)
  const [selectedProject, setSelectedProject] = useState<{ title: string; description: string | null; epicCount: number; taskCount: number } | null>(null)

  const [noteText,     setNoteText]     = useState("")
  const [noteDirty,    setNoteDirty]    = useState(false)
  const [editingDesc,  setEditingDesc]  = useState(false)
  const [editDescText, setEditDescText] = useState("")

  // â”€â”€ data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const { data: project } = useQuery({
    queryKey: ["project", projectId],
    queryFn:  () => getProjectApi(projectId),
  })

  const { data: epics = [], isLoading } = useQuery<Epic[]>({
    queryKey: ["epics", projectId],
    queryFn:  () => getProjectEpicsApi(projectId),
    enabled:  !!project,
  })

  if (project && !isLoading && !initialised) {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")
    const { nodes: n, edges: e } = buildProjectGraph(projectId, project.title, project.description, epics, saved)
    setNodes(n)
    setEdges(e)
    setInitialised(true)
  }

  // â”€â”€ task note â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const { data: taskNote } = useQuery({
    queryKey: ["task-note", selectedTask?.id],
    queryFn:  () => getTaskNoteApi(selectedTask!.id, role),
    enabled:  !!selectedTask,
  })

  useEffect(() => {
    setNoteText(taskNote?.note ?? "")
    setNoteDirty(false)
  }, [taskNote])

  const saveNoteMutation = useMutation({
    mutationFn: () => updateTaskNoteApi(selectedTask!.id, noteText),
    onSuccess: () => {
      setNoteDirty(false)
      queryClient.invalidateQueries({ queryKey: ["task-note", selectedTask?.id] })
      setNodes((curr) => curr.map((n) =>
        n.id === `task-${selectedTask?.id}`
          ? { ...n, data: { ...n.data, note: noteText } }
          : n
      ))
    },
  })

  // â”€â”€ module description â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const saveModuleDescMutation = useMutation({
    mutationFn: () => updateModuleApi(selectedModule!.id, { description: editDescText.trim() || undefined }, role as "admin" | "leader"),
    onSuccess: () => {
      const updated = editDescText.trim() || null
      setSelectedModule((m) => m ? { ...m, description: updated } : m)
      setNodes((curr) => curr.map((n) =>
        n.id === `module-${selectedModule?.id}`
          ? { ...n, data: { ...n.data, description: updated } }
          : n
      ))
      setEditingDesc(false)
      queryClient.invalidateQueries({ queryKey: ["epics", projectId] })
    },
  })

  // â”€â”€ layout save â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const saveLayout = useCallback(() => {
    if (!canEdit) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      setNodes((curr) => {
        const pos: Record<string, { x: number; y: number }> = {}
        curr.forEach((n) => { pos[n.id] = n.position })
        localStorage.setItem(STORAGE_KEY, JSON.stringify(pos))
        return curr
      })
    }, 800)
  }, [canEdit, STORAGE_KEY, setNodes])

  // â”€â”€ node click â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setEditingDesc(false)
    if (node.type === "taskNode") {
      setSelectedProject(null); setSelectedEpic(null); setSelectedModule(null)
      setSelectedTask({ id: String(node.data.taskId), title: String(node.data.label), status: String(node.data.status) })
    } else if (node.type === "moduleNode") {
      setSelectedProject(null); setSelectedEpic(null); setSelectedTask(null)
      setSelectedModule({ id: String(node.data.moduleId), title: String(node.data.label), description: node.data.description ? String(node.data.description) : null })
    } else if (node.type === "epicNode") {
      setSelectedProject(null); setSelectedModule(null); setSelectedTask(null)
      setSelectedEpic({ title: String(node.data.label), description: node.data.description ? String(node.data.description) : null, status: String(node.data.status) })
    } else if (node.type === "projectNode") {
      setSelectedEpic(null); setSelectedModule(null); setSelectedTask(null)
      setSelectedProject({ title: String(node.data.label), description: node.data.description ? String(node.data.description) : null, epicCount: Number(node.data.epicCount), taskCount: Number(node.data.taskCount) })
    }
  }, [])

  const closePanel = () => {
    setSelectedTask(null); setSelectedModule(null)
    setSelectedEpic(null); setSelectedProject(null)
    setEditingDesc(false)
  }

  const panelOpen = !!(selectedTask || selectedModule || selectedEpic || selectedProject)
  const totalTasks = epics.reduce((a, e) => a + e.modules.reduce((b, m) => b + m.tasks.length, 0), 0)

  if (isLoading || !project) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate({ to: "/" })}
            className="p-2 rounded-xl border border-gray-200 text-gray-500 hover:text-black hover:border-gray-400 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[#643f83] mb-0.5">Project map</p>
            <h1 className="text-xl font-bold text-black tracking-tight leading-none">{project.title}</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {epics.length} epic{epics.length !== 1 ? "s" : ""} &middot; {totalTasks} task{totalTasks !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        {canEdit && (
          <p className="text-xs text-gray-400 italic">Drag nodes to rearrange â€” saved to browser</p>
        )}
      </div>

      {/* Canvas + Side panel */}
      <div className="flex gap-4" style={{ height: "calc(100vh - 13rem)" }}>
        <div className={cn("flex-1 rounded-2xl border border-gray-100 overflow-hidden", panelOpen ? "w-2/3" : "w-full")}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeDragStop={saveLayout}
            onNodeClick={onNodeClick}
            nodesDraggable={canEdit}
            fitView
            fitViewOptions={{ padding: 0.12 }}
          >
            <Background color="#f3f4f6" gap={20} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) =>
                n.type === "projectNode" ? "#000" :
                n.type === "epicNode"    ? "#000" :
                n.type === "moduleNode"  ? "#643f83" : "#e5e7eb"
              }
              maskColor="rgba(255,255,255,0.7)"
              style={{ borderRadius: 12 }}
            />
          </ReactFlow>
        </div>

        {/* â”€â”€ Project side panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {selectedProject && (
          <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold uppercase tracking-widest text-gray-400">Project</span>
                <p className="text-sm font-semibold text-black mt-1 leading-snug">{selectedProject.title}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {selectedProject.epicCount} epic{selectedProject.epicCount !== 1 ? "s" : ""} &middot; {selectedProject.taskCount} task{selectedProject.taskCount !== 1 ? "s" : ""}
                </p>
              </div>
              <button onClick={closePanel} className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
                <X size={14} />
              </button>
            </div>
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Description</p>
              <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[60px]">
                {selectedProject.description
                  ? <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedProject.description}</p>
                  : <p className="text-sm text-gray-300 italic">No description</p>}
              </div>
            </div>
          </div>
        )}

        {/* â”€â”€ Epic side panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {selectedEpic && (
          <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Epic</span>
                <p className="text-sm font-semibold text-black mt-1 leading-snug">{selectedEpic.title}</p>
                <span className={cn("text-[9px] font-bold px-1.5 py-0.5 rounded-full mt-1 inline-block", STATUS[selectedEpic.status as WorkStatus]?.badge ?? "bg-gray-100 text-gray-500")}>
                  {selectedEpic.status.replace("_", " ")}
                </span>
              </div>
              <button onClick={closePanel} className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
                <X size={14} />
              </button>
            </div>
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">Description</p>
              <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[60px]">
                {selectedEpic.description
                  ? <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedEpic.description}</p>
                  : <p className="text-sm text-gray-300 italic">No description</p>}
              </div>
            </div>
          </div>
        )}

        {/* â”€â”€ Module side panel â€” same as individual map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {selectedModule && !selectedTask && (
          <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Module</span>
                <p className="text-sm font-semibold text-black mt-1 leading-snug">{selectedModule.title}</p>
              </div>
              <button onClick={closePanel} className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
                <X size={14} />
              </button>
            </div>
            <div>
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">Scope / Description</p>
                {canEdit && !editingDesc && (
                  <button
                    onClick={() => { setEditingDesc(true); setEditDescText(selectedModule.description ?? "") }}
                    className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-[#643f83] transition-colors"
                  >
                    <Pencil size={10} /> Edit
                  </button>
                )}
              </div>
              {editingDesc ? (
                <>
                  <textarea
                    value={editDescText}
                    onChange={(e) => setEditDescText(e.target.value)}
                    placeholder="Describe this module's scope so interns understand the contextâ€¦"
                    rows={6}
                    autoFocus
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors"
                  />
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => saveModuleDescMutation.mutate()}
                      disabled={saveModuleDescMutation.isPending}
                      className="flex-1 h-9 flex items-center justify-center gap-1.5 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50"
                    >
                      <Check size={13} /> {saveModuleDescMutation.isPending ? "Savingâ€¦" : "Save"}
                    </button>
                    <button onClick={() => setEditingDesc(false)}
                      className="h-9 px-3 border border-gray-200 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition-colors">
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[80px]">
                  {selectedModule.description
                    ? <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedModule.description}</p>
                    : <p className="text-sm text-gray-300 italic">
                        {canEdit ? "No description yet â€” click Edit to add scope context for interns." : "No scope description set for this module."}
                      </p>}
                </div>
              )}
            </div>
          </div>
        )}

        {/* â”€â”€ Task side panel â€” same as individual map â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        {selectedTask && (
          <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className={cn(
                  "text-[9px] font-bold px-1.5 py-0.5 rounded-full",
                  STATUS[selectedTask.status as WorkStatus]?.badge ?? "bg-gray-100 text-gray-500"
                )}>
                  {selectedTask.status.replace("_", " ")}
                </span>
                <p className="text-sm font-semibold text-black mt-1.5 leading-snug">{selectedTask.title}</p>
              </div>
              <button onClick={closePanel} className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
                <X size={14} />
              </button>
            </div>
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                {role === "intern" ? "Your note" : "Intern note"}
              </p>
              {role === "intern" ? (
                <>
                  <textarea
                    value={noteText}
                    onChange={(e) => { setNoteText(e.target.value); setNoteDirty(true) }}
                    placeholder="Describe your approach, logic, or challengesâ€¦"
                    rows={6}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors"
                  />
                  {noteDirty && (
                    <button
                      onClick={() => saveNoteMutation.mutate()}
                      disabled={saveNoteMutation.isPending}
                      className="mt-2 w-full h-9 flex items-center justify-center gap-1.5 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50"
                    >
                      <Save size={13} /> {saveNoteMutation.isPending ? "Savingâ€¦" : "Save note"}
                    </button>
                  )}
                </>
              ) : (
                <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[80px]">
                  {taskNote?.note
                    ? <p className="text-sm text-gray-600 leading-relaxed italic">"{taskNote.note}"</p>
                    : <p className="text-sm text-gray-300 italic">No note yet</p>}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
