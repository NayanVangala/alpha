import Lenis from "lenis"
import gsap from "gsap"
import { ScrollTrigger } from "gsap/ScrollTrigger"
import "./landing.css"

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T
const slides = [...document.querySelectorAll<HTMLElement>(".slide")]
const still = matchMedia("(prefers-reduced-motion: reduce)").matches
const BLUE = "#0004F6"
let cur = 0

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
const showing = new Set<HTMLCanvasElement>()
function loop(now: number) {
  if (now - last > 40) {  // ~25 fps is plenty for pixels this big
    last = now
    showing.forEach((cv) => drawDither(cv, now / 1000))
  }
  requestAnimationFrame(loop)
}

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


/* ---------- scroll: Lenis for the smoothing, one GSAP timeline for every transition ---------- */
const SCENES = slides.length
const UNIT = () => innerHeight * 1.9  // scroll distance of one scene
const sceneTitle = $("sec"), count = $("count")
const bar = $("progress")
const dots = slides.map((_, i) => {
  const b = document.createElement("button")
  b.setAttribute("aria-label", `Go to scene ${i + 1}`)
  b.addEventListener("click", () => toScene(i))
  bar.append(b)
  return b
})
let lenis: Lenis | null = null
const toScene = (i: number) => {
  const y = i === 0 ? 0 : (Math.min(SCENES - 1, Math.max(0, i)) + 0.3) * UNIT()
  if (lenis) lenis.scrollTo(y, { duration: 1.4 })
  else slides[i].scrollIntoView({ behavior: "smooth" })
}

function setActive(i: number) {
  if (i === cur && slides[i].classList.contains("active")) return
  cur = i
  slides.forEach((s, k) => s.classList.toggle("active", k === i))
  dots.forEach((d, k) => d.classList.toggle("on", k === i))
  sceneTitle.textContent = slides[i].dataset.title ?? ""
  count.textContent = `${i + 1} / ${SCENES}`
  document.body.classList.toggle("on-dark", slides[i].classList.contains("dark") || slides[i].classList.contains("blue"))
  history.replaceState(null, "", `#${i + 1}`)
}

const COLORS = ["#9BFF60", "#CDCCFF", "#7B7DFF", "#FFFFFF", "#FFD166", "#FF7AA2", "#5EE6FF"]
const PARTS = ".w, .card, .node, .stats > div, .steps4 li, .road li, .rules li, .panel, .term, .lead, .body, .who, .tag, .micro, .credits"
const box = (el: Element) => { const r = el.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height, cx: r.left + r.width / 2, cy: r.top + r.height / 2 } }
const fs = (el: Element) => parseFloat(getComputedStyle(el).fontSize)

// the pixel dissolve between the demo and the diagram, scrubbed by the scroll
const cells = { cols: 0, rows: 0, size: 0, delay: [] as number[] }
const dissolve = { p: 0 }
function layoutCells() {
  cells.size = Math.ceil(innerWidth / 30)
  cells.cols = Math.ceil(innerWidth / cells.size)
  cells.rows = Math.ceil(innerHeight / cells.size)
  cells.delay = Array.from({ length: cells.cols * cells.rows }, () => Math.random() * 0.65)
}
function drawCells() {
  const cv = $<HTMLCanvasElement>("wipe")
  if (cv.width !== innerWidth || cv.height !== innerHeight) { cv.width = innerWidth; cv.height = innerHeight }
  const c = cv.getContext("2d")!
  c.clearRect(0, 0, cv.width, cv.height)
  if (dissolve.p <= 0) return
  c.fillStyle = BLUE
  cells.delay.forEach((d, i) => {
    const s = Math.min(1, Math.max(0, (dissolve.p - d) / 0.35))
    if (s <= 0) return
    const size = cells.size * s
    c.fillRect((i % cells.cols) * cells.size + (cells.size - size) / 2, Math.floor(i / cells.cols) * cells.size + (cells.size - size) / 2, size + 0.5, size + 0.5)
  })
}

function build() {
  gsap.registerPlugin(ScrollTrigger)
  const scroller = $("scroller")
  scroller.style.height = `${SCENES * UNIT() + innerHeight}px`
  gsap.set(slides, { zIndex: (i: number) => i + 1 })
  gsap.set(slides.slice(1), { autoAlpha: 0 })
  layoutCells()

  // the terminal's last line: the next slide's title, typed in colourful letters
  const typed = slides[1].querySelector<HTMLElement>(".typed")!
  const title = slides[2].querySelector("h2")!.getAttribute("aria-label") ?? ""
  typed.innerHTML = `<span class="pr">$</span><span class="tl">${[...title].map((ch, i) => `<span class="ch" style="color:${COLORS[i % COLORS.length]}">${ch === " " ? "&nbsp;" : ch}</span>`).join("")}</span>`
  const chars = gsap.utils.toArray<HTMLElement>(typed.querySelectorAll(".ch"))

  // the full stop that ends the title: a white square stands in for it, then grows to fill the screen
  const h1 = slides[0].querySelector<HTMLElement>("h1")!
  const period = [...h1.querySelectorAll<HTMLElement>(".c")].pop()!
  const dot = Object.assign(document.createElement("i"), { className: "dotzoom" })
  slides[0].append(dot)

  // measure everything with its entrance at rest
  document.body.classList.add("measuring")
  const pr = box(period), dsz = 0.17 * fs(h1)
  const tl_ = box(typed.querySelector(".tl")!), hr = box(slides[2].querySelector("h2")!), term = slides[1].querySelector<HTMLElement>(".term")!, trm = box(term)
  const zoomTerm = fs(slides[2].querySelector("h2")!) / fs(typed)
  const blue = slides[4].querySelector<HTMLElement>(".node.blue")!, bb = box(blue)
  const card = slides[7].querySelectorAll<HTMLElement>(".road li")[4], cb = box(card)
  document.body.classList.remove("measuring")
  Object.assign(dot.style, { width: `${dsz}px`, height: `${dsz}px`, left: `${pr.left + pr.width * 0.5 - dsz / 2}px`, top: `${pr.top + pr.height * 0.78 - dsz / 2}px` })

  const tl = gsap.timeline({ defaults: { ease: "power2.inOut" }, scrollTrigger: {
    trigger: scroller, start: "top top", end: "bottom bottom", scrub: 0.7, invalidateOnRefresh: true,
    onUpdate: (self) => {
      const p = self.progress * SCENES  // scene s is on screen from s + 0.1 until its own boundary swaps it out
      setActive(Math.min(SCENES - 1, Math.max(0, Math.floor(p - 0.05))))
      showing.clear()
      slides.forEach((sl) => {
        const cv = sl.querySelector<HTMLCanvasElement>("canvas.dither")
        if (cv && Number(gsap.getProperty(sl, "opacity")) > 0.02 && gsap.getProperty(sl, "visibility") !== "hidden") showing.add(cv)
      })
    },
  } })
  tl.to({}, { duration: SCENES }, 0)  // the timeline spans SCENES scene units
  tl.fromTo(h1, { scale: 1 }, { scale: 1.1, duration: 0.55, ease: "none" }, 0)

  // 0 -> 1: the full stop grows until it is the screen, and the screen is the problem slide's light page
  {
    const t = 0.55
    tl.set(dot, { visibility: "visible" }, t).set(period, { visibility: "hidden" }, t)
    tl.to(h1, { scale: 1.5, autoAlpha: 0, duration: 0.3, ease: "power2.in" }, t)
    tl.to(slides[0].querySelectorAll(".micro, .lead, .hint, canvas.dither"), { autoAlpha: 0, duration: 0.25 }, t)
    tl.to(dot, { x: innerWidth / 2 - (pr.left + pr.width * 0.5), y: innerHeight / 2 - (pr.top + pr.height * 0.78), scale: (Math.max(innerWidth, innerHeight) * 1.5) / dsz, duration: 0.55, ease: "power3.in" }, t)
    tl.fromTo(slides[1], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.15, ease: "none" }, t + 0.5)
    tl.set(slides[0], { autoAlpha: 0 }, t + 0.66)
  }

  // 1 -> 2: the terminal types the next title, then we zoom into the terminal and it becomes the slide
  {
    const t = 1.45
    tl.fromTo(slides[1].querySelector(".typed .pr"), { opacity: 0 }, { opacity: 1, duration: 0.05, ease: "none" }, t)
    tl.fromTo(chars, { opacity: 0 }, { opacity: 1, duration: 0.01, ease: "none", stagger: 0.3 / chars.length }, t + 0.05)
    tl.set(term, { transformOrigin: `${tl_.left - trm.left}px ${tl_.top - trm.top}px` }, t)
    tl.to(slides[1].querySelector(".cols > div:first-child"), { autoAlpha: 0, x: -80, duration: 0.25 }, t + 0.35)
    tl.to(term, { scale: zoomTerm, x: hr.left - tl_.left, y: hr.top - tl_.top, duration: 0.55, ease: "power3.inOut" }, t + 0.4)
    tl.to(term.querySelectorAll("p:not(.typed)"), { autoAlpha: 0, duration: 0.2 }, t + 0.55)
    tl.fromTo(slides[2], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.18, ease: "none" }, t + 0.82)
    tl.set(slides[1], { autoAlpha: 0 }, t + 1.0)
  }

  // 2 -> 3: eyelids close on the "close your eyes" slide, and open on the brake demo
  {
    const t = 2.55
    tl.to("#lidTop", { yPercent: 0, y: 0, duration: 0.22, ease: "power2.in" }, t).to("#lidBottom", { yPercent: 0, y: 0, duration: 0.22, ease: "power2.in" }, t)
    tl.set(slides[2], { autoAlpha: 0 }, t + 0.24).set(slides[3], { autoAlpha: 1 }, t + 0.24)
    tl.to("#lidTop", { yPercent: -104, duration: 0.3, ease: "power2.out" }, t + 0.3).to("#lidBottom", { yPercent: 104, duration: 0.3, ease: "power2.out" }, t + 0.3)
  }

  // 3 -> 4: the demo freezes and breaks into blue pixels, which clear to show the diagram
  {
    const t = 3.55
    tl.to(dissolve, { p: 1, duration: 0.3, ease: "none", onUpdate: drawCells }, t)
    tl.set(slides[3], { autoAlpha: 0 }, t + 0.31).set(slides[4], { autoAlpha: 1 }, t + 0.31)
    tl.to(dissolve, { p: 0, duration: 0.3, ease: "none", onUpdate: drawCells }, t + 0.34)
  }

  // 4 -> 5: zoom into the blue box (rein, on your computer) until blue is the whole screen: the impact slide
  {
    const t = 4.55
    tl.to(slides[4].querySelectorAll(".node:not(.blue), .arrow, .rules, h2, .tag"), { autoAlpha: 0, duration: 0.25 }, t)
    tl.to(blue, { x: innerWidth / 2 - bb.cx, y: innerHeight / 2 - bb.cy, scale: Math.max(innerWidth / bb.width, innerHeight / bb.height) * 1.2, duration: 0.55, ease: "power3.inOut" }, t + 0.1)
    tl.to(blue.children, { autoAlpha: 0, duration: 0.2 }, t + 0.35)
    tl.fromTo(slides[5], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.12, ease: "none" }, t + 0.6)
    tl.set(slides[4], { autoAlpha: 0 }, t + 0.74)
  }

  // 5 -> 6: the impact slide lifts away like a curtain and the how-to is already there
  {
    const t = 5.6
    tl.set(slides[6], { autoAlpha: 1, zIndex: 5 }, t)
    tl.fromTo(slides[6], { yPercent: 14, scale: 0.96 }, { yPercent: 0, scale: 1, duration: 0.55, ease: "power2.out" }, t)
    tl.to(slides[5], { yPercent: -100, duration: 0.55, ease: "power3.inOut" }, t)
    tl.set(slides[5], { autoAlpha: 0, yPercent: 0 }, t + 0.56).set(slides[6], { zIndex: 7 }, t + 0.56)
  }

  // 6 -> 7: the four steps burst apart and the roadmap is behind them
  {
    const t = 6.55
    tl.set(slides[7], { autoAlpha: 1, zIndex: 6 }, t)
    tl.to(gsap.utils.toArray<HTMLElement>(slides[6].querySelectorAll(PARTS)), { x: () => gsap.utils.random(-1000, 1000), y: () => gsap.utils.random(-700, 700), rotation: () => gsap.utils.random(-160, 160),
      scale: () => gsap.utils.random(0.4, 2.4), autoAlpha: 0, duration: 0.5, ease: "power3.in", stagger: { amount: 0.1, from: "center" } }, t)
    tl.set(slides[6], { autoAlpha: 0 }, t + 0.62).set(slides[7], { zIndex: 8 }, t + 0.62)
  }

  // 7 -> 8: zoom into the last roadmap card, "Real users", and it opens onto the close
  {
    const t = 7.55
    tl.to(slides[7].querySelectorAll(".road li:not(:nth-child(5)), h2, .tag"), { autoAlpha: 0, duration: 0.25 }, t)
    tl.to(card, { x: innerWidth / 2 - cb.cx, y: innerHeight / 2 - cb.cy, scale: Math.max(innerWidth / cb.width, innerHeight / cb.height) * 1.25, duration: 0.55, ease: "power3.inOut" }, t + 0.1)
    tl.to(card.children, { autoAlpha: 0, duration: 0.2 }, t + 0.4)
    tl.fromTo(slides[8], { autoAlpha: 0 }, { autoAlpha: 1, duration: 0.18, ease: "none" }, t + 0.55)
    tl.set(slides[7], { autoAlpha: 0 }, t + 0.74)
  }
  return tl
}

/* ---------- connect a Muse: scan, pick, connect, then explode into the app ---------- */
type Device = { name: string; brand: string; supported: boolean; simulated?: boolean }
const connectBtn = $<HTMLButtonElement>("connect"), codeLink = $("code"), panel = $("muse")
let serverPhase = "locked"

function burstInto(url: string, from: DOMRect) {
  const cv = $<HTMLCanvasElement>("wipe")
  const c = cv.getContext("2d")!
  cv.width = innerWidth
  cv.height = innerHeight
  const ox = from.left + from.width / 2, oy = from.top + from.height / 2
  const bits = Array.from({ length: 900 }, () => {
    const a = Math.random() * Math.PI * 2, v = 6 + Math.random() * 38
    return { x: ox, y: oy, vx: Math.cos(a) * v, vy: Math.sin(a) * v, s: 6 + Math.random() * 22, r: Math.random() * 6, col: [BLUE, "#CDCCFF", "#06060C", "#0004F6"][Math.floor(Math.random() * 4)] }
  })
  gsap.to(document.getElementById("deck"), { scale: 1.35, autoAlpha: 0, duration: 0.8, ease: "power3.in" })
  const t0 = performance.now()
  const frame = (now: number) => {
    const t = (now - t0) / 800
    c.clearRect(0, 0, cv.width, cv.height)
    for (const b of bits) {
      b.x += b.vx * (1 - t * 0.5); b.y += b.vy * (1 - t * 0.5)
      c.fillStyle = b.col
      c.globalAlpha = Math.max(0, 1 - t * 0.9)
      c.save(); c.translate(b.x, b.y); c.rotate(b.r + t * 3); c.fillRect(-b.s / 2, -b.s / 2, b.s, b.s); c.restore()
    }
    if (t < 1) requestAnimationFrame(frame)
    else { c.fillStyle = BLUE; c.globalAlpha = 1; c.fillRect(0, 0, cv.width, cv.height); location.assign(url) }
  }
  still ? location.assign(url) : requestAnimationFrame(frame)
}

const closePanel = () => { panel.hidden = true; connectBtn.setAttribute("aria-expanded", "false") }
const esc = (t: string) => t.replace(/[&<>"]/g, (ch) => `&#${ch.charCodeAt(0)};`)
const post = (path: string, body?: unknown) =>
  fetch(path, { method: "POST", headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined })

async function scan() {
  panel.innerHTML = `<h3>Looking for headbands…</h3><p>Put the Muse on and hold its button until the lights sweep.</p>`
  let devices: Device[] = [], error: string | null = null
  try { const r = await (await post("/api/scan")).json(); devices = r.devices ?? []; error = r.error ?? null } catch { error = "Couldn't reach the app." }
  panel.innerHTML = `<h3>Connect a Muse</h3>` + (devices.length
    ? devices.map((d, i) => `<div class="row"><span><b>${esc(d.name)}</b><small>${esc(d.brand)}${d.simulated ? " · for testing" : ""}</small></span>
        <button class="go" data-i="${i}" ${d.supported ? "" : "disabled"}>${d.supported ? "Connect" : "Support coming"}</button></div>`).join("")
    : `<p>${esc(error ?? "No headband found nearby.")} Hold the Muse's button until its lights sweep, then scan again.</p>`)
    + `<button class="link" id="rescan" type="button">Scan again</button>`
  panel.querySelectorAll<HTMLButtonElement>(".go").forEach((b) => b.addEventListener("click", () => connect(devices[Number(b.dataset.i)].name)))
  $("rescan").addEventListener("click", scan)
}

async function connect(name: string) {
  panel.innerHTML = `<h3>Connecting to ${esc(name)}…</h3><p>This takes about ten seconds. If nothing happens, hold the Muse's button until its lights sweep.</p>`
  try { await post("/api/connect", { name }) } catch { return void (panel.innerHTML = `<h3>Couldn't connect</h3><p>The app isn't answering.</p><button class="link" id="rescan">Scan again</button>`, $("rescan").addEventListener("click", scan)) }
  for (let i = 0; i < 120; i++) {  // up to a minute
    await new Promise((r) => setTimeout(r, 500))
    const st = await (await fetch("/api/state")).json().catch(() => null)
    if (st?.phase === "connected") {
      panel.innerHTML = `<h3>Connected</h3><p>Opening rein. It learns your jaw and blinks in 20 seconds: read the screen with your eyes open.</p>`
      return burstInto("/board", connectBtn.getBoundingClientRect())
    }
    if (st?.error || st?.phase === "locked") {
      panel.innerHTML = `<h3>Couldn't connect</h3><p>${esc(st?.error ?? "The headband didn't answer.")} Hold its button until the lights sweep.</p><button class="link" id="rescan" type="button">Scan again</button>`
      return void $("rescan").addEventListener("click", scan)
    }
  }
}

connectBtn.addEventListener("click", () => {
  if (serverPhase === "connected") return burstInto("/board", connectBtn.getBoundingClientRect())
  if (panel.hidden) { panel.hidden = false; connectBtn.setAttribute("aria-expanded", "true"); void scan() } else closePanel()
})
addEventListener("keydown", (e) => { if (e.key === "Escape") closePanel() })
// the app is here (not the public site): the button replaces the code link
fetch("/api/state").then((r) => (r.ok ? r.json() : Promise.reject())).then((st) => {
  serverPhase = st.phase
  connectBtn.hidden = false
  codeLink.hidden = true
  if (st.phase === "connected") connectBtn.querySelector("span")!.textContent = "Open the app"
}).catch(() => { /* the public site: View the code stays */ })

/* ---------- keys and start ---------- */
addEventListener("keydown", (e) => {
  if ((e.target as HTMLElement).closest("button, a, input")) return
  if (["ArrowDown", "PageDown", " "].includes(e.key)) { e.preventDefault(); toScene(Math.min(SCENES - 1, cur + 1)) }
  else if (["ArrowUp", "PageUp"].includes(e.key)) { e.preventDefault(); toScene(Math.max(0, cur - 1)) }
  else if (e.key === "Home") toScene(0)
  else if (e.key === "End") toScene(SCENES - 1)
  else if (/^[1-9]$/.test(e.key)) toScene(Number(e.key) - 1)
  else if (e.key === "f" || e.key === "F") void (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen())
})
addEventListener("hashchange", () => toScene(Number(location.hash.slice(1)) - 1))

if (still) {
  document.body.classList.add("plain")  // no smoothing, no flying scenes: they just stack
  slides.forEach((s) => s.classList.add("active"))
  slides.forEach((s) => { const cv = s.querySelector<HTMLCanvasElement>("canvas.dither"); if (cv) { cv.style.display = "block"; drawDither(cv, 3) } })
} else {
  lenis = new Lenis({ lerp: 0.085, wheelMultiplier: 0.9 })
  lenis.on("scroll", ScrollTrigger.update)
  gsap.ticker.add((t) => lenis?.raf(t * 1000))
  gsap.ticker.lagSmoothing(0)
  build()
  setActive(0)
  const start = Number(location.hash.slice(1)) - 1
  if (start > 0) requestAnimationFrame(() => toScene(start))
  addEventListener("resize", () => ScrollTrigger.refresh())
  requestAnimationFrame(loop)
}
showCard()
requestAnimationFrame(demoFrame)
