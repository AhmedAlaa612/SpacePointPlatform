import { api } from "@/api/client"
import type { EmailTemplate, EmailTemplatePreview } from "@/types/emailTemplates"

export const listEmailTemplatesApi = () =>
  api.get<EmailTemplate[]>("/email-templates").then((r) => r.data)

export const updateEmailTemplateApi = (id: string, data: { subject?: string; body_html?: string }) =>
  api.put<EmailTemplate>(`/email-templates/${id}`, data).then((r) => r.data)

export const pauseEmailTemplateApi = (id: string, is_paused: boolean) =>
  api.patch<EmailTemplate>(`/email-templates/${id}/pause`, { is_paused }).then((r) => r.data)

export const previewEmailTemplateApi = (
  id: string,
  data: { subject: string; body_html: string; values?: Record<string, string> },
) => api.post<EmailTemplatePreview>(`/email-templates/${id}/preview`, data).then((r) => r.data)

export const sendTestEmailTemplateApi = (
  id: string,
  data: { subject: string; body_html: string; values?: Record<string, string> },
) => api.post<{ sent: boolean; to: string }>(`/email-templates/${id}/send-test`, data).then((r) => r.data)
