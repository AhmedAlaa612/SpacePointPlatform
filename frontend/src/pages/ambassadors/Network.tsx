import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ChevronRight, Check, X } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import {
  getMyTeachersApi, getMyInstructorsApi, getAllSessionsApi,
} from "@/api/ambassadors/network"
import { listMyTeacherApplicationsApi, approveTeacherApplicationApi, rejectTeacherApplicationApi, getTeacherApplicationQuestionsApi } from "@/api/ambassadors/application"
import type { TeacherSession, TeacherApplication } from "@/types/ambassadors"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PageHeader, Spinner, EmptyState, StatusPill } from "@/pages/ambassadors/components/common"
import { NetworkTree } from "@/pages/ambassadors/components/NetworkTree"
import { SessionDetailModal } from "@/pages/ambassadors/components/SessionDetailModal"

export default function Network() {
  const { currentUser } = useAuth()
  const qc = useQueryClient()
  const [selectedSession, setSelectedSession] = useState<TeacherSession | null>(null)
  const [selectedApp, setSelectedApp] = useState<TeacherApplication | null>(null)

  const teachers = useQuery({ queryKey: ["teachers"], queryFn: getMyTeachersApi })
  const instructors = useQuery({ queryKey: ["instructors"], queryFn: getMyInstructorsApi })
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: getAllSessionsApi })
  const applications = useQuery({ queryKey: ["teacher-applications"], queryFn: () => listMyTeacherApplicationsApi() })
  const appQuestions = useQuery({ queryKey: ["application-questions-public"], queryFn: getTeacherApplicationQuestionsApi })
  const questionMap = Object.fromEntries((appQuestions.data ?? []).map(q => [q.id, q.question_text]))

  const approveApp = useMutation({
    mutationFn: (id: string) => approveTeacherApplicationApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teacher-applications"] })
      qc.invalidateQueries({ queryKey: ["teachers"] })
      qc.invalidateQueries({ queryKey: ["dashboard"] })
      setSelectedApp(null)
    },
  })

  const rejectApp = useMutation({
    mutationFn: (id: string) => rejectTeacherApplicationApi(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teacher-applications"] })
      setSelectedApp(null)
    },
  })

  if (teachers.isLoading || instructors.isLoading || sessions.isLoading || applications.isLoading) return <Spinner />

  const inviteCode = currentUser?.invite_code
  const teacherLink = inviteCode ? `${window.location.origin}/apply/teacher/${inviteCode}` : null
  const instructorLink = inviteCode ? `${window.location.origin}/apply/instructor/${inviteCode}` : null

  return (
    <div>
      <PageHeader title="My Network" subtitle="Your teachers, instructors and their sessions." />

      {inviteCode && (
        <Card className="mb-6">
          <CardContent className="p-5">
            <div className="mb-4">
              <p className="text-sm font-semibold text-foreground mb-3">Invite code & links</p>
              <p className="text-xs text-muted-foreground mb-4">Share these with people who want to join your network.</p>
            </div>

            <div className="space-y-3">
              {/* Invite Code */}
              <div className="flex items-center gap-2 p-3 bg-gray-50 dark:bg-zinc-900/30 rounded-lg">
                <div className="flex-1">
                  <p className="text-xs font-medium text-muted-foreground">Your invite code</p>
                  <code className="text-sm font-mono text-foreground">{inviteCode}</code>
                </div>
                <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(inviteCode)}>
                  Copy code
                </Button>
              </div>

              {/* Teacher Link */}
              {teacherLink && (
                <div className="flex items-center gap-2 p-3 bg-gray-50 dark:bg-zinc-900/30 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">Teacher join link</p>
                    <p className="text-sm text-gray-700 dark:text-zinc-300 truncate">{teacherLink}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(teacherLink)}>
                    Copy
                  </Button>
                </div>
              )}

              {/* Instructor Link */}
              {instructorLink && (
                <div className="flex items-center gap-2 p-3 bg-gray-50 dark:bg-zinc-900/30 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">Instructor join link</p>
                    <p className="text-sm text-gray-700 dark:text-zinc-300 truncate">{instructorLink}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(instructorLink)}>
                    Copy
                  </Button>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Sessions ── directly under the invite code */}
      <Card className="mb-6">
        <CardHeader><CardTitle>Sessions</CardTitle></CardHeader>
        <CardContent>
          {(sessions.data ?? []).length === 0 ? (
            <EmptyState title="No sessions submitted yet" />
          ) : (
            <div className="max-h-80 overflow-y-auto divide-y divide-gray-50 dark:divide-zinc-800 pr-1">
              {sessions.data!.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s)}
                  className="w-full flex items-center justify-between py-3 gap-2 text-left hover:bg-gray-50/60 dark:hover:bg-zinc-800/40 rounded-lg px-1"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-foreground truncate">{s.title}</p>
                    <p className="text-xs text-gray-400 truncate">
                      {s.teacher_name} · {new Date(s.date).toLocaleDateString()}
                      {s.status === "done" && ` · ${s.attended_students} students`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {s.status === "pending" && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Needs review" />}
                    {s.status === "approved" && !s.material_sent && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Send material" />}
                    <StatusPill status={s.status} />
                    <ChevronRight size={16} className="text-gray-300" />
                  </div>
                </button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Network tree */}
      <Card className="mb-6">
        <CardHeader><CardTitle>Network map</CardTitle></CardHeader>
        <CardContent>
          <NetworkTree
            rootName={currentUser?.full_name ?? "You"}
            teachers={teachers.data ?? []}
            instructors={instructors.data ?? []}
            sessions={sessions.data ?? []}
          />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pending Applications */}
        <Card>
          <CardHeader><CardTitle>Teacher Applications</CardTitle></CardHeader>
          <CardContent>
            {(applications.data?.filter(a => a.status === "pending") ?? []).length === 0 ? (
              <EmptyState title="No pending applications" />
            ) : (
              <div className="divide-y divide-gray-50 dark:divide-zinc-800">
                {applications.data!.filter(a => a.status === "pending").map((a) => (
                  <div key={a.id} className="flex items-center justify-between py-3 gap-2">
                    <button
                      onClick={() => setSelectedApp(a)}
                      className="flex-1 min-w-0 text-left hover:bg-gray-50 dark:hover:bg-zinc-800/50 px-1 py-1 rounded"
                    >
                      <p className="font-medium text-foreground truncate">{a.full_name}</p>
                      <p className="text-xs text-gray-400 truncate">{a.email}</p>
                    </button>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant="default"
                        onClick={() => approveApp.mutate(a.id)}
                        disabled={approveApp.isPending}
                      >
                        <Check size={16} />
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => rejectApp.mutate(a.id)}
                        disabled={rejectApp.isPending}
                      >
                        <X size={16} />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Teachers */}
        <Card>
          <CardHeader><CardTitle>Active Teachers</CardTitle></CardHeader>
          <CardContent>
            {(teachers.data ?? []).length === 0 ? (
              <EmptyState title="No teachers yet" hint="Share your invite code to recruit teachers." />
            ) : (
              <div className="divide-y divide-gray-50 dark:divide-zinc-800">
                {teachers.data!.map((t) => (
                  <Link
                    key={t.id}
                    to="/ambassadors/network/teacher/$teacherId"
                    params={{ teacherId: t.id }}
                    className="flex items-center justify-between py-3 gap-2 hover:bg-gray-50 dark:hover:bg-zinc-800/50 rounded-lg px-1 -mx-1"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">{t.full_name}</p>
                      <p className="text-xs text-gray-400 truncate">{t.email}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusPill status={t.status} />
                      <ChevronRight size={15} className="text-gray-300" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Instructors */}
        <Card>
          <CardHeader><CardTitle>Instructors</CardTitle></CardHeader>
          <CardContent>
            {(instructors.data ?? []).length === 0 ? (
              <EmptyState title="No instructors yet" />
            ) : (
              <div className="divide-y divide-gray-50 dark:divide-zinc-800">
                {instructors.data!.map((i) => (
                  <div key={i.id} className="flex items-center justify-between py-3 gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">{i.full_name}</p>
                      <p className="text-xs text-gray-400 truncate">{i.email}</p>
                    </div>
                    <StatusPill status={i.status} />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {selectedSession && (
        <SessionDetailModal session={selectedSession} role="manager" onClose={() => setSelectedSession(null)} />
      )}

      {/* Teacher Application Detail Modal */}
      {selectedApp && (
        <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-opacity-80 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-zinc-900 rounded-lg max-w-2xl w-full max-h-[90vh] overflow-y-auto border dark:border-zinc-800">
            <div className="p-6 border-b border-gray-200 dark:border-zinc-800 sticky top-0 bg-white dark:bg-zinc-900">
              <h2 className="text-xl font-bold text-foreground">{selectedApp.full_name}</h2>
              <p className="text-sm text-muted-foreground">{selectedApp.email}</p>
            </div>

            <div className="p-6 space-y-6">
              {/* Application Answers */}
              {selectedApp.answers && Object.keys(selectedApp.answers).length > 0 && (
                <div>
                  <h3 className="font-semibold text-foreground mb-4">Application Answers</h3>
                  <div className="space-y-4">
                    {Object.entries(selectedApp.answers).map(([qId, answer]) => (
                      <div key={qId} className="p-3 bg-gray-50 dark:bg-zinc-950 rounded-lg border dark:border-zinc-800">
                        <p className="text-sm font-medium text-muted-foreground mb-1">{questionMap[qId] ?? "Unknown question"}</p>
                        <p className="text-sm text-foreground">{Array.isArray(answer) ? answer.join(", ") : String(answer)}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 pt-4 border-t border-gray-200 dark:border-zinc-800">
                <Button
                  variant="default"
                  onClick={() => approveApp.mutate(selectedApp.id)}
                  disabled={approveApp.isPending}
                  className="flex-1"
                >
                  {approveApp.isPending ? "Approving…" : "Approve"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => rejectApp.mutate(selectedApp.id)}
                  disabled={rejectApp.isPending}
                  className="flex-1"
                >
                  {rejectApp.isPending ? "Rejecting…" : "Reject"}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setSelectedApp(null)}
                  className="flex-1"
                >
                  Close
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
