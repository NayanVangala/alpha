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
const onGaze = ({ x, y, ok }: Gaze) => {
  dot.style.transform = `translate(${x}px, ${y}px)`
  dot.classList.toggle("lost", !ok)
  const under = ok ? targets.find((t) => { const r = t.getBoundingClientRect(); return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom }) ?? null : null
  if (under !== on) { on?.classList.remove("on"); under?.classList.add("on"); on = under }
}

let source: GazeSource | null = null
async function begin(mouse: boolean) {
  source?.stop()
  status.textContent = "Starting…"
  try {
    source = await startGaze(onGaze, { mouse })
    status.textContent = source.mode === "eyedid" ? "Eye tracking on. Calibrate once, then look at a target." : "Mouse stand-in (no eye tracking): the dot follows your mouse."
  } catch (e) {
    status.textContent = `${(e as Error).message} Using the mouse stand-in.`
    source = await startGaze(onGaze, { mouse: true })
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
