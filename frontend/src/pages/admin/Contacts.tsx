import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Search, Pencil, Link2, X, History } from "lucide-react"
import { Modal, Field, ModalActions, Spinner } from "@/pages/admin/components/common"
import { cn, formatDate } from "@/lib/utils"
import {
  searchContactsApi,
  getContactApi,
  updateContactApi,
  createContactRelationshipApi,
  getContactRoleHistoryApi,
  listOrganizationsApi,
} from "@/api/spine/contacts"
import {
  CONTACT_ROLE_LABEL,
  LIFECYCLE_STAGE_LABEL,
  RELATION_LABEL,
  ROLE_EVENT_SOURCE_LABEL,
  type ContactRole,
  type LifecycleStage,
  type ContactRelationType,
  type ContactDetail,
  type ContactListItem,
} from "@/types/spine"
import { ROLE_LABEL } from "@/types/shared"

const ALL_CONTACT_ROLES: ContactRole[] = [
  "student", "parent_guardian", "teacher", "school_admin", "sponsor_rep",
  "gov_official", "alumnus", "instructor", "ambassador", "intern", "other",
]
const ALL_LIFECYCLE_STAGES: LifecycleStage[] = ["subscriber", "lead", "mql", "sql", "customer", "alumni"]
const ALL_RELATIONS: ContactRelationType[] = ["guardian_of", "child_of", "sibling_of", "spouse_of", "other"]

const LIFECYCLE_BADGE_COLOR: Record<string, string> = {
  subscriber: "bg-slate-100 text-slate-700 dark:bg-slate-500/15 dark:text-slate-300",
  lead: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400",
  mql: "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-400",
  sql: "bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-400",
  customer: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-400",
  alumni: "bg-purple-100 text-purple-700 dark:bg-purple-500/15 dark:text-purple-400",
}

const LIMIT = 20

/* ================================================================== */
/* Contacts page                                                      */
/* ================================================================== */
export default function Contacts() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [roleFilter, setRoleFilter] = useState<ContactRole | "all">("all")
  const [offset, setOffset] = useState(0)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["spine-contacts", search, roleFilter, offset],
    queryFn: () =>
      searchContactsApi({
        q: search.trim() || undefined,
        role: roleFilter === "all" ? undefined : roleFilter,
        limit: LIMIT,
        offset,
      }),
    placeholderData: (prev) => prev,
  })

  const contacts = data?.items ?? []
  const total = data?.total ?? 0

  const resetPaging = () => setOffset(0)

  if (isLoading && !data) return <Spinner />

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold text-foreground tracking-tight">Contacts</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Search and manage every contact across the platform</p>
      </div>

      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          {total} contact{total !== 1 ? "s" : ""}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative w-full sm:w-72">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={search}
              onChange={(e) => { setSearch(e.target.value); resetPaging() }}
              placeholder="Search by name, phone, or email…"
              className="h-9 pl-8 pr-3 w-full border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
            />
          </div>
          <select
            value={roleFilter}
            onChange={(e) => { setRoleFilter(e.target.value as ContactRole | "all"); resetPaging() }}
            className="h-9 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            <option value="all">All roles</option>
            {ALL_CONTACT_ROLES.map((r) => (
              <option key={r} value={r}>{CONTACT_ROLE_LABEL[r]}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2">
          {contacts.map((c) => (
            <button
              key={c.id}
              onClick={() => setSelectedId(c.id)}
              className="flex items-center justify-between gap-3 p-4 bg-card border border-border rounded-2xl hover:border-muted-foreground/30 transition-colors text-left"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground truncate">{c.full_name}</p>
              </div>
              <div className="hidden md:flex flex-wrap gap-1 max-w-[220px] justify-end">
                {c.contact_roles.map((r) => (
                  <span key={r} className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                    {CONTACT_ROLE_LABEL[r as ContactRole] ?? r}
                  </span>
                ))}
              </div>
              <p className="hidden sm:block text-xs text-muted-foreground w-32 truncate flex-shrink-0">
                {c.primary_phone_e164 || "—"}
              </p>
              <p className="hidden lg:block text-xs text-muted-foreground w-24 truncate flex-shrink-0">
                {c.city || "—"}
              </p>
              <span className={cn(
                "text-xs font-semibold px-2 py-0.5 rounded-full flex-shrink-0",
                LIFECYCLE_BADGE_COLOR[c.lifecycle_stage] ?? "bg-muted text-muted-foreground",
              )}>
                {LIFECYCLE_STAGE_LABEL[c.lifecycle_stage as LifecycleStage] ?? c.lifecycle_stage}
              </span>
            </button>
          ))}
          {contacts.length === 0 && (
            <div className="flex items-center justify-center h-32 border border-dashed border-border rounded-2xl">
              <p className="text-sm text-muted-foreground">
                {total === 0 && !search && roleFilter === "all" ? "No contacts yet" : "No contacts match your search/filter"}
              </p>
            </div>
          )}
        </div>

        {total > LIMIT && (
          <div className="flex items-center justify-between">
            <button
              onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}
              disabled={offset === 0}
              className="h-9 px-4 border border-border rounded-xl text-sm text-muted-foreground hover:bg-muted transition-colors disabled:opacity-40"
            >
              Previous
            </button>
            <p className="text-xs text-muted-foreground">
              {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
            </p>
            <button
              onClick={() => setOffset((o) => o + LIMIT)}
              disabled={offset + LIMIT >= total}
              className="h-9 px-4 border border-border rounded-xl text-sm text-muted-foreground hover:bg-muted transition-colors disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>

      {selectedId && (
        <ContactDetailModal
          contactId={selectedId}
          onClose={() => setSelectedId(null)}
          onChanged={() => queryClient.invalidateQueries({ queryKey: ["spine-contacts"] })}
        />
      )}
    </div>
  )
}

/* ================================================================== */
/* Contact detail modal — bigger than the shared `Modal` primitive, so it's a
   custom panel (same visual language, matching the existing
   UserProfileModal pattern for wide detail views elsewhere in admin/).      */
/* ================================================================== */
function ContactDetailModal({
  contactId, onClose, onChanged,
}: { contactId: string; onClose: () => void; onChanged: () => void }) {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [addRelationOpen, setAddRelationOpen] = useState(false)

  const { data: contact, isLoading } = useQuery({
    queryKey: ["spine-contact", contactId],
    queryFn: () => getContactApi(contactId),
  })

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["spine-contact", contactId] })
    onChanged()
  }

  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-end sm:items-center justify-center p-4" onClick={onClose}>
      <div
        className="w-full max-w-2xl bg-card border border-border rounded-2xl p-6 flex flex-col gap-4 shadow-2xl max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-base font-semibold text-foreground truncate">{contact?.full_name ?? "Contact"}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded-lg text-muted-foreground hover:text-foreground transition-colors flex-shrink-0">
            <X size={16} />
          </button>
        </div>

        {isLoading || !contact ? (
          <Spinner />
        ) : editing ? (
          <ContactEditForm
            contact={contact}
            onCancel={() => setEditing(false)}
            onSuccess={() => { setEditing(false); refresh() }}
          />
        ) : (
          <>
            <div className="flex flex-wrap gap-1.5">
              {contact.contact_roles.map((r) => (
                <span key={r} className="text-xs font-semibold px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                  {CONTACT_ROLE_LABEL[r as ContactRole] ?? r}
                </span>
              ))}
              <span className={cn(
                "text-xs font-semibold px-2 py-0.5 rounded-full",
                LIFECYCLE_BADGE_COLOR[contact.lifecycle_stage] ?? "bg-muted text-muted-foreground",
              )}>
                {LIFECYCLE_STAGE_LABEL[contact.lifecycle_stage as LifecycleStage] ?? contact.lifecycle_stage}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <InfoField label="Phone" value={contact.primary_phone_e164} />
              <InfoField label="WhatsApp" value={contact.whatsapp_e164} />
              <InfoField label="Email" value={contact.email} />
              <InfoField label="City" value={contact.city} />
              <InfoField label="Country" value={contact.country} />
              <InfoField label="Date of birth" value={contact.date_of_birth} />
              <InfoField label="Grade" value={contact.grade} />
              <InfoField label="Organization" value={contact.organization_name} />
            </div>

            {contact.notes && (
              <div>
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-1">Notes</p>
                <p className="text-sm text-foreground whitespace-pre-wrap">{contact.notes}</p>
              </div>
            )}

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Relationships</p>
                <button
                  onClick={() => setAddRelationOpen(true)}
                  className="text-xs font-medium text-primary hover:opacity-80 transition-opacity flex items-center gap-1"
                >
                  <Link2 size={12} /> Add
                </button>
              </div>
              {contact.relationships.length === 0 ? (
                <p className="text-xs text-muted-foreground">No relationships recorded</p>
              ) : (
                <div className="flex flex-col gap-1.5">
                  {contact.relationships.map((rel) => (
                    <div key={rel.id} className="flex items-center justify-between p-2.5 border border-border rounded-xl text-sm">
                      <span className="text-foreground">
                        <span className="font-medium">{rel.other_contact?.full_name ?? "Unknown contact"}</span>
                        <span className="text-muted-foreground">
                          {" — "}
                          {rel.direction === "outgoing"
                            ? (RELATION_LABEL[rel.relation as ContactRelationType] ?? rel.relation)
                            : `related as ${(RELATION_LABEL[rel.relation as ContactRelationType] ?? rel.relation).toLowerCase()}`}
                        </span>
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <RoleHistorySection contactId={contact.id} />

            <button
              onClick={() => setEditing(true)}
              className="flex items-center justify-center gap-1.5 h-10 border border-border rounded-xl text-sm font-medium text-foreground hover:bg-muted transition-colors"
            >
              <Pencil size={14} /> Edit contact
            </button>
          </>
        )}
      </div>

      {addRelationOpen && contact && (
        <AddRelationshipModal
          contact={contact}
          onClose={() => setAddRelationOpen(false)}
          onSuccess={() => { setAddRelationOpen(false); refresh() }}
        />
      )}
    </div>
  )
}

function InfoField({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-0.5">{label}</p>
      <p className="text-sm text-foreground truncate">{value || "—"}</p>
    </div>
  )
}

/* ================================================================== */
/* Role history — "in this date they were lead, in that date they     */
/* became student, then intern, then instructor" (2026-07-24)          */
/* ================================================================== */
function RoleHistorySection({ contactId }: { contactId: string }) {
  const { data: events, isLoading } = useQuery({
    queryKey: ["spine-contact-role-history", contactId],
    queryFn: () => getContactRoleHistoryApi(contactId),
  })

  const roleLabel = (role: string) => ROLE_LABEL[role as keyof typeof ROLE_LABEL] ?? CONTACT_ROLE_LABEL[role as ContactRole] ?? role

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground font-medium uppercase tracking-wider flex items-center gap-1.5">
        <History size={12} /> Role history
      </p>
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : !events || events.length === 0 ? (
        <p className="text-xs text-muted-foreground">No role changes recorded yet</p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {[...events].reverse().map((e) => (
            <div key={e.id} className="flex items-start justify-between gap-2 p-2.5 border border-border rounded-xl text-sm">
              <div className="min-w-0">
                <span className="text-foreground">
                  <span className={cn("font-medium", e.action === "added" ? "text-emerald-600 dark:text-emerald-400" : "text-red-500")}>
                    {e.action === "added" ? "Became" : "No longer"}
                  </span>{" "}
                  <span className="font-medium">{roleLabel(e.role)}</span>
                </span>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {ROLE_EVENT_SOURCE_LABEL[e.source] ?? e.source}
                  {e.changed_by_name ? ` — by ${e.changed_by_name}` : ""}
                </p>
              </div>
              <span className="text-xs text-muted-foreground flex-shrink-0 whitespace-nowrap">
                {formatDate(e.occurred_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ================================================================== */
/* Edit contact form                                                   */
/* ================================================================== */
function ContactEditForm({
  contact, onCancel, onSuccess,
}: { contact: ContactDetail; onCancel: () => void; onSuccess: () => void }) {
  const [fullName, setFullName] = useState(contact.full_name)
  const [phone, setPhone] = useState(contact.primary_phone_e164 || "")
  const [whatsapp, setWhatsapp] = useState(contact.whatsapp_e164 || "")
  const [email, setEmail] = useState(contact.email || "")
  const [city, setCity] = useState(contact.city || "")
  const [country, setCountry] = useState(contact.country || "")
  const [dateOfBirth, setDateOfBirth] = useState(contact.date_of_birth || "")
  const [grade, setGrade] = useState(contact.grade || "")
  const [organizationId, setOrganizationId] = useState(contact.organization_id || "")
  const [lifecycleStage, setLifecycleStage] = useState(contact.lifecycle_stage)
  const [notes, setNotes] = useState(contact.notes || "")
  const [error, setError] = useState("")

  const { data: organizations = [] } = useQuery({
    queryKey: ["spine-organizations", "picker"],
    queryFn: () => listOrganizationsApi(),
  })

  const mutation = useMutation({
    mutationFn: () => updateContactApi(contact.id, {
      full_name: fullName,
      primary_phone_e164: phone || null,
      whatsapp_e164: whatsapp || null,
      email: email || null,
      city: city || null,
      country: country || null,
      date_of_birth: dateOfBirth || null,
      grade: grade || null,
      organization_id: organizationId || null,
      lifecycle_stage: lifecycleStage,
      notes: notes || null,
    }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to update contact"),
  })

  return (
    <div className="flex flex-col gap-3">
      <Field label="Full name">
        <input
          value={fullName} onChange={(e) => setFullName(e.target.value)} autoFocus
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Phone">
          <input
            value={phone} onChange={(e) => setPhone(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="WhatsApp">
          <input
            value={whatsapp} onChange={(e) => setWhatsapp(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
      </div>
      <Field label="Email">
        <input
          value={email} onChange={(e) => setEmail(e.target.value)} type="email"
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="City">
          <input
            value={city} onChange={(e) => setCity(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Country">
          <input
            value={country} onChange={(e) => setCountry(e.target.value)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Date of birth">
          <input
            value={dateOfBirth} onChange={(e) => setDateOfBirth(e.target.value)} type="date"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
        <Field label="Grade">
          <input
            value={grade} onChange={(e) => setGrade(e.target.value)} placeholder="Grade 8"
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
          />
        </Field>
      </div>
      <Field label="School / organization">
        <select
          value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          <option value="">— None —</option>
          {organizations.map((o) => <option key={o.id} value={o.id}>{o.name_latin}</option>)}
        </select>
      </Field>
      <Field label="Lifecycle stage">
        <select
          value={lifecycleStage} onChange={(e) => setLifecycleStage(e.target.value)}
          className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
        >
          {ALL_LIFECYCLE_STAGES.map((s) => (
            <option key={s} value={s}>{LIFECYCLE_STAGE_LABEL[s]}</option>
          ))}
        </select>
      </Field>
      <Field label="Notes">
        <textarea
          value={notes} onChange={(e) => setNotes(e.target.value)} rows={3}
          className="w-full px-3 py-2 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors resize-none"
        />
      </Field>
      {error && <p className="text-xs text-red-500">{error}</p>}
      <ModalActions
        onCancel={onCancel} onConfirm={() => mutation.mutate()}
        loading={mutation.isPending} disabled={!fullName.trim()}
        label="Save changes"
      />
    </div>
  )
}

/* ================================================================== */
/* Add relationship modal — contact-picker reuses the search endpoint  */
/* ================================================================== */
function AddRelationshipModal({
  contact, onClose, onSuccess,
}: { contact: ContactDetail; onClose: () => void; onSuccess: () => void }) {
  const [query, setQuery] = useState("")
  const [relation, setRelation] = useState<ContactRelationType>("guardian_of")
  const [selected, setSelected] = useState<ContactListItem | null>(null)
  const [error, setError] = useState("")

  const { data, isFetching } = useQuery({
    queryKey: ["spine-contact-picker", query],
    queryFn: () => searchContactsApi({ q: query.trim(), limit: 8 }),
    enabled: query.trim().length >= 2,
  })

  const options = (data?.items ?? []).filter((c) => c.id !== contact.id)

  const mutation = useMutation({
    mutationFn: () => createContactRelationshipApi(contact.id, { related_contact_id: selected!.id, relation }),
    onSuccess,
    onError: (e: any) => setError(e?.response?.data?.detail ?? "Failed to create relationship"),
  })

  return (
    <Modal title={`Add relationship — ${contact.full_name}`} onClose={onClose}>
      <div className="flex flex-col gap-3">
        <Field label="Relation type">
          <select
            value={relation} onChange={(e) => setRelation(e.target.value as ContactRelationType)}
            className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors cursor-pointer"
          >
            {ALL_RELATIONS.map((r) => (
              <option key={r} value={r}>{RELATION_LABEL[r]}</option>
            ))}
          </select>
        </Field>
        <Field label="Related contact">
          {selected ? (
            <div className="flex items-center justify-between p-2.5 border border-primary/40 bg-primary/5 rounded-xl text-sm">
              <span className="text-foreground font-medium truncate">{selected.full_name}</span>
              <button onClick={() => setSelected(null)} className="text-xs text-muted-foreground hover:text-foreground flex-shrink-0 ml-2">
                Change
              </button>
            </div>
          ) : (
            <>
              <input
                value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
                placeholder="Search by name, phone, or email…"
                className="w-full h-10 px-3 border border-border bg-card text-foreground rounded-xl text-sm focus:outline-none focus:border-primary transition-colors"
              />
              {query.trim().length >= 2 && (
                <div className="mt-1.5 border border-border rounded-xl max-h-40 overflow-y-auto divide-y divide-border">
                  {isFetching ? (
                    <p className="text-xs text-muted-foreground p-2.5">Searching…</p>
                  ) : options.length === 0 ? (
                    <p className="text-xs text-muted-foreground p-2.5">No contacts found</p>
                  ) : (
                    options.map((c) => (
                      <button
                        key={c.id} onClick={() => setSelected(c)}
                        className="w-full text-left p-2.5 text-sm hover:bg-muted transition-colors"
                      >
                        <p className="font-medium text-foreground">{c.full_name}</p>
                        <p className="text-xs text-muted-foreground">{c.primary_phone_e164 || c.email || "—"}</p>
                      </button>
                    ))
                  )}
                </div>
              )}
            </>
          )}
        </Field>
        {error && <p className="text-xs text-red-500">{error}</p>}
        <ModalActions
          onCancel={onClose} onConfirm={() => mutation.mutate()}
          loading={mutation.isPending} disabled={!selected}
          label="Add relationship"
        />
      </div>
    </Modal>
  )
}
