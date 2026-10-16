import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  Mail,
  UserPlus,
  Trash2,
  KeyRound,
  ExternalLink,
  Shield,
  Search,
  Check,
  AlertTriangle,
  RefreshCw,
  Edit,
  UserCheck,
  FileText,
} from "lucide-react";
import { Spinner, EmptyState } from "@/components/ui/primitives";
import { Modal, Field } from "@/pages/admin/components/common";
import {
  getTestUsersApi,
  getTestApplicationsApi,
  createTestUserApi,
  updateTestUserApi,
  getTestUserResetLinkApi,
  cascadeDeleteTestUserApi,
  cascadeDeleteTestEmailApi,
  type CreateTestUserPayload,
  type UpdateTestUserPayload,
} from "@/api/operations/testAccounts";
import type { Role, User } from "@/types/shared";

const TEST_DOMAIN = "spacepoint.local";

const AVAILABLE_ROLES: { role: Role; label: string; desc: string }[] = [
  { role: "student", label: "Student", desc: "Access to LMS (/learn/*), courses, quizzes" },
  { role: "instructor", label: "Instructor", desc: "Teaching cohorts, grading submissions" },
  { role: "facilitator", label: "Facilitator", desc: "Ground station, session operations" },
  { role: "intern", label: "Intern", desc: "Internship kanban, teams, proposals" },
  { role: "leader", label: "Team Leader", desc: "Intern team leadership and approvals" },
  { role: "applicant", label: "Applicant", desc: "Pending instructor/intern pipeline" },
  { role: "ambassador", label: "Ambassador", desc: "Ambassador portal and community tasks" },
  { role: "teacher", label: "Teacher", desc: "School coordinator view" },
  { role: "judge", label: "Judge", desc: "Competition judging surface (/judge/*)" },
  { role: "lms_author", label: "LMS Author", desc: "Course and learning path authoring" },
  { role: "observer", label: "Observer", desc: "Read-only inspection of learner views" },
  { role: "organization", label: "Organization", desc: "B2B client & school portal" },
  { role: "storekeeper", label: "Storekeeper", desc: "Inventory warehouse management" },
  { role: "coo", label: "COO", desc: "Operations & inventory executive" },
  { role: "operations", label: "Operations", desc: "Full operations platform access" },
];

function errorDetail(err: unknown, fallback: string): string {
  if (isAxiosError(err) && typeof err.response?.data?.detail === "string") {
    return err.response.data.detail;
  }
  return fallback;
}

export default function TestAccounts() {
  const queryClient = useQueryClient();

  const [activeTab, setActiveTab] = useState<"users" | "applications">("users");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<string>("all");

  // Modals state
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<User | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id?: string; email: string; name?: string } | null>(null);
  const [purgeEmailOpen, setPurgeEmailOpen] = useState(false);
  const [copiedResetUrl, setCopiedResetUrl] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [actionSuccess, setActionSuccess] = useState("");

  // Create form state
  const [newName, setNewName] = useState("");
  const [newEmailPrefix, setNewEmailPrefix] = useState("");
  const [newPassword, setNewPassword] = useState("SpacePoint123!");
  const [newPhone, setNewPhone] = useState("+971501234567");
  const [newRoles, setNewRoles] = useState<Role[]>(["student"]);

  // Edit form state
  const [editName, setEditName] = useState("");
  const [editRoles, setEditRoles] = useState<Role[]>([]);
  const [editStatus, setEditStatus] = useState<string>("active");
  const [editPassword, setEditPassword] = useState("");

  // Purge by email state
  const [purgeEmailInput, setPurgeEmailInput] = useState("");

  // Queries
  const {
    data: users = [],
    isLoading: usersLoading,
    refetch: refetchUsers,
  } = useQuery({
    queryKey: ["operations-test-users"],
    queryFn: getTestUsersApi,
  });

  const {
    data: applications = [],
    isLoading: appsLoading,
    refetch: refetchApps,
  } = useQuery({
    queryKey: ["operations-test-applications"],
    queryFn: getTestApplicationsApi,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: (payload: CreateTestUserPayload) => createTestUserApi(payload),
    onSuccess: (created) => {
      setCreateOpen(false);
      resetCreateForm();
      setActionError("");
      setActionSuccess(`Created test account: ${created.email}`);
      void queryClient.invalidateQueries({ queryKey: ["operations-test-users"] });
      setTimeout(() => setActionSuccess(""), 5000);
    },
    onError: (e) => setActionError(errorDetail(e, "Could not create test user")),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateTestUserPayload }) =>
      updateTestUserApi(id, payload),
    onSuccess: (updated) => {
      setEditTarget(null);
      setActionError("");
      setActionSuccess(`Updated test account: ${updated.email}`);
      void queryClient.invalidateQueries({ queryKey: ["operations-test-users"] });
      setTimeout(() => setActionSuccess(""), 5000);
    },
    onError: (e) => setActionError(errorDetail(e, "Could not update test user")),
  });

  const deleteUserMutation = useMutation({
    mutationFn: (id: string) => cascadeDeleteTestUserApi(id),
    onSuccess: () => {
      setDeleteTarget(null);
      setActionError("");
      setActionSuccess("Account and all dependent rows/files cascade-deleted successfully.");
      void queryClient.invalidateQueries({ queryKey: ["operations-test-users"] });
      void queryClient.invalidateQueries({ queryKey: ["operations-test-applications"] });
      setTimeout(() => setActionSuccess(""), 5000);
    },
    onError: (e) => setActionError(errorDetail(e, "Cascade delete failed")),
  });

  const deleteEmailMutation = useMutation({
    mutationFn: (email: string) => cascadeDeleteTestEmailApi(email),
    onSuccess: () => {
      setDeleteTarget(null);
      setPurgeEmailOpen(false);
      setPurgeEmailInput("");
      setActionError("");
      setActionSuccess("Target email and all linked dependencies cascade-deleted successfully.");
      void queryClient.invalidateQueries({ queryKey: ["operations-test-users"] });
      void queryClient.invalidateQueries({ queryKey: ["operations-test-applications"] });
      setTimeout(() => setActionSuccess(""), 5000);
    },
    onError: (e) => setActionError(errorDetail(e, "Purge by email failed")),
  });

  const resetLinkMutation = useMutation({
    mutationFn: (id: string) => getTestUserResetLinkApi(id),
    onSuccess: (data) => {
      void navigator.clipboard.writeText(data.reset_url);
      setCopiedResetUrl(data.user_id);
      setActionSuccess(`Copied 72h password set link for ${data.email} to clipboard!`);
      setTimeout(() => {
        setCopiedResetUrl(null);
        setActionSuccess("");
      }, 5000);
    },
    onError: (e) => setActionError(errorDetail(e, "Could not generate reset link")),
  });

  const resetCreateForm = () => {
    setNewName("");
    setNewEmailPrefix("");
    setNewPassword("SpacePoint123!");
    setNewPhone("+971501234567");
    setNewRoles(["student"]);
  };

  const handleOpenEdit = (user: User) => {
    setEditTarget(user);
    setEditName(user.full_name || "");
    setEditRoles((user.roles || []).filter((r) => r !== "admin"));
    setEditStatus(user.status || "active");
    setEditPassword("");
    setActionError("");
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setActionError("");
    const trimmedPrefix = newEmailPrefix.trim();
    if (!trimmedPrefix) {
      setActionError("Email prefix is required");
      return;
    }
    const finalEmail = trimmedPrefix.includes("@")
      ? trimmedPrefix.toLowerCase()
      : `${trimmedPrefix.toLowerCase()}@${TEST_DOMAIN}`;

    if (!finalEmail.endsWith(`@${TEST_DOMAIN}`)) {
      setActionError(`Test accounts must end with @${TEST_DOMAIN}`);
      return;
    }

    if (newRoles.length === 0) {
      setActionError("Select at least one role");
      return;
    }

    createMutation.mutate({
      full_name: newName.trim() || trimmedPrefix,
      email: finalEmail,
      password: newPassword,
      roles: newRoles,
      phone: newPhone.trim() || undefined,
    });
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editTarget) return;
    setActionError("");
    if (editRoles.length === 0) {
      setActionError("Select at least one role");
      return;
    }

    const payload: UpdateTestUserPayload = {
      full_name: editName.trim(),
      roles: editRoles,
      status: editStatus,
    };
    if (editPassword.trim()) {
      payload.password = editPassword.trim();
    }

    updateMutation.mutate({ id: editTarget.id, payload });
  };

  // Filtered lists
  const filteredUsers = users.filter((u) => {
    const matchesSearch =
      u.full_name?.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole =
      roleFilter === "all" || (u.roles && u.roles.includes(roleFilter as Role));
    return matchesSearch && matchesRole;
  });

  const filteredApps = applications.filter((a) => {
    const matchesSearch =
      a.full_name?.toLowerCase().includes(search.toLowerCase()) ||
      a.email.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === "all" || a.role === roleFilter;
    return matchesSearch && matchesRole;
  });

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-6 max-w-7xl mx-auto w-full">
      {/* Top Banner / Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Shield className="text-primary" size={24} />
            Test Accounts & Local Catch-All
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Disposable <code className="bg-muted px-1.5 py-0.5 rounded text-xs font-mono">@{TEST_DOMAIN}</code> accounts
            with split SMTP routing to Mailpit and safe cascade deletion.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <a
            href="https://test-inbox.spacepoint.ae"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 transition-colors shadow-sm"
          >
            <Mail size={14} />
            Open Test Inbox
            <ExternalLink size={12} className="opacity-70" />
          </a>

          <button
            onClick={() => {
              setPurgeEmailOpen(true);
              setActionError("");
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-rose-500/10 text-rose-600 dark:text-rose-400 hover:bg-rose-500/20 border border-rose-500/20 transition-colors shadow-sm"
          >
            <Trash2 size={14} />
            Purge by Email
          </button>

          <button
            onClick={() => {
              setCreateOpen(true);
              setActionError("");
            }}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 transition-colors shadow-sm"
          >
            <UserPlus size={14} />
            New Test Account
          </button>
        </div>
      </div>

      {/* Global Alerts */}
      {actionSuccess && (
        <div className="flex items-center gap-2 p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-700 dark:text-emerald-300 rounded-xl text-sm animate-in fade-in duration-200">
          <Check size={16} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {actionError && (
        <div className="flex items-center gap-2 p-3 bg-rose-500/15 border border-rose-500/30 text-rose-700 dark:text-rose-300 rounded-xl text-sm animate-in fade-in duration-200">
          <AlertTriangle size={16} />
          <span>{actionError}</span>
        </div>
      )}

      {/* Navigation Tabs & Search Toolbar */}
      <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div className="flex items-center gap-1 bg-muted/60 p-1 rounded-xl self-start">
          <button
            onClick={() => setActiveTab("users")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activeTab === "users"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <UserCheck size={14} />
            Test Accounts ({users.length})
          </button>
          <button
            onClick={() => setActiveTab("applications")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              activeTab === "applications"
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <FileText size={14} />
            Pending Applications ({applications.length})
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 sm:w-64">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search by name or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-card border border-border rounded-xl focus:outline-none focus:ring-1 focus:ring-primary"
            />
          </div>

          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-card border border-border rounded-xl focus:outline-none focus:ring-1 focus:ring-primary text-foreground"
          >
            <option value="all">All Roles</option>
            {AVAILABLE_ROLES.map((r) => (
              <option key={r.role} value={r.role}>
                {r.label}
              </option>
            ))}
          </select>

          <button
            onClick={() => {
              if (activeTab === "users") void refetchUsers();
              else void refetchApps();
            }}
            className="p-1.5 rounded-xl border border-border hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Refresh list"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {/* Main Content: Users List */}
      {activeTab === "users" && (
        <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm">
          {usersLoading ? (
            <div className="py-20 flex justify-center">
              <Spinner size="lg" />
            </div>
          ) : filteredUsers.length === 0 ? (
            <div className="py-12">
              <EmptyState
                title="No test accounts found"
                hint={
                  search || roleFilter !== "all"
                    ? "Try adjusting your search query or role filter."
                    : `No @${TEST_DOMAIN} test accounts have been created yet.`
                }
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Account Details</th>
                    <th className="px-4 py-3">Roles</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Created</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredUsers.map((u) => (
                    <tr key={u.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3">
                        <div className="font-semibold text-foreground text-sm">{u.full_name || "—"}</div>
                        <div className="text-muted-foreground font-mono text-xs">{u.email}</div>
                        {u.phone && <div className="text-[11px] text-muted-foreground/70">{u.phone}</div>}
                      </td>

                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1 max-w-xs">
                          {(u.roles || []).map((r) => (
                            <span
                              key={r}
                              className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/10 text-primary border border-primary/20 capitalize"
                            >
                              {r.replace("_", " ")}
                            </span>
                          ))}
                        </div>
                      </td>

                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                            u.status === "active"
                              ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20"
                              : "bg-muted text-muted-foreground border border-border"
                          }`}
                        >
                          {u.status || "active"}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                      </td>

                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => resetLinkMutation.mutate(u.id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground text-[11px] transition-colors"
                            title="Generate & copy 72h password reset link"
                          >
                            {copiedResetUrl === u.id ? <Check size={12} className="text-emerald-500" /> : <KeyRound size={12} />}
                            {copiedResetUrl === u.id ? "Copied" : "Reset Link"}
                          </button>

                          <button
                            onClick={() => handleOpenEdit(u)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-border bg-card hover:bg-muted text-muted-foreground hover:text-foreground text-[11px] transition-colors"
                            title="Edit roles and status"
                          >
                            <Edit size={12} />
                            Edit
                          </button>

                          <button
                            onClick={() =>
                              setDeleteTarget({
                                id: u.id,
                                email: u.email,
                                name: u.full_name,
                              })
                            }
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-rose-500/20 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 text-[11px] transition-colors"
                            title="Completely wipe test user, dependencies, and inbox"
                          >
                            <Trash2 size={12} />
                            Cascade Wipe
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Main Content: Applications List */}
      {activeTab === "applications" && (
        <div className="bg-card border border-border rounded-2xl overflow-hidden shadow-sm">
          {appsLoading ? (
            <div className="py-20 flex justify-center">
              <Spinner size="lg" />
            </div>
          ) : filteredApps.length === 0 ? (
            <div className="py-12">
              <EmptyState
                title="No test applications found"
                hint={`No pending applications submitted with @${TEST_DOMAIN}.`}
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-muted/40 border-b border-border text-muted-foreground uppercase text-[10px] tracking-wider font-semibold">
                  <tr>
                    <th className="px-4 py-3">Applicant</th>
                    <th className="px-4 py-3">Target Role</th>
                    <th className="px-4 py-3">Application Status</th>
                    <th className="px-4 py-3">Submitted</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredApps.map((a) => (
                    <tr key={a.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 py-3">
                        <div className="font-semibold text-foreground text-sm">{a.full_name}</div>
                        <div className="text-muted-foreground font-mono text-xs">{a.email}</div>
                      </td>

                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-muted text-muted-foreground uppercase">
                          {a.role}
                        </span>
                      </td>

                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-400 border border-amber-500/20 capitalize">
                          {a.status}
                        </span>
                      </td>

                      <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                        {a.created_at ? new Date(a.created_at).toLocaleDateString() : "—"}
                      </td>

                      <td className="px-4 py-3 text-right whitespace-nowrap">
                        <button
                          onClick={() =>
                            setDeleteTarget({
                              email: a.email,
                              name: a.full_name,
                            })
                          }
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-rose-500/20 bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 text-[11px] transition-colors"
                        >
                          <Trash2 size={12} />
                          Cascade Wipe
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Modal: Create Test Account ──────────────────────────────────── */}
      {createOpen && (
        <Modal title="Create @spacepoint.local Test Account" onClose={() => setCreateOpen(false)}>
          <form onSubmit={handleCreateSubmit} className="flex flex-col gap-4">
            <Field label="Full Name">
              <input
                type="text"
                required
                placeholder="e.g. Ali Al-Zaabi"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
              />
            </Field>

            <Field label={`Email Prefix (@${TEST_DOMAIN})`}>
              <div className="flex items-center">
                <input
                  type="text"
                  required
                  placeholder="ali.test"
                  value={newEmailPrefix}
                  onChange={(e) => setNewEmailPrefix(e.target.value)}
                  className="w-full px-3 py-2 bg-muted/40 border border-border rounded-l-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                />
                <span className="px-3 py-2 bg-muted border border-l-0 border-border rounded-r-xl text-xs text-muted-foreground font-mono">
                  @{TEST_DOMAIN}
                </span>
              </div>
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field label="Initial Password">
                <input
                  type="text"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-none"
                />
              </Field>

              <Field label="Phone (Optional)">
                <input
                  type="text"
                  value={newPhone}
                  onChange={(e) => setNewPhone(e.target.value)}
                  className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
                />
              </Field>
            </div>

            <Field label="Assign Roles (Non-Admin Only)">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-2 bg-muted/20 border border-border rounded-xl max-h-48 overflow-y-auto">
                {AVAILABLE_ROLES.map(({ role, label }) => {
                  const checked = newRoles.includes(role);
                  return (
                    <label
                      key={role}
                      className={`flex items-center gap-2 p-1.5 rounded-lg text-xs cursor-pointer select-none transition-colors ${
                        checked ? "bg-primary/10 text-primary font-semibold" : "hover:bg-muted text-foreground"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          if (checked) setNewRoles(newRoles.filter((r) => r !== role));
                          else setNewRoles([...newRoles, role]);
                        }}
                        className="rounded border-border text-primary focus:ring-primary"
                      />
                      <span>{label}</span>
                    </label>
                  );
                })}
              </div>
            </Field>

            {actionError && <div className="text-xs text-rose-500">{actionError}</div>}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setCreateOpen(false)}
                className="px-3 py-1.5 rounded-xl border border-border text-xs text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-1.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold"
              >
                {createMutation.isPending ? "Creating..." : "Create Account"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Modal: Edit Test Account ────────────────────────────────────── */}
      {editTarget && (
        <Modal title={`Edit Test User: ${editTarget.email}`} onClose={() => setEditTarget(null)}>
          <form onSubmit={handleEditSubmit} className="flex flex-col gap-4">
            <Field label="Full Name">
              <input
                type="text"
                required
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
              />
            </Field>

            <Field label="Account Status">
              <select
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value)}
                className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
              >
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </Field>

            <Field label="New Password (leave blank to keep current)">
              <input
                type="password"
                placeholder="••••••••"
                value={editPassword}
                onChange={(e) => setEditPassword(e.target.value)}
                className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground focus:ring-1 focus:ring-primary focus:outline-none"
              />
            </Field>

            <Field label="Toggle Roles (Non-Admin Only)">
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 p-2 bg-muted/20 border border-border rounded-xl max-h-48 overflow-y-auto">
                {AVAILABLE_ROLES.map(({ role, label }) => {
                  const checked = editRoles.includes(role);
                  return (
                    <label
                      key={role}
                      className={`flex items-center gap-2 p-1.5 rounded-lg text-xs cursor-pointer select-none transition-colors ${
                        checked ? "bg-primary/10 text-primary font-semibold" : "hover:bg-muted text-foreground"
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          if (checked) setEditRoles(editRoles.filter((r) => r !== role));
                          else setEditRoles([...editRoles, role]);
                        }}
                        className="rounded border-border text-primary focus:ring-primary"
                      />
                      <span>{label}</span>
                    </label>
                  );
                })}
              </div>
            </Field>

            {actionError && <div className="text-xs text-rose-500">{actionError}</div>}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setEditTarget(null)}
                className="px-3 py-1.5 rounded-xl border border-border text-xs text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={updateMutation.isPending}
                className="px-4 py-1.5 rounded-xl bg-primary text-primary-foreground hover:bg-primary/90 text-xs font-semibold"
              >
                {updateMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* ── Modal: Cascade Delete Confirmation ──────────────────────────── */}
      {deleteTarget && (
        <Modal title="Confirm Cascade Wipe" onClose={() => setDeleteTarget(null)}>
          <div className="flex flex-col gap-4">
            <div className="flex items-start gap-3 p-3 bg-rose-500/10 border border-rose-500/20 text-rose-700 dark:text-rose-300 rounded-xl text-xs">
              <AlertTriangle size={20} className="shrink-0 mt-0.5 text-rose-500" />
              <div>
                <p className="font-semibold text-sm mb-1">Permanent Cascade Delete</p>
                <p>
                  This action will completely wipe <strong>{deleteTarget.email}</strong>, linked Spine
                  Contacts, orphan guardian records, learner team entries, live game records, uploaded
                  documents/contracts, and captured emails in Mailpit.
                </p>
                <p className="mt-1 font-medium">This operation is irreversible.</p>
              </div>
            </div>

            {actionError && <div className="text-xs text-rose-500">{actionError}</div>}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="px-3 py-1.5 rounded-xl border border-border text-xs text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (deleteTarget.id) {
                    deleteUserMutation.mutate(deleteTarget.id);
                  } else {
                    deleteEmailMutation.mutate(deleteTarget.email);
                  }
                }}
                disabled={deleteUserMutation.isPending || deleteEmailMutation.isPending}
                className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm"
              >
                <Trash2 size={12} />
                {deleteUserMutation.isPending || deleteEmailMutation.isPending
                  ? "Wiping..."
                  : "Nuke Everything"}
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ── Modal: Purge by Email Input ─────────────────────────────────── */}
      {purgeEmailOpen && (
        <Modal title="Purge Test Account by Email" onClose={() => setPurgeEmailOpen(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = purgeEmailInput.trim().toLowerCase();
              if (!trimmed.endsWith(`@${TEST_DOMAIN}`)) {
                setActionError(`Email must end with @${TEST_DOMAIN}`);
                return;
              }
              deleteEmailMutation.mutate(trimmed);
            }}
            className="flex flex-col gap-4"
          >
            <p className="text-xs text-muted-foreground">
              Enter any <code className="font-mono">@{TEST_DOMAIN}</code> email address to completely wipe it
              from the system (including applications, contacts, and Mailpit inbox), even if no active user row
              exists.
            </p>

            <Field label="Test Email Address">
              <input
                type="email"
                required
                placeholder={`test.student@${TEST_DOMAIN}`}
                value={purgeEmailInput}
                onChange={(e) => setPurgeEmailInput(e.target.value)}
                className="w-full px-3 py-2 bg-muted/40 border border-border rounded-xl text-xs text-foreground font-mono focus:ring-1 focus:ring-primary focus:outline-none"
              />
            </Field>

            {actionError && <div className="text-xs text-rose-500">{actionError}</div>}

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
              <button
                type="button"
                onClick={() => setPurgeEmailOpen(false)}
                className="px-3 py-1.5 rounded-xl border border-border text-xs text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={deleteEmailMutation.isPending}
                className="px-4 py-1.5 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm"
              >
                <Trash2 size={12} />
                {deleteEmailMutation.isPending ? "Purging..." : "Purge Email"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
