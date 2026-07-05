import { useEffect, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Upload, X, CheckCircle2 } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { updatePhotoApi, updateMeApi, getUserStatsApi, fetchMe, changePassword } from "@/api/auth"
import { getIdCardApi } from "@/api/documents"
import { ROLE_LABEL } from "@/types/shared"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { AmbassadorCard, TeacherCard, InstructorCard } from "@/components/ProfileStatsCards"

export default function Profile() {
  const { user, roles, activeRole, setCurrentUser } = useAuth()
  const qc = useQueryClient()
  const photoRef = useRef<HTMLInputElement>(null)

  const isAmbassador = roles.includes("ambassador")
  const isTeacher = roles.includes("teacher")
  const isInstructor = roles.includes("instructor") || roles.includes("facilitator")
  const hasApplicantDetails =
    roles.includes("instructor") || roles.includes("facilitator") || roles.includes("applicant")

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe, initialData: user ?? undefined })

  const [fullName, setFullName] = useState(user?.full_name ?? "")
  const [phone, setPhone] = useState(user?.phone ?? "")
  const [country, setCountry] = useState(user?.country ?? "")
  const [city, setCity] = useState("")
  const [hasTransport, setHasTransport] = useState(false)
  const [deliverCities, setDeliverCities] = useState<string[]>([])
  const [cityInput, setCityInput] = useState("")
  const [saved, setSaved] = useState(false)
  const [pwOpen, setPwOpen] = useState(false)

  useEffect(() => {
    if (!me) return
    setFullName(me.full_name ?? "")
    setPhone(me.phone ?? "")
    setCountry(me.country ?? "")
    setCity(me.city_of_residence ?? "")
    setHasTransport(!!me.has_own_transportation)
    setDeliverCities(me.deliver_cities ?? [])
  }, [me])

  const { data: idCard } = useQuery({
    queryKey: ["instructor-id-card", activeRole],
    queryFn: () => getIdCardApi(activeRole ?? "instructor"),
    enabled: isInstructor,
  })

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => updatePhotoApi(file),
    onSuccess: (updated) => {
      setCurrentUser(updated)
      qc.invalidateQueries({ queryKey: ["me"] })
    },
  })

  const saveInfo = useMutation({
    mutationFn: () =>
      updateMeApi({
        full_name: fullName,
        phone: phone || undefined,
        country: country || undefined,
        ...(hasApplicantDetails
          ? {
              city_of_residence: city || undefined,
              deliver_cities: deliverCities,
              has_own_transportation: hasTransport,
            }
          : {}),
      }),
    onSuccess: (updated) => {
      setCurrentUser(updated)
      qc.invalidateQueries({ queryKey: ["me"] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    },
  })

  const { data: stats } = useQuery({
    queryKey: ["user-stats", user?.id],
    queryFn: () => getUserStatsApi(user!.id),
    enabled: !!user && (isAmbassador || isTeacher || isInstructor),
  })

  if (!user) return null

  const initial = user.full_name.charAt(0).toUpperCase()
  const titleLabel = roles.includes("instructor")
    ? "Certified Instructor"
    : activeRole
    ? ROLE_LABEL[activeRole]
    : roles[0]
    ? ROLE_LABEL[roles[0]]
    : ""
  const joined = me?.created_at
    ? new Date(me.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : null

  const addCity = () => {
    const c = cityInput.trim()
    if (c && !deliverCities.includes(c)) setDeliverCities((prev) => [...prev, c])
    setCityInput("")
  }

  const labelCls = "block text-[11px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5"
  const inputCls =
    "w-full rounded-xl bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary focus:ring-2 focus:ring-primary/30 transition-all"

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-8">
      {/* ── Profile card ─────────────────────────────────────── */}
      <div className="rounded-3xl border border-white/5 bg-card/60 backdrop-blur-xl p-8 shadow-2xl">
        {/* Header */}
        <div className="flex items-center gap-6 pb-8 border-b border-white/10 mb-8">
          <div
            className="relative w-20 h-20 rounded-full bg-muted flex items-center justify-center text-2xl font-display font-bold text-primary border-2 border-primary shadow-[0_0_20px_rgba(167,125,255,0.3)] cursor-pointer group overflow-hidden shrink-0"
            onClick={() => photoRef.current?.click()}
            title="Click to change photo"
          >
            {user.photo_url ? (
              <img src={user.photo_url} alt="Profile" className="w-full h-full object-cover" />
            ) : (
              initial
            )}
            <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center rounded-full">
              <Upload size={18} className="text-white" />
            </div>
            {uploadPhoto.isPending && (
              <div className="absolute inset-0 bg-black/50 flex items-center justify-center rounded-full">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </div>
            )}
          </div>
          <input
            ref={photoRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) uploadPhoto.mutate(f)
              e.currentTarget.value = ""
            }}
          />
          <div className="min-w-0">
            <h2 className="font-display text-2xl font-bold text-foreground truncate">{user.full_name}</h2>
            {titleLabel && (
              <p className="text-primary tracking-wider uppercase text-xs font-semibold mt-1">{titleLabel}</p>
            )}
            {(idCard?.card_id || joined) && (
              <p className="text-muted-foreground/80 text-xs mt-1">
                {idCard?.card_id && <span className="font-mono">{idCard.card_id}</span>}
                {idCard?.card_id && joined && <span> · </span>}
                {joined && <span>Joined {joined}</span>}
              </p>
            )}
          </div>
        </div>

        {/* Form */}
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <div>
              <label className={labelCls}>Full Name</label>
              <input value={fullName} onChange={(e) => setFullName(e.target.value)} className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Phone Number</label>
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="+971 50 000 0000"
                className={inputCls}
              />
            </div>
          </div>

          <div>
            <label className={labelCls}>
              Email <span className="normal-case font-normal text-muted-foreground/60">(cannot be changed)</span>
            </label>
            <div className="w-full rounded-xl bg-muted/30 border border-border/60 px-4 py-2.5 text-sm text-muted-foreground select-all">
              {user.email}
            </div>
          </div>

          {hasApplicantDetails ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className={labelCls}>City of Residence</label>
                <input
                  value={city}
                  onChange={(e) => setCity(e.target.value)}
                  placeholder="e.g. Dubai"
                  className={inputCls}
                />
              </div>
              <div>
                <label className={labelCls}>Country</label>
                <input
                  value={country}
                  onChange={(e) => setCountry(e.target.value)}
                  placeholder="United Arab Emirates"
                  className={inputCls}
                />
              </div>
            </div>
          ) : (
            <div>
              <label className={labelCls}>Country</label>
              <input
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="Country"
                className={inputCls}
              />
            </div>
          )}

          {hasApplicantDetails && (
            <>
              <div className="flex items-center justify-between bg-background/50 border border-border rounded-xl px-5 py-4">
                <div>
                  <p className="text-foreground text-sm font-medium">Own Transportation</p>
                  <p className="text-muted-foreground text-xs mt-0.5">
                    Do you have your own vehicle to travel to workshop locations?
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setHasTransport((v) => !v)}
                  className={`relative w-12 h-6 rounded-full transition-all shrink-0 ${
                    hasTransport ? "bg-primary" : "bg-muted-foreground/30"
                  }`}
                  aria-pressed={hasTransport}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      hasTransport ? "translate-x-6" : ""
                    }`}
                  />
                </button>
              </div>

              <div>
                <label className={labelCls}>Cities I Can Deliver In</label>
                <div className="flex gap-2 mb-2">
                  <input
                    value={cityInput}
                    onChange={(e) => setCityInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault()
                        addCity()
                      }
                    }}
                    placeholder="Type a city and press Enter or Add"
                    className={`flex-1 ${inputCls}`}
                  />
                  <button
                    type="button"
                    onClick={addCity}
                    className="px-4 py-2.5 rounded-xl bg-primary/10 hover:bg-primary hover:text-primary-foreground text-primary border border-primary/30 text-sm font-semibold transition-all shrink-0"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2 min-h-[36px]">
                  {deliverCities.length === 0 ? (
                    <span className="text-muted-foreground/60 text-sm italic">No cities added yet.</span>
                  ) : (
                    deliverCities.map((c) => (
                      <span
                        key={c}
                        className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-primary/10 border border-primary/30 text-primary text-sm"
                      >
                        {c}
                        <button
                          type="button"
                          onClick={() => setDeliverCities((prev) => prev.filter((x) => x !== c))}
                          className="text-primary/60 hover:text-red-400 transition-colors"
                        >
                          <X size={13} />
                        </button>
                      </span>
                    ))
                  )}
                </div>
              </div>
            </>
          )}

          {saved && (
            <p className="text-sm text-emerald-500 font-medium flex items-center gap-1.5">
              <CheckCircle2 size={15} /> Changes saved
            </p>
          )}

          <div className="flex items-center gap-4 pt-2">
            <button
              onClick={() => saveInfo.mutate()}
              disabled={saveInfo.isPending}
              className="flex-1 py-3 rounded-xl bg-primary text-primary-foreground font-bold text-sm hover:bg-primary/90 transition-all shadow-lg shadow-primary/20 disabled:opacity-60"
            >
              {saveInfo.isPending ? "Saving…" : "Save Changes"}
            </button>
            <button
              onClick={() => setPwOpen(true)}
              className="px-5 py-3 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:border-foreground/20 text-sm font-medium transition-all"
            >
              Change Password
            </button>
          </div>
        </div>
      </div>

      {/* ── Extra: role stat cards ───────────────────────────── */}
      {isAmbassador && stats?.ambassador && <AmbassadorCard name={user.full_name} stats={stats.ambassador} />}
      {isTeacher && stats?.teacher && <TeacherCard name={user.full_name} stats={stats.teacher} />}
      {isInstructor && stats?.instructor && <InstructorCard stats={stats.instructor} />}

      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} mustChange={!!user.must_change_password} />
    </div>
  )
}

function ChangePasswordDialog({
  open,
  onOpenChange,
  mustChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  mustChange: boolean
}) {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const reset = () => {
    setCurrent("")
    setNext("")
    setConfirm("")
    setError(null)
    setDone(false)
  }

  const change = useMutation({
    mutationFn: () => changePassword(next, mustChange ? undefined : current),
    onSuccess: () => {
      setDone(true)
      setError(null)
      setTimeout(() => {
        reset()
        onOpenChange(false)
      }, 1500)
    },
    onError: (err: any) => setError(err?.response?.data?.detail || "Failed to change password"),
  })

  const submit = () => {
    setError(null)
    if (next.length < 8) return setError("Password must be at least 8 characters.")
    if (next !== confirm) return setError("Passwords do not match.")
    change.mutate()
  }

  const inputCls =
    "w-full rounded-xl bg-background border border-border px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:border-primary transition-all"

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v)
        if (!v) reset()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-base font-display font-bold">Change Password</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2">
          {!mustChange && (
            <input
              type="password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              placeholder="Current password"
              className={inputCls}
            />
          )}
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="New password"
            className={inputCls}
          />
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirm new password"
            className={inputCls}
          />
          {error && <p className="text-xs text-red-500">{error}</p>}
          {done && (
            <p className="text-xs text-emerald-500 flex items-center gap-1.5">
              <CheckCircle2 size={14} /> Password updated
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={change.isPending}>
            {change.isPending ? "Updating…" : "Update Password"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
