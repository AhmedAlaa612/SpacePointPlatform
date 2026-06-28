import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Upload } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { updatePhotoApi, updateMeApi, getUserStatsApi } from "@/api/auth"
import { ROLE_LABEL } from "@/types/shared"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { ROLE_BADGE, AmbassadorCard, TeacherCard, InstructorCard } from "@/components/ProfileStatsCards"

export default function Profile() {
  const { user, roles, logout, setCurrentUser } = useAuth()
  const qc = useQueryClient()
  const photoRef = useRef<HTMLInputElement>(null)

  const [editing, setEditing] = useState(false)
  const [fullName, setFullName] = useState(user?.full_name ?? "")
  const [phone, setPhone] = useState(user?.phone ?? "")
  const [saved, setSaved] = useState(false)

  const isAmbassador = roles.includes("ambassador")
  const isTeacher    = roles.includes("teacher")
  const isInstructor = roles.includes("instructor") || roles.includes("facilitator")

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => updatePhotoApi(file),
    onSuccess: (updated) => {
      setCurrentUser(updated)
      qc.invalidateQueries({ queryKey: ["me"] })
    },
  })

  const saveInfo = useMutation({
    mutationFn: () => updateMeApi({ full_name: fullName, phone: phone || undefined }),
    onSuccess: (updated) => {
      setCurrentUser(updated)
      setEditing(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const { data: stats } = useQuery({
    queryKey: ["user-stats", user?.id],
    queryFn: () => getUserStatsApi(user!.id),
    enabled: !!user && (isAmbassador || isTeacher || isInstructor),
  })

  if (!user) return null

  const initials = user.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase()

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-5 pt-2">

      {/* Identity */}
      <Card>
        <CardContent className="p-5 flex items-center gap-5">
          <div
            className="relative w-20 h-20 rounded-full bg-muted flex items-center justify-center text-xl font-bold text-foreground cursor-pointer group overflow-hidden border-2 border-border shrink-0"
            onClick={() => photoRef.current?.click()}
            title="Click to change photo"
          >
            {user.photo_url ? (
              <img src={user.photo_url} alt="Profile" className="w-full h-full object-cover" />
            ) : initials}
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-full">
              <Upload size={18} className="text-white" />
            </div>
            {uploadPhoto.isPending && (
              <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-full">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </div>
            )}
          </div>
          <input ref={photoRef} type="file" accept="image/*" className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) uploadPhoto.mutate(f)
              e.currentTarget.value = ""
            }}
          />
          <div className="flex-1 min-w-0">
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
        <CardContent className="p-5 flex flex-col gap-4">
          <p className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">Account info</p>
          {editing ? (
            <>
              <div>
                <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Full name</label>
                <input value={fullName} onChange={(e) => setFullName(e.target.value)}
                  className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary" />
              </div>
              <div>
                <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">WhatsApp</label>
                <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
                  className="w-full h-10 px-3 border border-border bg-background text-foreground rounded-xl text-sm focus:outline-none focus:border-primary" />
              </div>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => { setEditing(false); setFullName(user.full_name); setPhone(user.phone ?? "") }}>
                  Cancel
                </Button>
                <Button className="flex-1" onClick={() => saveInfo.mutate()} disabled={saveInfo.isPending}>
                  {saveInfo.isPending ? "Saving…" : "Save"}
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">Email</p>
                  <p className="text-foreground truncate">{user.email}</p>
                </div>
                <div>
                  <p className="text-xs text-muted-foreground uppercase tracking-wider font-medium mb-0.5">WhatsApp</p>
                  <p className="text-foreground">{user.phone || <span className="text-muted-foreground italic">Not set</span>}</p>
                </div>
              </div>
              {saved && <p className="text-sm text-emerald-600 font-medium">Saved ✓</p>}
              <Button variant="outline" onClick={() => setEditing(true)}>Edit profile</Button>
            </>
          )}
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

      {/* Sign out */}
      <div className="border-t border-border pt-4">
        <Button variant="destructive" onClick={logout}>Sign out</Button>
      </div>
    </div>
  )
}
