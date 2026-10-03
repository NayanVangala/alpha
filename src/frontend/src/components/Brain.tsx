import { useEffect, useState } from "react"
import type { BoardState, Decision } from "@/lib/api"
import { cn } from "@/lib/utils"

const N = 160 // points on a trace: ~20 s of the board's 120 ms polls
const TOP = 2 // a trace's top edge, as a multiple of its line

/** The last N values of a level whose line is 1.0, one per poll; null where the headband sent nothing. */
function useTrail(value: number | null | undefined, poll: unknown) {
  const [trail, setTrail] = useState<(number | null)[]>([])
  useEffect(() => setTrail((t) => [...t.slice(1 - N), value ?? null]), [poll, value])
  return trail
}

/** SVG path for a trail, newest at the right edge, with gaps where there was no data. */
function path(trail: (number | null)[]) {
  let d = ""
  let pen = false
  trail.forEach((v, i) => {
    if (v == null) {
      pen = false
      return
    }
    d += `${pen ? "L" : "M"}${i + N - trail.length},${(20 * (1 - Math.min(v, TOP) / TOP)).toFixed(1)}`
    pen = true
  })
  return d
}

function Trace({ name, what, trail, brain }: { name: string; what: string; trail: (number | null)[]; brain?: boolean }) {
  const now = trail.at(-1)
  const over = now != null && now >= 1
  return (
    <div className="grid grid-cols-[5.5rem_1fr] items-center gap-3">
      <div className="leading-tight">
        <div className={cn("text-tag font-semibold uppercase tracking-[0.08em]", over && brain ? "text-ultramarine" : "text-foreground")}>
          {name}
        </div>
        <div className="text-tag text-muted-foreground">{what}</div>
      </div>
      <svg viewBox={`0 0 ${N} 20`} preserveAspectRatio="none" className="h-7 w-full overflow-visible" role="img" aria-label={`${name}: ${what}${over ? ", past the line" : ""}`}>
        <line x1="0" x2={N} y1="10" y2="10" className="stroke-foreground/40" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />
        <path d={path(trail)} fill="none" className={brain ? "stroke-ultramarine" : "stroke-foreground"} strokeWidth="1.5" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

const BY: Record<Decision["by"], string> = { brain: "brain", muscle: "muscle", silence: "silence", keys: "keyboard" }

/**
 * What decided each of Claude's steps, live: the wearer's alpha waves (brain) and jaw (muscle) against their
 * lines, the latest decisions with what made them, and the counts. The bite is labeled muscle on purpose.
 */
export function BrainPanel({ s, compact, className }: { s: BoardState; compact?: boolean; className?: string }) {
  const alpha = useTrail(s.headband.alpha, s)
  const muscle = useTrail(s.headband.muscle, s)
  const shown = s.ledger.slice(compact ? -2 : -5).reverse()
  return (
    <section className={cn("grid gap-2", className)} aria-label="What your brain and muscles decided">
      <Trace name="Brain" what="alpha · no" trail={alpha} brain />
      <Trace name="Muscle" what="jaw · yes" trail={muscle} />
      {shown.length > 0 && (
        <ol className="m-0 grid list-none gap-0.5 p-0 text-label">
          {shown.map((d, i) => (
            <li key={s.counts.decisions - i} className="flex items-baseline gap-2">
              <span className="w-[2.6em] shrink-0 text-tag font-semibold uppercase tracking-[0.08em]">{d.verdict}</span>
              <span className="min-w-0 flex-1 truncate">{d.what}</span>
              <span className={cn("shrink-0 text-tag font-semibold uppercase tracking-[0.08em]", d.by === "brain" ? "text-ultramarine" : "text-muted-foreground")}>
                {BY[d.by]}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="m-0 text-tag text-muted-foreground tabular-nums">
        Decisions {s.counts.decisions} · Headband inputs {s.counts.wearer} · Keystrokes {s.counts.keys}
      </p>
    </section>
  )
}
