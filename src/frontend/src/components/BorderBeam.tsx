import { motion, useReducedMotion } from "motion/react"

/** A streak of light that keeps running round the edge of its (relative, rounded) parent. */
export function BorderBeam({ width = 2, duration = 5, color = "#ffffff" }: { width?: number; duration?: number; color?: string }) {
  const still = useReducedMotion()
  return (
    <div aria-hidden className="beam-frame" style={{ padding: width }}>
      <motion.div
        className="absolute left-1/2 top-1/2 aspect-square w-[200%] -translate-x-1/2 -translate-y-1/2"
        style={{ background: `conic-gradient(from 0deg, transparent 0 70%, ${color} 92%, transparent 100%)` }}
        animate={still ? undefined : { rotate: 360 }}
        transition={{ repeat: Infinity, ease: "linear", duration }}
      />
    </div>
  )
}
