export default function Calendar() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="w-12 h-12 rounded-2xl border-2 border-gray-200 flex items-center justify-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-gray-400">
          <rect x="3" y="4" width="18" height="18" rx="2" />
          <path d="M16 2v4M8 2v4M3 10h18" />
        </svg>
      </div>
      <p className="text-base font-semibold text-black">Calendar</p>
      <p className="text-sm text-gray-400 text-center max-w-xs">
        Deadlines and meeting scheduling — TBD
      </p>
    </div>
  )
}
