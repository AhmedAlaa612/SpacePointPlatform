import { useState } from "react"
import type { PlatformFootprint, ResolvedAnswer } from "@/api/apply"
import { Button } from "@/components/ui/button"
import { UserProfileModal } from "@/components/UserProfileModal"
import { ExternalLink, FileText, Globe2, History, UserCheck } from "lucide-react"

function formatDateStr(val: string | null | undefined): string {
  if (!val) return "—"
  const d = new Date(val)
  if (Number.isNaN(d.getTime())) return val
  return d.toLocaleDateString()
}

function AnswerValue({ item }: { item: ResolvedAnswer }) {
  const { value, question_type } = item
  if (value === null || value === undefined || value === "") {
    return <span className="text-muted-foreground italic">Not answered</span>
  }
  if (Array.isArray(value)) {
    return (
      <div className="flex flex-wrap gap-1.5 mt-1">
        {value.map((v, i) => (
          <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            {String(v)}
          </span>
        ))}
      </div>
    )
  }
  const str = String(value)
  if (question_type === "multiple_choice" && str.includes(",")) {
    const parts = str.split(",").map((s) => s.trim()).filter(Boolean)
    return (
      <div className="flex flex-wrap gap-1.5 mt-1">
        {parts.map((p, i) => (
          <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary">
            {p}
          </span>
        ))}
      </div>
    )
  }
  if ((question_type === "url" || str.startsWith("http://") || str.startsWith("https://")) && !str.includes(" ")) {
    return (
      <a
        href={str}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 text-sm text-primary hover:underline break-all"
      >
        {str} <ExternalLink size={12} />
      </a>
    )
  }
  return <p className="text-sm text-foreground whitespace-pre-wrap break-words">{str}</p>
}

export function ResolvedAnswersSection({
  answers,
  title = "Custom Questions & Answers",
}: {
  answers?: ResolvedAnswer[]
  title?: string
}) {
  if (!answers || answers.length === 0) return null

  return (
    <div className="bg-muted/30 rounded-xl p-4 flex flex-col gap-3">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{title}</p>
      <div className="flex flex-col gap-3">
        {answers.map((item) => (
          <div key={item.key} className="border-b border-border/50 pb-2.5 last:border-0 last:pb-0">
            <div className="flex items-center gap-2 flex-wrap">
              <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
              {item.is_deleted && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                  Removed question
                </span>
              )}
              {item.is_legacy && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                  Legacy field
                </span>
              )}
            </div>
            <div className="mt-0.5">
              <AnswerValue item={item} />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export function PlatformFootprintSection({
  footprint,
  title = "Cross-Platform Record & History",
}: {
  footprint?: PlatformFootprint | null
  title?: string
}) {
  const [profileUserId, setProfileUserId] = useState<string | null>(null)
  if (!footprint) return null
  const hasAnything = Boolean(
    footprint.existing_user ||
      footprint.spine_contact ||
      footprint.other_applications.length > 0 ||
      footprint.role_requests.length > 0 ||
      footprint.instructor_onboarding ||
      footprint.intern_profile,
  )

  return (
    <div className="bg-muted/30 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <Globe2 size={14} className="text-muted-foreground" />
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">{title}</p>
      </div>

      {!hasAnything ? (
        <p className="text-xs text-muted-foreground">No prior account, CRM contact, or other applications matched this email.</p>
      ) : (
        <div className="flex flex-col gap-3 text-xs">
          {footprint.existing_user && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <UserCheck size={13} className="text-emerald-500" />
                  Existing User Account
                </span>
                <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-mono text-[11px]">
                  {footprint.existing_user.card_id || footprint.existing_user.status}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
                <span>Roles: <strong className="text-foreground">{footprint.existing_user.roles.join(", ") || "—"}</strong></span>
                <span>Joined: <strong className="text-foreground">{formatDateStr(footprint.existing_user.created_at)}</strong></span>
                <span>Last login: <strong className="text-foreground">{formatDateStr(footprint.existing_user.last_login_at)}</strong></span>
                {footprint.existing_user.student_id && (
                  <span>Student ID: <strong className="text-foreground font-mono">{footprint.existing_user.student_id}</strong></span>
                )}
              </div>
              <div className="pt-1.5">
                <Button
                  type="button"
                  onClick={() => setProfileUserId(footprint.existing_user!.id)}
                  className="h-auto py-2 px-4 rounded-[10px] bg-[#653F84] hover:bg-[#653F84]/90 text-white text-xs font-medium"
                >
                  Open User Profile
                </Button>
              </div>
            </div>
          )}

          {footprint.spine_contact && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="font-semibold text-foreground">Spine CRM Contact</span>
                <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-[11px]">
                  {footprint.spine_contact.lifecycle_stage}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
                <span>Contact roles: <strong className="text-foreground">{footprint.spine_contact.contact_roles.join(", ") || "—"}</strong></span>
                {footprint.spine_contact.organization_name && (
                  <span>Organization: <strong className="text-foreground">{footprint.spine_contact.organization_name}</strong></span>
                )}
                {footprint.spine_contact.primary_phone && (
                  <span>Phone: <strong className="text-foreground">{footprint.spine_contact.primary_phone}</strong></span>
                )}
                {footprint.spine_contact.whatsapp && (
                  <span>WhatsApp: <strong className="text-foreground">{footprint.spine_contact.whatsapp}</strong></span>
                )}
              </div>
              {footprint.spine_contact.notes && (
                <p className="text-muted-foreground border-t border-border/40 pt-1.5 mt-1">
                  Notes: <span className="text-foreground">{footprint.spine_contact.notes}</span>
                </p>
              )}
            </div>
          )}

          {footprint.other_applications.length > 0 && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1.5">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <History size={13} className="text-amber-500" />
                Other Applications ({footprint.other_applications.length})
              </span>
              {footprint.other_applications.map((oa) => (
                <div key={oa.id} className="flex items-center justify-between gap-2 border-t border-border/40 pt-1.5">
                  <span className="capitalize text-foreground">
                    {oa.role} · <span className="text-muted-foreground">{formatDateStr(oa.created_at)}</span>
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{oa.status}</span>
                </div>
              ))}
            </div>
          )}

          {footprint.role_requests.length > 0 && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1.5">
              <span className="font-semibold text-foreground">
                Role Requests ({footprint.role_requests.length})
              </span>
              {footprint.role_requests.map((rr) => (
                <div key={rr.id} className="flex items-center justify-between gap-2 border-t border-border/40 pt-1.5">
                  <span className="capitalize text-foreground">
                    Target: {rr.target_role} · <span className="text-muted-foreground">{formatDateStr(rr.created_at)}</span>
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-muted text-muted-foreground capitalize">{rr.status}</span>
                </div>
              ))}
            </div>
          )}

          {footprint.instructor_onboarding && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-foreground">Instructor Onboarding</span>
                <span className="px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-400 capitalize">
                  {(footprint.instructor_onboarding.status || "").replace(/_/g, " ")}
                </span>
              </div>
              {footprint.instructor_onboarding.feedback && (
                <p className="text-muted-foreground">Feedback: <span className="text-foreground">{footprint.instructor_onboarding.feedback}</span></p>
              )}
            </div>
          )}

          {footprint.intern_profile && (
            <div className="rounded-lg bg-background/60 border border-border/60 p-3 flex flex-col gap-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-semibold text-foreground flex items-center gap-1.5">
                  <FileText size={13} className="text-blue-400" />
                  Intern Profile & Letter
                </span>
                {footprint.intern_profile.ref_number && (
                  <span className="font-mono text-foreground">{footprint.intern_profile.ref_number}</span>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-muted-foreground">
                {footprint.intern_profile.work_city && (
                  <span>Work City: <strong className="text-foreground">{footprint.intern_profile.work_city}</strong></span>
                )}
                {footprint.intern_profile.start_date && (
                  <span>Start Date: <strong className="text-foreground">{footprint.intern_profile.start_date}</strong></span>
                )}
                {footprint.intern_profile.duration_weeks && (
                  <span>Duration: <strong className="text-foreground">{footprint.intern_profile.duration_weeks} wks</strong></span>
                )}
                {footprint.intern_profile.letter_signed_at && (
                  <span>Signed: <strong className="text-emerald-500">{formatDateStr(footprint.intern_profile.letter_signed_at)}</strong></span>
                )}
              </div>
              {(footprint.intern_profile.letter_url || footprint.intern_profile.signed_letter_url) && (
                <div className="flex flex-wrap gap-3 pt-1">
                  {footprint.intern_profile.letter_url && (
                    <a href={footprint.intern_profile.letter_url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline inline-flex items-center gap-1">
                      View Generated Letter <ExternalLink size={11} />
                    </a>
                  )}
                  {footprint.intern_profile.signed_letter_url && (
                    <a href={footprint.intern_profile.signed_letter_url} target="_blank" rel="noopener noreferrer" className="text-emerald-500 hover:underline inline-flex items-center gap-1">
                      View Signed Letter <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
      {profileUserId && (
        <UserProfileModal userId={profileUserId} onClose={() => setProfileUserId(null)} />
      )}
    </div>
  )
}

