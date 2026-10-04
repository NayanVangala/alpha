import { motion } from "motion/react"
import { useEffect, useId, useState } from "react"
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

/** SVG line and area paths for a trail, newest at the right edge, with gaps where there was no data. */
function shapes(trail: (number | null)[]) {
  const x0 = N - trail.length
  let line = ""
  let fill = ""
  let segStart = 0
  let open = false
  trail.forEach((v, i) => {
    const x = x0 + i
    if (v == null) {
      if (open) {
        fill += `L${x - 1},20L${x0 + segStart},20Z`
        open = false
      }
      return
    }
    const y = (20 * (1 - Math.min(v, TOP) / TOP)).toFixed(1)
    if (!open) {
      line += `M${x},${y}`
      fill += `M${x},20L${x},${y}`
      segStart = i
      open = true
    } else {
      line += `L${x},${y}`
      fill += `L${x},${y}`
    }
  })
  if (open) fill += `L${N - 1},20L${x0 + segStart},20Z`
  return { line, fill }
}

function Trace({
  name,
  what,
  line,
  trail,
  brain,
}: {
  name: string
  what: string
  line: string
  trail: (number | null)[]
  brain?: boolean
}) {
  const gid = useId().replace(/:/g, "")
  const now = trail.at(-1)
  const over = now != null && now >= 1
  const { line: d, fill } = shapes(trail)
  return (
    <div
      className={cn(
        "-mx-2 grid grid-cols-[5.75rem_1fr] items-center gap-3 rounded-xl px-2 py-1.5 ring-1 ring-transparent transition-all duration-300",
        over && brain && "bg-ultramarine/[0.07] ring-ultramarine/30",
        over && !brain && "bg-foreground/[0.04] ring-foreground/15",
      )}
    >
      <div className="min-w-0 leading-tight">
        <div
          className={cn(
            "text-tag font-semibold uppercase tracking-[0.08em]",
            over && brain ? "text-ultramarine" : "text-foreground",
          )}
        >
          {name}
        </div>
        <div className="text-tag text-muted-foreground">{what}</div>
        {over && (
          <motion.span
            initial={{ opacity: 0, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ type: "spring", stiffness: 500, damping: 28 }}
            className={cn(
              "mt-1 inline-flex items-center gap-1 whitespace-nowrap rounded-full px-1.5 py-px text-[0.65rem] font-bold uppercase tracking-[0.08em]",
              brain ? "bg-ultramarine text-white" : "bg-foreground text-background",
            )}
          >
            <span className="size-1.5 animate-pulse rounded-full bg-current" />
            {brain ? "past the line" : "bite"}
          </motion.span>
        )}
      </div>
      <div className="relative">
        {over && brain && <div aria-hidden className="absolute inset-0 animate-pulse rounded-lg bg-ultramarine/15 blur-md" />}
        <svg
          viewBox={`0 0 ${N} 20`}
          preserveAspectRatio="none"
          className="relative h-12 w-full overflow-visible"
          role="img"
          aria-label={`${name}: ${what}${over ? ", past the line" : ""}`}
        >
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop
                offset="0%"
                stopColor="currentColor"
                stopOpacity={over ? 0.4 : 0.16}
                className={brain ? "text-ultramarine" : "text-foreground"}
              />
              <stop
                offset="100%"
                stopColor="currentColor"
                stopOpacity="0"
                className={brain ? "text-ultramarine" : "text-foreground"}
              />
            </linearGradient>
          </defs>
          <path d={fill} fill={`url(#${gid})`} />
          <line
            x1="0"
            x2={N}
            y1="10"
            y2="10"
            strokeDasharray="6 4"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
            strokeWidth="2"
            className={cn(brain ? "stroke-ultramarine/50" : "stroke-foreground/50", over && brain && "stroke-ultramarine")}
          />
          <path
            d={d}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
            strokeWidth="2.75"
            className={cn(
              brain ? "stroke-ultramarine" : "stroke-foreground",
              over && "drop-shadow-[0_0_10px_currentColor]",
            )}
          />
        </svg>
        <span
          className={cn(
            "pointer-events-none absolute right-1 top-1/2 -translate-y-1/2 whitespace-nowrap rounded-full bg-background/85 px-1.5 py-px text-[0.65rem] font-semibold uppercase tracking-[0.08em] text-muted-foreground backdrop-blur-sm",
            over && brain && "text-ultramarine",
          )}
        >
          {line}
        </span>
      </div>
    </div>
  )
}

const BY: Record<Decision["by"], string> = { brain: "brain", muscle: "muscle", silence: "silence", keys: "keyboard", camera: "camera", presence: "headband off", head: "head" }

/** The wearer's own pulse, from the headband's optical sensor: the dot beats at the measured rate (not beat-locked). */
function Pulse({ bpm }: { bpm: number | null }) {
  if (!bpm) return null
  return (
    <p className="m-0 flex items-center gap-2 text-tag text-muted-foreground tabular-nums">
      <span className="relative flex size-2.5">
        <span
          className="absolute inline-flex h-full w-full animate-ping rounded-full bg-ultramarine opacity-40"
          style={{ animationDuration: `${(60 / bpm).toFixed(2)}s` }}
        />
        <span
          className="beat relative inline-flex size-2.5 rounded-full bg-ultramarine"
          style={{ animation: `beat ${(60 / bpm).toFixed(2)}s ease-out infinite` }}
        />
      </span>
      Pulse <b className="font-semibold text-foreground">{Math.round(bpm)}</b> bpm
    </p>
  )
}

/**
 * What decided each of Claude's steps, live: the wearer's alpha waves (brain) and jaw (muscle) against their
 * lines, the latest decisions with what made them, and the counts. The bite is labeled muscle on purpose.
 */
export function BrainPanel({ s, compact, className }: { s: BoardState; compact?: boolean; className?: string }) {
  const alpha = useTrail(s.headband.alpha, s)
  const muscle = useTrail(s.headband.muscle, s)
  const shown = s.ledger.slice(compact ? -2 : -5).reverse()
  return (
    <section className={cn("grid gap-2.5", className)} aria-label="What your brain and muscles decided">
      <div className="flex items-center justify-between">
        <h2 className="m-0 text-tag font-semibold uppercase tracking-[0.1em] text-muted-foreground">Live signals</h2>
        <span className="flex items-center gap-1.5 text-tag font-semibold uppercase tracking-[0.1em] text-ultramarine">
          <span className="size-1.5 animate-pulse rounded-full bg-ultramarine" />
          Live
        </span>
      </div>
      <Trace name="Brain" what="alpha · no" line="brake line" trail={alpha} brain />
      <Trace name="Muscle" what="jaw · yes" line="bite line" trail={muscle} />
      <Pulse bpm={s.headband.hr} />
      {shown.length > 0 && (
        <ol className="m-0 grid list-none divide-y divide-foreground/[0.06] p-0 text-label">
          {shown.map((d, i) => (
            <li key={s.counts.decisions - i} className="flex items-baseline gap-2 py-1">
              <span
                className={cn(
                  "flex w-[3.2em] shrink-0 items-center gap-1 text-tag font-semibold uppercase tracking-[0.08em]",
                  d.verdict === "yes" ? "text-muted-foreground" : "text-ultramarine",
                )}
              >
                {d.verdict === "stop" && <span className="size-1.5 animate-pulse rounded-full bg-ultramarine" />}
                {d.verdict}
              </span>
              <span className="min-w-0 flex-1 truncate">{d.what}</span>
              <span className={cn("shrink-0 text-tag font-semibold uppercase tracking-[0.08em]", d.by === "brain" ? "text-ultramarine" : "text-muted-foreground")}>
                {BY[d.by]}
              </span>
            </li>
          ))}
        </ol>
      )}
      <p className="m-0 flex flex-wrap gap-x-4 gap-y-1 text-tag tabular-nums">
        {(
          [
            ["Decisions", s.counts.decisions],
            ["Headband inputs", s.counts.wearer],
            ["Keystrokes", s.counts.keys],
          ] as const
        ).map(([label, v]) => (
          <span key={label} className="text-muted-foreground">
            {label} <b className="font-semibold text-foreground">{v}</b>
          </span>
        ))}
      </p>
    </section>
  )
}
