import { EyeOff } from "lucide-react"
import { motion } from "motion/react"
import { cn } from "@/lib/utils"

/** Shown while the wearer's closed eyes hold the coding agent back. */
export function Brake({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <motion.p
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        "m-0 flex items-center gap-2.5 rounded-md bg-ultramarine px-5 py-3 text-label font-medium text-white shadow-[0_14px_36px_-14px_rgba(0,4,246,0.8)]",
        className,
      )}
      role="status"
    >
      <motion.span
        aria-hidden
        className="size-2 shrink-0 rounded-full bg-white"
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
      />
      <EyeOff className="size-4 shrink-0" aria-hidden />
      <span>
        <b className="font-semibold">Brake on.</b> Claude stops before its next step{compact ? "." : " and asks what's next."}
      </span>
    </motion.p>
  )
}
