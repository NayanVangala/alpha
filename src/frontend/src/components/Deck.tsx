import { Sparkles } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { BorderBeam } from "@/components/BorderBeam"
import { Autopilot, auraOpacity } from "@/components/Mind"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import type { BoardState } from "@/lib/api"
import { cn } from "@/lib/utils"

const EASE = [0.625, 0.05, 0, 1] as const

/**
 * The mind reader: one guess at a time, never a deck. Alpha shows what it thinks the wearer wants; closing the
 * eyes says "no, guess again", a bite says yes, and a guessed sentence says itself when its ring runs out.
 */
export function Deck({ s }: { s: BoardState }) {
  const n = s.tiles.length
  if (!n) return null
  const lit = Math.min(s.lit ?? 0, n - 1)
  const tile = s.tiles[lit]
  const agent = s.screen === "agent"
  const sentence = s.screen === "options" || s.screen === "replies" || (tile.guess && !tile.more)
  const kicker = agent
    ? tile.guess ? "Alpha’s guess" : "Or"
    : tile.more ? "Is it about" : tile.guess || sentence ? "Alpha thinks you want to say" : "Do you want"
  const key = `${s.screen}|${s.path.join(">")}|${s.heard ?? ""}|${s.agent?.detail ?? ""}|${lit}|${tile.label}`

  return (
    <div className="flex flex-1 flex-col items-center gap-[18px]">
      <div className="relative flex w-full max-w-[1100px] flex-1 overflow-hidden rounded-lg bg-ultramarine text-white">
        {/* the pixel aura swells with the wearer's live alpha waves */}
        <div className="absolute inset-0 transition-opacity duration-500" style={{ opacity: auraOpacity(s.headband.alpha) }}>
          <FlickeringGrid
            className="absolute inset-0 [mask-image:radial-gradient(90%_80%_at_50%_45%,#000_0%,transparent_75%)]"
            squareSize={4}
            gridGap={6}
            color="#ffffff"
            maxOpacity={0.3}
            flickerChance={0.12}
          />
        </div>
        <BorderBeam />
        <AnimatePresence initial={false} mode="popLayout">
          <motion.div
            key={key}
            initial={{ opacity: 0, filter: "blur(18px)", scale: 0.97 }}
            animate={{ opacity: 1, filter: "blur(0px)", scale: 1 }}
            exit={{ opacity: 0, filter: "blur(18px)", scale: 1.02 }}
            transition={{ duration: 0.5, ease: EASE }}
            className="relative z-10 flex w-full flex-col justify-between gap-6 p-[clamp(28px,4vw,64px)]"
            aria-live="polite"
          >
            <div className="flex items-center justify-between gap-3 text-tag font-semibold uppercase tracking-[0.08em] text-white/80">
              <span className="flex items-center gap-2">
                {(tile.guess || sentence) && <Sparkles className="size-4" aria-hidden />}
                {kicker}
              </span>
              <span className="tabular-nums">
                guess {lit + 1} of {n}
              </span>
            </div>
            <p
              className={cn(
                "m-0 font-medium tracking-[-0.05em] [overflow-wrap:anywhere]",
                tile.label.length > 24 ? "text-headline leading-[1.05]" : "text-display leading-none",
              )}
            >
              {sentence && !agent ? `“${tile.label}”` : tile.label}
              {tile.more ? "…" : ""}
            </p>
            {s.auto_s != null && s.auto_total ? (
              <Autopilot left={s.auto_s} total={s.auto_total} className="text-body text-white" />
            ) : s.talk_s != null ? (
              <Autopilot left={s.talk_s} total={s.talk_total} verb="Saying it" then="close your eyes to guess again" className="text-body text-white" />
            ) : (
              <p className="m-0 text-body text-white/80">
                <b className="font-semibold text-white">Bite down</b>: {tile.more ? "yes, that" : "yes"} ·{" "}
                <b className="font-semibold text-white">close your eyes</b>: guess again
              </p>
            )}
          </motion.div>
        </AnimatePresence>
        {s.next_s != null && s.scan_s ? (
          <div
            className="absolute inset-x-0 bottom-0 z-20 h-2 origin-left bg-white/85"
            style={{ transform: `scaleX(${Math.max(0, Math.min(1, s.next_s / s.scan_s))})` }}
          />
        ) : null}
      </div>
      <div className="flex gap-2.5" aria-hidden>
        {s.tiles.map((t, i) => (
          <span
            key={i}
            className={cn("relative size-2 rounded-xs", i === lit ? "bg-ultramarine" : t.guess ? "shadow-[inset_0_0_0_1.5px_#0004f6]" : "bg-foreground/20")}
          >
            {i === lit && (
              <motion.span layoutId="lit-dot" className="absolute -inset-1 rounded-xs border-[1.5px] border-ultramarine" transition={{ duration: 0.3, ease: EASE }} />
            )}
          </span>
        ))}
      </div>
    </div>
  )
}
