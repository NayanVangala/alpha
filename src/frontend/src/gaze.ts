import { type Gaze, type GazeSource, startGaze } from "@/lib/gaze"

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
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
const onGaze = ({ x, y, ok, open }: Gaze) => {
  openNow = open
  if (testing) buf.push({ x, y, ok, open })
  dot.style.transform = `translate(${x}px, ${y}px)`
  dot.classList.toggle("lost", !ok)
  const under = ok ? targets.find((t) => { const r = t.getBoundingClientRect(); return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom }) ?? null : null
  if (under !== on) { on?.classList.remove("on"); under?.classList.add("on"); on = under }
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
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
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
  result.innerHTML = `<b>${hits} of ${order.length} targets hit (${Math.round((100 * hits) / order.length)}%)</b><br>` +
    (Number.isFinite(mean) ? `Average distance from the target's centre: ${Math.round(mean)} px. Targets about ${need} px across or bigger should be reliable; these are ${small} px.` : "No usable gaze samples: calibrate, sit about an arm's length from the screen, and try again.")
  status.textContent = "Accuracy test done."
})
