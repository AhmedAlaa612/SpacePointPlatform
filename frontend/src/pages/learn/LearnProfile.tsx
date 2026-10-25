import { useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  Award,
  CheckCircle2,
  Download,
  LogOut,
  Pencil,
  Plus,
  RefreshCw,
  Upload,
  Users,
  Ticket,
  KeyRound,
  ArrowRight,
  BookOpen,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { changePassword, fetchMe, rerollNicknameApi, updateMeApi, updatePhotoApi } from "@/api/auth";
import { fetchMyActivity, fetchMyCertificates, fetchMyCourses } from "@/api/lms";
import { fetchMyTeams } from "@/api/missions";
import { Button } from "@/components/ui/button";
import { CountrySelect } from "@/components/ui/CountrySelect";
import { CitySelect, useCitiesForCountry } from "@/components/ui/CitySelect";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { getCountries } from "@/lib/countries";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ImageCropModal } from "@/components/ui/ImageCropModal";
import { cn } from "@/lib/utils";
import { CourseProgress } from "./CourseProgress";
import { RedeemInviteModal } from "./components/RedeemInviteModal";

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

type ProfileTab = "record" | "certificates" | "teams";

export default function LearnProfile() {
  const { currentUser, setCurrentUser, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [tab, setTab] = useState<ProfileTab>("record");
  const [editOpen, setEditOpen] = useState(false);
  const [pwOpen, setPwOpen] = useState(false);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [rerollError, setRerollError] = useState<string | null>(null);

  const { data: me } = useQuery({ queryKey: ["me"], queryFn: fetchMe, initialData: currentUser ?? undefined });
  const { data: dashboard } = useQuery({ queryKey: ["lms-my-courses"], queryFn: fetchMyCourses });
  const { data: activity } = useQuery({ queryKey: ["lms-my-activity"], queryFn: fetchMyActivity });
  const { data: certificates = [] } = useQuery({ queryKey: ["lms-my-certificates"], queryFn: fetchMyCertificates });
  const { data: teams = [] } = useQuery({ queryKey: ["my-teams"], queryFn: fetchMyTeams });

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

  const rawBirthDate = me.birthdate || me.date_of_birth;
  const birthDateFormatted = rawBirthDate
    ? new Date(rawBirthDate).toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: "numeric",
      })
    : "Not set";

  const location = [me.city_name, getCountries().find((c) => c.code === me.country)?.name ?? me.country]
    .filter(Boolean)
    .join(", ");

  const redeemedCodes = (me.invitation_codes_used && me.invitation_codes_used.length > 0)
    ? me.invitation_codes_used.map((c) => c.code)
    : me.invitation_code_used
    ? [me.invitation_code_used]
    : [];

  const handleLogout = async () => {
    await logout();
    void navigate({ to: "/learn/login" });
  };

  return (
    <div className="mx-auto max-w-[1240px] px-6 sm:px-10 lg:px-12 py-10 sm:py-16 flex flex-col gap-10 sm:gap-12">
      {/* Profile Identity Card */}
      <section className="lms-card p-6 sm:p-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6">
        <div className="flex items-center gap-5 sm:gap-6 min-w-0">
          <div className="size-20 sm:size-24 rounded-full border-2 border-lms-accent bg-lms-cta-light flex items-center justify-center font-display font-extrabold text-2xl sm:text-3xl text-lms-cta dark:text-lms-accent overflow-hidden shrink-0 shadow-sm">
            {me.photo_url ? (
              <img src={me.photo_url} alt="" className="w-full h-full object-cover" />
            ) : (
              initials
            )}
          </div>
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-display text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight truncate">
                {me.full_name}
              </h1>
              <span
                className={cn(
                  "text-[10px] sm:text-xs font-bold uppercase tracking-wider px-2.5 py-0.5 rounded-full border",
                  me.roles?.includes("observer")
                    ? "bg-lms-cta-light text-lms-cta dark:text-lms-accent border-lms-accent-border"
                    : "bg-white/10 text-white border-white/20"
                )}
              >
                {me.roles?.includes("observer") ? "Observer" : "Student"}
              </span>
            </div>

            {me.nickname && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground flex-wrap">
                <span className="font-bold uppercase tracking-wider text-[11px] text-[#A880FF]">
                  Callsign:
                </span>
                <strong className="font-semibold text-foreground">{me.nickname}</strong>
                <button
                  onClick={() => {
                    setRerollError(null);
                    reroll.mutate();
                  }}
                  disabled={reroll.isPending}
                  className="inline-flex items-center gap-1 text-xs text-[#A880FF] hover:underline cursor-pointer disabled:opacity-50"
                  title="Reroll callsign"
                >
                  <RefreshCw className={cn("size-3", reroll.isPending && "animate-spin")} />
                  {reroll.isPending ? "Rerolling..." : "Reroll"}
                </button>
              </div>
            )}
            {rerollError && <p className="text-xs text-destructive">{rerollError}</p>}
            {memberSince && (
              <span className="text-[11px] text-muted-foreground">
                Explorer since {memberSince}
              </span>
            )}
          </div>
        </div>

        <button
          onClick={() => setEditOpen(true)}
          className="lms-btn-secondary h-11 px-5 text-xs sm:text-sm inline-flex items-center gap-2 cursor-pointer shrink-0"
        >
          <Pencil className="size-3.5" />
          Edit profile
        </button>
      </section>

      {/* Account & Security Layout */}
      <section className="lms-card p-6 sm:p-8 flex flex-col gap-6">
        <h2 className="font-display text-xl sm:text-2xl font-extrabold text-foreground tracking-tight">
          Account & security
        </h2>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Account Details */}
          <div className="lg:col-span-7 flex flex-col divide-y divide-border/20">
            <div className="py-3.5 first:pt-0 grid grid-cols-3 sm:grid-cols-4 items-center text-xs">
              <span className="font-bold text-muted-foreground uppercase tracking-wider text-[11px]">
                Email
              </span>
              <span className="col-span-2 sm:col-span-3 font-medium text-foreground truncate">
                {me.email}
              </span>
            </div>

            <div className="py-3.5 grid grid-cols-3 sm:grid-cols-4 items-center text-xs">
              <span className="font-bold text-muted-foreground uppercase tracking-wider text-[11px]">
                WhatsApp
              </span>
              <span className="col-span-2 sm:col-span-3 font-medium text-foreground">
                {me.phone || "Not set"}
              </span>
            </div>

            <div className="py-3.5 grid grid-cols-3 sm:grid-cols-4 items-center text-xs">
              <span className="font-bold text-muted-foreground uppercase tracking-wider text-[11px]">
                Location
              </span>
              <span className="col-span-2 sm:col-span-3 font-medium text-foreground">
                {location || "Not set"}
              </span>
            </div>

            <div className="py-3.5 last:pb-0 grid grid-cols-3 sm:grid-cols-4 items-center text-xs">
              <span className="font-bold text-muted-foreground uppercase tracking-wider text-[11px]">
                Birthdate
              </span>
              <span className="col-span-2 sm:col-span-3 font-medium text-foreground">
                {birthDateFormatted}
              </span>
            </div>
          </div>

          {/* Security & Quick Actions */}
          <div className="lg:col-span-5 flex flex-col gap-3 border-t lg:border-t-0 lg:border-l border-border/40 pt-6 lg:pt-0 lg:pl-8">
            <button
              onClick={() => setRedeemOpen(true)}
              className="lms-btn-secondary h-11 px-4 text-xs sm:text-sm inline-flex items-center justify-between cursor-pointer w-full"
            >
              <span className="inline-flex items-center gap-2">
                <Ticket className="size-4 text-[#A880FF]" />
                Redeem invite code
              </span>
              <ArrowRight className="size-3.5 text-muted-foreground" />
            </button>

            <button
              onClick={() => setPwOpen(true)}
              className="lms-btn-secondary h-11 px-4 text-xs sm:text-sm inline-flex items-center justify-between cursor-pointer w-full"
            >
              <span className="inline-flex items-center gap-2">
                <KeyRound className="size-4 text-[#A880FF]" />
                Change password
              </span>
              <ArrowRight className="size-3.5 text-muted-foreground" />
            </button>

            <button
              onClick={() => void handleLogout()}
              className="lms-btn-secondary h-11 px-4 text-xs sm:text-sm inline-flex items-center justify-between cursor-pointer w-full text-red-400/90 hover:text-red-300 hover:border-red-500/50"
            >
              <span className="inline-flex items-center gap-2">
                <LogOut className="size-4" />
                Sign out
              </span>
              <ArrowRight className="size-3.5" />
            </button>

            {redeemedCodes.length > 0 && (
              <div className="flex flex-col gap-1.5 pt-2">
                <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                  Redeemed Codes
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {redeemedCodes.map((code) => (
                    <span
                      key={code}
                      className="font-mono text-xs font-semibold px-2 py-0.5 rounded border border-lms-accent-border bg-lms-cta-light text-lms-cta dark:text-lms-accent"
                    >
                      {code}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Tabs Control */}
      <div className="flex items-center gap-2.5 sm:gap-3 flex-wrap">
        <button
          onClick={() => setTab("record")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "record"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          <BookOpen className="size-4" />
          Learning record
        </button>

        <button
          onClick={() => setTab("certificates")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "certificates"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          <Award className="size-4" />
          Certificates
          {certificates.length > 0 && (
            <span
              className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded-full",
                tab === "certificates" ? "bg-white/20 text-white" : "text-muted-foreground"
              )}
            >
              {certificates.length}
            </span>
          )}
        </button>

        <button
          onClick={() => setTab("teams")}
          className={cn(
            "h-10 px-5 rounded-full text-xs sm:text-sm font-bold transition-all cursor-pointer inline-flex items-center gap-2 select-none",
            tab === "teams"
              ? "bg-lms-cta text-white shadow-none"
              : "bg-transparent text-muted-foreground border border-border/60 dark:border-lms-accent-border hover:text-foreground hover:border-lms-accent"
          )}
        >
          <Users className="size-4" />
          Teams
          {teams.length > 0 && (
            <span
              className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded-full",
                tab === "teams" ? "bg-white/20 text-white" : "text-muted-foreground"
              )}
            >
              {teams.length}
            </span>
          )}
        </button>
      </div>

      {/* Tab Panels */}
      {tab === "record" && (
        <div className="flex flex-col gap-8">
          {/* Course Progress List */}
          <div className="lms-card p-6 sm:p-8 flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-xl font-bold text-foreground">
                Course progress
              </h2>
              <button
                onClick={() => void navigate({ to: "/learn/my-courses" })}
                className="text-xs font-semibold text-[#A880FF] hover:underline inline-flex items-center gap-1 cursor-pointer"
              >
                Go to my learning <ArrowRight className="size-3" />
              </button>
            </div>

            {!dashboard || dashboard.courses.length === 0 ? (
              <div className="py-8 text-center text-xs sm:text-sm text-muted-foreground">
                No enrolled courses yet. Explore the catalog to start learning.
              </div>
            ) : (
              <div className="flex flex-col divide-y divide-border/20">
                {dashboard.courses.map((c) => (
                  <div
                    key={c.course_id}
                    onClick={() => void navigate({ to: `/learn/courses/${c.course_id}/learn` as never })}
                    className="py-4 first:pt-0 last:pb-0 flex flex-col sm:flex-row sm:items-center justify-between gap-4 cursor-pointer group"
                  >
                    <div className="flex-1 min-w-0">
                      <strong className="font-semibold text-sm text-foreground group-hover:text-[#A880FF] transition-colors truncate block">
                        {c.title}
                      </strong>
                      <span className="text-xs text-muted-foreground mt-0.5 block">
                        {c.status === "completed"
                          ? "Completed"
                          : `${c.modules_done} of ${c.modules_total} modules completed`}
                      </span>
                    </div>

                    <div className="w-full sm:w-56 shrink-0 flex items-center gap-3">
                      <CourseProgress value={c.pct} className="flex-1" />
                      <ArrowRight className="size-4 text-muted-foreground group-hover:text-[#A880FF] transition-colors shrink-0" />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity */}
          {activity && activity.length > 0 && (
            <div className="lms-card p-6 sm:p-8 flex flex-col gap-5">
              <h2 className="font-display text-xl font-bold text-foreground">
                Recent activity
              </h2>
              <div className="flex flex-col divide-y divide-border/20">
                {activity.map((a) => (
                  <div key={a.item_id} className="py-3.5 first:pt-0 last:pb-0 flex items-start gap-3">
                    <CheckCircle2 className="size-4 text-[#A880FF] shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1 flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                      <span className="text-xs sm:text-sm text-foreground">
                        Completed <strong className="font-semibold">{a.item_title ?? a.item_kind}</strong> in {a.course_title}
                      </span>
                      {a.completed_at && (
                        <span className="text-[11px] text-muted-foreground shrink-0">
                          {new Date(a.completed_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "certificates" && (
        <div className="flex flex-col gap-6">
          {certificates.length === 0 ? (
            <div className="lms-card p-12 text-center flex flex-col items-center gap-3">
              <Award className="size-10 text-muted-foreground/40" />
              <h3 className="font-display text-lg font-bold text-foreground">No certificates yet</h3>
              <p className="text-xs sm:text-sm text-muted-foreground max-w-sm">
                Complete a course or program checklist to earn and download verified certificates.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {certificates.map((c) => (
                <div key={c.id} className="lms-card p-6 flex flex-col justify-between gap-5">
                  <div className="flex flex-col gap-3">
                    <div className="size-10 rounded-full border border-lms-accent-border bg-lms-cta-light flex items-center justify-center text-lms-cta dark:text-lms-accent">
                      <Award className="size-5" />
                    </div>
                    <div>
                      <strong className="font-display text-base font-bold text-foreground block line-clamp-2">
                        {c.title}
                      </strong>
                      <span className="text-xs text-muted-foreground mt-1 block">
                        {c.type === "student_completion"
                          ? "Program Certificate"
                          : c.type === "lms_path_completion"
                          ? "Learning Path Certificate"
                          : "Course Certificate"}
                        {c.issued_at &&
                          ` · ${new Date(c.issued_at).toLocaleDateString("en-US", {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}`}
                      </span>
                    </div>
                  </div>

                  {c.url && (
                    <a
                      href={c.url}
                      target="_blank"
                      rel="noreferrer"
                      className="lms-btn-secondary h-10 px-4 text-xs inline-flex items-center justify-center gap-2 cursor-pointer font-bold"
                    >
                      <Download className="size-3.5" />
                      Download PDF
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "teams" && (
        <div className="flex flex-col gap-6">
          {teams.length === 0 ? (
            <div className="lms-card p-12 text-center flex flex-col items-center gap-3">
              <Users className="size-10 text-muted-foreground/40" />
              <h3 className="font-display text-lg font-bold text-foreground">No teams yet</h3>
              <p className="text-xs sm:text-sm text-muted-foreground max-w-sm">
                Join or create a team inside a collaborative space mission or cohort.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {teams.map((t) => (
                <div key={t.id} className="lms-card p-6 flex flex-col justify-between gap-4">
                  <div className="flex flex-col gap-2">
                    <div className="size-10 rounded-full border border-lms-accent-border bg-lms-cta-light flex items-center justify-center text-lms-cta dark:text-lms-accent">
                      <Users className="size-5" />
                    </div>
                    <strong className="font-display text-base font-bold text-foreground truncate mt-1">
                      {t.name}
                    </strong>
                    <span className="text-xs text-muted-foreground">
                      {t.cohort_id ? "Cohort team" : "Self-formed team"}
                    </span>
                  </div>

                  {t.member_names && t.member_names.length > 0 && (
                    <div className="border-t border-border/20 pt-3 flex flex-col gap-1">
                      <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                        Members ({t.member_names.length})
                      </span>
                      <p className="text-xs text-foreground/80 line-clamp-2">
                        {t.member_names.join(", ")}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Functional Dialogs */}
      <EditProfileDialog open={editOpen} onOpenChange={setEditOpen} />
      <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
      <RedeemInviteModal
        open={redeemOpen}
        onOpenChange={setRedeemOpen}
        onSuccess={() => {
          void queryClient.invalidateQueries({ queryKey: ["me"] });
          void queryClient.invalidateQueries({ queryKey: ["lms-my-checklists"] });
          void queryClient.invalidateQueries({ queryKey: ["lms-my-courses"] });
        }}
      />
    </div>
  );
}

function EditProfileDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
  const [birthdate, setBirthdate] = useState(currentUser?.birthdate || currentUser?.date_of_birth || "");
  const [cropSrc, setCropSrc] = useState<string | null>(null);
  const [cropOpen, setCropOpen] = useState(false);

  const countryCities = useCitiesForCountry(country);

  const uploadPhoto = useMutation({
    mutationFn: (file: File) => updatePhotoApi(file),
    onSuccess: (updated) => {
      setCurrentUser(updated);
      void queryClient.invalidateQueries({ queryKey: ["me"] });
      setCropOpen(false);
      setCropSrc(null);
    },
  });

  const save = useMutation({
    mutationFn: () =>
      updateMeApi({
        full_name: fullName,
        phone: phone || undefined,
        country: country || undefined,
        birthdate: birthdate || undefined,
        date_of_birth: birthdate || undefined,
        city_id: cityId || undefined,
        city_other: cityOther || undefined,
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
            className="relative w-16 h-16 rounded-full bg-lms-cta-light border-2 border-lms-accent/50 flex items-center justify-center text-lg font-display font-bold text-lms-cta dark:text-lms-accent overflow-hidden shrink-0 cursor-pointer group"
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
            ref={photoRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) {
                const reader = new FileReader();
                reader.onload = () => {
                  setCropSrc(reader.result as string);
                  setCropOpen(true);
                };
                reader.readAsDataURL(f);
              }
              e.currentTarget.value = "";
            }}
          />
          <div>
            <button
              onClick={() => photoRef.current?.click()}
              className="text-sm font-medium text-[#A880FF] hover:underline cursor-pointer"
            >
              Upload photo
            </button>
            <div className="text-xs text-muted-foreground mt-0.5">JPG or PNG</div>
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Full name</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">Email</label>
            <div className="w-full h-11 rounded-xl border border-border/60 bg-muted/30 px-3.5 flex items-center text-sm text-muted-foreground">
              {currentUser.email}
            </div>
            <div className="text-xs text-muted-foreground mt-1.5">
              Contact support to change your email — it's your sign-in.
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              WhatsApp <span className="normal-case font-normal">(optional)</span>
            </label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+971..."
              className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1.5">
              Birthdate <span className="normal-case font-normal">(optional)</span>
            </label>
            <input
              type="date"
              value={birthdate ? birthdate.slice(0, 10) : ""}
              onChange={(e) => setBirthdate(e.target.value)}
              className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                Country <span className="normal-case font-normal">(optional)</span>
              </label>
              <CountrySelect
                value={country}
                onChange={setCountry}
                valueType="code"
                className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors"
              />
            </div>
            {countryCities.length > 0 || country ? (
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1.5">
                  City <span className="normal-case font-normal">(optional)</span>
                </label>
                <CitySelect
                  country={country}
                  value={cityId}
                  onChange={setCityId}
                  otherValue={cityOther}
                  onOtherChange={setCityOther}
                  className="w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors"
                />
              </div>
            ) : null}
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="outline" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button onClick={() => save.mutate()} disabled={save.isPending} className="bg-lms-cta hover:bg-lms-cta-hover text-white">
          {save.isPending ? "Saving..." : "Save changes"}
        </Button>
      </DialogFooter>

      {cropSrc && (
        <ImageCropModal
          isOpen={cropOpen}
          onClose={() => {
            if (!uploadPhoto.isPending) {
              setCropOpen(false);
              setCropSrc(null);
            }
          }}
          imageSrc={cropSrc}
          title="Crop Profile Photo"
          aspect={1}
          circularCrop={true}
          showPreview={false}
          isUploading={uploadPhoto.isPending}
          onCropComplete={async (croppedFile) => {
            await uploadPhoto.mutateAsync(croppedFile);
          }}
        />
      )}
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
    setCurrent("");
    setNext("");
    setConfirm("");
    setError(null);
    setDone(false);
  };

  const change = useMutation({
    mutationFn: () => changePassword(next, current),
    onSuccess: () => {
      setDone(true);
      setError(null);
      setTimeout(() => {
        reset();
        onOpenChange(false);
      }, 1500);
    },
    onError: (err: unknown) => setError(errorDetail(err, "Failed to change password")),
  });

  const submit = () => {
    setError(null);
    if (next.length < 8) return setError("Password must be at least 8 characters.");
    if (next !== confirm) return setError("Passwords do not match.");
    change.mutate();
  };

  const inputCls =
    "w-full h-11 rounded-xl border border-border bg-background px-3.5 text-sm focus:outline-none focus:border-[#A880FF] transition-colors";

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        onOpenChange(v);
        if (!v) reset();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display">Change password</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3 py-2">
          <PasswordInput
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="Current password"
            className={inputCls}
          />
          <PasswordInput
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="New password"
            className={inputCls}
          />
          <PasswordInput
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Confirm new password"
            className={inputCls}
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
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
          <Button onClick={submit} disabled={change.isPending} className="bg-lms-cta hover:bg-lms-cta-hover text-white">
            {change.isPending ? "Updating..." : "Update password"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
