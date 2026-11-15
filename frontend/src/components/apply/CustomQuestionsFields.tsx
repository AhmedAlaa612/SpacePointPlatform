import type { ApplyQuestion, FormFieldConfig } from "@/api/apply"

export function isFieldEnabled(fields: FormFieldConfig[] | undefined, key: string, fallback = true): boolean {
  const f = fields?.find((item) => item.key === key)
  return f ? f.enabled : fallback
}

export function isFieldRequired(fields: FormFieldConfig[] | undefined, key: string, fallback = false): boolean {
  const f = fields?.find((item) => item.key === key)
  return f ? (f.enabled && f.required) : fallback
}

export function validateCustomQuestionAnswers(
  questions: ApplyQuestion[],
  answers: Record<string, string>,
): string | null {
  const missing = questions
    .filter((q) => {
      if (!q.required) return false
      const val = answers[q.id]
      if (!val || !val.trim()) return true
      return false
    })
    .map((q) => q.question_text)

  if (missing.length === 0) return null
  return `Please answer the required question(s): ${missing.join(", ")}`
}

interface CustomQuestionsFieldsProps {
  questions: ApplyQuestion[]
  answers: Record<string, string>
  onChange: (next: Record<string, string>) => void
  inputClassName?: string
  labelClassName?: string
}

export function CustomQuestionsFields({
  questions,
  answers,
  onChange,
  inputClassName = "input",
  labelClassName = "text-xs font-medium text-muted-foreground uppercase tracking-wider",
}: CustomQuestionsFieldsProps) {
  if (!questions || questions.length === 0) return null

  return (
    <div className="flex flex-col gap-3">
      {questions.map((q) => {
        const val = answers[q.id] ?? ""
        const setVal = (v: string) => onChange({ ...answers, [q.id]: v })
        const selectedMulti = val.split(",").filter(Boolean)

        return (
          <div key={q.id} className="flex flex-col gap-1.5">
            <label className={labelClassName}>
              {q.question_text}
              {q.required && <span className="text-destructive ml-0.5">*</span>}
            </label>

            {q.question_type === "radio" || q.question_type === "multiple_choice" ? (
              <div className="flex flex-col gap-2 pt-0.5">
                {q.options.map((opt) => (
                  <label key={opt} className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
                    <input
                      type={q.question_type === "multiple_choice" ? "checkbox" : "radio"}
                      name={`custom-q-${q.id}`}
                      value={opt}
                      checked={q.question_type === "multiple_choice" ? selectedMulti.includes(opt) : val === opt}
                      onChange={(e) => {
                        if (q.question_type === "multiple_choice") {
                          const next = e.target.checked
                            ? [...selectedMulti, opt]
                            : selectedMulti.filter((item) => item !== opt)
                          setVal(next.join(","))
                        } else {
                          setVal(opt)
                        }
                      }}
                    />
                    <span>{opt}</span>
                  </label>
                ))}
              </div>
            ) : q.question_type === "textarea" ? (
              <textarea
                rows={3}
                className={`${inputClassName} min-h-[84px] py-2`}
                value={val}
                onChange={(e) => setVal(e.target.value)}
              />
            ) : (
              <input
                className={inputClassName}
                type={
                  q.question_type === "number"
                    ? "number"
                    : q.question_type === "date"
                      ? "date"
                      : q.question_type === "url"
                        ? "url"
                        : "text"
                }
                placeholder={q.question_type === "url" ? "https://..." : undefined}
                value={val}
                onChange={(e) => setVal(e.target.value)}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

