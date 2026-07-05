import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { X, FileText, ExternalLink, CreditCard } from "lucide-react"
import { getUserProfileApi, getUserStatsApi } from "@/api/auth"
import { getUserDossierApi, getUserIdCardApi, type DossierItem } from "@/api/admin/users"
import { ROLE_LABEL } from "@/types/shared"
import { Card, CardContent } from "@/components/ui/card"
import { ROLE_BADGE, AmbassadorCard, TeacherCard, InstructorCard } from "@/components/ProfileStatsCards"

function IdCardDialog({ userId, role, onClose }: { userId: string; role: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-user-id-card", userId, role],
    queryFn: () => getUserIdCardApi(userId, role),
  })
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="bg-card rounded-2xl p-5 max-w-lg w-full flex flex-col gap-3" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold text-foreground">{data?.card_id ?? "ID Card"}</p>
          <button onClick={onClose} className="p-1.5 rounded-lg text-muted-foreground hover:bg-muted"><X size={16} /></button>
        </div>
        {isLoading ? (
          <div className="py-10 flex justify-center"><div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {data?.front_b64 && <img src={`data:image/png;base64,${data.front_b64}`} alt="Front" className="w-full rounded-lg border border-border" />}
            {data?.back_b64 && <img src={`data:image/png;base64,${data.back_b64}`} alt="Back" className="w-full rounded-lg border border-border" />}
          </div>
        )}
      </div>
    </div>
  )
}

function DossierSection({ userId }: { userId: string }) {
  const [cardView, setCardView] = useState<string | null>(null)
  const { data, isLoading } = useQuery({
    queryKey: ["admin-user-dossier", userId],
    queryFn: () => getUserDossierApi(userId),
  })

  const groups = (data?.items ?? []).reduce<Record<string, DossierItem[]>>((acc, item) => {
    (acc[item.category] ??= []).push(item)
    return acc
  }, {})

  return (
    <Card>
      <CardContent className="p-5 flex flex-col gap-3">
        <p className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Documents</p>
        {isLoading ? (
          <div className="py-4 flex justify-center"><div className="w-5 h-5 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>
        ) : Object.keys(groups).length === 0 ? (
          <p className="text-sm text-muted-foreground italic">No documents on file.</p>
        ) : (
          Object.entries(groups).map(([category, items]) => (
            <div key={category} className="flex flex-col gap-1.5">
              <p className="text-[11px] font-semibold text-muted-foreground">{category}</p>
              {items.map((item, i) => (
                <div key={i} className="flex items-center gap-2 text-sm px-2.5 py-1.5 rounded-lg bg-muted/50">
                  {category === "ID Cards" ? <CreditCard size={14} className="text-muted-foreground shrink-0" /> : <FileText size={14} className="text-muted-foreground shrink-0" />}
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground truncate">{item.label}</p>
                    <p className="text-[11px] text-muted-foreground truncate">
                      {[item.meta, item.date ? new Date(item.date).toLocaleDateString() : null].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  {category === "ID Cards" && item.url ? (
                    <button
                      onClick={() => setCardView(new URL(item.url!, window.location.origin).searchParams.get("role") ?? "")}
                      className="p-1 rounded text-muted-foreground hover:text-primary shrink-0"
                    >
                      <ExternalLink size={14} />
                    </button>
                  ) : item.url ? (
                    <a href={item.url} target="_blank" rel="noreferrer" className="p-1 rounded text-muted-foreground hover:text-primary shrink-0">
                      <ExternalLink size={14} />
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          ))
        )}
      </CardContent>
      {cardView && <IdCardDialog userId={userId} role={cardView} onClose={() => setCardView(null)} />}
    </Card>
  )
}

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

                <DossierSection userId={userId} />
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
