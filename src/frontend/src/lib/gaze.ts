import { OneEuro, claimCamera } from "@/lib/gazeKit"

// Eye tracking through the Eyedid (SeeSo) web SDK or WebGazer (keyless, in-browser) and the webcam.
// Falls back to the mouse when no tracker starts, so the screens work, labeled, without one.
// Gaze only ever points; it never approves anything.
export type Gaze = { x: number; y: number; ok: boolean; open: number | null } // open: both eyes, 0 shut to ~1 wide
export type GazeSource = {
  mode: "eyedid" | "webgazer" | "mouse"
  calibrate: (onPoint: (x: number, y: number, progress: number) => void) => Promise<void>
  stop: () => void
  note?: string // why the better tracker was skipped, when this is a fallback
}

const SAVED = "alpha.gaze.cal"
const STALE_MS = 500 // a reading older than this is thrown away rather than shown as where you are looking
const SUCCESS = 0 // the SDK's TrackingState.SUCCESS
const CLOSED_S = 0.8 // eyes shut this long is a deliberate closure, not a blink

function mouseSource(onGaze: (g: Gaze) => void): GazeSource {
  const move = (e: MouseEvent) => onGaze({ x: e.clientX, y: e.clientY, ok: true, open: null })
  addEventListener("mousemove", move)
  return { mode: "mouse", calibrate: async () => {}, stop: () => removeEventListener("mousemove", move) }
}

export async function startGaze(onGaze: (g: Gaze) => void, opts: { mouse?: boolean; onEyesClosed?: () => void } = {}): Promise<GazeSource> {
  // The ladder: Eyedid (needs its license key) > WebGazer (keyless, in-browser) > mouse.
  // A refused Eyedid license falls through to WebGazer instead of failing: that's the whole point.
  let note = "no Eyedid key on the server (start it with --env-file .env)"
  if (!opts.mouse) {
    const key = (await fetch("/api/gaze/config").then((r) => r.json())).key
    if (key) {
      try {
        return await eyedidSource(onGaze, opts, key)
      } catch (e) {
        note = (e as Error).message  // license refused or the webcam failed: try the keyless tracker, and say why
      }
    }
  }
  try {
    return { ...(await webgazerSource(onGaze)), note }
  } catch {
    return mouseSource(onGaze)
  }
}

async function webgazerSource(onGaze: (g: Gaze) => void): Promise<GazeSource> {
  // WebGazer: keyless eye tracking that runs entirely in the browser. Gaze position only —
  // it reports no eye-openness signal, so the camera brake (eye closure) stays Eyedid-only.
  const release = await claimCamera()  // one camera owner: gaze and the camera brake never fight over the webcam
  const webgazer = (await import("webgazer")).default
  let sx = innerWidth / 2, sy = innerHeight / 2, lastGood = 0
  const fx = new OneEuro(), fy = new OneEuro()  // same smoothing as the Eyedid path
  try {
    webgazer
      .setRegression("ridge")
      .setTracker("clmtrackr")
      .setGazeListener((data) => {
        if (!data) return
        const now = performance.now()
        if (lastGood && now - lastGood > STALE_MS) { fx.filter(data.x / innerWidth, now / 1000 - 1); fy.filter(data.y / innerHeight, now / 1000 - 1) }
        lastGood = now
        sx = fx.filter(data.x / innerWidth, now / 1000) * innerWidth
        sy = fy.filter(data.y / innerHeight, now / 1000) * innerHeight
        onGaze({ x: sx, y: sy, ok: true, open: null })
      })
    webgazer.showVideoPreview(false).showPredictionPoints(false).showFaceOverlay(false).showFaceFeedbackBox(false)
    await webgazer.begin()
  } catch {
    release()
    throw new Error("The webcam didn't start.")
  }
  return {
    mode: "webgazer",
    stop: () => { webgazer.end(); webgazer.clearData(); release() },
    // five points: the caller draws the dot via onPoint; the user gets a beat to look, then the
    // current gaze is recorded at the point several times. WebGazer keeps its model in memory —
    // nothing is saved to localStorage, so this calibration lasts for the page load only.
    calibrate: async (onPoint) => {
      const pts: Array<[number, number]> = [
        [innerWidth * 0.15, innerHeight * 0.15],
        [innerWidth * 0.85, innerHeight * 0.15],
        [innerWidth * 0.5, innerHeight * 0.5],
        [innerWidth * 0.15, innerHeight * 0.85],
        [innerWidth * 0.85, innerHeight * 0.85],
      ]
      for (const [x, y] of pts) {
        onPoint(x, y, 0)
        await new Promise((r) => setTimeout(r, 1200)) // a beat of looking at the dot first
        for (let i = 0; i < 8; i++) {
          webgazer.recordScreenPosition(x, y)
          await new Promise((r) => setTimeout(r, 100))
        }
      }
      onPoint(NaN, NaN, 1)
    },
  }
}

async function eyedidSource(onGaze: (g: Gaze) => void, opts: { onEyesClosed?: () => void }, key: string): Promise<GazeSource> {
  const release = await claimCamera()  // one camera owner: gaze and the camera brake never fight over the webcam
  const { default: EasySeeSo } = await import("seeso/easy-seeso")
  const sdk = new EasySeeSo()
  try {
    // gaze only: attention, blink and drowsiness detection stay off (the SDK's default), so the tracker does one job
    await new Promise<void>((ok, fail) => sdk.init(key, ok, (code?: unknown) => fail(new Error(`The Eyedid license key was refused or couldn't be checked (it needs the internet)${code === undefined ? "" : `, code ${String(code)}`}.`))))
  } catch (e) {
    release()
    throw e
  }
  const saved = localStorage.getItem(SAVED)
  if (saved) await sdk.setCalibrationData(saved)

  let sx = innerWidth / 2, sy = innerHeight / 2, lastGood = 0
  const fx = new OneEuro(), fy = new OneEuro()  // on screen-normalised coordinates: 1 Hz minimum cutoff, beta 10
  // The camera brake: both eyes well under their own wide-open level for CLOSED_S (a blink is far shorter).
  let wide = 0, shutSince = 0, told = false
  const watchEyes = (open: number, now: number) => {
    wide = Math.max(wide * 0.9995, open) // the wearer's own wide-open level, slowly forgetting
    if (open > wide * 0.6) { shutSince = 0; told = false }
    else if (open < wide * 0.4) {
      shutSince ||= now
      if (!told && now - shutSince >= CLOSED_S * 1000) { told = true; opts.onEyesClosed?.() }
    }
  }
  const started = await sdk.startTracking(
    (g: { x: number; y: number; trackingState: number; leftOpenness: number; rightOpenness: number }) => {
      const open = Number.isFinite(g.leftOpenness) && Number.isFinite(g.rightOpenness) ? (g.leftOpenness + g.rightOpenness) / 2 : null
      if (open !== null) watchEyes(open, performance.now())
      const now = performance.now()
      // confidence gating: only a successful track counts, and a reading that is stale is no reading
      if (g.trackingState !== SUCCESS) return onGaze({ x: sx, y: sy, ok: false, open })
      if (lastGood && now - lastGood > STALE_MS) { fx.filter(g.x / innerWidth, now / 1000 - 1); fy.filter(g.y / innerHeight, now / 1000 - 1) }
      lastGood = now
      sx = fx.filter(g.x / innerWidth, now / 1000) * innerWidth
      sy = fy.filter(g.y / innerHeight, now / 1000) * innerHeight
      onGaze({ x: sx, y: sy, ok: true, open })
    },
    () => {},
  )
  if (!started) {
    release()
    throw new Error("The webcam didn't start.")
  }

  return {
    mode: "eyedid",
    stop: () => { sdk.stopTracking(); sdk.deinit(); release() },
    // five points: the caller draws the dot where the SDK asks, we tell it to sample after a beat of looking
    calibrate: (onPoint) =>
      new Promise<void>((done, fail) => {
        const began = sdk.startCalibration(
          (x: number, y: number) => { onPoint(x, y, 0); setTimeout(() => sdk.startCollectSamples(), 1000) }, // a second of looking at each dot first
          (progress: number) => onPoint(NaN, NaN, progress),
          (data: string) => { localStorage.setItem(SAVED, data); done() },
          5,
        )
        if (!began) fail(new Error("Calibration couldn't start."))
      }),
  }
}
