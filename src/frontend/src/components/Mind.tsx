import { cn } from "@/lib/utils"

/** The autopilot's countdown: a ring that fills until Alpha does its guess, unless the wearer steps in. */
export function Autopilot({ left, total, className, verb = "Doing it", then = "close your eyes to stop" }: {
  left: number
  total: number
  className?: string
  verb?: string
  then?: string
}) {
  const r = 9
  const c = 2 * Math.PI * r
  return (
    <span className={cn("flex items-center gap-2.5", className)} role="timer" aria-live="off">
      <svg viewBox="0 0 24 24" className="size-6 shrink-0" aria-hidden>
        <circle cx="12" cy="12" r={r} fill="none" stroke="currentColor" strokeOpacity={0.25} strokeWidth="3" />
        <circle
          cx="12"
          cy="12"
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (left / total)}
          transform="rotate(-90 12 12)"
          style={{ transition: "stroke-dashoffset 0.12s linear" }}
        />
      </svg>
      <span>
        <b className="font-semibold">{verb} in {Math.ceil(left)} s</b> · {then}
      </span>
    </span>
  )
}

const MAX = 1.5 // the meter's right end, as a multiple of the brake line

/** Live alpha waves behind the ears against the brake line: crossing it is what stops the agent. */
export function AlphaMeter({ level, className, compact }: { level: number | null | undefined; className?: string; compact?: boolean }) {
  if (level == null) return null
  const closed = level >= 1
  const bar = (
    <div className="relative h-2 flex-1 rounded-xs bg-border">
      <div
        className="absolute inset-0 origin-left rounded-xs bg-ultramarine transition-transform duration-300 ease-out"
        style={{ transform: `scaleX(${Math.min(level, MAX) / MAX})` }}
      />
      <div className="absolute -inset-y-1 w-0.5 bg-foreground" style={{ left: `${100 / MAX}%` }} aria-hidden />
    </div>
  )
  if (compact) {
    return (
      <div className={cn("flex items-center gap-3 text-tag font-semibold uppercase tracking-[0.08em] text-muted-foreground", className)}>
        <span>Alpha</span>
        {bar}
        <span className={cn("w-[7.5em] text-right", closed && "text-ultramarine")}>{closed ? "eyes closed" : "eyes open"}</span>
      </div>
    )
  }
  return (
    <div className={cn("grid gap-1.5", className)} title="Alpha waves (8-13 Hz) behind your ears. Past the line, Claude stops.">
      <div className="flex justify-between gap-3 text-tag font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        <span>Your alpha waves</span>
        <span className={cn(closed && "text-ultramarine")}>{closed ? "eyes closed: brake" : "eyes open"}</span>
      </div>
      <div className="flex">{bar}</div>
    </div>
  )
}

/** How strongly the card's pixel aura shows: it swells with the wearer's alpha waves. */
export const auraOpacity = (level: number | null | undefined) => (level == null ? 1 : 0.3 + 0.7 * Math.min(1, level))
