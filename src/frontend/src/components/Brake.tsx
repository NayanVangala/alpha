import { EyeOff } from "lucide-react"
import { motion } from "motion/react"
import { cn } from "@/lib/utils"

/** Shown while the wearer's closed eyes hold the coding agent back. */
export function Brake({ className, compact }: { className?: string; compact?: boolean }) {
  return (
    <motion.p
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("m-0 flex items-center gap-2 rounded-sm bg-ultramarine px-4 py-2 text-label text-white", className)}
      role="status"
    >
      <EyeOff className="size-4 shrink-0" aria-hidden />
      <span>
        <b className="font-semibold">Brake on.</b> Claude stops before its next step{compact ? "." : " and asks what's next."}
      </span>
    </motion.p>
  )
}
