import { useQuery } from "@tanstack/react-query"
import { X } from "lucide-react"
import { getUserProfileApi, getUserStatsApi } from "@/api/auth"
import { ROLE_LABEL } from "@/types/shared"
import { Card, CardContent } from "@/components/ui/card"
import { ROLE_BADGE, AmbassadorCard, TeacherCard, InstructorCard } from "@/components/ProfileStatsCards"

interface Props {
  userId: string
  onClose: () => void
}

export function UserProfileModal({ userId, onClose }: Props) {
  const { data: user, isLoading: loadingUser } = useQuery({
    queryKey: ["user-profile", userId],
    queryFn: () => getUserProfileApi(userId),
  })

  const roles = user?.roles ?? []
  const isAmbassador = roles.includes("ambassador")
  const isTeacher    = roles.includes("teacher")
  const isInstructor = roles.includes("instructor") || roles.includes("facilitator")

  const { data: stats, isLoading: loadingStats } = useQuery({
    queryKey: ["user-stats", userId],
    queryFn: () => getUserStatsApi(userId),
    enabled: !!user && (isAmbassador || isTeacher || isInstructor),
  })

  const isLoading = loadingUser || loadingStats

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-background w-full max-w-lg h-screen flex flex-col shadow-2xl border-l border-border">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-border shrink-0">
          <p className="text-sm font-semibold text-foreground">Profile</p>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted transition-colors"
          >
            <X size={16} />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          <div className="p-5 flex flex-col gap-4">
            {isLoading ? (
              <div className="flex items-center justify-center py-16">
                <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
              </div>
            ) : !user ? (
              <p className="text-sm text-muted-foreground text-center py-8">User not found</p>
            ) : (
              <>
                {/* Identity */}
                <Card>
                  <CardContent className="p-5 flex items-center gap-5">
                    <div className="w-20 h-20 rounded-full bg-muted border-2 border-border flex items-center justify-center text-xl font-bold text-foreground overflow-hidden shrink-0">
                      {user.photo_url ? (
                        <img src={user.photo_url} alt={user.full_name} className="w-full h-full object-cover" />
                      ) : (
                        user.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-lg font-bold text-foreground truncate">{user.full_name}</p>
                      <p className="text-sm text-muted-foreground truncate">{user.email}</p>
                      {user.country && <p className="text-xs text-muted-foreground mt-0.5">{user.country}</p>}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {roles.map((r) => (
                          <span key={r} className={`text-[11px] font-semibold px-2.5 py-0.5 rounded-full ${ROLE_BADGE[r] ?? "bg-muted text-foreground"}`}>
                            {ROLE_LABEL[r] ?? r}
                          </span>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>

                {/* Account info */}
                <Card>
                  <CardContent className="p-5 flex flex-col gap-3">
                    <p className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Account info</p>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">Email</p>
                        <p className="text-foreground truncate">{user.email}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">WhatsApp</p>
                        <p className="text-foreground">{user.phone ?? <span className="text-muted-foreground italic">Not set</span>}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">Status</p>
                        <p className={`font-medium ${user.status === "active" ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
                          {user.status}
                        </p>
                      </div>
                      {user.created_at && (
                        <div>
                          <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">Member since</p>
                          <p className="text-foreground">
                            {new Date(user.created_at).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" })}
                          </p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>

                {isAmbassador && stats?.ambassador && (
                  <AmbassadorCard name={user.full_name} stats={stats.ambassador} />
                )}
                {isTeacher && stats?.teacher && (
                  <TeacherCard name={user.full_name} stats={stats.teacher} />
                )}
                {isInstructor && stats?.instructor && (
                  <InstructorCard stats={stats.instructor} />
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
