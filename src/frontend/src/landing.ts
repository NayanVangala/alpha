import "./landing.css"

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const slides = [...document.querySelectorAll<HTMLElement>(".slide")]
const still = matchMedia("(prefers-reduced-motion: reduce)").matches
const BLUE = "#0004F6"
let cur = -1
let busy = false

/* ---------- headings roll in letter by letter ---------- */
document.querySelectorAll<HTMLElement>(".roll").forEach((el) => {
  const text = el.textContent ?? ""
  el.setAttribute("aria-label", text)
  el.textContent = ""
  let n = 0
  for (const tok of text.split(/(\s+)/)) {
    if (!tok.trim()) { el.append(tok); continue }
    const word = document.createElement("span")
    word.className = "w"
    word.setAttribute("aria-hidden", "true")
    for (const ch of tok) {
      const c = document.createElement("span")
      c.className = "c"
      c.style.setProperty("--i", String(n++))
      c.textContent = ch
      word.append(c)
    }
    el.append(word)
  }
})

/* ---------- live dither: Bayer-thresholded waves in ink, ultramarine and pale, rippling around the pointer ---------- */
const BAYER = [0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22,
  3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21]
const INK = [6, 6, 12], BLU = [0, 4, 246], PALE = [205, 204, 255]
const pointer = { x: 0.7, y: 0.4 }
addEventListener("pointermove", (e) => { pointer.x = e.clientX / innerWidth; pointer.y = e.clientY / innerHeight })

function drawDither(cv: HTMLCanvasElement, t: number) {
  const cell = 5
  const w = Math.max(8, Math.ceil(cv.clientWidth / cell)), h = Math.max(8, Math.ceil(cv.clientHeight / cell))
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h }
  const ctx = cv.getContext("2d")!
  const img = ctx.createImageData(w, h)
  const mx = pointer.x * w, my = pointer.y * h
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const dx = x - mx, dy = y - my, d = Math.hypot(dx, dy)
      const v = 0.46 + 0.22 * Math.sin(x * 0.05 + t * 0.9) * Math.cos(y * 0.07 - t * 0.6) + 0.18 * Math.sin((x * 0.6 + y) * 0.04 + t * 0.5)
        + 0.38 * Math.sin(d * 0.4 - t * 3.2) * Math.exp(-d * 0.035)
      const thr = (BAYER[(y & 7) * 8 + (x & 7)] + 0.5) / 64
      const col = v > thr + 0.4 ? PALE : v > thr ? BLU : INK
      const i = (y * w + x) * 4
      img.data[i] = col[0]; img.data[i + 1] = col[1]; img.data[i + 2] = col[2]; img.data[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
}

let last = 0
function loop(now: number) {
  if (now - last > 40) {  // ~25 fps is plenty for pixels this big
    last = now
    const cv = slides[cur]?.querySelector<HTMLCanvasElement>("canvas.dither")
    if (cv) drawDither(cv, now / 1000)
  }
  requestAnimationFrame(loop)
}

/* ---------- pixel wipe between slides ---------- */
function wipe(onMid: () => void) {
  if (still) return onMid()
  busy = true
  const cvs = $<HTMLCanvasElement>("wipe")
  const c = cvs.getContext("2d")!
  cvs.width = innerWidth
  cvs.height = innerHeight
  const cell = Math.ceil(innerWidth / 30)
  const cols = Math.ceil(innerWidth / cell), rows = Math.ceil(innerHeight / cell)
  const delay = Array.from({ length: cols * rows }, () => Math.random() * 0.65)
  const t0 = performance.now()
  let mid = false
  const frame = (now: number) => {
    const t = (now - t0) / 340  // 0 to 1 fills the screen with squares, 1 to 2 clears them
    c.clearRect(0, 0, cvs.width, cvs.height)
    const phase = t < 1 ? t : 2 - t
    if (t >= 1 && !mid) { mid = true; onMid() }
    c.fillStyle = BLUE
    for (let i = 0; i < delay.length; i++) {
      const s = Math.min(1, Math.max(0, (phase - delay[i]) / 0.35))
      if (s <= 0) continue
      const size = cell * s
      c.fillRect((i % cols) * cell + (cell - size) / 2, Math.floor(i / cols) * cell + (cell - size) / 2, size + 0.5, size + 0.5)
    }
    if (t < 2) requestAnimationFrame(frame)
    else { c.clearRect(0, 0, cvs.width, cvs.height); busy = false }
  }
  requestAnimationFrame(frame)
}

/* ---------- navigation ---------- */
const bar = $("progress")
const dots = slides.map((_, i) => {
  const b = document.createElement("button")
  b.setAttribute("aria-label", `Go to slide ${i + 1}`)
  b.addEventListener("click", () => go(i))
  bar.append(b)
  return b
})

function show(i: number) {
  cur = i
  slides.forEach((s, k) => s.classList.toggle("active", k === i))
  dots.forEach((d, k) => d.classList.toggle("on", k === i))
  $("sec").textContent = slides[i].dataset.title ?? ""
  $("count").textContent = `${i + 1} / ${slides.length}`
  document.body.classList.toggle("on-dark", slides[i].classList.contains("dark") || slides[i].classList.contains("blue"))
  history.replaceState(null, "", `#${i + 1}`)
  slides[i].scrollTop = 0
}

function go(i: number) {
  if (busy || i === cur || i < 0 || i >= slides.length) return
  if (cur < 0) return show(i)
  wipe(() => show(i))
}

$("prev").addEventListener("click", () => go(cur - 1))
$("next").addEventListener("click", () => go(cur + 1))
addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).closest("button, a") && (e.key === " " || e.key === "Enter")) return
  if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); go(cur + 1) }
  else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); go(cur - 1) }
  else if (e.key === "Home") go(0)
  else if (e.key === "End") go(slides.length - 1)
  else if (/^[1-9]$/.test(e.key)) go(Number(e.key) - 1)
  else if (e.key === "f" || e.key === "F") void (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen())
})
let sx = 0
addEventListener("touchstart", (e) => { sx = e.touches[0].clientX }, { passive: true })
addEventListener("touchend", (e) => { const dx = e.changedTouches[0].clientX - sx; if (Math.abs(dx) > 60) go(cur + (dx < 0 ? 1 : -1)) }, { passive: true })
addEventListener("hashchange", () => go(Number(location.hash.slice(1)) - 1))

/* ---------- the brake demo (simulated): a card counts down, closing your eyes lifts the alpha trace past your line ---------- */
const CARDS = [
  { verb: "Claude wants to run", cmd: "npm test", risky: false },
  { verb: "Claude wants to edit", cmd: "pager.py (+1 −1)", risky: false },
  { verb: "Claude wants to run", cmd: 'git commit -m "Fix off-by-one"', risky: true },
  { verb: "Claude wants to read", cmd: "tests/test_pager.py", risky: false },
]
const AUTO = 6, LINE = 0.37, HOLD = 1.5, OPEN = 0.21, SHUT = 0.56, GAP = 2.4, HZ = 30, N = 240
const demo = { closed: false, value: OPEN, over: 0, card: 0, t: 0, decided: "" as "" | "brain" | "muscle" | "silence", gap: 0, acc: 0 }
const hist: number[] = Array(N).fill(OPEN)
const tally = { dec: 0, brain: 0, muscle: 0, silence: 0 }
let log: string[] = []
const trace = $<HTMLCanvasElement>("trace")
const tctx = trace.getContext("2d")!

function setStatus(kind: string, text: string) {
  const p = $("pill")
  p.className = `pill2 ${kind}`
  p.textContent = kind.toUpperCase()
  $("statustext").textContent = text
}
function showCard() {
  const c = CARDS[demo.card % CARDS.length]
  $("verb").textContent = c.verb
  $("cmd").textContent = c.cmd
  $("ringbar").style.width = "0%"
  ;($("ringbar").parentNode as HTMLElement).style.visibility = c.risky ? "hidden" : "visible"
  setStatus("silence", c.risky ? "Waits for a bite down. Silence never approves this." : `Goes ahead in ${AUTO} s unless you stop it.`)
}
function decide(kind: "brain" | "muscle" | "silence", text: string) {
  demo.decided = kind
  demo.gap = GAP
  tally.dec++
  tally[kind]++
  log = [`${CARDS[demo.card % CARDS.length].cmd}: ${text}`, ...log].slice(0, 3)
  $("cDec").textContent = String(tally.dec)
  $("cBrain").textContent = String(tally.brain)
  $("cMuscle").textContent = String(tally.muscle)
  $("cSilence").textContent = String(tally.silence)
  $("ledger").replaceChildren(...log.map((l) => Object.assign(document.createElement("li"), { textContent: l })))
  setStatus(kind, { brain: "Refused. You stopped Claude.", muscle: "Approved with a bite.", silence: "Approved by silence." }[kind])
}
function stepDemo(dt: number) {
  const target = demo.closed ? SHUT : OPEN
  const tau = demo.closed ? 1.5 : 0.7
  demo.value += (target - demo.value) * (1 - Math.exp(-dt / tau)) + (Math.random() - 0.5) * 0.012
  demo.over = demo.value > LINE ? demo.over + dt : 0
  demo.acc += dt
  while (demo.acc >= 1 / HZ) { demo.acc -= 1 / HZ; hist.push(demo.value); hist.shift() }
  if (demo.decided) {
    demo.gap -= dt
    if (demo.gap <= 0) { demo.decided = ""; demo.card++; demo.t = 0; showCard() }
    return
  }
  const c = CARDS[demo.card % CARDS.length]
  if (demo.over >= HOLD) return decide("brain", "stopped by BRAIN")
  if (!c.risky) {
    demo.t += dt
    $("ringbar").style.width = `${Math.min(100, (demo.t / AUTO) * 100)}%`
    $("statustext").textContent = `Goes ahead in ${Math.max(0, Math.ceil(AUTO - demo.t))} s unless you stop it.`
    if (demo.t >= AUTO) decide("silence", "approved by SILENCE")
  }
}
function drawTrace() {
  const dpr = devicePixelRatio || 1, w = trace.clientWidth, h = trace.clientHeight
  if (!w) return
  if (trace.width !== Math.round(w * dpr)) { trace.width = Math.round(w * dpr); trace.height = Math.round(h * dpr) }
  tctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  tctx.clearRect(0, 0, w, h)
  const top = 22, bottom = h - 10, max = 0.7
  const y = (v: number) => bottom - (Math.min(v, max) / max) * (bottom - top)
  const x = (i: number) => (i / (N - 1)) * w
  tctx.font = "500 12px 'Host Grotesk', sans-serif"
  tctx.fillStyle = "#57524F"
  tctx.fillText("alpha share (BRAIN)", 0, 13)
  tctx.setLineDash([5, 5])
  tctx.strokeStyle = "#201D1D"
  tctx.lineWidth = 1
  tctx.beginPath(); tctx.moveTo(0, y(LINE)); tctx.lineTo(w, y(LINE)); tctx.stroke()
  tctx.setLineDash([])
  tctx.textAlign = "right"; tctx.fillStyle = "#201D1D"; tctx.fillText("your line", w - 2, y(LINE) - 5); tctx.textAlign = "left"
  const path = () => { tctx.beginPath(); hist.forEach((v, i) => (i ? tctx.lineTo(x(i), y(v)) : tctx.moveTo(x(i), y(v)))) }
  tctx.lineJoin = "round"; tctx.lineWidth = 2; tctx.strokeStyle = "#57524F"; path(); tctx.stroke()
  tctx.save(); tctx.beginPath(); tctx.rect(0, 0, w, y(LINE)); tctx.clip()
  tctx.lineWidth = 3; tctx.strokeStyle = BLUE; path(); tctx.stroke(); tctx.restore()
}
let demoLast = 0
function demoFrame(now: number) {
  const dt = Math.min(0.05, (now - demoLast) / 1000)
  demoLast = now
  if (slides[cur]?.contains(trace)) { stepDemo(dt); drawTrace() }  // only runs while its slide is showing
  requestAnimationFrame(demoFrame)
}
$("eyes").addEventListener("click", function (this: HTMLElement) {
  demo.closed = !demo.closed
  this.setAttribute("aria-pressed", String(demo.closed))
  this.textContent = demo.closed ? "Open your eyes" : "Close your eyes"
})
$("bite").addEventListener("click", () => { if (!demo.decided) decide("muscle", "approved by MUSCLE") })

/* ---------- on the public site there is no app behind this page: point "Open the app" at the code instead ---------- */
fetch("/api/gaze/config")
  .then((r) => { if (!r.ok) throw new Error("no app here") })
  .catch(() => {
    const a = document.querySelector<HTMLAnchorElement>(".bubble")
    if (!a) return
    a.href = "https://github.com/NayanVangala/alpha"
    a.target = "_blank"
    a.rel = "noopener"
    a.querySelector("span")!.textContent = "View the code"
  })

/* ---------- start ---------- */
showCard()
show(Math.min(slides.length - 1, Math.max(0, Number(location.hash.slice(1)) - 1 || 0)))
if (!still) requestAnimationFrame(loop)
else slides.forEach((s) => { const cv = s.querySelector<HTMLCanvasElement>("canvas.dither"); if (cv) { cv.style.display = "block"; drawDither(cv, 3) } })
requestAnimationFrame(demoFrame)
