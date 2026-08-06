import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, CheckCircle2 } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchCatalog, fetchMyCourses, fetchUpcomingPrograms } from "@/api/lms";
import { UpcomingProgramRow } from "./UpcomingProgramRow";
import { CourseProgress } from "./CourseProgress";

/** /learn/catalog (design 1d/1e) — three tabs behind one route, so the API
 * contract and the URL both stay single. "Upcoming programs" is /public/catalog
 * (public + registration_open — exactly "public and upcoming"), no LMS-specific
 * backend needed. */
export default function LearnCatalog() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<"courses" | "programs" | "enrolled">(() => {
    const t = new URLSearchParams(window.location.search).get("tab");
    return t === "programs" || t === "enrolled" ? t : "courses";
  });

  const { data: catalog, isLoading: catalogLoading } = useQuery({ queryKey: ["lms-catalog"], queryFn: fetchCatalog });
  const { data: programs, isLoading: programsLoading } = useQuery({ queryKey: ["lms-upcoming-programs"], queryFn: fetchUpcomingPrograms });
  const { data: dashboard, isLoading: dashboardLoading } = useQuery({ queryKey: ["lms-my-courses"], queryFn: fetchMyCourses });

  const enrolledIds = useMemo(() => new Set((dashboard?.courses ?? []).map((c) => c.course_id)), [dashboard]);

  return (
    <div className="mx-auto max-w-[1320px] px-5 sm:px-8 lg:px-14 py-8 sm:py-10 flex flex-col gap-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-bold tracking-tight">Course catalog</h1>
        <p className="text-sm text-muted-foreground mt-1.5">Enrol any time — modules unlock as you go.</p>
      </div>

      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList>
          <TabsTrigger value="courses">Courses {catalog && <span className="text-muted-foreground font-normal ml-1">{catalog.length}</span>}</TabsTrigger>
          <TabsTrigger value="programs">Upcoming programs {programs && <span className="text-muted-foreground font-normal ml-1">{programs.length}</span>}</TabsTrigger>
          <TabsTrigger value="enrolled">Enrolled {dashboard && <span className="text-muted-foreground font-normal ml-1">{dashboard.courses.length}</span>}</TabsTrigger>
        </TabsList>

        <TabsContent value="courses">
          {catalogLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {catalog && catalog.length === 0 && <p className="text-sm text-muted-foreground">No courses are published yet.</p>}
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {catalog?.map((course) => {
              const enrolled = enrolledIds.has(course.id);
              return (
                <Card
                  key={course.id}
                  className="cursor-pointer hover:ring-primary/30 transition-shadow p-0"
                  onClick={() => void navigate({ to: `/learn/courses/${course.id}` })}
                >
                  <div
                    className="h-[130px] rounded-t-2xl bg-[repeating-linear-gradient(135deg,hsl(var(--primary)/0.11)_0px,hsl(var(--primary)/0.11)_8px,hsl(var(--primary)/0.03)_8px,hsl(var(--primary)/0.03)_16px)] flex items-start justify-end p-3 overflow-hidden"
                    style={course.image_url ? { backgroundImage: `url(${course.image_url})`, backgroundSize: "cover", backgroundPosition: "center" } : undefined}
                  >
                    {enrolled && (
                      <span className="flex items-center gap-1 text-[10px] font-semibold text-emerald-500 bg-background/80 backdrop-blur px-2 py-1 rounded-md">
                        <CheckCircle2 className="size-3" /> ENROLLED
                      </span>
                    )}
                  </div>
                  <div className="p-4 flex flex-col gap-2">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <BookOpen className="size-3.5" />
                      {course.kind === "mission" ? "Mission" : "Course"}
                      {course.level && <span className="capitalize">· {course.level}</span>}
                    </div>
                    <div className="font-display text-base font-semibold leading-snug">{course.title}</div>
                    {course.description && <div className="text-sm text-muted-foreground line-clamp-2">{course.description}</div>}
                  </div>
                </Card>
              );
            })}
          </div>
        </TabsContent>

        <TabsContent value="programs">
          {programsLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {programs && programs.length === 0 && (
            <p className="text-sm text-muted-foreground">No public programs open right now.</p>
          )}
          <Card className="p-2 sm:p-3">
            {programs?.map((p) => <div key={p.cohort_id} className="px-3"><UpcomingProgramRow program={p} /></div>)}
          </Card>
        </TabsContent>

        <TabsContent value="enrolled">
          {dashboardLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {dashboard && dashboard.courses.length === 0 && (
            <p className="text-sm text-muted-foreground">You haven't enrolled in anything yet — browse the Courses tab.</p>
          )}
          <div className="flex flex-col gap-2.5">
            {dashboard?.courses.map((c) => (
              <Card
                key={c.course_id}
                className="flex-row items-center gap-4 p-4 cursor-pointer hover:ring-primary/30 transition-shadow"
                onClick={() => void navigate({ to: `/learn/courses/${c.course_id}` })}
              >
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">{c.title}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {c.status === "completed" ? "Completed" : `${c.modules_done} of ${c.modules_total} modules`}
                  </div>
                </div>
                <CourseProgress value={c.pct} className="w-40 shrink-0 hidden sm:flex" />
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
