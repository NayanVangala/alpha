/** The board server's API: one poll for everything on screen, plus the inputs the page sends. */

export type Tile = { label: string; more: boolean; guess: boolean }
export type Out = { id: number; text: string }
export type Device = { name: string; brand: string; supported: boolean; simulated?: boolean; rssi?: number | null }
export type Headband = {
  phase: "locked" | "connecting" | "connected"
  device: Device | null
  error: string | null
  live: boolean
  calibrating: boolean
  calibrate_left: number | null
  /** live alpha waves behind the ears, as a fraction of the brake line (1 = eyes closed); null with no data */
  alpha: number | null
  /** live jaw-muscle level behind the ears, as a fraction of the bite line (1 = biting); null with no data */
  muscle: number | null
  /** the headband's battery, percent (real Muse only) */
  battery: number | null
  /** pulse from the headband's optical sensor, beats per minute */
  hr: number | null
  /** blinks seen since connecting: the page flashes its blink light each time this goes up */
  blink_n: number
}
/** One agent decision: what, yes / no / stop, and what decided it (the keyboard stand-in counts as keys). */
export type Decision = { what: string; verdict: "yes" | "no" | "stop"; by: "brain" | "muscle" | "silence" | "keys" | "camera" | "presence" | "head" }
export type BoardState = {
  screen: "menu" | "options" | "replies" | "confirm" | "agent"
  overlay: "back" | "help" | null
  path: string[]
  tiles: Tile[]
  lit: number | null
  mode: "glance" | "scan"
  next_s: number | null
  scan_s: number | null
  finding: boolean
  heard: string | null
  thinking: boolean
  plain: string | null
  sentence: string | null
  action: "speak" | "text" | "call" | null
  to: string | null
  can_back: boolean
  left_s: number | null
  said: Out | null
  alert: Out | null
  notice: Out | null
  /** what the board says aloud about Claude: each question, and when it's stopped */
  narrate: Out | null
  took: { id: number; n: number; glances: number } | null
  /** a question from the coding agent (Claude Code) while screen is "agent" */
  agent: { kind: "permission" | "next"; title: string; detail: string } | null
  /** the wearer closed their eyes: the coding agent stops before its next step */
  brake: boolean
  /** autopilot: seconds until rein does its guess, and the whole countdown */
  auto_s: number | null
  auto_total: number | null
  /** mind reader: seconds until the guessed sentence on screen says itself */
  talk_s: number | null
  talk_total: number
  /** rein is driving Claude Code: the floating window is open and a headband is connected */
  claude_code: boolean
  headband: Headband
  /** the latest agent decisions, oldest first */
  ledger: Decision[]
  /** decisions made; inputs from the headband; inputs from the keyboard */
  counts: { decisions: number; wearer: number; keys: number }
}
export type Gesture = "clench" | "long_clench" | "double_blink" | "glance_left" | "glance_right" | "eyes_closed"

const post = (url: string, body?: unknown) =>
  fetch(url, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

async function boardOrNull(r: Response) {
  return r.ok ? ((await r.json()) as BoardState) : null
}

export const api = {
  board: async () => (await (await fetch("/api/board")).json()) as BoardState,
  input: async (kind: Gesture, ago = 0) => boardOrNull(await post("/api/input", { kind, ago })),
  /** the webcam saw the eyes close: the board brakes, labeled "camera" */
  cameraBrake: () => post("/api/input", { kind: "eyes_closed", by: "camera" }),
  heard: async (text: string) => boardOrNull(await post("/api/heard", { text })),
  scan: async () => (await (await post("/api/scan")).json()) as { devices?: Device[]; error?: string | null },
  connect: (name: string) => post("/api/connect", { name }),
  disconnect: () => post("/api/disconnect"),
  calibrate: () => post("/api/calibrate"),
  /** simulator only: shut its eyes so its alpha swells (the E key) */
  simEyes: (closed: boolean) => post("/api/sim/eyes", { closed }),
  /** the floating window says it's open, so rein drives Claude Code (repeat every 2 s) */
  arm: () => post("/api/agent/arm"),
  nerd: async () => (await (await fetch("/api/nerd")).json()) as Nerd,
}

/** /api/nerd: a live snapshot of the headband for Stats for nerds, or {live: false}. */
export type Quality = {
  overall: "strong" | "ok" | "weak" | "lost"
  brake_ready: boolean
  notes: string[]
  sensors: { name: string; where: string; uv: number; status: "good" | "noisy" | "bad" | "off" }[]
}
export type Hist = {
  step_s: number
  alpha: (number | null)[]
  spec: number[][]
  bands: Record<string, number>[]
  contact: number[][]
  fs: (number | null)[]
  hr: (number | null)[]
  tilt: (number | null)[]
}
export type Nerd = {
  quality: Quality
  hist: Hist
  ppg: number[]
  gyro: number[][]
  live: boolean
  fs: number
  age_ms: number
  channels: string[]
  raw: number[][]
  freqs: number[]
  psd: number[]
  bands: Record<string, number[]>
  muscle: [number, number][]
  window_s: number
  threshold: number
  events: [number, string][]
  hr: number | null
  blink_rate: number | null
  tilt: number | null
}
