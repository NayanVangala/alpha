import { motion, useReducedMotion } from "motion/react"
import { cn } from "@/lib/utils"

const EASE = [0.625, 0.05, 0, 1] as const

/** Letters rise in one after another. Give it a `key` of the text so it replays only when the text changes. */
export function RollText({ parts, className }: { parts: [string, string?][]; className?: string }) {
  const still = useReducedMotion()
  const label = parts.map(([t]) => t).join("")
  if (still) {
    return (
      <p className={className}>
        {parts.map(([t, cls], i) => <span key={i} className={cls}>{t}</span>)}
      </p>
    )
  }
  let n = 0
  return (
    <p className={className} aria-label={label}>
      {parts.map(([text, cls], p) => (
        <span key={p} className={cls} aria-hidden>
          {text.split(/(\s+)/).map((word, w) =>
            /^\s*$/.test(word) ? (
              word
            ) : (
              <span key={w} className="inline-block whitespace-nowrap">
                {[...word].map((ch, c) => (
                  <motion.span
                    key={c}
                    className={cn("inline-block")}
                    initial={{ y: "0.55em", opacity: 0, filter: "blur(0.09em)" }}
                    animate={{ y: 0, opacity: 1, filter: "blur(0em)" }}
                    transition={{ duration: 0.6, ease: EASE, delay: n++ * 0.014 }}
                  >
                    {ch}
                  </motion.span>
                ))}
              </span>
            ),
          )}
        </span>
      ))}
    </p>
  )
}
