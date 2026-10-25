import { useMemo, useState } from "react"
import { Link, useNavigate } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ArrowRight, Lock, Rocket, Unlock } from "lucide-react"
import { fetchMissionCatalog, fetchMissionGraph, type MissionGraphNode } from "@/api/missions"

/** /learn/missions (P5-4/P5-6) — standalone challenges, separate from the
 * course catalog. Only `published` + `access_mode='open'` missions ever
 * show here; invite-only ones are reachable through course embedding
 * instead (P5-5). The Map tab is the "constellation view" P5-6 asks for —
 * missions grouped by whether their prerequisites (P5-1/P5-6) are met,
 * rather than a node-and-edge canvas: the DAGs here are shallow, so a
 * grouped list communicates readiness at a glance without inventing a new
 * interaction model for it. */
export default function MissionCatalog() {
  const navigate = useNavigate()
  const [tab, setTab] = useState<"missions" | "map">("missions")
  const { data: missions, isLoading } = useQuery({ queryKey: ["missions-catalog"], queryFn: fetchMissionCatalog })

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-8">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <h1 className="font-['Outfit'] text-2xl sm:text-3xl lg:text-4xl font-extrabold tracking-tight text-foreground">
            Missions
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground font-medium mt-1">
            Standalone challenges — attempt any time, pick your difficulty.
          </p>
        </div>

        {/* Tab Pills */}
        <div className="inline-flex items-center gap-1.5 p-1 rounded-2xl bg-muted/40 dark:bg-[#12091f] border border-border/80 dark:border-lms-accent-border/30 self-start sm:self-auto">
          <button
            type="button"
            onClick={() => setTab("missions")}
            className={`px-5 py-2 rounded-xl text-sm font-bold transition-all cursor-pointer flex items-center gap-2 ${
              tab === "missions"
                ? "bg-lms-cta dark:bg-lms-accent text-white dark:text-black shadow-md shadow-lms-cta/20"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Missions</span>
            {missions && (
              <span className={`text-xs px-2 py-0.5 rounded-full ${tab === "missions" ? "bg-white/20 dark:bg-black/20 text-current" : "bg-muted dark:bg-[#1a0f26] text-muted-foreground"}`}>
                {missions.length}
              </span>
            )}
          </button>
          <button
            type="button"
            onClick={() => setTab("map")}
            className={`px-5 py-2 rounded-xl text-sm font-bold transition-all cursor-pointer flex items-center gap-2 ${
              tab === "map"
                ? "bg-lms-cta dark:bg-lms-accent text-white dark:text-black shadow-md shadow-lms-cta/20"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <span>Constellation Map</span>
          </button>
        </div>
      </div>

      {tab === "missions" && (
        <div className="flex flex-col gap-6">
          {isLoading && (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-72 rounded-2xl bg-muted/30 animate-pulse border border-border/60" />
              ))}
            </div>
          )}

          {missions && missions.length === 0 && (
            <div className="lms-card p-12 text-center rounded-2xl flex flex-col items-center gap-3">
              <Rocket className="size-12 text-muted-foreground/60 stroke-[1.5]" />
              <p className="text-base font-semibold text-foreground">No missions are open yet</p>
              <p className="text-sm text-muted-foreground">Check back soon for new standalone challenges.</p>
            </div>
          )}

          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {missions?.map((mission) => {
              const maxPoints = mission.variants.reduce((max, v) => Math.max(max, v.points), 0)
              return (
                <div
                  key={mission.id}
                  className="lms-card group relative flex flex-col overflow-hidden rounded-2xl border border-border/80 dark:border-lms-accent-border/30 bg-muted/10 dark:bg-[#0d0915] transition-all duration-300 hover:shadow-2xl hover:shadow-black/30 hover:-translate-y-1 hover:border-lms-cta dark:hover:border-lms-accent cursor-pointer"
                  onClick={() => void navigate({ to: "/learn/missions/$missionId", params: { missionId: mission.id } })}
                >
                  <div
                    className="h-44 relative bg-gradient-to-br from-lms-cta-light/40 via-muted/30 to-lms-accent-glow/20 flex items-start justify-between p-3.5 overflow-hidden border-b border-border/60 dark:border-white/5"
                    style={
                      mission.image_url
                        ? { backgroundImage: `url(${mission.image_url})`, backgroundSize: "cover", backgroundPosition: "center" }
                        : undefined
                    }
                  >
                    <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full bg-background/80 dark:bg-black/70 backdrop-blur-md border border-white/10 text-foreground">
                      <Rocket className="size-3.5 text-lms-cta dark:text-lms-accent" />
                      <span>{mission.track || "Mission"}</span>
                    </div>
                    {mission.locked ? (
                      <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground bg-background/80 dark:bg-black/70 backdrop-blur-md px-2.5 py-1 rounded-full border border-white/10">
                        <Lock className="size-3" /> Locked
                      </span>
                    ) : maxPoints > 0 ? (
                      <span className="flex items-center gap-1 text-[11px] font-bold uppercase tracking-wider text-lms-cta dark:text-lms-accent bg-background/80 dark:bg-black/70 backdrop-blur-md px-2.5 py-1 rounded-full border border-lms-cta-border dark:border-lms-accent-border">
                        Up to {maxPoints} pts
                      </span>
                    ) : null}
                  </div>
                  <div className="p-5 flex flex-col flex-1 gap-3">
                    <h2 className="font-['Outfit'] text-lg font-bold text-foreground leading-snug group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors">
                      {mission.title}
                    </h2>
                    {mission.summary && (
                      <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
                        {mission.summary}
                      </p>
                    )}
                    <div className="mt-auto pt-3 border-t border-border/60 dark:border-white/5 flex items-center justify-between text-xs text-muted-foreground font-medium">
                      <span>{mission.variants.length > 1 ? `${mission.variants.length} difficulty levels` : "Standard challenge"}</span>
                      <span className="font-bold text-lms-cta dark:text-lms-accent group-hover:translate-x-1 transition-transform inline-flex items-center gap-1">
                        Explore <ArrowRight size={13} />
                      </span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {tab === "map" && <MissionMap />}
    </div>
  )
}

function MissionMap() {
  const { data: nodes, isLoading } = useQuery({ queryKey: ["missions-graph"], queryFn: fetchMissionGraph })
  const byId = useMemo(() => new Map((nodes ?? []).map((n) => [n.id, n])), [nodes])

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading constellation map...</p>
  if (!nodes || nodes.length === 0) return <p className="text-sm text-muted-foreground">No missions are open yet.</p>

  const available = nodes.filter((n) => !n.locked)
  const locked = nodes.filter((n) => n.locked)

  return (
    <div className="flex flex-col gap-10">
      <MapSection title="Available now" icon={<Unlock className="size-5 text-emerald-400" />} nodes={available} byId={byId} />
      <MapSection title="Locked missions" icon={<Lock className="size-5 text-muted-foreground" />} nodes={locked} byId={byId} />
    </div>
  )
}

function MapSection({
  title,
  icon,
  nodes,
  byId,
}: {
  title: string
  icon: React.ReactNode
  nodes: MissionGraphNode[]
  byId: Map<string, MissionGraphNode>
}) {
  if (nodes.length === 0) return null
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2.5">
        {icon}
        <h3 className="font-['Outfit'] text-xl font-bold text-foreground">{title}</h3>
        <span className="text-xs font-bold px-2.5 py-0.5 rounded-full bg-muted/60 dark:bg-[#1a0f26] border border-border/80 dark:border-lms-accent-border/30 text-muted-foreground">
          {nodes.length}
        </span>
      </div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {nodes.map((node) => (
          <Link
            key={node.id}
            to="/learn/missions/$missionId"
            params={{ missionId: node.id }}
            className="block group"
          >
            <div
              className={`lms-card p-5 rounded-2xl flex flex-col gap-3 transition-all duration-300 hover:shadow-xl hover:shadow-black/20 hover:-translate-y-0.5 border border-border/80 dark:border-lms-accent-border/30 hover:border-lms-cta dark:hover:border-lms-accent ${
                node.locked ? "opacity-75" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-semibold text-lms-cta dark:text-lms-accent">
                  <Rocket className="size-3.5" />
                  <span>{node.track || "Mission"}</span>
                </div>
                {node.locked && (
                  <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground px-2 py-0.5 rounded-md bg-muted/50 border border-border/60">
                    <Lock size={10} /> Locked
                  </span>
                )}
              </div>
              <div className="font-['Outfit'] text-base font-bold leading-snug group-hover:text-lms-cta dark:group-hover:text-lms-accent transition-colors text-foreground">
                {node.title}
              </div>
              {node.requires.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1 pt-2 border-t border-border/50 dark:border-white/5">
                  {node.requires.map((reqId) => {
                    const req = byId.get(reqId)
                    return (
                      <span
                        key={reqId}
                        className="text-[11px] font-semibold px-2.5 py-1 rounded-lg bg-muted/60 dark:bg-[#1a0f26] border border-border/60 dark:border-lms-accent-border/20 text-muted-foreground"
                      >
                        Prereq: {req?.title ?? "another mission"}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
