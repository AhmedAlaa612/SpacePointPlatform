import { useEffect, useState } from "react"
import { Check, AlertCircle, Loader2 } from "lucide-react"
import { EmojiRating } from "@/components/ui/EmojiRating"
import { useCourseRating } from "@/api/course_ratings"

export interface CourseRatingWidgetProps {
  courseId: string
  title?: string
  size?: "sm" | "md" | "lg"
  className?: string
  onSubmitted?: () => void
  showTitle?: boolean
}

export function CourseRatingWidget({
  courseId,
  title,
  size = "sm",
  className = "",
  onSubmitted,
  showTitle = true,
}: CourseRatingWidgetProps) {
  const [savedRating, , { reviewText: savedReviewText, submitRating, isSubmitting }] =
    useCourseRating(courseId)

  const [selectedRating, setSelectedRating] = useState<number | null>(savedRating)
  const [feedbackText, setFeedbackText] = useState<string>(savedReviewText || "")
  const [isDirty, setIsDirty] = useState(false)
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null)

  // Sync with fetched data when it arrives, provided the user hasn't modified the form
  useEffect(() => {
    if (!isDirty) {
      setSelectedRating(savedRating)
      setFeedbackText(savedReviewText || "")
    }
  }, [savedRating, savedReviewText, isDirty])

  const isMandatory = selectedRating !== null && selectedRating < 3
  const isFeedbackEmpty = !feedbackText.trim()

  const isSavedUnchanged =
    savedRating !== null &&
    savedRating === selectedRating &&
    (savedReviewText || "").trim() === feedbackText.trim() &&
    !isDirty

  const handleSubmit = async () => {
    if (!selectedRating) return

    if (selectedRating < 3 && isFeedbackEmpty) {
      setStatus({
        type: "error",
        message: "Written feedback is required for ratings below 3 stars.",
      })
      return
    }

    try {
      setStatus(null)
      await submitRating(selectedRating, feedbackText.trim() || null)
      setIsDirty(false)
      setStatus({
        type: "success",
        message: "Thank you! Your feedback has been submitted.",
      })
      onSubmitted?.()
      setTimeout(() => {
        setStatus(null)
      }, 3500)
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } }; message?: string }
      const msg =
        errorObj?.response?.data?.detail ||
        errorObj?.message ||
        "Could not submit feedback. Please try again."
      setStatus({
        type: "error",
        message: msg,
      })
    }
  }

  return (
    <div
      className={`flex flex-col items-center gap-2 p-4 rounded-xl border border-border/80 dark:border-lms-accent-border/30 bg-muted/20 dark:bg-[#12091f]/60 text-center w-full ${className}`}
    >
      {showTitle && (
        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          {savedRating ? "Your rating" : (title || "Rate this course")}
        </p>
      )}

      {/* 1. Rating selection */}
      <EmojiRating
        value={selectedRating}
        onChange={(val) => {
          setSelectedRating(val)
          setIsDirty(true)
          setStatus(null)
        }}
        size={size}
      />

      {selectedRating && (
        <p className="text-[11px] text-muted-foreground font-medium -mt-1">
          Rated {selectedRating}/5 · Click an emoji to change
        </p>
      )}

      {/* 2. Feedback text area directly under the rating */}
      <div className="w-full flex flex-col gap-1.5 mt-2 text-left">
        <label
          htmlFor={`course-feedback-${courseId}`}
          className="text-xs font-semibold text-foreground flex items-center justify-between"
        >
          <span className="flex items-center">
            Your feedback
            {isMandatory && (
              <span className="text-red-500 font-bold ml-1 text-sm" title="Mandatory for ratings below 3 stars">
                *
              </span>
            )}
          </span>
          {isMandatory && isFeedbackEmpty && (
            <span className="text-[11px] text-amber-500 font-normal">
              Required for 1 & 2 stars
            </span>
          )}
        </label>
        <textarea
          id={`course-feedback-${courseId}`}
          value={feedbackText}
          onChange={(e) => {
            setFeedbackText(e.target.value)
            setIsDirty(true)
            setStatus(null)
          }}
          placeholder="Share your thoughts and experience with this course..."
          rows={3}
          className={`w-full text-xs p-2.5 rounded-lg bg-background border ${
            isMandatory && isFeedbackEmpty && isDirty
              ? "border-amber-500/70 focus:border-amber-500"
              : "border-border"
          } resize-none focus:outline-none focus:ring-1 focus:ring-primary text-foreground placeholder:text-muted-foreground/60 transition-colors`}
        />
      </div>

      {/* Status feedback message */}
      {status && (
        <div
          className={`w-full flex items-center gap-1.5 text-xs font-medium py-1 px-2 rounded-md ${
            status.type === "success"
              ? "bg-emerald-500/10 text-emerald-500"
              : "bg-destructive/10 text-destructive"
          }`}
        >
          {status.type === "success" ? (
            <Check className="size-3.5 shrink-0" />
          ) : (
            <AlertCircle className="size-3.5 shrink-0" />
          )}
          <span>{status.message}</span>
        </div>
      )}

      {/* 3. Submit feedback button directly under the textarea */}
      <button
        type="button"
        disabled={!selectedRating || isSavedUnchanged || isSubmitting}
        onClick={() => void handleSubmit()}
        className="w-full mt-1 text-xs font-semibold py-2 px-3.5 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-all cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5 shadow-sm"
      >
        {isSubmitting ? (
          <>
            <Loader2 className="size-3.5 animate-spin" />
            <span>Submitting feedback...</span>
          </>
        ) : isSavedUnchanged ? (
          <>
            <Check className="size-3.5 text-emerald-400" />
            <span>Feedback submitted</span>
          </>
        ) : savedRating && isDirty ? (
          <span>Update feedback</span>
        ) : (
          <span>Submit feedback</span>
        )}
      </button>
    </div>
  )
}

export default CourseRatingWidget
