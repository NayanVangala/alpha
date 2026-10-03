import { useCallback, useEffect, useState } from "react"
import { api } from "@/lib/api"
import { type GazeSource, startGaze } from "@/lib/gaze"

// The webcam brake: while it's on, the camera watches the wearer's eyes (Eyedid SeeSo), and a closure of about a
// second tells the board to brake, the same brake the headband's alpha applies, labeled "camera" in the ledger.
// Off by default, because it uses the camera; the choice is remembered on this computer.
const KEY = "alpha.camera"
export type CameraBrake = { state: "off" | "starting" | "on" | "error"; message: string; toggle: () => void }

const saved = () => {
  try {
    return localStorage.getItem(KEY) === "1"
  } catch {
    return false // private window: start off
  }
}

export function useCameraBrake(): CameraBrake {
  const [want, setWant] = useState(saved)
  const [state, setState] = useState<CameraBrake["state"]>("off")
  const [message, setMessage] = useState("")

  useEffect(() => {
    if (!want) {
      setState("off")
      setMessage("")
      return
    }
    let src: GazeSource | null = null
    let dead = false
    let late = false // gave up waiting: stop it if it does start
    setState("starting")
    setMessage("Starting the camera…")
    const timer = setTimeout(() => {
      late = true
      setState("error")
      setMessage("The eye tracker didn't start in 20 s. It needs the internet for its license check, and camera permission.")
    }, 20000)
    startGaze(() => {}, { onEyesClosed: () => void api.cameraBrake().catch(() => {}) })
      .then((s) => {
        clearTimeout(timer)
        if (dead || late) return s.stop()
        if (s.mode !== "eyedid") {
          s.stop()
          setState("error")
          setMessage("No Eyedid license key on the server: start it with --env-file .env.")
          return
        }
        src = s
        setState("on")
        setMessage("The webcam brake is on: close your eyes for a second and rein stops Claude.")
      })
      .catch((e: Error) => {
        clearTimeout(timer)
        if (dead || late) return
        setState("error")
        setMessage(e.message)
      })
    return () => {
      dead = true
      clearTimeout(timer)
      src?.stop()
    }
  }, [want])

  const toggle = useCallback(
    () =>
      setWant((v) => {
        try {
          localStorage.setItem(KEY, v ? "0" : "1")
        } catch {
          /* private window: it just won't be remembered */
        }
        return !v
      }),
    [],
  )
  return { state, message, toggle }
}
