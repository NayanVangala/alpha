// Eye tracking through the Eyedid (SeeSo) web SDK and the webcam. Falls back to the mouse when there is no key,
// so the screens work, labeled, without it. Gaze only ever points; it never approves anything.
export type Gaze = { x: number; y: number; ok: boolean }
export type GazeSource = {
  mode: "eyedid" | "mouse"
  calibrate: (onPoint: (x: number, y: number, progress: number) => void) => Promise<void>
  stop: () => void
}

const SAVED = "alpha.gaze.cal"
const SMOOTH = 0.2 // how far each reading pulls the dot: lower is steadier, higher is quicker
const SUCCESS = 0 // the SDK's TrackingState.SUCCESS

function mouseSource(onGaze: (g: Gaze) => void): GazeSource {
  const move = (e: MouseEvent) => onGaze({ x: e.clientX, y: e.clientY, ok: true })
  addEventListener("mousemove", move)
  return { mode: "mouse", calibrate: async () => {}, stop: () => removeEventListener("mousemove", move) }
}

export async function startGaze(onGaze: (g: Gaze) => void, opts: { mouse?: boolean } = {}): Promise<GazeSource> {
  const key = opts.mouse ? null : (await fetch("/api/gaze/config").then((r) => r.json())).key
  if (!key) return mouseSource(onGaze)

  const { default: EasySeeSo } = await import("seeso/easy-seeso")
  const sdk = new EasySeeSo()
  await new Promise<void>((ok, fail) => sdk.init(key, ok, () => fail(new Error("The Eyedid license key was refused or couldn't be checked (it needs the internet)."))))
  const saved = localStorage.getItem(SAVED)
  if (saved) await sdk.setCalibrationData(saved)

  let sx = innerWidth / 2, sy = innerHeight / 2
  const started = await sdk.startTracking(
    (g: { x: number; y: number; trackingState: number }) => {
      if (g.trackingState !== SUCCESS) return onGaze({ x: sx, y: sy, ok: false })
      sx += (g.x - sx) * SMOOTH
      sy += (g.y - sy) * SMOOTH
      onGaze({ x: sx, y: sy, ok: true })
    },
    () => {},
  )
  if (!started) throw new Error("The webcam didn't start.")

  return {
    mode: "eyedid",
    stop: () => { sdk.stopTracking(); sdk.deinit() },
    // five points: the caller draws the dot where the SDK asks, we tell it to sample after a beat of looking
    calibrate: (onPoint) =>
      new Promise<void>((done, fail) => {
        const began = sdk.startCalibration(
          (x: number, y: number) => { onPoint(x, y, 0); setTimeout(() => sdk.startCollectSamples(), 900) },
          (progress: number) => onPoint(NaN, NaN, progress),
          (data: string) => { localStorage.setItem(SAVED, data); done() },
          5,
        )
        if (!began) fail(new Error("Calibration couldn't start."))
      }),
  }
}
