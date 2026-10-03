import { useEffect, useRef } from "react"
import { toast } from "sonner"
import type { BoardState, Out } from "@/lib/api"
import { play } from "@/lib/speech"

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`

/** Voice and toast each new thing the board said, sent or raised, once. Nothing old replays on load. */
export function useOutputs(s: BoardState | null) {
  const seen = useRef<{ said: number; alert: number; notice: number } | null>(null)
  useEffect(() => {
    if (!s) return
    if (!seen.current) {
      seen.current = { said: s.said?.id ?? 0, alert: s.alert?.id ?? 0, notice: s.notice?.id ?? 0 }
      return
    }
    const took = (out: Out) => {
      if (!s.took || s.took.id !== out.id) return ""
      return ` in ${plural(s.took.n, "bite")}${s.took.glances ? ` + ${plural(s.took.glances, "glance")}` : ""}`
    }
    const was = seen.current
    if (s.alert && s.alert.id > was.alert) {
      was.alert = s.alert.id
      play(s.alert, true)
      toast(`Help requested: “${s.alert.text}”`, { duration: 8000, className: "alpha-toast alpha-toast--alert" })
    }
    if (s.said && s.said.id > was.said) {
      was.said = s.said.id
      play(s.said)
      toast(`Said${took(s.said)}: “${s.said.text}”`)
    }
    if (s.notice && s.notice.id > was.notice) {
      was.notice = s.notice.id
      toast(s.notice.text + took(s.notice))
    }
  }, [s])
}
