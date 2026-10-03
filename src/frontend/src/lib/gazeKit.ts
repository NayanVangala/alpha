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

/** Which tile is lit. The lit tile holds until the gaze truly leaves its box; a new tile must be entered 5% in from
 * its edges, and the gaze has to stay there for `holdMs` before the highlight moves. Changing your mind restarts the timer. */
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
