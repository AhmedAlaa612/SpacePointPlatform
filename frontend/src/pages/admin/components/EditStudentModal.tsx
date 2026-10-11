import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Modal, Field } from "@/pages/admin/components/common"
import { useToast } from "@/components/ui/toast"
import { getErrorMessage } from "@/lib/utils"
import { updateContactApi } from "@/api/spine/contacts"
import type { Registration } from "@/types/sessions"

export function EditStudentModal({
  registration,
  onClose,
  onSuccess,
}: {
  registration: Registration
  onClose: () => void
  onSuccess: () => void
}) {
  const toast = useToast()
  const [studentName, setStudentName] = useState(registration.student_name || "")
  const [email, setEmail] = useState(registration.student_email || "")
  const [phone, setPhone] = useState(registration.student_phone || "")
  const [gender, setGender] = useState(registration.student_gender || "")
  const [error, setError] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      updateContactApi(registration.contact_id, {
        full_name: studentName.trim(),
        email: email.trim() || null,
        primary_phone_e164: phone.trim() || null,
        gender: gender.trim() || null,
      }),
    onSuccess: () => {
      toast.success("Student details updated")
      onSuccess()
    },
    onError: (e: any) => setError(getErrorMessage(e, "Failed to update student details")),
  })

  const canSubmit = !!studentName.trim()

  return (
    <Modal title={`Edit student — ${registration.student_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        {error && <p className="text-xs text-destructive m-0">{error}</p>}
        <Field label="Student full name">
          <input
            value={studentName}
            onChange={(e) => setStudentName(e.target.value)}
            placeholder="Jane Smith"
            autoFocus
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Email address">
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              type="email"
              placeholder="jane@example.com"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
          <Field label="Phone number">
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+971 50 123 4567 or +20 10 1234 5678"
              className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </Field>
        </div>
        <Field label="Gender (optional)">
          <input
            value={gender}
            onChange={(e) => setGender(e.target.value)}
            placeholder="Male / Female"
            list="student-gender-options"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
          <datalist id="student-gender-options">
            <option value="Male" />
            <option value="Female" />
          </datalist>
        </Field>

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border/50">
          <button
            type="button"
            onClick={onClose}
            className="px-4 h-9 rounded-lg border border-border text-xs font-medium text-foreground hover:bg-muted transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSubmit || mutation.isPending}
            onClick={() => mutation.mutate()}
            className="px-4 h-9 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save changes"}
          </button>
        </div>
      </div>
    </Modal>
  )
}
