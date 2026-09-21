import { api } from "@/api/client"
import type {
  ProgramCertificateTemplate,
  ProgramCertificateTemplateCreate,
  ProgramCertificateTemplateUpdate,
  CertificatePreviewRequest,
} from "@/types/sessions"

export const listProgramCertificateTemplatesApi = (programId: string) =>
  api
    .get<ProgramCertificateTemplate[]>(`/sessions/programs/${programId}/certificate-templates`)
    .then((r) => r.data)

export const createProgramCertificateTemplateApi = (
  programId: string,
  data: ProgramCertificateTemplateCreate
) =>
  api
    .post<ProgramCertificateTemplate>(`/sessions/programs/${programId}/certificate-templates`, data)
    .then((r) => r.data)

export const updateProgramCertificateTemplateApi = (
  programId: string,
  templateId: string,
  data: ProgramCertificateTemplateUpdate
) =>
  api
    .put<ProgramCertificateTemplate>(
      `/sessions/programs/${programId}/certificate-templates/${templateId}`,
      data
    )
    .then((r) => r.data)

export const deleteProgramCertificateTemplateApi = (programId: string, templateId: string) =>
  api
    .delete<void>(`/sessions/programs/${programId}/certificate-templates/${templateId}`)
    .then((r) => r.data)

export const setDefaultProgramCertificateTemplateApi = (programId: string, templateId: string) =>
  api
    .post<ProgramCertificateTemplate>(
      `/sessions/programs/${programId}/certificate-templates/${templateId}/set-default`
    )
    .then((r) => r.data)

export const setStockDefaultCertificateTemplateApi = (programId: string, theme: "dark" | "light") =>
  api
    .post<{ default_theme: string }>(
      `/sessions/programs/${programId}/certificate-templates/set-stock-default`,
      undefined,
      { params: { theme } }
    )
    .then((r) => r.data)

export const uploadCertificateBackgroundApi = (programId: string, file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  return api
    .post<{ file_path: string; file_url: string }>(
      `/sessions/programs/${programId}/certificate-templates/upload-background`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    )
    .then((r) => r.data)
}

export const uploadCertificateSignatureApi = (programId: string, file: File) => {
  const formData = new FormData()
  formData.append("file", file)
  return api
    .post<{ file_path: string; file_url: string }>(
      `/sessions/programs/${programId}/certificate-templates/upload-signature`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } }
    )
    .then((r) => r.data)
}

export const getStockSignatoryInfoApi = () =>
  api
    .get<{ signatory_name: string; signatory_title: string }>(
      "/sessions/programs/stock-signatory-info"
    )
    .then((r) => r.data)

export const previewCertificateTemplateApi = async (
  programId: string,
  data: CertificatePreviewRequest
): Promise<Blob> => {
  const res = await api.post(
    `/sessions/programs/${programId}/certificate-templates/preview`,
    data,
    { responseType: "blob" }
  )
  return res.data as Blob
}
