import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Route as RouteIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/primitives";
import { fetchLearningPaths } from "@/api/lms";
import { CourseProgress } from "./CourseProgress";

/** /learn/paths — catalog of curated multi-course sequences (design 4a "The
 * ledger" is the detail page this links into). Scaffolding for when more
 * paths ship; there's realistically one today. */
export default function LearnPaths() {
  const navigate = useNavigate();
  const { data: paths, isLoading } = useQuery({ queryKey: ["lms-learning-paths"], queryFn: fetchLearningPaths });

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Learning paths</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Curated sequences of courses (and missions, soon) that build toward a certificate.</p>
      </div>

      {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
      {paths && paths.length === 0 && (
        <EmptyState title="No learning paths yet" hint="Check back soon — this is where curated course sequences will show up." />
      )}

      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {paths?.map((path) => (
          <Card
            key={path.id}
            className="cursor-pointer hover:ring-primary/30 transition-shadow p-0"
            onClick={() => void navigate({ to: `/learn/paths/${path.id}` })}
          >
            <div
              className="h-[130px] rounded-t-2xl bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.11)_0px,hsl(var(--primary)/0.11)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)] flex items-end p-3"
              style={path.image_url ? { backgroundImage: `url(${path.image_url})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
            />
            <div className="p-4 flex flex-col gap-2.5">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <RouteIcon className="size-3.5" />
                Learning path · {path.course_count} course{path.course_count === 1 ? "" : "s"}
                {path.mission_count > 0 && <span>· {path.mission_count} mission{path.mission_count === 1 ? "" : "s"}</span>}
              </div>
              <div className="font-display text-base font-semibold leading-snug">{path.title}</div>
              {path.description && <div className="text-sm text-muted-foreground line-clamp-2">{path.description}</div>}
              <CourseProgress value={path.pct} className="mt-1" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
