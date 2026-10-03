import { useEffect, useRef } from "react"
import type { Gesture } from "@/lib/api"

const LONG_MS = 2500 // hold Space this long for help, like a held bite
const EYES_MS = 1500 // hold E this long for eyes closed, the brake

type Keys = {
  enabled: boolean
  send: (kind: Gesture, ago?: number) => void
  onListen: () => void
  onNerd: () => void
  onEyes?: (closed: boolean) => void // E held down or let go: the simulator shuts or opens its eyes
}

/** The keyboard stand-in: the same events as the headband, so the board can't tell them apart. */
export function useKeys(keys: Keys) {
  const latest = useRef(keys)
  latest.current = keys
  useEffect(() => {
    let downAt: number | null = null
    let longSent = false
    let longTimer: ReturnType<typeof setTimeout> | undefined
    let eyesTimer: ReturnType<typeof setTimeout> | undefined
    const down = (e: KeyboardEvent) => {
      const k = latest.current
      if (e.code === "KeyN" && !e.repeat) return k.onNerd()
      if (!k.enabled) return
      if (e.code === "Space") {
        e.preventDefault()
        if (e.repeat || downAt !== null) return
        downAt = performance.now()
        longSent = false
        longTimer = setTimeout(() => {
          longSent = true
          latest.current.send("long_clench")
        }, LONG_MS)
      } else if (e.repeat) {
        return
      } else if (e.code === "KeyB") {
        k.send("double_blink")
      } else if (e.code === "ArrowLeft" || e.code === "ArrowRight") {
        e.preventDefault()
        k.send(e.code === "ArrowLeft" ? "glance_left" : "glance_right")
      } else if (e.code === "KeyL") {
        k.onListen()
      } else if (e.code === "KeyE" && eyesTimer === undefined) {
        k.onEyes?.(true)
        eyesTimer = setTimeout(() => latest.current.send("eyes_closed"), EYES_MS)
      }
    }
    const up = (e: KeyboardEvent) => {
      if (e.code === "KeyE" && eyesTimer !== undefined) {
        clearTimeout(eyesTimer) // opened them too soon: not a closure
        eyesTimer = undefined
        latest.current.onEyes?.(false)
      }
      if (e.code !== "Space" || downAt === null) return
      clearTimeout(longTimer)
      // the bite began at key-down: the board picks what was lit then
      if (!longSent) latest.current.send("clench", Math.min(5, (performance.now() - downAt) / 1000))
      downAt = null
    }
    addEventListener("keydown", down)
    addEventListener("keyup", up)
    return () => {
      removeEventListener("keydown", down)
      removeEventListener("keyup", up)
      clearTimeout(longTimer)
      clearTimeout(eyesTimer)
    }
  }, [])
}
