import { useEffect, useState } from "react"
import { api, type BoardState } from "@/lib/api"

/** The board's state, polled every 120 ms so a move shows within a frame or two. */
export function useBoard() {
  const [s, setS] = useState<BoardState | null>(null)
  const [lost, setLost] = useState(false)
  useEffect(() => {
    let alive = true
    const tick = () =>
      api.board().then(
        (next) => {
          if (alive) {
            setS(next)
            setLost(false)
          }
        },
        () => alive && setLost(true),
      )
    tick()
    const id = setInterval(tick, 120)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])
  return { s, setS, lost }
}
