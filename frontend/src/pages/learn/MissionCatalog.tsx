import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Rocket, Sparkles } from "lucide-react";
import { Card } from "@/components/ui/card";
import { fetchMissionCatalog } from "@/api/missions";

/** /learn/missions (P5-4) — standalone challenges, separate from the course
 * catalog. Only `published` + `access_mode='open'` missions ever show here;
 * invite-only ones are reachable through course embedding instead (P5-5). */
export default function MissionCatalog() {
  const navigate = useNavigate();
  const { data: missions, isLoading } = useQuery({ queryKey: ["missions-catalog"], queryFn: fetchMissionCatalog });

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Missions</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Standalone challenges — attempt any time, pick your difficulty.</p>
      </div>

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
              onClick={() => void navigate({ to: `/learn/missions/${mission.id}` })}
            >
              <div
                className="h-[130px] rounded-t-2xl bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.11)_0px,hsl(var(--primary)/0.11)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)] flex items-start justify-end p-3 overflow-hidden"
                style={mission.image_url ? { backgroundImage: `url(${mission.image_url})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
              >
                {maxPoints > 0 && (
                  <span className="flex items-center gap-1 text-[10px] font-semibold text-primary bg-background/80 backdrop-blur px-2 py-1 rounded-md">
                    <Sparkles className="size-3" /> UP TO {maxPoints} PTS
                  </span>
                )}
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
    </div>
  );
}
