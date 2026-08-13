import { useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import { Award, CheckCircle2, Download, LogOut, Pencil, RefreshCw, Upload } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { changePassword, fetchMe, rerollNicknameApi, updateMeApi, updatePhotoApi } from "@/api/auth";
import { fetchMyActivity, fetchMyCertificates, fetchMyCourses } from "@/api/lms";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { CountrySelect } from "@/components/ui/CountrySelect";
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect";
import { getCountries } from "@/lib/countries";
import { EmptyState } from "@/components/ui/primitives";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatTile } from "@/components/ProfileStatsCards";
import { CourseProgress } from "./CourseProgress";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/** /learn/profile (design 2a/2b) — follows the portal's own profile
 * vocabulary (`pages/shared/Profile.tsx`'s edit mutations, `StatTile` from
 * `ProfileStatsCards.tsx`) rather than inventing a new one. Certificates
 * landed 2026-08-13 (auto-issued on course/path completion, see
 * `services/lms/certificates.py`); the achievements grid is still deferred,
 * as are playback-preference toggles — there's no backend to persist those
 * against. */
export default function LearnProfile() {
  const { currentUser, setCurrentUser, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [rerollError, setRerollError] = useState<string | null>(null);

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe, initialData: currentUser ?? undefined });
  const { data: dashboard } = useQuery({ queryKey: ["lms-my-courses"], queryFn: fetchMyCourses });
  const { data: activity } = useQuery({ queryKey: ["lms-my-activity"], queryFn: fetchMyActivity });
  const { data: certificates } = useQuery({ queryKey: ["lms-my-certificates"], queryFn: fetchMyCertificates });

  const reroll = useMutation({
    mutationFn: rerollNicknameApi,
    onSuccess: (updated) => {
      setRerollError(null);
      setCurrentUser(updated);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    onError: (err: unknown) => setRerollError(errorDetail(err, "Couldn't reroll your nickname")),
  });

  if (!me) return null;

  const initials = me.full_name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
  const memberSince = me.created_at
    ? new Date(me.created_at).toLocaleDateString("en-US", { month: "long", year: "numeric" })
    : null;

  const handleLogout = async () => {
    await logout();
    void navigate({ to: "/learn/login" });
  };

  return (
    <div className="mx-auto max-w-[1180px] px-5 sm:px-8 lg:px-10 py-6 sm:py-8 flex flex-col gap-6">
      <Tabs defaultValue="profile">
        <TabsList>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="settings">Settings</TabsTrigger>
        </TabsList>

        <TabsContent value="profile" className="flex flex-col gap-6 mt-6">
          <Card className="flex-row items-center gap-6 p-6">
            <div className="w-24 h-24 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center text-2xl font-display font-bold text-primary overflow-hidden shrink-0">
              {me.photo_url ? <img src={me.photo_url} alt="" className="w-full h-full object-cover" /> : initials}
            </div>
            <div className="flex-1 min-w-0 flex flex-col gap-1.5">
              <div className="flex items-center gap-2.5 flex-wrap">
                <div className="font-display text-2xl font-bold tracking-tight">{me.full_name}</div>
                <span className="text-[11px] font-semibold px-2.5 py-1 rounded-full bg-primary/10 text-primary">Student</span>
              </div>
              <div className="text-sm text-muted-foreground">{me.email}</div>
              {me.nickname && (
                <div className="flex items-center gap-2 text-xs text-muted-foreground" title="What other students see on leaderboards and in live games — never your real name.">
                  <span>Nickname: <span className="font-medium text-foreground">{me.nickname}</span></span>
                  <button
                    onClick={() => { setRerollError(null); reroll.mutate(); }}
                    disabled={reroll.isPending}
                    className="inline-flex items-center gap-1 text-primary hover:opacity-80 cursor-pointer font-medium disabled:opacity-50"
                  >
                    <RefreshCw className={`size-3 ${reroll.isPending ? "animate-spin" : ""}`} />
                    {reroll.isPending ? "Rerolling..." : "Reroll"}
                  </button>
                </div>
              )}
              {rerollError && <div className="text-xs text-destructive">{rerollError}</div>}
              {memberSince && <div className="text-xs text-muted-foreground">Student since {memberSince}</div>}
            </div>
            <Button variant="outline" onClick={() => setEditOpen(true)} className="shrink-0">
              <Pencil className="size-3.5" /> Edit profile
            </Button>
          </Card>

          <div className="grid lg:grid-cols-[1fr_340px] gap-5 items-start">
            <div className="flex flex-col gap-5 min-w-0">
              <div className="flex flex-col gap-3">
                <h2 className="font-display text-lg font-bold tracking-tight">Learning record</h2>
                <div className="grid grid-cols-3 gap-3">
                  <StatTile label="Enrolled" value={dashboard?.stats.total_enrolled ?? 0} />
                  <StatTile label="In progress" value={dashboard?.stats.in_progress ?? 0} />
                  <StatTile label="Modules done" value={dashboard?.stats.modules_done ?? 0} />
                </div>
              </div>

              <Card className="p-5 gap-4">
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-base font-bold tracking-tight">Courses</h2>
                  <button
                    onClick={() => void navigate({ to: "/learn/my-courses" })}
                    className="text-xs font-medium text-primary hover:opacity-80 cursor-pointer"
                  >
                    Go to my courses
                  </button>
                </div>
                {!dashboard || dashboard.courses.length === 0 ? (
                  <EmptyState title="No courses yet" hint="Enrol in something from the catalog to see it here." />
                ) : (
                  <div className="flex flex-col divide-y divide-border">
                    {dashboard.courses.map((c) => (
                      <div key={c.course_id} className="flex items-center gap-4 py-3 first:pt-0 last:pb-0">
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{c.title}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {c.status === "completed" ? "Completed" : `${c.modules_done} of ${c.modules_total} modules`}
                          </div>
                        </div>
                        <CourseProgress value={c.pct} className="w-36 shrink-0 hidden sm:flex" />
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              <Card className="p-5 gap-4">
                <h2 className="font-display text-base font-bold tracking-tight">Recent activity</h2>
                {!activity || activity.length === 0 ? (
                  <EmptyState title="Nothing here yet" hint="Completed lessons, quizzes and flashcards will show up here." />
                ) : (
                  <div className="flex flex-col gap-3">
                    {activity.map((a) => (
                      <div key={a.item_id} className="flex items-start gap-3">
                        <CheckCircle2 className="size-4 text-primary shrink-0 mt-0.5" />
                        <div className="min-w-0">
                          <div className="text-sm text-foreground leading-snug">
                            Completed <span className="font-medium">{a.item_title ?? a.item_kind}</span> in {a.course_title}
                          </div>
                          {a.completed_at && (
                            <div className="text-xs text-muted-foreground mt-0.5">
                              {new Date(a.completed_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              <Card className="p-5 gap-4">
                <h2 className="font-display text-base font-bold tracking-tight">Certificates</h2>
                {!certificates || certificates.length === 0 ? (
                  <EmptyState
                    title="No certificates yet"
                    hint="Finish a course or a learning path and its certificate appears here automatically."
                  />
                ) : (
                  <div className="flex flex-col gap-2">
                    {certificates.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center gap-3 rounded-xl border border-border p-3"
                      >
                        <div className="flex size-10 shrink-0 items-center justify-center rounded-full ring-1 ring-primary/35 text-primary">
                          <Award className="size-5" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-foreground truncate">{c.title}</div>
                          <div className="text-xs text-muted-foreground">
                            {c.type === "lms_path_completion" ? "Learning path" : "Course"}
                            {c.issued_at && ` · ${new Date(c.issued_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`}
                          </div>
                        </div>
                        {c.url && (
                          <a
                            href={c.url}
                            target="_blank"
                            rel="noreferrer"
                            className="shrink-0 flex items-center gap-1.5 text-sm font-medium text-primary hover:opacity-80"
                          >
                            <Download className="size-3.5" /> PDF
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>

            <Card className="p-5 gap-4">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">Account info</div>
              <div className="flex flex-col gap-3">
                <AccountField label="Email" value={me.email} />
                <AccountField label="WhatsApp" value={me.phone || "Not set"} />
                <AccountField
                  label="Location"
                  value={
                    [me.city_name, getCountries().find((c) => c.code === me.country)?.name ?? me.country]
                      .filter(Boolean)
                      .join(", ") || "Not set"
                  }
                />
                {memberSince && <AccountField label="Member since" value={memberSince} />}
              </div>
              <div className="h-px bg-border" />
              <button onClick={() => setPwOpen(true)} className="text-sm font-medium text-primary hover:opacity-80 cursor-pointer text-left">
                Change password
              </button>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="settings" className="flex flex-col gap-4 mt-6 max-w-md">
          <Card className="flex-row items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm font-medium">Change password</div>
              <div className="text-xs text-muted-foreground mt-0.5">Update the password you sign in with.</div>
            </div>
            <Button variant="outline" onClick={() => setPwOpen(true)} className="shrink-0">Change</Button>
          </Card>
          <Card className="flex-row items-center justify-between gap-4 p-5">
            <div>
              <div className="text-sm font-medium text-destructive">Sign out of SpacePoint Learn</div>
              <div className="text-xs text-muted-foreground mt-0.5">Your progress is saved on the server, not this device.</div>
            </div>
            <Button variant="destructive" onClick={() => void handleLogout()} className="shrink-0">
              <LogOut className="size-3.5" /> Sign out
            </Button>
          </Card>
        </TabsContent>
      </Tabs>

      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen} />
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
    </div>
  );
}

function AccountField({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10.5px] font-medium uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className="text-sm mt-0.5">{value}</div>
    </div>
  );
}

function EditProfileDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* Mounting the form fresh each time it opens (instead of an effect
       * that resets state on `open`) is what discards any unsaved edits
       * from a previous open — React's own recommended fix for "reset state
       * when X changes" (see the set-state-in-effect rule this avoids). */}
      {open && <EditProfileForm onOpenChange={onOpenChange} />}
    </Dialog>
  );
}

function EditProfileForm({ onOpenChange }: { onOpenChange: (v: boolean) => void }) {
  const { currentUser, setCurrentUser } = useAuth();
  const queryClient = useQueryClient();
  const photoRef = useRef<HTMLInputElement>(null);
  const [fullName, setFullName] = useState(currentUser?.full_name ?? "");
  const [phone, setPhone] = useState(currentUser?.phone ?? "");
  const [country, setCountry] = useState(currentUser?.country ?? "");
  const [cityId, setCityId] = useState(currentUser?.city_id ?? "");
  const [cityOther, setCityOther] = useState(currentUser?.city_other ?? "");

  const countryCities = useCitiesForCountry(country);

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => updatePhotoApi(file),
    onSuccess: (updated) => {
      setCurrentUser(updated);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const save = useMutation({
    mutationFn: () => updateMeApi({
      full_name: fullName, phone: phone || undefined,
      country: country || undefined, city_id: cityId || undefined, city_other: cityOther || undefined,
    }),
    onSuccess: (updated) => {
      setCurrentUser(updated);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      onOpenChange(false);
    },
  });

  if (!currentUser) return null;

  return (
    <DialogContent className="sm:max-w-md">
      <DialogHeader>
        <DialogTitle className="font-display">Edit profile</DialogTitle>
      </DialogHeader>
        <div className="flex flex-col gap-5 py-2">
          <div className="flex items-center gap-4">
            <div
              className="relative w-16 h-16 rounded-full bg-primary/10 border-2 border-primary/30 flex items-center justify-center text-lg font-display font-bold text-primary overflow-hidden shrink-0 cursor-pointer group"
              onClick={() => photoRef.current?.click()}
            >
              {currentUser.photo_url ? (
                <img src={currentUser.photo_url} alt="" className="w-full h-full object-cover" />
              ) : (
                currentUser.full_name.split(" ").map((w) => w[0]).slice(0, 2).join("")
              )}
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                <Upload size={16} className="text-white" />
              </div>
              {uploadPhoto.isPending && (
                <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
                  <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                </div>
              )}
            </div>
            <input
              ref={photoRef} type="file" accept="image/*" className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) uploadPhoto.mutate(f);
                e.currentTarget.value = "";
              }}
            />
            <div>
              <button onClick={() => photoRef.current?.click()} className="text-sm font-medium text-primary hover:opacity-80 cursor-pointer">
                Upload photo
              </button>
              <div className="text-xs text-muted-foreground mt-0.5">JPG or PNG</div>
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Full name</label>
              <input
                value={fullName} onChange={(e) => setFullName(e.target.value)}
                className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">Email</label>
              <div className="w-full h-11 rounded-xl border border-border/60 bg-muted/30 px-3.5 flex items-center text-sm text-muted-foreground">
                {currentUser.email}
              </div>
              <div className="text-xs text-muted-foreground mt-1.5">Contact support to change your email — it's your sign-in.</div>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                WhatsApp <span className="normal-case font-normal">(optional)</span>
              </label>
              <input
                value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+234..."
                className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-primary transition-colors"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  Country <span className="normal-case font-normal">(optional)</span>
                </label>
                <CountrySelect
                  value={country} onChange={setCountry} valueType="code"
                  className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-primary transition-colors"
                />
              </div>
              {countryCities.length > 0 || country ? (
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                    City <span className="normal-case font-normal">(optional)</span>
                  </label>
                  <CitySelect
                    country={country} value={cityId} onChange={setCityId}
                    otherValue={cityOther} onOtherChange={setCityOther}
                    className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-primary transition-colors"
                  />
                </div>
              ) : null}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isPending ? "Saving..." : "Save changes"}
          </Button>
        </DialogFooter>
    </DialogContent>
  );
}

function ChangePasswordDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const reset = () => {
    setCurrent(""); setNext(""); setConfirm(""); setError(null); setDone(false);
  };

  const change = useMutation({
    mutationFn: () => changePassword(next, current),
    onSuccess: () => {
      setDone(true);
      setError(null);
      setTimeout(() => { reset(); onOpenChange(false); }, 1500);
    },
    onError: (err: unknown) => setError(errorDetail(err, "Failed to change password")),
  });

  const submit = () => {
    setError(null);
    if (next.length < 8) return setError("Password must be at least 8 characters.");
    if (next !== confirm) return setError("Passwords do not match.");
    change.mutate();
  };

  const inputCls = "w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-primary transition-colors";

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">Change password</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2">
          <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} placeholder="Current password" className={inputCls} />
          <input type="password" value={next} onChange={(e) => setNext(e.target.value)} placeholder="New password" className={inputCls} />
          <input type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirm new password" className={inputCls} />
          {error && <p className="text-xs text-destructive">{error}</p>}
          {done && <p className="text-xs text-emerald-500 flex items-center gap-1.5"><CheckCircle2 size={14} /> Password updated</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={change.isPending}>{change.isPending ? "Updating..." : "Update password"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
