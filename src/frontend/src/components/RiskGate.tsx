import { EyeOff, ShieldAlert } from "lucide-react"
import { motion } from "motion/react"
import { useEffect, useRef, useState } from "react"
import type { BoardState } from "@/lib/api"
import { cn } from "@/lib/utils"

const HOLD_S = 1 // the board's GATE_BITE_S: how long the bite has to be held
const LIME = "#9bff60"

/**
 * A risky step, full screen and no cards: what Claude wants to do, and the two ways to answer. A bite held for a second
 * approves, closed eyes veto, silence does nothing. Fills the floating window too (`compact`).
 */
export function RiskGate({ s, compact }: { s: BoardState; compact?: boolean }) {
  const agent = s.agent!
  const muscle = s.headband.muscle ?? 0
  const alpha = Math.min(1, s.headband.alpha ?? 0)
  const since = useRef<number | null>(null)
  const [held, setHeld] = useState(0) // 0..1 of the hold, from the live jaw level (the board decides; this only shows it)
  useEffect(() => {
    if (muscle >= 1) {
      since.current ??= performance.now()
      setHeld(Math.min(1, (performance.now() - since.current) / (HOLD_S * 1000)))
    } else {
      since.current = null
      setHeld(0)
    }
  }, [s, muscle])

  return (
    <motion.div
      role="alertdialog"
      aria-label={`${agent.title} ${agent.detail}. Bite down and hold for a second to approve, or close your eyes to veto.`}
      initial={{ opacity: 0, scale: 1.04 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.45, ease: [0.625, 0.05, 0, 1] }}
      className={cn(
        "relative flex flex-col overflow-hidden bg-[#06060c] text-white",
        compact ? "flex-1 rounded-lg p-4" : "fixed inset-0 z-[15] px-[var(--pad-x)] py-10",
      )}
    >
      {/* ambient glow: a faint lime wash behind the risky step, ultramarine pooling at the bottom */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(90%_65%_at_50%_28%,rgba(155,255,96,0.09),transparent_70%),radial-gradient(120%_90%_at_50%_112%,rgba(0,4,246,0.28),transparent_60%)]"
      />
      <div className={cn("relative z-10 flex flex-1 flex-col justify-between", compact ? "gap-6" : "gap-8")}>
        <p className="m-0 flex items-center justify-between gap-3 text-tag font-semibold uppercase tracking-[0.08em] text-white/70">
          <span className="flex items-center gap-2.5" style={{ color: LIME }}>
            <motion.span
              aria-hidden
              animate={{ scale: [1, 1.18, 1], opacity: [1, 0.7, 1] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
            >
              <ShieldAlert className="size-4" aria-hidden />
            </motion.span>
            Not on the safe list · this one needs you
          </span>
          {!compact && <span>Claude Code</span>}
        </p>

        <div className="grid gap-3">
          <p className={cn("m-0 text-white/70", compact ? "text-label" : "text-title")}>{agent.title}</p>
          <p
            className={cn(
              "m-0 font-mono font-medium tracking-[-0.03em] [overflow-wrap:anywhere]",
              compact ? "line-clamp-3 text-title leading-[1.1]" : "line-clamp-6 text-[clamp(1.8rem,5.2vw,5rem)] leading-[1.08]",
            )}
          >
            {agent.detail}
          </p>
        </div>

        <div className={cn("grid gap-4", !compact && "grid-cols-2 max-[800px]:grid-cols-1")}>
          <div
            className={cn(
              "grid gap-3 rounded-lg border-2 p-5 transition-shadow duration-200",
              held > 0 && "shadow-[0_0_60px_-12px_rgba(155,255,96,0.65)]",
            )}
            style={{ borderColor: LIME }}
          >
            <p
              className={cn("m-0 font-medium tracking-[-0.04em] [text-shadow:0_0_28px_rgba(155,255,96,0.55)]", compact ? "text-title" : "text-headline leading-none")}
              style={{ color: LIME }}
            >
              Bite down
            </p>
            <p className="m-0 text-body text-white/80">and hold for a full second to approve.</p>
            <div className="relative h-3 overflow-hidden rounded-xs bg-white/15">
              <div
                className="absolute inset-y-0 left-0 rounded-xs"
                style={{ width: `${held * 100}%`, background: LIME, boxShadow: "0 0 14px rgba(155,255,96,0.9)", transition: "width 0.1s linear" }}
              />
            </div>
            <p className="m-0 h-5 text-label text-white/60">
              {held >= 1 ? (
                <b className="font-semibold" style={{ color: LIME }}>Held. Approving…</b>
              ) : muscle >= 1 ? (
                "Keep holding…"
              ) : (
                "Jaw relaxed"
              )}
            </p>
          </div>
          <div
            className={cn(
              "grid gap-3 rounded-lg border-2 p-5 transition-shadow duration-200",
              alpha >= 1 ? "border-white shadow-[0_0_50px_-12px_rgba(255,255,255,0.5)]" : "border-white/40",
            )}
          >
            <p className={cn("m-0 flex items-center gap-3 font-medium tracking-[-0.04em]", compact ? "text-title" : "text-headline leading-none")}>
              <EyeOff className="size-[0.8em]" aria-hidden />
              Close your eyes
            </p>
            <p className="m-0 text-body text-white/80">to veto. Claude stops and asks what's next.</p>
            <div className="relative h-3 overflow-hidden rounded-xs bg-white/15">
              <div className="absolute inset-y-0 left-0 rounded-xs bg-white" style={{ width: `${alpha * 100}%`, transition: "width 0.2s linear" }} />
            </div>
            <p className="m-0 h-5 text-label text-white/60">{alpha >= 1 ? "Eyes closed: vetoing" : "Eyes open"}</p>
          </div>
        </div>
        <p className="m-0 text-label text-white/50">Doing nothing does nothing: this waits for you.</p>
      </div>
    </motion.div>
  )
}
