import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { Download } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { updateMeApi } from "@/api/interns/auth"
import { getMyDocumentsApi } from "@/api/documents"

const roleBadge: Record<string, string> = {
  admin:  "bg-black text-white",
  leader: "bg-[#643f83] text-white",
  intern: "bg-[#d6c7e1] text-[#643f83]",
}

export default function Profile() {
  const { currentUser, setCurrentUser } = useAuth()
  const [editing, setEditing] = useState(false)
  const [fullName, setFullName] = useState(currentUser?.full_name ?? "")
  const [phone, setPhone] = useState(currentUser?.phone ?? "")
  const [saved, setSaved] = useState(false)

  const saveMutation = useMutation({
    mutationFn: () => updateMeApi({ full_name: fullName, phone: phone || undefined }),
    onSuccess: (updated) => {
      setCurrentUser(updated)
      setEditing(false)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  if (!currentUser) return null

  const initials = currentUser.full_name
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()

  return (
    <div className="max-w-md mx-auto flex flex-col gap-6 pt-4">
      <div className="flex items-center gap-4">
        <div className="w-16 h-16 rounded-full bg-[#d6c7e1]/40 dark:bg-[#d6c7e1]/10 text-[#643f83] dark:text-[#d6c7e1] text-xl font-bold flex items-center justify-center flex-shrink-0 border border-border">
          {initials}
        </div>
        <div>
          <p className="text-lg font-bold text-foreground">{currentUser.full_name}</p>
          <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${roleBadge[currentUser.role ?? "intern"]}`}>
            {currentUser.role}
          </span>
        </div>
      </div>

      <div className="border border-border bg-card rounded-2xl p-5 flex flex-col gap-4">
        <div>
          <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1">Email</p>
          <p className="text-sm text-foreground">{currentUser.email}</p>
        </div>

        {editing ? (
          <>
            <div>
              <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">Full name</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)}
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
            </div>
            <div>
              <label className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1 block">WhatsApp number</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors" />
              <p className="text-xs text-muted-foreground mt-1">Used for WhatsApp contact on task cards</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => { setEditing(false); setFullName(currentUser.full_name); setPhone(currentUser.phone ?? "") }}
                className="flex-1 h-10 border border-border rounded-xl text-sm font-medium text-muted-foreground hover:bg-muted transition-colors">
                Cancel
              </button>
              <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
                className="flex-1 h-10 bg-primary text-primary-foreground rounded-xl text-sm font-medium hover:opacity-90 transition-colors disabled:opacity-50">
                {saveMutation.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1">WhatsApp</p>
              <p className="text-sm text-foreground">{currentUser.phone || <span className="text-muted-foreground/50 italic">Not set</span>}</p>
            </div>
            <button onClick={() => setEditing(true)}
              className="h-10 border border-border bg-card rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors">
              Edit profile
            </button>
          </>
        )}

        {saved && <p className="text-sm text-green-600 font-medium text-center">Saved ✓</p>}
      </div>

      <MyDocuments />
    </div>
  )
}

function MyDocuments() {
  const { data, isLoading } = useQuery({ queryKey: ["my-documents"], queryFn: getMyDocumentsApi })

  const items = [
    ...(data?.certificates ?? []).map((c) => ({
      id: c.id,
      label: c.type === "internship_completion" ? "Internship completion certificate" : "Certificate",
      url: c.file_url,
    })),
    ...(data?.recommendation_letters ?? []).map((r) => ({ id: r.id, label: "Recommendation letter", url: r.file_url })),
    ...(data?.intern_letters ?? []).map((l) => ({
      id: l.id, label: l.type === "completion" ? "Completion letter" : "Confirmation letter", url: l.file_url,
    })),
  ]

  if (isLoading) return null

  return (
    <div className="border border-border bg-card rounded-2xl p-5 flex flex-col gap-3">
      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">My documents</p>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground/70 italic">Nothing generated for you yet</p>
      ) : (
        items.map((item) => (
          <a
            key={item.id} href={item.url} target="_blank" rel="noreferrer"
            className="flex items-center justify-between text-sm text-foreground hover:text-primary transition-colors"
          >
            <span>{item.label}</span>
            <Download size={14} />
          </a>
        ))
      )}
    </div>
  )
}
