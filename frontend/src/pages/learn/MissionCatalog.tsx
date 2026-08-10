import { useMemo } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Lock, Rocket, Sparkles, Unlock } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchMissionCatalog, fetchMissionGraph, type MissionGraphNode } from "@/api/missions";

/** /learn/missions (P5-4/P5-6) — standalone challenges, separate from the
 * course catalog. Only `published` + `access_mode='open'` missions ever
 * show here; invite-only ones are reachable through course embedding
 * instead (P5-5). The Map tab is the "constellation view" P5-6 asks for —
 * missions grouped by whether their prerequisites (P5-1/P5-6) are met,
 * rather than a node-and-edge canvas: the DAGs here are shallow, so a
 * grouped list communicates readiness at a glance without inventing a new
 * interaction model for it. */
export default function MissionCatalog() {
  const navigate = useNavigate();
  const { data: missions, isLoading } = useQuery({ queryKey: ["missions-catalog"], queryFn: fetchMissionCatalog });

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Missions</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Standalone challenges — attempt any time, pick your difficulty.</p>
      </div>

      <Tabs defaultValue="missions">
        <TabsList>
          <TabsTrigger value="missions">Missions {missions && <span className="text-muted-foreground font-normal ml-1">{missions.length}</span>}</TabsTrigger>
          <TabsTrigger value="map">Map</TabsTrigger>
        </TabsList>

        <TabsContent value="missions">
          {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {missions && missions.length === 0 && (
            <p className="text-sm text-muted-foreground">No missions are open yet — check back soon.</p>
          )}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {missions?.map((mission) => {
              const maxPoints = mission.variants.reduce((max, v) => Math.max(max, v.points), 0);
              return (
                <Card
                  key={mission.id}
                  className="cursor-pointer hover:ring-primary/30 transition-shadow p-0"
                  onClick={() => void navigate({ to: "/learn/missions/$missionId", params: { missionId: mission.id } })}
                >
                  <div
                    className="h-[130px] rounded-t-2xl bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.11)_0px,hsl(var(--primary)/0.11)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)] flex items-start justify-end p-3 overflow-hidden"
                    style={mission.image_url ? { backgroundImage: `url(${mission.image_url})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
                  >
                    {mission.locked ? (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-muted-foreground bg-background/80 backdrop-blur px-2 py-1 rounded-md">
                        <Lock className="size-3" /> LOCKED
                      </span>
                    ) : maxPoints > 0 ? (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-primary bg-background/80 backdrop-blur px-2 py-1 rounded-md">
                        <Sparkles className="size-3" /> UP TO {maxPoints} PTS
                      </span>
                    ) : null}
                  </div>
                  <div className="p-4 flex flex-col gap-2">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Rocket className="size-3.5" />
                      Mission
                      {mission.track && <span>· {mission.track}</span>}
                    </div>
                    <div className="font-display text-base font-semibold leading-snug">{mission.title}</div>
                    {mission.summary && <div className="text-sm text-muted-foreground line-clamp-2">{mission.summary}</div>}
                    {mission.variants.length > 1 && (
                      <div className="text-xs text-muted-foreground mt-1">{mission.variants.length} difficulty levels</div>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="map">
          <MissionMap />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function MissionMap() {
  const { data: nodes, isLoading } = useQuery({ queryKey: ["missions-graph"], queryFn: fetchMissionGraph });
  const byId = useMemo(() => new Map((nodes ?? []).map((n) => [n.id, n])), [nodes]);

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading...</p>;
  if (!nodes || nodes.length === 0) return <p className="text-sm text-muted-foreground">No missions are open yet.</p>;

  const available = nodes.filter((n) => !n.locked);
  const locked = nodes.filter((n) => n.locked);

  return (
    <div className="flex flex-col gap-8">
      <MapSection title="Available now" icon={<Unlock className="size-4 text-emerald-500" />} nodes={available} byId={byId} />
      <MapSection title="Locked" icon={<Lock className="size-4 text-muted-foreground" />} nodes={locked} byId={byId} />
    </div>
  );
}

function MapSection({
  title, icon, nodes, byId,
}: { title: string; icon: React.ReactNode; nodes: MissionGraphNode[]; byId: Map<string, MissionGraphNode> }) {
  if (nodes.length === 0) return null;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2 text-sm font-semibold">{icon} {title} <span className="text-muted-foreground font-normal">{nodes.length}</span></div>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {nodes.map((node) => (
          <Link
            key={node.id}
            to="/learn/missions/$missionId"
            params={{ missionId: node.id }}
            className="block"
          >
            <Card className={`p-4 flex flex-col gap-2 hover:ring-primary/30 transition-shadow ${node.locked ? "opacity-70" : ""}`}>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Rocket className="size-3.5" />
                Mission
                {node.track && <span>· {node.track}</span>}
              </div>
              <div className="font-display text-sm font-semibold leading-snug">{node.title}</div>
              {node.requires.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {node.requires.map((reqId) => {
                    const req = byId.get(reqId);
                    return (
                      <span key={reqId} className="text-[11px] px-2 py-0.5 rounded-md bg-muted text-muted-foreground">
                        Requires: {req?.title ?? "another mission"}
                      </span>
                    );
                  })}
                </div>
              )}
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
