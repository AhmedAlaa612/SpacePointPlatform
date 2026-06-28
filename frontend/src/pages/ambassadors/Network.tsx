import { useState } from "react"
import { Link } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { ChevronRight } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import {
  getMyTeachersApi, getMyInstructorsApi, getAllSessionsApi,
} from "@/api/ambassadors/network"
import type { TeacherSession } from "@/types/ambassadors"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { PageHeader, Spinner, EmptyState, StatusPill } from "@/pages/ambassadors/components/common"
import { NetworkTree } from "@/pages/ambassadors/components/NetworkTree"
import { SessionDetailModal } from "@/pages/ambassadors/components/SessionDetailModal"

export default function Network() {
  const { currentUser } = useAuth()
  const [selectedSession, setSelectedSession] = useState<TeacherSession | null>(null)

  const teachers = useQuery({ queryKey: ["teachers"], queryFn: getMyTeachersApi })
  const instructors = useQuery({ queryKey: ["instructors"], queryFn: getMyInstructorsApi })
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: getAllSessionsApi })

  if (teachers.isLoading || instructors.isLoading || sessions.isLoading) return <Spinner />

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
              <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
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
                <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">Teacher join link</p>
                    <p className="text-sm text-foreground truncate">{teacherLink}</p>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigator.clipboard?.writeText(teacherLink)}>
                    Copy
                  </Button>
                </div>
              )}

              {/* Instructor Link */}
              {instructorLink && (
                <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg">
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium text-muted-foreground">Instructor join link</p>
                    <p className="text-sm text-foreground truncate">{instructorLink}</p>
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
            <div className="max-h-80 overflow-y-auto divide-y divide-border pr-1">
              {sessions.data!.map((s) => (
                <button
                  key={s.id}
                  onClick={() => setSelectedSession(s)}
                  className="w-full flex items-center justify-between py-3 gap-2 text-left hover:bg-muted/50 rounded-lg px-1"
                >
                  <div className="min-w-0">
                    <p className="font-medium text-foreground truncate">{s.title}</p>
                    <p className="text-xs text-muted-foreground truncate">
                      {s.teacher_name} · {new Date(s.date).toLocaleDateString()}
                      {s.status === "done" && ` · ${s.attended_students} students`}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {s.status === "pending" && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Needs review" />}
                    {s.status === "approved" && !s.material_sent && <span className="w-2 h-2 rounded-full bg-heliotrope" title="Send material" />}
                    <StatusPill status={s.status} />
                    <ChevronRight size={16} className="text-muted-foreground" />
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
        {/* Teachers */}
        <Card>
          <CardHeader><CardTitle>Active Teachers</CardTitle></CardHeader>
          <CardContent>
            {(teachers.data ?? []).length === 0 ? (
              <EmptyState title="No teachers yet" hint="Share your invite code to recruit teachers." />
            ) : (
              <div className="divide-y divide-border">
                {teachers.data!.map((t) => (
                  <Link
                    key={t.id}
                    to="/ambassadors/network/teacher/$teacherId"
                    params={{ teacherId: t.id }}
                    className="flex items-center justify-between py-3 gap-2 hover:bg-muted/50 rounded-lg px-1 -mx-1"
                  >
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">{t.full_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{t.email}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <StatusPill status={t.status} />
                      <ChevronRight size={15} className="text-muted-foreground" />
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
              <div className="divide-y divide-border">
                {instructors.data!.map((i) => (
                  <div key={i.id} className="flex items-center justify-between py-3 gap-2">
                    <div className="min-w-0">
                      <p className="font-medium text-foreground truncate">{i.full_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{i.email}</p>
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
    </div>
  )
}
