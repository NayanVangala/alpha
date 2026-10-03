import { useEffect, useRef, useState } from "react"
import { onSpeaking } from "@/lib/speech"

type Rec = {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: (e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void
  onerror: (e: { error: string }) => void
  onend: (() => void) | null
  start: () => void
  abort: () => void
}
const w = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec }
const Recognition = w.SpeechRecognition ?? w.webkitSpeechRecognition

/**
 * Conversation mode: Chrome transcribes the room and each finished sentence goes to the board,
 * which offers replies. The microphone pauses while the board talks, so it never answers itself.
 */
export function useListening(enabled: boolean, onHeard: (text: string) => void, onBlocked: () => void) {
  const [on, setOn] = useState(false)
  const [interim, setInterim] = useState("")
  const rec = useRef<Rec | null>(null)
  const speaking = useRef(false)
  const wanted = useRef(false)
  const handlers = useRef({ onHeard, onBlocked })
  handlers.current = { onHeard, onBlocked }

  const stop = () => {
    if (rec.current) {
      rec.current.onend = null
      rec.current.abort()
      rec.current = null
    }
    setInterim("")
  }
  const start = () => {
    if (!Recognition || rec.current || !wanted.current || speaking.current) return
    const r = new Recognition()
    r.continuous = true
    r.interimResults = true
    r.lang = "en-US"
    r.onresult = (e) => {
      let heard = ""
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const result = e.results[i]
        const text = result[0].transcript.trim()
        if (result.isFinal) {
          if (text.length > 1 && !speaking.current) handlers.current.onHeard(text)
        } else heard += result[0].transcript
      }
      setInterim(heard)
    }
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setOn(false)
        handlers.current.onBlocked()
      }
    }
    r.onend = () => {
      rec.current = null
      start() // Chrome stops after a pause; keep listening
    }
    rec.current = r
    r.start()
  }

  useEffect(() => {
    onSpeaking((talking) => {
      speaking.current = talking
      if (talking) stop()
      else setTimeout(start, 400) // let the room's echo die down
    })
  }, [])

  useEffect(() => {
    if (!enabled) setOn(false)
    wanted.current = on && enabled
    if (wanted.current) start()
    else stop()
  }, [on, enabled])

  return { supported: !!Recognition, listening: on && enabled, interim, toggle: () => setOn((v) => !v) }
}
