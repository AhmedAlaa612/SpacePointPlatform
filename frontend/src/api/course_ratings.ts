import { useEffect, useState, useCallback } from "react"
import { api } from "@/api/client"

const EVENT_NAME = "spacepoint:course-rating-changed"

export interface StudentCourseRating {
  rating: number | null
  review_text: string | null
  created_at?: string | null
  updated_at?: string | null
}

export async function fetchCourseRatingApi(courseId: string): Promise<StudentCourseRating> {
  const res = await api.get<StudentCourseRating>(`/lms/courses/${courseId}/rating`)
  return res.data
}

export async function submitCourseRatingApi(
  courseId: string,
  payload: { rating: number; review_text?: string | null }
): Promise<StudentCourseRating> {
  const res = await api.put<StudentCourseRating>(`/lms/courses/${courseId}/rating`, payload)
  return res.data
}

export function getCourseRating(courseId: string): number | null {
  if (!courseId || typeof window === "undefined") return null
  const raw = localStorage.getItem(`course_rating_${courseId}`)
  if (!raw) return null
  const num = parseInt(raw, 10)
  return Number.isFinite(num) && num >= 1 && num <= 5 ? num : null
}

export function getCourseReviewText(courseId: string): string {
  if (!courseId || typeof window === "undefined") return ""
  return localStorage.getItem(`course_review_${courseId}`) || ""
}

export function setCourseRating(courseId: string, rating: number, reviewText?: string | null): void {
  if (!courseId || typeof window === "undefined") return
  localStorage.setItem(`course_rating_${courseId}`, String(rating))
  if (reviewText !== undefined) {
    if (reviewText) {
      localStorage.setItem(`course_review_${courseId}`, reviewText)
    } else {
      localStorage.removeItem(`course_review_${courseId}`)
    }
  }
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: { courseId, rating, reviewText } }))
}

export function useCourseRating(courseId: string | undefined | null) {
  const [rating, setRatingState] = useState<number | null>(() =>
    courseId ? getCourseRating(courseId) : null
  )
  const [reviewText, setReviewTextState] = useState<string>(() =>
    courseId ? getCourseReviewText(courseId) : ""
  )
  const [isLoading, setIsLoading] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  // Fetch initial rating and review from backend
  useEffect(() => {
    if (!courseId) return
    let active = true

    setIsLoading(true)
    fetchCourseRatingApi(courseId)
      .then((data) => {
        if (!active) return
        if (data.rating) {
          setRatingState(data.rating)
          setCourseRating(courseId, data.rating, data.review_text)
        }
        if (data.review_text) {
          setReviewTextState(data.review_text)
        }
      })
      .catch(() => {
        // Fallback to local storage if network or offline
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })

    const handleStorage = (e: StorageEvent) => {
      if (e.key === `course_rating_${courseId}`) {
        setRatingState(getCourseRating(courseId))
      }
      if (e.key === `course_review_${courseId}`) {
        setReviewTextState(getCourseReviewText(courseId))
      }
    }

    const handleCustom = (e: Event) => {
      const customEvent = e as CustomEvent<{ courseId: string; rating: number; reviewText?: string }>
      if (customEvent.detail?.courseId === courseId) {
        setRatingState(customEvent.detail.rating)
        if (customEvent.detail.reviewText !== undefined) {
          setReviewTextState(customEvent.detail.reviewText || "")
        }
      }
    }

    window.addEventListener("storage", handleStorage)
    window.addEventListener(EVENT_NAME, handleCustom)
    return () => {
      active = false
      window.removeEventListener("storage", handleStorage)
      window.removeEventListener(EVENT_NAME, handleCustom)
    }
  }, [courseId])

  const submitRating = useCallback(
    async (newRating: number, newReviewText?: string | null) => {
      if (!courseId) return
      setRatingState(newRating)
      const reviewVal = newReviewText !== undefined ? newReviewText : reviewText
      if (newReviewText !== undefined) setReviewTextState(newReviewText || "")
      setCourseRating(courseId, newRating, reviewVal)

      setIsSubmitting(true)
      try {
        await submitCourseRatingApi(courseId, {
          rating: newRating,
          review_text: reviewVal ? reviewVal.trim() : null,
        })
      } catch (err) {
        console.error("Failed to persist course rating:", err)
      } finally {
        setIsSubmitting(false)
      }
    },
    [courseId, reviewText]
  )

  const updateRating = useCallback(
    (val: number) => {
      void submitRating(val, undefined)
    },
    [submitRating]
  )

  const saveReview = useCallback(
    async (text: string) => {
      if (!courseId || rating === null) return
      await submitRating(rating, text)
    },
    [courseId, rating, submitRating]
  )

  return [
    rating,
    updateRating,
    {
      reviewText,
      setReviewText: setReviewTextState,
      saveReview,
      submitRating,
      isLoading,
      isSubmitting,
    },
  ] as const
}
