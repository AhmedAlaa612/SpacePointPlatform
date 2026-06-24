import { useState, useCallback, useRef, useEffect } from "react"
import { useParams, useNavigate } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  ReactFlow, Background, Controls, MiniMap,
  useNodesState, useEdgesState,
  type Node, type Edge,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { ArrowLeft, X, Save, Pencil, Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { useAuth } from "@/context/AuthContext"
import type { Epic, WorkStatus } from "@/types/interns"
import {
  getEpicForMapApi, getLayoutApi, saveLayoutApi,
  getTaskNoteApi, updateTaskNoteApi,
} from "@/api/interns/mindmap"
import { updateModuleApi } from "@/api/interns/modules"
import { STATUS, epicMapNodeTypes as nodeTypes } from "@/pages/interns/components/mindmap/SharedNodes"

// ── Layout builder ────────────────────────────────────────────────────────────
function buildGraph(
  epic: Epic,
  savedPositions: Record<string, { x: number; y: number }>,
  notes: Record<string, string | null>
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = []
  const edges: Edge[] = []

  const epicPos = savedPositions[`epic-${epic.id}`] ?? { x: 0, y: 0 }
  nodes.push({
    id: `epic-${epic.id}`,
    type: "epicNode",
    position: epicPos,
    data: { label: epic.title, status: epic.status, team_name: epic.team_name ?? null, leader_name: epic.leader_name ?? null },
  })

  const modCount  = epic.modules.length
  const modSpan   = Math.max(modCount - 1, 0) * 320

  epic.modules.forEach((mod, mi) => {
    const defaultModX = (epicPos.x - modSpan / 2) + mi * 320
    const modPos = savedPositions[`module-${mod.id}`] ?? { x: defaultModX, y: epicPos.y + 220 }

    nodes.push({
      id: `module-${mod.id}`,
      type: "moduleNode",
      position: modPos,
      data: {
        label: mod.title,
        moduleId: mod.id,
        description: mod.description ?? (mod.title === "General" ? epic.description : null) ?? null,
      },
    })
    edges.push({
      id: `e-epic-${mod.id}`,
      source: `epic-${epic.id}`,
      target: `module-${mod.id}`,
      type: "smoothstep",
      style: { stroke: "#643f83", strokeWidth: 2 },
    })

    const taskCount = mod.tasks.length
    const taskSpan  = Math.max(taskCount - 1, 0) * 240

    mod.tasks.forEach((task, ti) => {
      const defaultTaskX = (modPos.x - taskSpan / 2) + ti * 240
      const taskPos = savedPositions[`task-${task.id}`] ?? { x: defaultTaskX, y: modPos.y + 200 }

      nodes.push({
        id: `task-${task.id}`,
        type: "taskNode",
        position: taskPos,
        data: {
          label: task.title,
          status: task.status,
          assigneeCount: task.assignee_count,
          assignees: task.assignees ?? [],
          note: notes[task.id] ?? null,
          taskId: task.id,
        },
      })
      edges.push({
        id: `e-mod-${task.id}`,
        source: `module-${mod.id}`,
        target: `task-${task.id}`,
        type: "smoothstep",
        style: { stroke: "#d6c7e1", strokeWidth: 1.5 },
      })
    })
  })

  return { nodes, edges }
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function MindMap() {
  const { epicId }    = useParams({ strict: false }) as { epicId: string }
  const navigate      = useNavigate()
  const { currentUser } = useAuth()
  const queryClient   = useQueryClient()
  const role          = (currentUser?.role ?? "admin") as "admin" | "leader" | "intern"
  const canEdit       = role !== "intern"   // only admin/leader drag nodes
  const saveTimer     = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [selectedTask,   setSelectedTask]   = useState<{ id: string; title: string; status: string } | null>(null)
  const [selectedModule, setSelectedModule] = useState<{ id: string; title: string; description: string | null } | null>(null)
  const [noteText,       setNoteText]       = useState("")
  const [noteDirty,      setNoteDirty]      = useState(false)
  const [editingDesc,    setEditingDesc]    = useState(false)
  const [editDescText,   setEditDescText]   = useState("")
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [initialised, setInitialised]  = useState(false)

  // ── Fetch epic ───────────────────────────────────────────────────────────
  const { data: epic, isLoading: epicLoading } = useQuery<Epic>({
    queryKey: ["epic", epicId],
    queryFn: () => getEpicForMapApi(epicId, role),
  })

  // ── Fetch layout ─────────────────────────────────────────────────────────
  const { data: layout, isLoading: layoutLoading } = useQuery({
    queryKey: ["mind-map-layout", epicId],
    queryFn: () => getLayoutApi(epicId, role),
    enabled: !!epic,
  })

  // ── Build graph once both are loaded ─────────────────────────────────────
  if (epic && layout && !initialised) {
    const saved = layout.layout ?? {}
    const { nodes: n, edges: e } = buildGraph(epic, saved, {})
    setNodes(n)
    setEdges(e)
    setInitialised(true)
  }

  // ── Save layout (debounced) ───────────────────────────────────────────────
  const saveLayout = useCallback(() => {
    if (!canEdit) return
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => {
      const positions: Record<string, { x: number; y: number }> = {}
      setNodes((curr) => {
        curr.forEach((n) => { positions[n.id] = n.position })
        return curr
      })
      saveLayoutApi(epicId, positions, role as "admin" | "leader")
        .then(() => queryClient.invalidateQueries({ queryKey: ["mind-map-layout", epicId] }))
    }, 800)
  }, [canEdit, epicId, role, queryClient, setNodes])

  // ── Task note fetch ───────────────────────────────────────────────────────
  const { data: taskNote } = useQuery({
    queryKey: ["task-note", selectedTask?.id],
    queryFn: () => getTaskNoteApi(selectedTask!.id, role),
    enabled: !!selectedTask,
  })

  // Sync note text into the editor when the fetched note changes
  useEffect(() => {
    setNoteText(taskNote?.note ?? "")
    setNoteDirty(false)
  }, [taskNote])

  // ── Save note ─────────────────────────────────────────────────────────────
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

  // ── Save module description ───────────────────────────────────────────────
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
      queryClient.invalidateQueries({ queryKey: ["epic", epicId] })
    },
  })

  // ── Node click ────────────────────────────────────────────────────────────
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    if (node.type === "taskNode") {
      setSelectedModule(null)
      setEditingDesc(false)
      const taskId = String(node.data.taskId)
      setSelectedTask({ id: taskId, title: String(node.data.label), status: String(node.data.status) })
    } else if (node.type === "moduleNode") {
      setSelectedTask(null)
      setEditingDesc(false)
      setSelectedModule({
        id: String(node.data.moduleId),
        title: String(node.data.label),
        description: node.data.description ? String(node.data.description) : null,
      })
    }
  }, [])

  if (epicLoading || layoutLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-black border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  if (!epic) return <p className="text-gray-400">Epic not found.</p>

  return (
    <div className="flex flex-col gap-4">
      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate({ to: "/" })}
            className="p-2 rounded-xl border border-gray-200 text-gray-500 hover:text-black hover:border-gray-400 transition-colors">
            <ArrowLeft size={16} />
          </button>
          <div>
            <h1 className="text-xl font-bold text-black tracking-tight">{epic.title}</h1>
            <p className="text-sm text-gray-400 mt-0.5">
              {epic.modules.reduce((a, m) => a + m.tasks.length, 0)} tasks across {epic.modules.length} module{epic.modules.length !== 1 ? "s" : ""}
            </p>
          </div>
        </div>
        {canEdit && (
          <p className="text-xs text-gray-400 italic">Drag nodes to rearrange — saved automatically</p>
        )}
      </div>

      {/* ── Canvas + Sidebar ────────────────────────────────────────────── */}
      <div className="flex gap-4" style={{ height: "calc(100vh - 14rem)" }}>
        <div className={cn("flex-1 rounded-2xl border border-gray-100 overflow-hidden", (selectedTask || selectedModule) ? "w-2/3" : "w-full")}>
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
            fitViewOptions={{ padding: 0.2 }}
          >
            <Background color="#f3f4f6" gap={20} />
            <Controls showInteractive={false} />
            <MiniMap
              nodeColor={(n) =>
                n.type === "epicNode" ? "#000" :
                n.type === "moduleNode" ? "#643f83" : "#e5e7eb"
              }
              maskColor="rgba(255,255,255,0.7)"
              style={{ borderRadius: 12 }}
            />
          </ReactFlow>
        </div>

        {/* ── Module side panel ───────────────────────────────────────── */}
        {selectedModule && !selectedTask && (
          <div className="w-72 flex-shrink-0 bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-4 overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <span className="text-[9px] font-bold uppercase tracking-widest text-[#643f83]">Module</span>
                <p className="text-sm font-semibold text-black mt-1 leading-snug">{selectedModule.title}</p>
              </div>
              <button onClick={() => { setSelectedModule(null); setEditingDesc(false) }}
                className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
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
                    placeholder="Describe this module's scope so interns understand the context…"
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
                      <Check size={13} /> {saveModuleDescMutation.isPending ? "Saving…" : "Save"}
                    </button>
                    <button
                      onClick={() => setEditingDesc(false)}
                      className="h-9 px-3 border border-gray-200 rounded-xl text-sm text-gray-500 hover:bg-gray-50 transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                </>
              ) : (
                <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[80px]">
                  {selectedModule.description ? (
                    <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{selectedModule.description}</p>
                  ) : (
                    <p className="text-sm text-gray-300 italic">
                      {canEdit ? "No description yet — click Edit to add scope context for interns." : "No scope description set for this module."}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ── Task side panel ─────────────────────────────────────────── */}
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
              <button onClick={() => setSelectedTask(null)}
                className="p-1 rounded-lg text-gray-400 hover:text-black transition-colors flex-shrink-0">
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
                    placeholder="Describe your approach, logic, or challenges…"
                    rows={6}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-black transition-colors"
                  />
                  {noteDirty && (
                    <button
                      onClick={() => saveNoteMutation.mutate()}
                      disabled={saveNoteMutation.isPending}
                      className="mt-2 w-full h-9 flex items-center justify-center gap-1.5 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50"
                    >
                      <Save size={13} /> {saveNoteMutation.isPending ? "Saving…" : "Save note"}
                    </button>
                  )}
                </>
              ) : (
                <div className="px-3 py-2.5 bg-gray-50 rounded-xl min-h-[80px]">
                  {taskNote?.note ? (
                    <p className="text-sm text-gray-600 leading-relaxed italic">"{taskNote.note}"</p>
                  ) : (
                    <p className="text-sm text-gray-300 italic">No note yet</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
