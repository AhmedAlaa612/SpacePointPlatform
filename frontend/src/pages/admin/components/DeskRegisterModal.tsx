import { useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { Modal, Field, ModalActions } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { listOrganizationsApi } from "@/api/spine/contacts"
import { deskRegisterApi } from "@/api/sessions/cohorts"
import type { Cohort, Session } from "@/types/sessions"

export function DeskRegisterModal({ cohort, sessions, onClose, onSuccess }: {
  cohort: Cohort; sessions: Session[]; onClose: () => void; onSuccess: () => void
}) {
  const toast = useToast()
  const [studentName, setStudentName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")
  const [city, setCity] = useState("")
  const [dateOfBirth, setDateOfBirth] = useState("")
  const [grade, setGrade] = useState("")
  const [gender, setGender] = useState("")
  const [organizationName, setOrganizationName] = useState("")
  const [parentName, setParentName] = useState("")
  const [parentPhone, setParentPhone] = useState("")
  const [parentEmail, setParentEmail] = useState("")
  const [sendTicketEmail, setSendTicketEmail] = useState(true)
  const [sendWelcomeEmail, setSendWelcomeEmail] = useState(true)
  const [selectedSessionIds, setSelectedSessionIds] = useState<string[]>([])
  const [error, setError] = useState("")

  const toggleSession = (id: string) =>
    setSelectedSessionIds((prev) => prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id])

  const { data: organizations = [] } = useQuery({
    queryKey: ["spine-organizations", "picker"],
    queryFn: () => listOrganizationsApi(),
  })

  const mutation = useMutation({
    mutationFn: () => deskRegisterApi(cohort.id, {
      student_name: studentName.trim(),
      email: email.trim(),
      phone: phone.trim(),
      city: city.trim() || undefined,
      date_of_birth: dateOfBirth || undefined,
      grade: grade.trim() || undefined,
      gender: gender.trim() || undefined,
      organization_name: organizationName.trim() || undefined,
      parent_name: parentName.trim() || undefined,
      parent_phone: parentPhone.trim() || undefined,
      parent_email: parentEmail.trim() || undefined,
      session_ids: selectedSessionIds.length > 0 ? selectedSessionIds : undefined,
      send_ticket_email: sendTicketEmail,
      send_welcome_email: sendWelcomeEmail,
    }),
    onSuccess: () => { toast.success("Student registered"); onSuccess() },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to register student")),
  })

  const canSubmit = !!(studentName.trim() && email.trim() && phone.trim())

  return (
    <Modal title={`Register student — ${cohort.name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Student name">
          <input
            value={studentName} onChange={(e) => setStudentName(e.target.value)} placeholder="Jane Smith" autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Email">
            <input
              value={email} onChange={(e) => setEmail(e.target.value)} type="email" placeholder="jane@example.com"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Phone">
            <input
              value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+971 50 123 4567 or +20 10 1234 5678"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="City (optional)">
            <input
              value={city} onChange={(e) => setCity(e.target.value)} placeholder="Dubai"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Gender (optional)">
            <input
              value={gender} onChange={(e) => setGender(e.target.value)} placeholder="Male / Female" list="desk-gender-list"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
            <datalist id="desk-gender-list">
              <option value="Male" />
              <option value="Female" />
            </datalist>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date of birth (optional)">
            <input
              value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} type="date"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Grade (optional)">
            <input
              value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="Grade 8"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="School / organization (optional)">
          <input
            value={organizationName} onChange={(e) => setOrganizationName(e.target.value)}
            placeholder="Type to match or create" list="org-picker-list"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <datalist id="org-picker-list">
            {organizations.map((o) => <option key={o.id} value={o.name_latin} />)}
          </datalist>
        </Field>

        {sessions.length > 1 && (
          <Field label="Which sessions? (optional — leave blank for all)">
            <div className="flex flex-wrap gap-1.5">
              {sessions.map((s) => (
                <button
                  key={s.id} type="button" onClick={() => toggleSession(s.id)}
                  className={`h-9 px-3 rounded-xl text-xs font-medium border transition-colors ${
                    selectedSessionIds.includes(s.id)
                      ? "bg-primary text-primary-foreground border-primary"
                      : "border-border text-foreground hover:bg-muted"
                  }`}
                >
                  {s.meeting_date}{s.title ? ` · ${s.title}` : ""}
                </button>
              ))}
            </div>
          </Field>
        )}

        <p className="text-xs text-muted-foreground -mb-1">Parent/guardian details (optional)</p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Parent/guardian name">
            <input
              value={parentName} onChange={(e) => setParentName(e.target.value)}
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Parent/guardian phone">
            <input
              value={parentPhone} onChange={(e) => setParentPhone(e.target.value)} placeholder="+971 50 123 4567"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="Parent/guardian email (optional)">
          <input
            value={parentEmail} onChange={(e) => setParentEmail(e.target.value)} type="email"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>

        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={sendWelcomeEmail} onChange={(e) => setSendWelcomeEmail(e.target.checked)} />
          Send LMS onboarding mail
        </label>
        <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer select-none">
          <input type="checkbox" checked={sendTicketEmail} onChange={(e) => setSendTicketEmail(e.target.checked)} />
          Send Ticket
        </label>

        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!canSubmit}
          label="Register"
        />
      </div>
    </Modal>
  )
}
