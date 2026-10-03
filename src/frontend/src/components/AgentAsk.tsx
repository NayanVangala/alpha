import { SquareTerminal } from "lucide-react"
import { motion } from "motion/react"
import { AlphaMeter } from "@/components/Mind"
import type { BoardState } from "@/lib/api"
import { cn } from "@/lib/utils"

/** What the coding agent wants to do, or what it just did, above the cards that answer it. */
export function AgentAsk({ agent, alpha }: { agent: NonNullable<BoardState["agent"]>; alpha?: number | null }) {
  const permission = agent.kind === "permission"
  return (
    <motion.div
      key={agent.detail}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.625, 0.05, 0, 1] }}
      className="mb-[18px] grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-8 gap-y-2.5 rounded-lg bg-card px-[clamp(20px,2.4vw,32px)] py-[18px]"
    >
      <div className="grid gap-2.5">
      <p className="m-0 flex items-center gap-2 text-tag font-semibold uppercase tracking-[0.08em] text-muted-foreground">
        <SquareTerminal className="size-4 text-ultramarine" aria-hidden />
        Claude Code · {agent.title}
      </p>
      <p
        className={cn(
          "m-0 [overflow-wrap:anywhere]",
          permission
            ? "font-mono text-title font-medium leading-[1.15] tracking-[-0.02em] text-foreground"
            : "line-clamp-3 text-body text-foreground",
        )}
      >
        {agent.detail || "Done."}
      </p>
      </div>
      <AlphaMeter level={alpha} className="w-[clamp(180px,22vw,300px)]" />
    </motion.div>
  )
}
