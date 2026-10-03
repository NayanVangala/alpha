/** The board's voice: ElevenLabs through the server, the browser's own voice as the fallback. */
import type { Out } from "./api"

let unlocked = false
let speakingTimer: ReturnType<typeof setTimeout> | undefined
let listener: (speaking: boolean) => void = () => {}

/** Conversation mode pauses the microphone while the board talks, so it never answers itself. */
export function onSpeaking(f: (speaking: boolean) => void) {
  listener = f
}

/** Browsers only allow sound after a click: call this from one. */
export function unlock() {
  unlocked = true
  say(" ")
}

function start() {
  listener(true)
  clearTimeout(speakingTimer)
  speakingTimer = setTimeout(end, 15000) // in case no end event ever comes
}

function end() {
  clearTimeout(speakingTimer)
  listener(false)
}

function say(text: string, urgent = false, done?: () => void) {
  if (!unlocked || !("speechSynthesis" in window)) return done?.()
  if (urgent) speechSynthesis.cancel()
  const u = new SpeechSynthesisUtterance(text)
  u.rate = urgent ? 1 : 0.95
  if (done) u.onend = u.onerror = done
  speechSynthesis.speak(u)
}

export function play(out: Out, urgent = false) {
  if (!unlocked) return
  const audio = new Audio(`/api/speech/${out.id}`)
  let settled = false
  start()
  const fallback = () => {
    if (settled) return
    settled = true
    audio.removeAttribute("src")
    say(out.text, urgent, end)
  }
  audio.onplaying = () => {
    settled = true
  }
  audio.onended = end
  audio.onerror = fallback // 204: no ElevenLabs key, or it's failing
  audio.play().catch(fallback)
  setTimeout(fallback, 3000) // too slow: don't leave the room waiting
}

const NARRATE = "alpha.narrate"
/** Narration: the board reads each of Claude's questions aloud, and says when it's stopped. On unless the wearer turns it off. */
export function isNarrating() {
  try {
    return localStorage.getItem(NARRATE) !== "0"
  } catch {
    return true
  }
}
export function setNarrating(on: boolean) {
  try {
    localStorage.setItem(NARRATE, on ? "1" : "0")
  } catch {
    /* private window: it just won't be remembered */
  }
  if (!on && "speechSynthesis" in window) speechSynthesis.cancel()
}
