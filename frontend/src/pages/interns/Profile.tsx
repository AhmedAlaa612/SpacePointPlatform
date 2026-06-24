import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { useAuth } from "@/context/AuthContext"
import { updateMeApi } from "@/api/interns/auth"

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
        <div className="w-16 h-16 rounded-full bg-black text-white text-xl font-bold flex items-center justify-center flex-shrink-0">
          {initials}
        </div>
        <div>
          <p className="text-lg font-bold text-black">{currentUser.full_name}</p>
          <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full ${roleBadge[currentUser.role ?? "intern"]}`}>
            {currentUser.role}
          </span>
        </div>
      </div>

      <div className="border border-gray-100 rounded-2xl p-5 flex flex-col gap-4">
        <div>
          <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-1">Email</p>
          <p className="text-sm text-black">{currentUser.email}</p>
        </div>

        {editing ? (
          <>
            <div>
              <label className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-1 block">Full name</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)}
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
            </div>
            <div>
              <label className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-1 block">WhatsApp number</label>
              <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+20 10 0000 0000"
                className="w-full h-10 px-3 border border-gray-200 rounded-xl text-sm focus:outline-none focus:border-black transition-colors" />
              <p className="text-xs text-gray-400 mt-1">Used for WhatsApp contact on task cards</p>
            </div>
            <div className="flex gap-2">
              <button onClick={() => { setEditing(false); setFullName(currentUser.full_name); setPhone(currentUser.phone ?? "") }}
                className="flex-1 h-10 border border-gray-200 rounded-xl text-sm font-medium text-gray-600 hover:bg-gray-50 transition-colors">
                Cancel
              </button>
              <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
                className="flex-1 h-10 bg-black text-white rounded-xl text-sm font-medium hover:bg-gray-900 transition-colors disabled:opacity-50">
                {saveMutation.isPending ? "Savingâ€¦" : "Save"}
              </button>
            </div>
          </>
        ) : (
          <>
            <div>
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-1">WhatsApp</p>
              <p className="text-sm text-black">{currentUser.phone || <span className="text-gray-400 italic">Not set</span>}</p>
            </div>
            <button onClick={() => setEditing(true)}
              className="h-10 border border-gray-200 rounded-xl text-sm font-medium text-black hover:bg-gray-50 transition-colors">
              Edit profile
            </button>
          </>
        )}

        {saved && <p className="text-sm text-green-600 font-medium text-center">Saved âœ“</p>}
      </div>
    </div>
  )
}
