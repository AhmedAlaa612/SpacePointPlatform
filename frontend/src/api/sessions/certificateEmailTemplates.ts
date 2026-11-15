import { api } from "@/api/client"
import type { CertificateEmailTemplate, CertificateEmailTemplateKind } from "@/types/sessions"

export interface CertificateEmailTemplateCreate {
  name: string
  kind: CertificateEmailTemplateKind
  subject: string
  body_html: string
  is_default?: boolean
}

export type CertificateEmailTemplateUpdate = Partial<CertificateEmailTemplateCreate>

export interface CertificateEmailTemplateTestIn {
  to_email: string
  recipient_name?: string
  subject?: string
  body_html?: string
  kind?: CertificateEmailTemplateKind
  cohort_id?: string
  certificate_template_id?: string | null
}

export const listCertificateEmailTemplatesApi = () =>
  api.get<CertificateEmailTemplate[]>("/sessions/certificate-email-templates").then((r) => r.data)

export const createCertificateEmailTemplateApi = (data: CertificateEmailTemplateCreate) =>
  api.post<CertificateEmailTemplate>("/sessions/certificate-email-templates", data).then((r) => r.data)

export const updateCertificateEmailTemplateApi = (id: string, data: CertificateEmailTemplateUpdate) =>
  api.put<CertificateEmailTemplate>(`/sessions/certificate-email-templates/${id}`, data).then((r) => r.data)

export const deleteCertificateEmailTemplateApi = (id: string) =>
  api.delete<void>(`/sessions/certificate-email-templates/${id}`).then((r) => r.data)

export const sendTestEmailTemplateApi = (data: CertificateEmailTemplateTestIn) =>
  api.post<{ sent: boolean; to: string; subject: string }>("/sessions/certificate-email-templates/test-email", data).then((r) => r.data)
