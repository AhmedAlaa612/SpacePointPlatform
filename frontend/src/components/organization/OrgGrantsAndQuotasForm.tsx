import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Check, ShieldCheck, BookOpen, Layers, Users, Eye, Globe, HelpCircle } from "lucide-react"
import { listCoursesApi, type AdminCourse } from "@/api/lms_admin"
import { listCohortQuizTemplatesApi } from "@/api/cohort_quiz"
import type { CohortQuizTemplate } from "@/types/cohort_quiz"

export interface OrgGrantsAndQuotasData {
  is_approved: boolean
  can_publish_events: boolean
  can_author_courses: boolean
  can_publish_courses: boolean
  course_scope_all: boolean
  allowed_course_ids: string[]
  quiz_scope: "all" | "selected" | "own"
  allowed_quiz_template_ids: string[]
  max_events: number | null
  max_programs: number | null
  max_cohorts: number | null
  max_students_per_cohort: number | null
  max_observers_per_cohort: number | null
}

export function OrgGrantsAndQuotasForm({
  data,
  onChange,
}: {
  data: OrgGrantsAndQuotasData
  onChange: (data: OrgGrantsAndQuotasData) => void
}) {
  const [courseSearch, setCourseSearch] = useState("")
  const [quizSearch, setQuizSearch] = useState("")

  const { data: courses = [] } = useQuery<AdminCourse[]>({
    queryKey: ["admin-courses-catalog"],
    queryFn: () => listCoursesApi(),
  })

  const { data: quizTemplates = [] } = useQuery<CohortQuizTemplate[]>({
    queryKey: ["admin-quiz-templates-catalog"],
    queryFn: () => listCohortQuizTemplatesApi(),
  })

  // Filter courses for picker (only platform courses without organization_id, or published)
  const availableCourses = courses.filter((c) => !c.organization_id)
  const filteredCourses = availableCourses.filter(
    (c) =>
      c.title.toLowerCase().includes(courseSearch.toLowerCase()) ||
      (c.track && c.track.toLowerCase().includes(courseSearch.toLowerCase()))
  )

  const toggleCourse = (courseId: string) => {
    const set = new Set(data.allowed_course_ids || [])
    if (set.has(courseId)) {
      set.delete(courseId)
    } else {
      set.add(courseId)
    }
    onChange({ ...data, allowed_course_ids: Array.from(set) })
  }

  // Filter quiz templates for picker
  const availableQuizTemplates = quizTemplates.filter((t) => !t.organization_id)
  const filteredQuizTemplates = availableQuizTemplates.filter((t) =>
    t.name.toLowerCase().includes(quizSearch.toLowerCase())
  )

  const toggleQuizTemplate = (templateId: string) => {
    const set = new Set(data.allowed_quiz_template_ids || [])
    if (set.has(templateId)) {
      set.delete(templateId)
    } else {
      set.add(templateId)
    }
    onChange({ ...data, allowed_quiz_template_ids: Array.from(set) })
  }

  const handleQuotaNumber = (key: keyof OrgGrantsAndQuotasData, rawVal: string) => {
    const trimmed = rawVal.trim()
    const val = trimmed === "" ? null : parseInt(trimmed, 10)
    onChange({
      ...data,
      [key]: isNaN(val as number) ? null : val,
    })
  }

  return (
    <div className="flex flex-col gap-5 pt-2">
      {/* ── Feature Grants Section ─────────────────────────────────────────── */}
      <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 sm:p-5 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-primary" />
          <h3 className="text-sm font-bold text-foreground">Access Grants & Permissions</h3>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {/* Account Approved */}
          <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-card cursor-pointer hover:border-primary/40 transition">
            <input
              type="checkbox"
              checked={data.is_approved}
              onChange={(e) => onChange({ ...data, is_approved: e.target.checked })}
              className="mt-1 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">Account Approved</span>
              <span className="text-[11px] text-muted-foreground block">
                Allow full login access to host programs and manage cohorts.
              </span>
            </div>
          </label>

          {/* Publish Landing Pages */}
          <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-card cursor-pointer hover:border-primary/40 transition">
            <input
              type="checkbox"
              checked={data.can_publish_events}
              onChange={(e) => onChange({ ...data, can_publish_events: e.target.checked })}
              className="mt-1 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">Publish Landing Pages Directly</span>
              <span className="text-[11px] text-muted-foreground block">
                If unchecked, landing pages remain in draft mode until Ops publishes them.
              </span>
            </div>
          </label>

          {/* Author Courses */}
          <label className="flex items-start gap-3 p-3 rounded-xl border border-border bg-card cursor-pointer hover:border-primary/40 transition">
            <input
              type="checkbox"
              checked={data.can_author_courses}
              onChange={(e) => onChange({ ...data, can_author_courses: e.target.checked })}
              className="mt-1 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">LMS Course Authoring</span>
              <span className="text-[11px] text-muted-foreground block">
                Grants access to author training modules and courses.
              </span>
            </div>
          </label>

          {/* Publish Courses */}
          <label
            className={`flex items-start gap-3 p-3 rounded-xl border border-border bg-card transition ${
              !data.can_author_courses
                ? "opacity-50 cursor-not-allowed"
                : "cursor-pointer hover:border-primary/40"
            }`}
          >
            <input
              type="checkbox"
              disabled={!data.can_author_courses}
              checked={data.can_publish_courses}
              onChange={(e) => onChange({ ...data, can_publish_courses: e.target.checked })}
              className="mt-1 h-4 w-4 rounded text-primary focus:ring-primary border-border"
            />
            <div>
              <span className="text-xs font-semibold text-foreground block">Publish Courses Directly</span>
              <span className="text-[11px] text-muted-foreground block">
                If unchecked, newly authored courses require review by Ops before going live.
              </span>
            </div>
          </label>
        </div>

        {/* SpacePoint Catalog Course Sharing */}
        <div className="pt-2 border-t border-border/60 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold text-foreground">Catalog Course Access</span>
            </div>
            <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-foreground">
              <input
                type="checkbox"
                checked={data.course_scope_all}
                onChange={(e) => onChange({ ...data, course_scope_all: e.target.checked })}
                className="h-4 w-4 rounded text-primary focus:ring-primary border-border"
              />
              All Platform Courses
            </label>
          </div>

          {!data.course_scope_all && (
            <div className="rounded-xl border border-border bg-background p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">
                  Select specific platform courses this organization can attach to their cohorts:
                </span>
                <span className="text-[11px] font-semibold text-primary">
                  {data.allowed_course_ids?.length || 0} selected
                </span>
              </div>
              <input
                type="text"
                value={courseSearch}
                onChange={(e) => setCourseSearch(e.target.value)}
                placeholder="Search catalog courses..."
                className="w-full h-8 px-3 rounded-lg border border-border bg-card text-xs focus:outline-none focus:border-primary"
              />
              <div className="max-h-40 overflow-y-auto space-y-1 pr-1">
                {filteredCourses.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-3">No matching courses</p>
                ) : (
                  filteredCourses.map((c) => {
                    const isSelected = (data.allowed_course_ids || []).includes(c.id)
                    return (
                      <div
                        key={c.id}
                        onClick={() => toggleCourse(c.id)}
                        className={`flex items-center justify-between p-2 rounded-lg text-xs cursor-pointer transition ${
                          isSelected
                            ? "bg-primary/10 text-primary font-medium"
                            : "hover:bg-muted/60 text-foreground"
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <div
                            className={`w-4 h-4 rounded flex items-center justify-center border ${
                              isSelected
                                ? "bg-primary border-primary text-primary-foreground"
                                : "border-border"
                            }`}
                          >
                            {isSelected && <Check className="w-3 h-3" />}
                          </div>
                          <span className="truncate">{c.title}</span>
                          {c.track && (
                            <span className="text-[10px] uppercase tracking-wider text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                              {c.track}
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>

        {/* Quiz & Question Bank Access */}
        <div className="pt-2 border-t border-border/60 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HelpCircle className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold text-foreground">Quiz & Question Bank Access</span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {[
              { id: "own", label: "Only Own Items", desc: "Access strictly to quizzes/questions authored by this organization." },
              { id: "selected", label: "Selected Quizzes", desc: "Access to specific platform quizzes in addition to own items." },
              { id: "all", label: "All Platform Quizzes", desc: "Full access to the entire platform question bank & templates." },
            ].map((opt) => (
              <label
                key={opt.id}
                className={`flex flex-col p-2.5 rounded-xl border text-xs cursor-pointer transition ${
                  (data.quiz_scope || "own") === opt.id
                    ? "border-primary bg-primary/10 text-primary font-medium"
                    : "border-border bg-card hover:border-primary/40 text-foreground"
                }`}
              >
                <div className="flex items-center gap-2 mb-1">
                  <input
                    type="radio"
                    name="quiz_scope"
                    value={opt.id}
                    checked={(data.quiz_scope || "own") === opt.id}
                    onChange={() => onChange({ ...data, quiz_scope: opt.id as "all" | "selected" | "own" })}
                    className="h-3.5 w-3.5 text-primary focus:ring-primary border-border"
                  />
                  <span className="font-semibold">{opt.label}</span>
                </div>
                <span className="text-[10px] text-muted-foreground leading-snug">{opt.desc}</span>
              </label>
            ))}
          </div>

          {data.quiz_scope === "selected" && (
            <div className="rounded-xl border border-border bg-background p-3 flex flex-col gap-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] text-muted-foreground">
                  Select specific platform quiz templates this organization can attach to their cohorts:
                </span>
                <span className="text-[11px] font-semibold text-primary">
                  {data.allowed_quiz_template_ids?.length || 0} selected
                </span>
              </div>
              <input
                type="text"
                value={quizSearch}
                onChange={(e) => setQuizSearch(e.target.value)}
                placeholder="Search quiz templates..."
                className="w-full h-8 px-3 rounded-lg border border-border bg-card text-xs focus:outline-none focus:border-primary"
              />
              <div className="max-h-40 overflow-y-auto space-y-1 pr-1">
                {filteredQuizTemplates.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-3">No matching quiz templates</p>
                ) : (
                  filteredQuizTemplates.map((t) => {
                    const isSelected = (data.allowed_quiz_template_ids || []).includes(t.id)
                    return (
                      <div
                        key={t.id}
                        onClick={() => toggleQuizTemplate(t.id)}
                        className={`flex items-center justify-between p-2 rounded-lg text-xs cursor-pointer transition ${
                          isSelected
                            ? "bg-primary/10 text-primary font-medium"
                            : "hover:bg-muted/60 text-foreground"
                        }`}
                      >
                        <div className="flex items-center gap-2 truncate">
                          <div
                            className={`w-4 h-4 rounded flex items-center justify-center border ${
                              isSelected
                                ? "bg-primary border-primary text-primary-foreground"
                                : "border-border"
                            }`}
                          >
                            {isSelected && <Check className="w-3 h-3" />}
                          </div>
                          <span className="truncate">{t.name}</span>
                          <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                            {t.question_count} questions
                          </span>
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Numeric Limits & Quotas Section ─────────────────────────────────── */}
      <div className="rounded-2xl border border-border bg-card p-4 sm:p-5 flex flex-col gap-4">
        <div>
          <h3 className="text-sm font-bold text-foreground">Usage Quotas & Constraints</h3>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Leave any field empty for <strong>unlimited</strong> usage.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {/* Max Programs */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> Max Programs
            </span>
            <input
              type="number"
              min="0"
              value={data.max_programs ?? ""}
              onChange={(e) => handleQuotaNumber("max_programs", e.target.value)}
              placeholder="Unlimited"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </label>

          {/* Max Cohorts */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5" /> Max Cohorts
            </span>
            <input
              type="number"
              min="0"
              value={data.max_cohorts ?? ""}
              onChange={(e) => handleQuotaNumber("max_cohorts", e.target.value)}
              placeholder="Unlimited"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </label>

          {/* Max Students per Cohort */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Users className="w-3.5 h-3.5" /> Max Students / Cohort
            </span>
            <input
              type="number"
              min="0"
              value={data.max_students_per_cohort ?? ""}
              onChange={(e) => handleQuotaNumber("max_students_per_cohort", e.target.value)}
              placeholder="Unlimited (e.g. 100)"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </label>

          {/* Max Observers per Cohort */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Eye className="w-3.5 h-3.5" /> Max Observers / Cohort
            </span>
            <input
              type="number"
              min="0"
              value={data.max_observers_per_cohort ?? ""}
              onChange={(e) => handleQuotaNumber("max_observers_per_cohort", e.target.value)}
              placeholder="Unlimited (e.g. 5)"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </label>

          {/* Max Landing Pages */}
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
              <Globe className="w-3.5 h-3.5" /> Max Landing Pages
            </span>
            <input
              type="number"
              min="0"
              value={data.max_events ?? ""}
              onChange={(e) => handleQuotaNumber("max_events", e.target.value)}
              placeholder="Unlimited"
              className="w-full h-9 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary"
            />
          </label>
        </div>
      </div>
    </div>
  )
}
