import { useState } from "react"
import { Building2, Check, ChevronRight, Lock, Mail, Phone, Upload, User as UserIcon } from "lucide-react"
import type { ApplyQuestion, FormFieldConfig } from "@/api/apply"
import { CustomQuestionsFields, isFieldEnabled, isFieldRequired } from "@/components/apply/CustomQuestionsFields"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

const ROLE_LABEL: Record<string, string> = {
  ambassador: "SpacePoint Ambassador",
  intern: "SpacePoint Intern",
  teacher: "SpacePoint Teacher",
  facilitator: "SpacePoint Facilitator",
}

const DEGREES = ["High School", "Diploma", "Bachelor's", "Master's", "PhD", "Other"]
const BACKGROUNDS = [
  "Aerospace Engineering",
  "Mechanical Engineering",
  "Electrical Engineering",
  "Computer Science",
  "Physics",
  "Mathematics",
  "Education",
  "Other",
]

function PreviewField({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium text-muted-foreground">
        {label} {required && <span className="text-destructive">*</span>}
      </label>
      {children}
    </div>
  )
}

export function ApplicationLivePreview({
  role,
  fields,
  questions,
}: {
  role: string
  fields: FormFieldConfig[]
  questions: ApplyQuestion[]
}) {
  const [step, setStep] = useState<1 | 2>(1)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [hasInviteCode, setHasInviteCode] = useState(false)
  const [applyLocation, setApplyLocation] = useState<"within" | "outside">("within")
  const [hasCar, setHasCar] = useState<"true" | "false" | "">("")
  const [parentOpen, setParentOpen] = useState(false)
  const visibleQuestions = questions.filter((q) => q.enabled !== false)

  if (role === "instructor") {
    const reqMark = (key: string, fallback = false) =>
      isFieldRequired(fields, key, fallback) ? <span className="text-destructive"> *</span> : (
        <span className="text-xs text-muted-foreground font-normal"> (optional)</span>
      )

    return (
      <div className="dark rounded-[10px] border border-border bg-[#0b0713] text-white p-5">
        <div className="max-w-2xl mx-auto">
          <div className="mb-5 flex items-center justify-center">
            <img src="/space-logo-white.png" alt="SpacePoint" className="h-9 w-auto object-contain" />
          </div>

          <h2 className="text-center text-xl font-bold text-foreground tracking-tight">Submit Your Interest</h2>
          <p className="mt-1 text-center text-xs text-muted-foreground mb-5">
            Complete your details to create your SpacePoint account.
          </p>

          <div className="flex flex-col gap-4">
            {isFieldEnabled(fields, "invite_code", true) && (
              <div className="rounded-[10px] border border-border p-4 space-y-2.5">
                <label className="block text-sm font-medium text-foreground">
                  Do you have an invitation code?{reqMark("invite_code", false)}
                </label>
                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setHasInviteCode(true)}
                    className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                      hasInviteCode
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    Yes
                  </button>
                  <button
                    type="button"
                    onClick={() => setHasInviteCode(false)}
                    className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                      !hasInviteCode
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:bg-muted"
                    }`}
                  >
                    No
                  </button>
                </div>
                {hasInviteCode && (
                  <input className="input uppercase" placeholder="INV-XXXXX" readOnly />
                )}
              </div>
            )}

            <div className="rounded-[10px] border border-border p-4 space-y-2.5">
              <label className="block text-sm font-medium text-foreground">
                Are you applying from within the UAE or outside the UAE?
              </label>
              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={() => setApplyLocation("within")}
                  className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                    applyLocation === "within"
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Within UAE
                </button>
                <button
                  type="button"
                  onClick={() => setApplyLocation("outside")}
                  className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                    applyLocation === "outside"
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-muted-foreground hover:bg-muted"
                  }`}
                >
                  Outside UAE
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Full Name <span className="text-destructive">*</span></label>
                <input className="input" placeholder="Full name" readOnly />
              </div>
              {isFieldEnabled(fields, "phone", true) && (
                <div>
                  <label className="block text-sm font-medium text-foreground mb-1">
                    Phone Number{reqMark("phone", true)}
                  </label>
                  <input className="input" type="tel" placeholder="e.g., +971 50 123 4567" readOnly />
                </div>
              )}
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Email Address <span className="text-destructive">*</span></label>
                <input className="input" type="email" placeholder="you@example.com" readOnly />
              </div>
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">Password <span className="text-destructive">*</span></label>
                <input className="input" type="password" placeholder="Password" readOnly />
              </div>
            </div>

            {(isFieldEnabled(fields, "birthdate", true) || isFieldEnabled(fields, "nationality", true)) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {isFieldEnabled(fields, "birthdate", true) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Date of Birth{reqMark("birthdate", true)}
                    </label>
                    <input className="input" type="date" readOnly />
                  </div>
                )}
                {isFieldEnabled(fields, "nationality", true) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Nationality{reqMark("nationality", true)}
                    </label>
                    <select className="input" defaultValue="">
                      <option value="">Select nationality...</option>
                    </select>
                  </div>
                )}
              </div>
            )}

            {(isFieldEnabled(fields, "work_status", true) || isFieldEnabled(fields, "fluent_languages", true)) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {isFieldEnabled(fields, "work_status", true) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Current Work Status{reqMark("work_status", true)}
                    </label>
                    <input className="input" placeholder="e.g. Space Systems Engineer, Student" readOnly />
                  </div>
                )}
                {isFieldEnabled(fields, "fluent_languages", true) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      Fluent Languages{reqMark("fluent_languages", true)}
                    </label>
                    <input className="input" placeholder="Select fluent languages..." readOnly />
                  </div>
                )}
              </div>
            )}

            {isFieldEnabled(fields, "graduated_university", true) && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  University (Attending or Graduated){reqMark("graduated_university", true)}
                </label>
                <input className="input" placeholder="e.g. Khalifa University, UAEU, UOWD" readOnly />
              </div>
            )}

            {isFieldEnabled(fields, "university", true) && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Other / Unlisted University{reqMark("university", false)}
                </label>
                <input className="input" placeholder="Optional university name" readOnly />
              </div>
            )}

            {isFieldEnabled(fields, "highest_degree", true) && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Highest Degree{reqMark("highest_degree", true)}
                </label>
                <select className="input" defaultValue="">
                  <option value="">Select...</option>
                  {DEGREES.map((d) => <option key={d} value={d}>{d}</option>)}
                </select>
              </div>
            )}

            {isFieldEnabled(fields, "country", true) && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  Country of Residence{reqMark("country", true)}
                </label>
                <select className="input" defaultValue="AE">
                  <option value="AE">United Arab Emirates</option>
                </select>
              </div>
            )}

            {applyLocation === "within" && (
              <>
                {isFieldEnabled(fields, "city_of_residence_id", true) && (
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-1">
                      City of Residence{reqMark("city_of_residence_id", true)}
                    </label>
                    <select className="input" defaultValue="">
                      <option value="">Select...</option>
                    </select>
                  </div>
                )}

                {isFieldEnabled(fields, "has_own_transportation", true) && (
                  <div className="rounded-[10px] border border-border p-4 space-y-2.5">
                    <label className="block text-sm font-medium text-foreground">
                      Do you have a car / own transportation?{reqMark("has_own_transportation", false)}
                    </label>
                    <div className="flex gap-3">
                      <button
                        type="button"
                        onClick={() => setHasCar("true")}
                        className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                          hasCar === "true"
                            ? "bg-primary text-primary-foreground border-primary"
                            : "border-border text-muted-foreground hover:bg-muted"
                        }`}
                      >
                        Yes, I have a car
                      </button>
                      <button
                        type="button"
                        onClick={() => setHasCar("false")}
                        className={`flex-1 py-2 rounded-[10px] border text-sm font-bold transition-all ${
                          hasCar === "false"
                            ? "bg-rose-500/20 text-rose-300 border-rose-500/50"
                            : "border-border text-muted-foreground hover:bg-muted"
                        }`}
                      >
                        No, I don't
                      </button>
                    </div>
                  </div>
                )}

                {isFieldEnabled(fields, "deliver_city_ids", true) && (
                  <div>
                    <p className="text-sm font-medium text-foreground mb-2">
                      Can you deliver sessions in any of the following cities?{reqMark("deliver_city_ids", true)}
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {["Abu Dhabi", "Dubai", "Sharjah", "Al Ain"].map((c) => (
                        <div key={c} className="flex items-center gap-2.5 rounded-[10px] border border-border px-3 py-2 text-xs text-muted-foreground">
                          <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border border-border bg-background">
                            <Check className="h-3 w-3 opacity-0" />
                          </span>
                          <span>{c}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            {isFieldEnabled(fields, "background_areas", true) && (
              <div>
                <p className="text-sm font-medium text-foreground mb-2">
                  Which areas best describe your background?{reqMark("background_areas", true)}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  {BACKGROUNDS.map((b) => (
                    <div key={b} className="flex items-center gap-2.5 rounded-[10px] border border-border px-3 py-2 text-xs text-muted-foreground">
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border border-border bg-background" />
                      <span>{b}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {isFieldEnabled(fields, "cv", true) && (
              <div>
                <label className="block text-sm font-medium text-foreground mb-1">
                  CV / Resume{reqMark("cv", false)}
                </label>
                <div className="flex items-center gap-3 p-3 border border-border rounded-[10px] text-sm text-muted-foreground">
                  <Upload size={16} className="shrink-0" />
                  <span>Upload PDF or Word doc</span>
                </div>
              </div>
            )}

            <CustomQuestionsFields
              questions={visibleQuestions}
              answers={answers}
              onChange={setAnswers}
            />

            <Button type="button" className="w-full rounded-[10px] mt-1">
              Submit Application
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (role === "organization") {
    return (
      <div className="dark rounded-[10px] bg-[#08040f] text-white p-5 border border-[#653f84]/40">
        <div className="w-full max-w-lg mx-auto space-y-4 rounded-[10px] border border-[#653f84]/40 bg-[#12091e] p-6">
          <div className="space-y-2 text-center">
            <img src="/space-logo-white.png" alt="SpacePoint" className="mx-auto h-9 w-auto object-contain" />
            <h2 className="text-xl font-bold tracking-tight text-white">Partner Organization Sign Up</h2>
            <p className="text-xs text-white/60">
              Create an organization account to add and customize your events on SpacePoint
            </p>
          </div>

          <div className="space-y-3">
            <div className="space-y-1">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Organization Name *
              </label>
              <div className="relative">
                <Building2 className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                <input
                  readOnly
                  placeholder="Abu Dhabi University / Space Club"
                  className="w-full h-10 pl-10 pr-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                />
              </div>
            </div>

            {isFieldEnabled(fields, "org_name_arabic", true) && (
              <div className="space-y-1">
                <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                  Organization Name (Arabic){isFieldRequired(fields, "org_name_arabic", false) ? " *" : ""}
                </label>
                <input
                  readOnly
                  placeholder="اسم المؤسسة"
                  className="w-full h-10 px-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                />
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {isFieldEnabled(fields, "org_type", true) && (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                    Type{isFieldRequired(fields, "org_type", true) ? " *" : ""}
                  </label>
                  <select defaultValue="university" className="w-full h-10 px-2.5 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none">
                    <option value="university">University</option>
                    <option value="school">School</option>
                    <option value="company">Company</option>
                  </select>
                </div>
              )}
              {isFieldEnabled(fields, "country", true) && (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                    Country{isFieldRequired(fields, "country", true) ? " *" : ""}
                  </label>
                  <select defaultValue="AE" className="w-full h-10 px-2.5 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none">
                    <option value="AE">United Arab Emirates</option>
                  </select>
                </div>
              )}
              {isFieldEnabled(fields, "city", true) && (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                    City{isFieldRequired(fields, "city", false) ? " *" : ""}
                  </label>
                  <select defaultValue="" className="w-full h-10 px-2.5 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none">
                    <option value="">Select city...</option>
                  </select>
                </div>
              )}
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Representative Full Name *
              </label>
              <div className="relative">
                <UserIcon className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                <input
                  readOnly
                  placeholder="Your Full Name"
                  className="w-full h-10 pl-10 pr-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <div className="space-y-1">
                <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                  Work Email *
                </label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                  <input
                    readOnly
                    placeholder="name@organization.ae"
                    className="w-full h-10 pl-10 pr-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                  />
                </div>
              </div>
              {isFieldEnabled(fields, "phone", true) && (
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                    Phone{isFieldRequired(fields, "phone", true) ? " *" : ""}
                  </label>
                  <div className="relative">
                    <Phone className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                    <input
                      readOnly
                      placeholder="+971 50 123 4567"
                      className="w-full h-10 pl-10 pr-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-white/70 uppercase tracking-wider block">
                Password *
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 text-white/40 size-4" />
                <input
                  type="password"
                  readOnly
                  placeholder="Min. 6 characters"
                  className="w-full h-10 pl-10 pr-3 rounded-[10px] border border-[#653f84]/40 bg-[#0b0514] text-sm text-white outline-none"
                />
              </div>
            </div>

            <CustomQuestionsFields
              questions={visibleQuestions}
              answers={answers}
              onChange={setAnswers}
            />

            <Button type="button" className="w-full rounded-[10px] bg-[#653F84] hover:bg-[#53326e] text-white">
              Create Organization Account
            </Button>
          </div>
        </div>
      </div>
    )
  }

  if (role === "student") {
    const phoneEnabled = isFieldEnabled(fields, "phone", true)
    const phoneRequired = isFieldRequired(fields, "phone", true)
    const nationalityEnabled = isFieldEnabled(fields, "nationality", true)
    const nationalityRequired = isFieldRequired(fields, "nationality", true)
    const dobEnabled = isFieldEnabled(fields, "date_of_birth", true)
    const dobRequired = isFieldRequired(fields, "date_of_birth", false)
    const countryEnabled = isFieldEnabled(fields, "country", true)
    const countryRequired = isFieldRequired(fields, "country", false)
    const cityEnabled = isFieldEnabled(fields, "city", true)
    const cityRequired = isFieldRequired(fields, "city", false)
    const inviteEnabled = isFieldEnabled(fields, "invite_code", true)
    const inviteRequired = isFieldRequired(fields, "invite_code", false)
    const parentEnabled = isFieldEnabled(fields, "parent_info", true)
    const parentRequired = isFieldRequired(fields, "parent_info", false)

    return (
      <div className="dark rounded-[10px] bg-background border border-border p-5 flex items-center justify-center">
        <div className="w-full max-w-sm">
          <div className="flex justify-center mb-6">
            <img src="/space-logo-white.png" alt="SpacePoint" className="h-9 w-auto object-contain" />
          </div>
          <Card className="p-6 rounded-[10px]">
            <h2 className="text-center text-xl font-bold mb-5 text-foreground">Sign up</h2>
            <div className="flex flex-col gap-3">
              <input className="h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border" placeholder="Full name *" readOnly />
              <input className="h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border" placeholder="Email *" readOnly />
              {phoneEnabled && (
                <input
                  className="h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border"
                  placeholder={phoneRequired ? "Phone *" : "Phone (optional)"}
                  readOnly
                />
              )}
              {nationalityEnabled && (
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                    Nationality {nationalityRequired ? "*" : "(optional)"}
                  </label>
                  <select className="w-full h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border" defaultValue="">
                    <option value="">Select nationality...</option>
                  </select>
                </div>
              )}
              {dobEnabled && (
                <div>
                  <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                    Date of birth {dobRequired ? "*" : "(optional)"}
                  </label>
                  <input type="date" className="w-full h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border" readOnly />
                </div>
              )}
              {(countryEnabled || cityEnabled) && (
                <div className="grid grid-cols-2 gap-2">
                  {countryEnabled && (
                    <div>
                      <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                        Country {countryRequired ? "*" : "(optional)"}
                      </label>
                      <select className="w-full h-11 px-3 rounded-[10px] text-sm bg-background ring-1 ring-border" defaultValue="">
                        <option value="">Select...</option>
                      </select>
                    </div>
                  )}
                  {cityEnabled && (
                    <div>
                      <label className="block text-[11px] text-muted-foreground mb-1 pl-0.5">
                        City {cityRequired ? "*" : "(optional)"}
                      </label>
                      <select className="w-full h-11 px-3 rounded-[10px] text-sm bg-background ring-1 ring-border" defaultValue="">
                        <option value="">Select...</option>
                      </select>
                    </div>
                  )}
                </div>
              )}
              {inviteEnabled && (
                <input
                  className="h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border font-mono"
                  placeholder={inviteRequired ? "Invite code *" : "Invite code"}
                  readOnly
                />
              )}
              <input
                type="password"
                className="h-11 px-4 rounded-[10px] text-sm bg-background ring-1 ring-border"
                placeholder="Password *"
                readOnly
              />
              {parentEnabled && (
                <>
                  <button
                    type="button"
                    onClick={() => setParentOpen((v) => !v)}
                    className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground w-fit"
                  >
                    <span>Parent/guardian information {parentRequired ? "*" : "(optional)"}</span>
                  </button>
                  {(parentOpen || parentRequired) && (
                    <div className="flex flex-col gap-2 pl-3 border-l-2 border-border ml-1">
                      <input className="h-10 px-3.5 rounded-[10px] text-sm bg-background ring-1 ring-border" placeholder="Parent/guardian name" readOnly />
                      <input className="h-10 px-3.5 rounded-[10px] text-sm bg-background ring-1 ring-border" placeholder="Parent/guardian phone" readOnly />
                      <input className="h-10 px-3.5 rounded-[10px] text-sm bg-background ring-1 ring-border" placeholder="Parent/guardian email (optional)" readOnly />
                    </div>
                  )}
                </>
              )}
              {visibleQuestions.length > 0 && (
                <div className="pt-2 border-t border-border/60">
                  <CustomQuestionsFields
                    questions={visibleQuestions}
                    answers={answers}
                    onChange={setAnswers}
                  />
                </div>
              )}
              <Button type="button" className="w-full rounded-[10px] mt-1">Sign up</Button>
            </div>
          </Card>
        </div>
      </div>
    )
  }

  // ambassador / intern / teacher / facilitator — exact ApplyFlow.tsx layout
  const isIntern = role === "intern"
  const cvEnabled = isFieldEnabled(fields, "cv", true)
  const cvRequired = isFieldRequired(fields, "cv", true)
  const hasStep2 =
    cvEnabled ||
    visibleQuestions.length > 0 ||
    (isIntern &&
      [
        "university",
        "major",
        "university_id_number",
        "preferred_city_id",
        "requested_start_date",
        "requested_duration_weeks",
      ].some((k) => isFieldEnabled(fields, k, true)))

  return (
    <div className="dark rounded-[10px] bg-background border border-border p-5 flex flex-col items-center justify-center">
      {hasStep2 && (
        <div className="flex items-center gap-2 mb-3">
          <button
            type="button"
            onClick={() => setStep(1)}
            className={`px-3 py-1 text-xs font-medium rounded-[10px] transition-colors ${
              step === 1 ? "bg-[#653F84] text-white" : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            Step 1
          </button>
          <button
            type="button"
            onClick={() => setStep(2)}
            className={`px-3 py-1 text-xs font-medium rounded-[10px] transition-colors ${
              step === 2 ? "bg-[#653F84] text-white" : "bg-muted text-muted-foreground hover:text-foreground"
            }`}
          >
            Step 2
          </button>
        </div>
      )}

      <Card className="w-full max-w-lg rounded-[10px]">
        <CardContent className="p-6 flex flex-col gap-5">
          <div>
            <p className="text-xs text-muted-foreground uppercase tracking-wider font-semibold mb-0.5">
              Apply as
            </p>
            <h2 className="text-2xl font-bold text-foreground">{ROLE_LABEL[role] ?? role}</h2>
            {hasStep2 && (
              <div className="flex items-center gap-2 mt-2">
                {[1, 2].map((s) => (
                  <div
                    key={s}
                    className={`h-1.5 rounded-[10px] flex-1 transition-colors ${step >= s ? "bg-primary" : "bg-muted"}`}
                  />
                ))}
              </div>
            )}
          </div>

          {(!hasStep2 || step === 1) && (
            <div className="flex flex-col gap-3">
              {isFieldEnabled(fields, "invite_code", true) && (
                <PreviewField label="Invite code" required={isFieldRequired(fields, "invite_code", role === "teacher")}>
                  <input className="input" placeholder="e.g. AB12CD" readOnly />
                </PreviewField>
              )}
              <PreviewField label="Full name" required>
                <input className="input" placeholder="Your full name" readOnly />
              </PreviewField>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <PreviewField label="Email" required>
                  <input className="input" type="email" placeholder="you@email.com" readOnly />
                </PreviewField>
                {isFieldEnabled(fields, "birthdate", true) && (
                  <PreviewField label="Date of birth" required={isFieldRequired(fields, "birthdate", false)}>
                    <input className="input" type="date" readOnly />
                  </PreviewField>
                )}
              </div>
              {(isFieldEnabled(fields, "phone", true) || isFieldEnabled(fields, "country", true)) && (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {isFieldEnabled(fields, "phone", true) && (
                    <PreviewField label="Phone / WhatsApp" required={isFieldRequired(fields, "phone", false)}>
                      <input className="input" placeholder="+971 50 000 0000" readOnly />
                    </PreviewField>
                  )}
                  {isFieldEnabled(fields, "country", true) && (
                    <PreviewField label="Country" required={isFieldRequired(fields, "country", true)}>
                      <select className="input" defaultValue="">
                        <option value="">Select country...</option>
                      </select>
                    </PreviewField>
                  )}
                </div>
              )}
              {isIntern && isFieldEnabled(fields, "nationality", true) && (
                <PreviewField label="Nationality" required={isFieldRequired(fields, "nationality", true)}>
                  <select className="input" defaultValue="">
                    <option value="">Select nationality...</option>
                  </select>
                </PreviewField>
              )}
              {isFieldEnabled(fields, "city", true) && (
                <PreviewField label="City" required={isFieldRequired(fields, "city", true)}>
                  <select className="input" defaultValue="">
                    <option value="">Select city...</option>
                  </select>
                </PreviewField>
              )}
              <PreviewField label="Password" required>
                <input className="input" type="password" placeholder="Min. 6 characters" readOnly />
              </PreviewField>

              <Button type="button" className="mt-1 w-full rounded-[10px]" onClick={() => { if (hasStep2) setStep(2) }}>
                {hasStep2 ? (
                  <span className="flex items-center gap-1.5">Next <ChevronRight size={16} /></span>
                ) : "Submit application"}
              </Button>
            </div>
          )}

          {hasStep2 && step === 2 && (
            <div className="flex flex-col gap-4">
              {cvEnabled && (
                <PreviewField label="CV / Resume" required={cvRequired}>
                  <div className="flex items-center gap-3 p-3 border border-border rounded-[10px] text-sm text-muted-foreground">
                    <Upload size={16} className="shrink-0" />
                    <span>Upload PDF or Word doc</span>
                  </div>
                </PreviewField>
              )}

              {isIntern && (
                <>
                  {(isFieldEnabled(fields, "university", true) || isFieldEnabled(fields, "major", true)) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {isFieldEnabled(fields, "university", true) && (
                        <PreviewField label="University / Institution" required={isFieldRequired(fields, "university", false)}>
                          <input className="input" placeholder="e.g. UAE University" readOnly />
                        </PreviewField>
                      )}
                      {isFieldEnabled(fields, "major", true) && (
                        <PreviewField label="Major / Field of study" required={isFieldRequired(fields, "major", false)}>
                          <input className="input" placeholder="e.g. Computer Engineering" readOnly />
                        </PreviewField>
                      )}
                    </div>
                  )}
                  {isFieldEnabled(fields, "university_id_number", true) && (
                    <PreviewField label="University ID number" required={isFieldRequired(fields, "university_id_number", false)}>
                      <input className="input" readOnly />
                    </PreviewField>
                  )}
                  {isFieldEnabled(fields, "preferred_city_id", true) && (
                    <PreviewField label="Which city do you want to work at?" required={isFieldRequired(fields, "preferred_city_id", false)}>
                      <select className="input" defaultValue="">
                        <option value="">Select a city...</option>
                      </select>
                    </PreviewField>
                  )}
                  {(isFieldEnabled(fields, "requested_start_date", true) || isFieldEnabled(fields, "requested_duration_weeks", true)) && (
                    <div className="grid grid-cols-2 gap-3">
                      {isFieldEnabled(fields, "requested_start_date", true) && (
                        <PreviewField label="Preferred start date" required={isFieldRequired(fields, "requested_start_date", false)}>
                          <input className="input" type="date" readOnly />
                        </PreviewField>
                      )}
                      {isFieldEnabled(fields, "requested_duration_weeks", true) && (
                        <PreviewField label="Duration (weeks)" required={isFieldRequired(fields, "requested_duration_weeks", false)}>
                          <input className="input" type="number" readOnly />
                        </PreviewField>
                      )}
                    </div>
                  )}
                </>
              )}

              <CustomQuestionsFields
                questions={visibleQuestions}
                answers={answers}
                onChange={setAnswers}
              />

              <div className="flex gap-2 mt-1">
                <Button type="button" variant="outline" className="flex-1 rounded-[10px]" onClick={() => setStep(1)}>Back</Button>
                <Button type="button" className="flex-1 rounded-[10px]">Submit application</Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
