import { AnimatePresence, motion } from "motion/react"
import { Progress } from "@/components/ui/progress"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import type { BoardState } from "@/lib/api"

const EASE = [0.625, 0.05, 0, 1] as const
const BACK_S = 3 // the board's "Go back?" window

/** "Go back?" (a bite confirms, doing nothing stays) and the help countdown (closing the eyes cancels). */
export function Overlays({ s }: { s: BoardState }) {
  const left = s.left_s ?? 0
  return (
    <AnimatePresence>
      {s.overlay === "back" && (
        <motion.div
          key="back"
          className="fixed inset-0 z-20 grid place-items-center bg-background/85 px-[var(--pad-x)] backdrop-blur-sm"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.div
            role="alertdialog"
            aria-labelledby="backTitle"
            className="grid w-[min(720px,100%)] gap-5 rounded-lg bg-card p-[clamp(28px,4vw,56px)] shadow-[0_24px_60px_-30px_rgba(0,0,0,0.35)]"
            initial={{ y: 16, scale: 0.98 }}
            animate={{ y: 0, scale: 1 }}
            transition={{ duration: 0.3, ease: EASE }}
          >
            <h2 id="backTitle" className="m-0 text-headline font-medium leading-none tracking-[-0.05em]">
              Go back?
            </h2>
            <p className="m-0 text-body text-muted-foreground">
              <b className="font-semibold text-ultramarine">Bite down</b> to go back. Do nothing to stay.
            </p>
            <Progress value={(left / BACK_S) * 100} className="h-2.5 rounded-xs bg-border" />
          </motion.div>
        </motion.div>
      )}
      {s.overlay === "help" && (
        <motion.div
          key="help"
          className="fixed inset-0 z-20 grid place-items-center overflow-hidden bg-ultramarine text-white"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <FlickeringGrid className="absolute inset-0" squareSize={5} gridGap={7} color="#ffffff" maxOpacity={0.16} flickerChance={0.2} />
          <div role="alertdialog" aria-labelledby="helpTitle" className="relative grid gap-4 text-center">
            <motion.p
              key={Math.ceil(left)}
              initial={{ scale: 1.14 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.45, ease: EASE }}
              className="m-0 text-countdown font-medium leading-[0.85] tracking-[-0.06em] tabular-nums"
            >
              {Math.ceil(left)}
            </motion.p>
            <h2 id="helpTitle" className="m-0 text-headline font-medium tracking-[-0.04em]">
              Calling for help
            </h2>
            <p className="m-0 text-body text-white/90">Close your eyes to cancel.</p>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
