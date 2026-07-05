export default function Leaderboard() {
  return (
    <div className="flex flex-col items-center justify-center h-64 gap-3">
      <div className="w-12 h-12 rounded-2xl border-2 border-border flex items-center justify-center">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} className="w-6 h-6 text-muted-foreground">
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
      </div>
      <p className="text-base font-semibold text-foreground">Leaderboard</p>
      <p className="text-sm text-muted-foreground text-center max-w-xs">
        TBD
      </p>
    </div>
  )
}
