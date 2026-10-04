// The parts of an accurate gaze interface that aren't the tracker: smoothing that lets fast jumps through, tiles that
// don't flicker, and a check that the calibration still holds. All pure, so they can be tested without a camera.

/** One Euro filter (Casiez et al.): heavy smoothing when the signal is slow, little when it moves fast. Feed it
 * coordinates normalised to the screen (0 to 1): minCutoff 1 Hz and beta 10 are tuned for that scale. */
class LowPass {
  y: number | null = null
  filter(v: number, a: number) {
    this.y = this.y === null ? v : a * v + (1 - a) * this.y
    return this.y
  }
}
const smoothing = (cutoff: number, dt: number) => 1 / (1 + 1 / (2 * Math.PI * cutoff) / dt)

export class OneEuro {
  private x = new LowPass()
  private dx = new LowPass()
  private last: { v: number; t: number } | null = null
  private minCutoff: number
  private beta: number
  private dCutoff: number
  constructor(minCutoff = 1.0, beta = 10, dCutoff = 1.0) {
    this.minCutoff = minCutoff
    this.beta = beta
    this.dCutoff = dCutoff
  }
  /** `t` in seconds. */
  filter(v: number, t: number) {
    if (!this.last || t <= this.last.t) {
      this.last = { v, t }
      return this.x.filter(v, 1)
    }
    const dt = t - this.last.t
    const speed = this.dx.filter((v - this.last.v) / dt, smoothing(this.dCutoff, dt))
    this.last = { v, t }
    return this.x.filter(v, smoothing(this.minCutoff + this.beta * Math.abs(speed), dt))
  }
}

export type Rect = { left: number; top: number; right: number; bottom: number }
const inside = (r: Rect, x: number, y: number, shrink = 0) => {
  const dx = (r.right - r.left) * shrink, dy = (r.bottom - r.top) * shrink
  return x >= r.left + dx && x <= r.right - dx && y >= r.top + dy && y <= r.bottom - dy
}

/** Which tile is lit. The lit tile holds until the gaze truly leaves its box; a new tile lights after the
 * gaze stays inside it for `holdMs`. Changing your mind restarts the timer. `aiming` is the tile the gaze is
 * currently dwelling on but hasn't lit yet, so the UI can show progress. */
export class TileTracker {
  current = -1
  private candidate = -1
  private since = 0
  private shrink: number
  private holdMs: number
  constructor(shrink = 0.05, holdMs = 300) {
    this.shrink = shrink
    this.holdMs = holdMs
  }
  get aiming() {
    return this.candidate
  }
  update(rects: Rect[], x: number, y: number, nowMs: number) {
    if (this.current >= 0 && rects[this.current] && inside(rects[this.current], x, y)) {
      this.candidate = -1
      return this.current
    }
    const j = rects.findIndex((r) => inside(r, x, y, this.shrink))
    if (j < 0 || j === this.current) {
      this.candidate = -1
    } else if (this.candidate !== j) {
      this.candidate = j
      this.since = nowMs
    } else if (nowMs - this.since >= this.holdMs) {
      this.current = j
      this.candidate = -1
    }
    return this.current
  }
}

/** The startup check: a dot is shown at `target`; calibration passes only when the median gaze lands within half a
 * tile of it. Fewer than 10 samples is an automatic fail. */
export function calibrationHolds(samples: { x: number; y: number }[], target: { x: number; y: number }, tile: number) {
  if (samples.length < 10) return { pass: false, median: NaN, n: samples.length }
  const d = samples.map((s) => Math.hypot(s.x - target.x, s.y - target.y)).sort((a, b) => a - b)
  const median = d[Math.floor(d.length / 2)]
  return { pass: median <= tile / 2, median, n: samples.length }
}

/** One camera owner: only one rein window in this browser may run the eye tracker at a time (Web Locks). Returns a release function. */
export async function claimCamera(): Promise<() => void> {
  if (!("locks" in navigator)) return () => {}
  return new Promise((resolve, reject) => {
    navigator.locks.request("rein-camera", { ifAvailable: true }, (lock) =>
      lock ? new Promise<void>((release) => resolve(release)) : (reject(new Error("Another rein window already has the camera: close it, or turn its camera off.")), undefined),
    )
  })
}

/** The last rung of the fallback ladder: auto-scan. One tile is lit at a time and the light moves on every `stepMs`;
 * a bite (Space on the test page) takes the lit one. Needs no tracker, no pointer and no calibration. */
export class Scanner {
  current = 0
  private since = -1
  private n: number
  private stepMs: number
  constructor(n: number, stepMs = 1500) {
    this.n = n
    this.stepMs = stepMs
  }
  update(nowMs: number) {
    if (this.since < 0) this.since = nowMs
    else if (nowMs - this.since >= this.stepMs) {
      this.current = (this.current + 1) % this.n
      this.since = nowMs
    }
    return this.current
  }
  /** After a pick the sweep starts over from the first tile. */
  restart(nowMs: number) {
    this.current = 0
    this.since = nowMs
  }
}

/** Says when the tracker has given no usable reading for `lostMs`: the cue to step down the ladder. */
export class LossWatch {
  private lastOk: number
  private lostMs: number
  constructor(nowMs: number, lostMs = 5000) {
    this.lastOk = nowMs
    this.lostMs = lostMs
  }
  seen(ok: boolean, nowMs: number) {
    if (ok) this.lastOk = nowMs
  }
  lost(nowMs: number) {
    return nowMs - this.lastOk >= this.lostMs
  }
}
