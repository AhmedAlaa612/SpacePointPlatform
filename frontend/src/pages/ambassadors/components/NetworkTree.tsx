import { useMemo } from "react"
import { ReactFlow, Background, Controls, Position, type Node, type Edge, MarkerType } from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import type { Teacher, Instructor, TeacherSession } from "@/types/ambassadors"

const HELIO = "#a880ff"

function nodeStyle(bg: string, color = "#fff"): React.CSSProperties {
  return {
    background: bg,
    color,
    border: "none",
    borderRadius: 12,
    padding: "8px 14px",
    fontSize: 12,
    fontWeight: 600,
    boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
    width: 170,
    textAlign: "center",
  }
}

/** Visualises Ambassador → Teachers → Sessions, plus Instructors, as an
 *  interactive tree. Reuses the ReactFlow canvas. */
export function NetworkTree({
  rootName,
  teachers,
  instructors,
  sessions,
}: {
  rootName: string
  teachers: Teacher[]
  instructors: Instructor[]
  sessions: TeacherSession[]
}) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = []
    const edges: Edge[] = []

    nodes.push({
      id: "root",
      position: { x: 0, y: 0 },
      data: { label: rootName },
      style: {
        background: "hsl(var(--foreground))",
        color: "hsl(var(--background))",
        border: "none",
        borderRadius: 12,
        padding: "8px 14px",
        fontSize: 12,
        fontWeight: 600,
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        width: 170,
        textAlign: "center",
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
    })

    const activeTeachers = teachers.filter((t) => t.status === "active")
    const colGap = 120
    let row = 0

    activeTeachers.forEach((t) => {
      const teacherSessions = sessions.filter((s) => s.teacher_id === t.id)
      const tId = `t-${t.id}`
      nodes.push({
        id: tId,
        position: { x: 260, y: row * colGap },
        data: { label: `${t.full_name}  ·  Teacher` },
        style: nodeStyle(HELIO),
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      })
      edges.push({
        id: `e-root-${tId}`,
        source: "root",
        target: tId,
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: HELIO },
      })

      teacherSessions.slice(0, 4).forEach((s, j) => {
        const sId = `s-${s.id}`
        nodes.push({
          id: sId,
          position: { x: 520, y: row * colGap + (j - 1) * 46 },
          data: { label: `${s.title}  ·  ${s.status}${s.status === "done" ? ` (${s.attended_students})` : ""}` },
          style: nodeStyle(s.status === "done" ? "#4ade80" : "hsl(var(--muted))", s.status === "done" ? "#06321a" : "hsl(var(--foreground))"),
          targetPosition: Position.Left,
        })
        edges.push({
          id: `e-${tId}-${sId}`,
          source: tId,
          target: sId,
          style: { stroke: "hsl(var(--border))" },
        })
      })
      row += Math.max(1, Math.min(teacherSessions.length, 4))
    })

    instructors
      .filter((i) => i.status === "active")
      .forEach((i) => {
        const iId = `i-${i.id}`
        nodes.push({
          id: iId,
          position: { x: 260, y: row * colGap },
          data: { label: `${i.full_name}  ·  Instructor` },
          style: nodeStyle("#643f83"),
          targetPosition: Position.Left,
        })
        edges.push({
          id: `e-root-${iId}`,
          source: "root",
          target: iId,
          markerEnd: { type: MarkerType.ArrowClosed },
          style: { stroke: "hsl(var(--primary))" },
        })
        row += 1
      })

    return { nodes, edges }
  }, [rootName, teachers, instructors, sessions])

  return (
    <div className="h-[420px] w-full rounded-xl border bg-muted/20 overflow-hidden">
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
        <Background color="hsl(var(--border))" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
