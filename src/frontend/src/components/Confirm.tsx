import { RollText } from "@/components/RollText"
import type { BoardState } from "@/lib/api"
import { cn } from "@/lib/utils"

const Do = ({ children }: { children: string }) => <b className="font-semibold text-ultramarine">{children}</b>

/** The sentence and what will happen to it. Nothing is said or sent until one more bite. */
export function Confirm({ s }: { s: BoardState }) {
  const who = s.to ?? ""
  const text = (s.finding ? s.plain : s.sentence) ?? ""
  const doing = s.finding
    ? "Finding ways to say it…"
    : s.action === "text"
      ? `Text to ${who}`
      : s.action === "call"
        ? `Call ${who}`
        : "Say out loud"
  return (
    <section className="flex flex-1 flex-col justify-center gap-7 rounded-lg bg-card p-[clamp(24px,4vw,64px)]">
      <p className={cn("m-0 text-body font-semibold text-ultramarine", s.finding && "shimmer")}>{doing}</p>
      <RollText
        key={text}
        parts={[[text]]}
        className={cn("m-0 text-display font-medium leading-none tracking-[-0.05em]", s.finding && "text-muted-foreground")}
      />
      <p className="m-0 text-body text-muted-foreground">
        {s.finding ? (
          <>
            <Do>Bite down</Do> to use this one now.
          </>
        ) : (
          <>
            <Do>Bite down</Do>{" "}
            {s.action === "text" ? `to send it to ${who}.` : s.action === "call" ? `to call ${who}.` : "to say it."}{" "}
            <Do>Close your eyes</Do> to go back.
          </>
        )}
      </p>
    </section>
  )
}
