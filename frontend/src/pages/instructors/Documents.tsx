import { useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Trash2, Upload } from "lucide-react"
import { deleteDocumentApi, listDocumentsApi, uploadDocumentApi } from "@/api/instructors/instructor"
import { getMyDocumentsApi } from "@/api/documents"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { EmptyState, PageHeader, Spinner } from "@/pages/instructors/components/common"

const DOCUMENT_TYPES = ["Emirates ID", "Passport", "Visa", "CV", "Other"]

export default function Documents() {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [documentType, setDocumentType] = useState(DOCUMENT_TYPES[0])

  const { data: docs, isLoading } = useQuery({ queryKey: ["instructor-documents"], queryFn: listDocumentsApi })

  const upload = useMutation({
    mutationFn: (file: File) => uploadDocumentApi(documentType, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-documents"] }),
  })

  const remove = useMutation({
    mutationFn: (docId: string) => deleteDocumentApi(docId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instructor-documents"] }),
  })

  if (isLoading) return <Spinner />

  return (
    <div>
      <PageHeader title="My Documents" subtitle="Your personal document vault — only visible to you and admins." />

      <GeneratedDocuments />

      <Card className="mb-6">
        <CardContent className="p-5 flex flex-col sm:flex-row gap-3 items-stretch sm:items-end">
          <div className="flex-1">
            <label className="text-xs font-medium text-muted-foreground mb-1 block">Document type</label>
            <select className="input" value={documentType} onChange={(e) => setDocumentType(e.target.value)}>
              {DOCUMENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <input
            ref={fileRef} type="file" className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = "" }}
          />
          <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            <Upload size={16} className="mr-1.5" /> {upload.isPending ? "Uploading…" : "Upload document"}
          </Button>
        </CardContent>
      </Card>

      {(docs ?? []).length === 0 ? (
        <EmptyState title="No documents uploaded yet" />
      ) : (
        <div className="space-y-2">
          {docs!.map((d) => (
            <div key={d.id} className="flex items-center gap-3 p-3 rounded-lg border bg-card">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{d.document_type}</p>
                <p className="text-xs text-muted-foreground">{new Date(d.uploaded_at).toLocaleDateString()}</p>
              </div>
              <a href={d.file_url} target="_blank" rel="noreferrer" className="p-2 text-muted-foreground hover:text-foreground">
                <Download size={16} />
              </a>
              <button onClick={() => remove.mutate(d.id)} className="p-2 text-muted-foreground hover:text-destructive">
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function GeneratedDocuments() {
  const { data, isLoading } = useQuery({ queryKey: ["my-documents"], queryFn: getMyDocumentsApi })
  if (isLoading) return null

  const items = [
    ...(data?.certificates ?? []).map((c) => ({
      id: c.id,
      label: c.type === "instructor_completion" ? "Instructor program completion certificate" : "Certificate",
      url: c.file_url,
    })),
    ...(data?.recommendation_letters ?? []).map((r) => ({ id: r.id, label: "Recommendation letter", url: r.file_url })),
  ]
  if (items.length === 0) return null

  return (
    <Card className="mb-6">
      <CardContent className="p-5 flex flex-col gap-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
          Generated documents
        </p>
        {items.map((item) => (
          <a
            key={item.id} href={item.url} target="_blank" rel="noreferrer"
            className="flex items-center justify-between text-sm text-foreground hover:text-primary transition-colors"
          >
            <span>{item.label}</span>
            <Download size={14} />
          </a>
        ))}
      </CardContent>
    </Card>
  )
}
