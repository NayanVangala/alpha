import { type Gaze, type GazeSource, startGaze } from "@/lib/gaze"
import { TileTracker, calibrationHolds } from "@/lib/gazeKit"

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const status = $("status"), dot = $("dot"), picked = $("picked"), cal = $("cal"), calDot = cal.querySelector("i") as HTMLElement
const targets = ["Home", "Back", "Search", "Videos", "Read", "Stop"].map((name) => {
  const el = document.createElement("div")
  el.className = "t"
  el.textContent = name
  $("grid").append(el)
  return el
})

let on: HTMLElement | null = null
let testing = false
let buf: Gaze[] = []
let openNow: number | null = null
const tracker = new TileTracker()  // sticky borders: a tile lights after 300 ms inside it, and holds until you truly leave
let lastOk = 0
const rects = () => targets.map((t) => t.getBoundingClientRect())
const onGaze = ({ x, y, ok, open }: Gaze) => {
  openNow = open
  if (testing) buf.push({ x, y, ok, open })
  dot.style.transform = `translate(${x}px, ${y}px)`
  if (ok) lastOk = performance.now()
  dot.classList.toggle("lost", !ok)
  const idx = ok ? tracker.update(rects(), x, y, performance.now()) : tracker.current
  const under = idx >= 0 ? targets[idx] : null
  if (under !== on) { on?.classList.remove("on"); under?.classList.add("on"); on = under }
}
setInterval(() => { if (lastOk && performance.now() - lastOk > 500) dot.classList.add("lost") }, 150)  // a stale reading isn't where you are looking

/* The startup check: a dot appears on a tile; the calibration passes only if the median gaze lands within half a tile of it. */
const val = $("val")
async function checkCalibration() {
  if (source?.mode !== "eyedid" || !localStorage.getItem("alpha.gaze.cal")) return void (status.textContent = "Calibrate once first, then the check can run.")
  const tile = targets[Math.floor(Math.random() * targets.length)]
  const r = tile.getBoundingClientRect()
  const target = { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  val.style.left = `${target.x}px`
  val.style.top = `${target.y}px`
  val.style.display = "block"
  status.textContent = "Calibration check: look at the dot."
  testing = true
  buf = []
  await sleep(2200)
  testing = false
  val.style.display = "none"
  const samples = buf.filter((g) => g.ok).slice(Math.floor(buf.length / 2))
  const res = calibrationHolds(samples, target, Math.min(r.width, r.height))
  status.textContent = res.pass
    ? `Calibration check passed: your gaze lands within ${Math.round(res.median)} px of the dot.`
    : `Calibration check FAILED (${res.n < 10 ? `only ${res.n} readings` : `${Math.round(res.median)} px off`}): press Calibrate and try again.`
}

let fired = 0
function onEyesClosed() {
  fired++
  // the same brake the headband's alpha applies; the board refuses it (409) until a headband is connected
  fetch("/api/input", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ kind: "eyes_closed", by: "camera" }) })
    .then((r) => (picked.textContent = `Camera brake fired ×${fired} (board said ${r.status}).`))
    .catch(() => (picked.textContent = `Camera brake fired ×${fired}.`))
}
setInterval(() => { if (source?.mode === "eyedid") status.textContent = `Eye tracking on · eye openness ${openNow === null ? "?" : openNow.toFixed(2)} · close your eyes for a second to test the camera brake` }, 250)

let source: GazeSource | null = null
async function begin(mouse: boolean) {
  source?.stop()
  status.textContent = "Starting…"
  try {
    source = await startGaze(onGaze, { mouse, onEyesClosed })
    status.textContent = source.mode === "eyedid" ? "Eye tracking on. Calibrate once, then look at a target." : "Mouse stand-in (no eye tracking): the dot follows your mouse."
    if (source.mode === "eyedid" && localStorage.getItem("alpha.gaze.cal")) setTimeout(checkCalibration, 800)  // every startup re-checks the saved calibration
  } catch (e) {
    status.textContent = `${(e as Error).message} Using the mouse stand-in.`
    source = await startGaze(onGaze, { mouse: true, onEyesClosed })
  }
}

$("mouse-btn").addEventListener("click", () => begin(true))
$("cal-btn").addEventListener("click", async () => {
  if (source?.mode !== "eyedid") return void (status.textContent = "Calibration needs eye tracking: reload this page and allow the camera.")
  cal.style.display = "block"
  try {
    await source.calibrate((x, y, progress) => {
      if (!Number.isNaN(x)) { calDot.style.left = `${x}px`; calDot.style.top = `${y}px` }
      calDot.style.opacity = String(1 - 0.6 * progress)
    })
    status.textContent = "Calibrated and saved on this computer."
    setTimeout(checkCalibration, 700)
  } catch (e) {
    status.textContent = (e as Error).message
  } finally {
    cal.style.display = "none"
  }
})
addEventListener("keydown", (e) => {
  if (e.code === "Space" && on) { e.preventDefault(); picked.textContent = `Selected: ${on.textContent}`; }
})

begin(false)

/* The accuracy test: each of the six targets lights up twice, in random order, for two seconds. A target counts as hit when
   most of the gaze samples from the second half (once the eyes have landed) fall inside it. */
$("test-btn").addEventListener("click", async () => {
  if (testing) return
  testing = true
  const result = $("result")
  result.style.display = "none"
  const order = [...targets, ...targets].sort(() => Math.random() - 0.5)
  let hits = 0
  const errs: number[] = []
  for (let i = 0; i < order.length; i++) {
    const el = order[i]
    el.classList.add("aim")
    status.textContent = `Look at the outlined target: ${i + 1} of ${order.length}`
    buf = []
    await sleep(2000)
    el.classList.remove("aim")
    const r = el.getBoundingClientRect()
    const late = buf.filter((g) => g.ok).slice(Math.floor(buf.length / 2))
    if (late.length < 5) continue  // no usable samples: a miss
    const inside = late.filter((g) => g.x >= r.left && g.x <= r.right && g.y >= r.top && g.y <= r.bottom).length / late.length
    if (inside >= 0.6) hits++
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2
    errs.push(late.reduce((t, g) => t + Math.hypot(g.x - cx, g.y - cy), 0) / late.length)
  }
  testing = false
  const mean = errs.length ? errs.reduce((a, b) => a + b, 0) / errs.length : NaN
  const need = Number.isFinite(mean) ? Math.ceil((2 * mean) / 10) * 10 : 0
  const small = Math.round(Math.min(...targets.map((t) => Math.min(t.getBoundingClientRect().width, t.getBoundingClientRect().height))))
  result.style.display = "block"
  const rate = hits / order.length
  result.innerHTML = `<b>${hits} of ${order.length} targets hit (${Math.round(100 * rate)}%) · ${rate >= 0.9 ? "PASS" : "FAIL: the bar is 90%"}</b><br>` +
    (Number.isFinite(mean) ? `Average distance from the target's centre: ${Math.round(mean)} px. Targets about ${need} px across or bigger should be reliable; these are ${small} px.` : "No usable gaze samples: calibrate, sit about an arm's length from the screen, and try again.")
  status.textContent = "Accuracy test done."
})
