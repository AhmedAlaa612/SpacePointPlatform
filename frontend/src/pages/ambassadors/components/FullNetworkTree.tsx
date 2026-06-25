import { useMemo } from "react"
import { ReactFlow, Background, Controls, Position, type Node, type Edge, MarkerType } from "@xyflow/react"
import "@xyflow/react/dist/style.css"

const HELIO = "#a880ff"

export interface FullNetworkAmbassador {
  id: string
  full_name: string
  teachers: { id: string; full_name: string; status: string; sessions_done: number }[]
  instructors: { id: string; full_name: string; status: string }[]
}

function nodeStyle(bg: string, color = "#fff", width = 170): React.CSSProperties {
  return {
    background: bg, color, border: "none", borderRadius: 12, padding: "8px 14px",
    fontSize: 12, fontWeight: 600, boxShadow: "0 2px 8px rgba(0,0,0,0.08)", width, textAlign: "center",
  }
}

/** Whole-platform tree: SpacePoint → ambassadors → teachers/instructors.
 *  Teacher nodes show their completed-session count. */
export function FullNetworkTree({ ambassadors }: { ambassadors: FullNetworkAmbassador[] }) {
  const { nodes, edges } = useMemo(() => {
    const nodes: Node[] = []
    const edges: Edge[] = []
    const rowH = 70
    let row = 0

    // total rows to vertically center the root
    const totalRows = ambassadors.reduce(
      (sum, a) => sum + Math.max(1, a.teachers.length + a.instructors.length),
      0
    )

    nodes.push({
      id: "root",
      position: { x: 0, y: (Math.max(totalRows, 1) * rowH) / 2 - 20 },
      data: { label: "SpacePoint" },
      style: nodeStyle("#0a0a0a", "#fff", 150),
      sourcePosition: Position.Right,
    })

    ambassadors.forEach((a) => {
      const childCount = Math.max(1, a.teachers.length + a.instructors.length)
      const ambRow = row + (childCount - 1) / 2
      const ambId = `a-${a.id}`
      nodes.push({
        id: ambId,
        position: { x: 230, y: ambRow * rowH },
        data: { label: `${a.full_name}  ·  Ambassador` },
        style: nodeStyle("#643f83"),
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      })
      edges.push({
        id: `e-root-${ambId}`, source: "root", target: ambId, animated: true,
        markerEnd: { type: MarkerType.ArrowClosed }, style: { stroke: "#643f83" },
      })

      let childRow = row
      a.teachers.forEach((t) => {
        const tId = `t-${t.id}`
        const faded = t.status !== "active"
        nodes.push({
          id: tId,
          position: { x: 470, y: childRow * rowH },
          data: { label: `${t.full_name}  ·  Teacher${t.sessions_done ? `  ·  ${t.sessions_done} done` : ""}` },
          style: { ...nodeStyle(faded ? "#e5e7eb" : HELIO, faded ? "#6b7280" : "#fff"), opacity: faded ? 0.7 : 1 },
          targetPosition: Position.Left,
        })
        edges.push({ id: `e-${ambId}-${tId}`, source: ambId, target: tId, style: { stroke: faded ? "#e5e7eb" : HELIO } })
        childRow += 1
      })
      a.instructors.forEach((i) => {
        const iId = `i-${i.id}`
        const faded = i.status !== "active"
        nodes.push({
          id: iId,
          position: { x: 470, y: childRow * rowH },
          data: { label: `${i.full_name}  ·  Instructor` },
          style: { ...nodeStyle(faded ? "#e5e7eb" : "#8b6fb0", faded ? "#6b7280" : "#fff"), opacity: faded ? 0.7 : 1 },
          targetPosition: Position.Left,
        })
        edges.push({ id: `e-${ambId}-${iId}`, source: ambId, target: iId, style: { stroke: "#c4b5d8" } })
        childRow += 1
      })

      row += childCount
    })

    return { nodes, edges }
  }, [ambassadors])

  return (
    <div className="h-[560px] w-full rounded-xl border border-border bg-muted/40 overflow-hidden">
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.2} proOptions={{ hideAttribution: true }}>
        <Background color="#e5e7eb" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  )
}
