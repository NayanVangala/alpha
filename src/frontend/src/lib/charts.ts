// Small canvas chart helpers for the Stats for nerds panel: scrolling line charts, a spectrogram and status strips.
export const INK = "#201D1D"
export const INK2 = "#57524F"
export const RULE = "rgba(32, 29, 29, 0.12)"
export const BLUE = "#0004F6"
export const FAINT = "rgba(32, 29, 29, 0.045)"
const AMBER = "#B26A00"
const RED = "#B3261E"
const LEFT = 36 // room for y labels
const BOTTOM = 18 // room for the time axis

export function surface(canvas: HTMLCanvasElement): [CanvasRenderingContext2D, number, number] {
  const dpr = devicePixelRatio || 1
  const w = canvas.clientWidth
  const h = canvas.clientHeight
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr)
    canvas.height = Math.round(h * dpr)
  }
  const c = canvas.getContext("2d")!
  c.setTransform(dpr, 0, 0, dpr, 0, 0)
  c.clearRect(0, 0, w, h)
  c.font = `12px ${getComputedStyle(document.body).fontFamily}`
  return [c, w, h]
}

/** x of point i out of `n` slots, newest on the right: a short history fills in from the right edge. */
const xAt = (i: number, len: number, n: number, w: number) => w - ((len - 1 - i) / (n - 1)) * (w - LEFT)

function axes(c: CanvasRenderingContext2D, w: number, h: number, seconds: number, y: (v: number) => number, lo: number, hi: number, unit: string) {
  c.strokeStyle = RULE
  c.fillStyle = INK2
  c.lineWidth = 1
  c.textAlign = "right"
  for (const v of [lo, (lo + hi) / 2, hi]) {
    c.beginPath()
    c.moveTo(LEFT, y(v))
    c.lineTo(w, y(v))
    c.stroke()
    c.fillText(Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(1), LEFT - 5, y(v) + 4)
  }
  c.textAlign = "left"
  c.fillText(`${seconds} s ago`, LEFT, h - 3)
  c.textAlign = "right"
  c.fillText(`now${unit ? ` · ${unit}` : ""}`, w, h - 3)
  c.textAlign = "left"
}

export type Line = { ys: (number | null | undefined)[]; color: string; label: string; dash?: boolean; width?: number }

/** Lines over time. `n` is how many points a full history holds (they scroll in from the right). */
export function drawSeries(
  canvas: HTMLCanvasElement,
  series: Line[],
  o: { n: number; seconds: number; min?: number; max?: number; mark?: { y: number; label: string }; unit?: string },
) {
  const [c, w, h] = surface(canvas)
  const all = series.flatMap((s) => s.ys.filter((v): v is number => v != null && Number.isFinite(v)))
  let lo = o.min ?? Math.min(...all, o.mark?.y ?? Infinity)
  let hi = o.max ?? Math.max(...all, o.mark?.y ?? -Infinity)
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) return axes(c, w, h, o.seconds, () => h / 2, 0, 1, o.unit ?? "")
  if (hi - lo < 1e-6) hi = lo + 1
  const top = 16
  const y = (v: number) => h - BOTTOM - ((v - lo) / (hi - lo)) * (h - BOTTOM - top)
  axes(c, w, h, o.seconds, y, lo, hi, o.unit ?? "")
  if (o.mark) {
    c.setLineDash([5, 4])
    c.strokeStyle = INK
    c.beginPath()
    c.moveTo(LEFT, y(o.mark.y))
    c.lineTo(w, y(o.mark.y))
    c.stroke()
    c.setLineDash([])
    c.fillStyle = INK
    c.textAlign = "right"
    c.fillText(o.mark.label, w - 2, y(o.mark.y) - 4)
    c.textAlign = "left"
  }
  let lx = LEFT
  for (const s of series) {
    c.strokeStyle = s.color
    c.lineWidth = s.width ?? 1.6
    c.lineJoin = "round"
    c.setLineDash(s.dash ? [3, 3] : [])
    c.beginPath()
    let pen = false
    s.ys.forEach((v, i) => {
      if (v == null || !Number.isFinite(v)) return void (pen = false)
      const px = xAt(i, s.ys.length, o.n, w)
      pen ? c.lineTo(px, y(v)) : c.moveTo(px, y(v))
      pen = true
    })
    c.stroke()
    c.setLineDash([])
    c.fillStyle = s.color
    c.fillText(s.label, lx, 11)
    lx += c.measureText(s.label).width + 14
  }
}

const mix = (a: number[], b: number[], t: number) => a.map((v, i) => Math.round(v + (b[i] - v) * t))
const STOPS = [[242, 242, 242], [205, 204, 255], [0, 4, 246], [6, 6, 12]]
const ramp = (t: number) => {
  const x = Math.min(0.999, Math.max(0, t)) * (STOPS.length - 1)
  const i = Math.floor(x)
  return `rgb(${mix(STOPS[i], STOPS[i + 1], x - i).join(",")})`
}

/** Spectrogram: frequency (1-45 Hz, low at the bottom) against time, brighter is stronger. */
export function drawHeat(canvas: HTMLCanvasElement, spec: number[][], o: { n: number; seconds: number; bin0: number; band?: [number, number, string] }) {
  const [c, w, h] = surface(canvas)
  const rows = spec[0]?.length ?? 45
  const ph = h - BOTTOM
  const flat = spec.flat().sort((a, b) => a - b)
  const lo = flat[Math.floor(flat.length * 0.05)] ?? 0
  const hi = flat[Math.floor(flat.length * 0.98)] ?? 1
  const cw = (w - LEFT) / o.n
  spec.forEach((col, i) => {
    const x = xAt(i, spec.length, o.n, w) - cw
    col.forEach((v, r) => {
      c.fillStyle = ramp((v - lo) / (hi - lo || 1))
      c.fillRect(x, ph - ((r + 1) / rows) * ph, cw + 0.6, ph / rows + 0.6)
    })
  })
  c.fillStyle = INK2
  c.textAlign = "right"
  for (const f of [1, 10, 20, 30, 45]) c.fillText(`${f}`, LEFT - 5, ph - ((f - o.bin0 + 0.5) / rows) * ph + 4)
  c.textAlign = "left"
  c.fillText(`${o.seconds} s ago`, LEFT, h - 3)
  c.textAlign = "right"
  c.fillText("now · Hz up the side", w, h - 3)
  if (o.band) {
    const [a, b, label] = o.band
    const y1 = ph - ((b - o.bin0 + 1) / rows) * ph
    const y2 = ph - ((a - o.bin0) / rows) * ph
    c.strokeStyle = INK
    c.setLineDash([4, 3])
    c.strokeRect(LEFT, y1, w - LEFT, y2 - y1)
    c.setLineDash([])
    c.fillStyle = INK
    c.fillText(label, w - 4, y1 - 3)
  }
  c.textAlign = "left"
}

const SENSOR_COLOR = { good: BLUE, noisy: AMBER, bad: RED, off: "#B9B6B3" } as const
export const sensorStatus = (uv: number) => (uv < 1 ? "off" : uv <= 100 ? "good" : uv <= 150 ? "noisy" : "bad")

/** One strip per sensor over time, coloured by how well it touched the skin. */
export function drawStrips(canvas: HTMLCanvasElement, contact: number[][], names: string[], o: { n: number; seconds: number }) {
  const [c, w, h] = surface(canvas)
  const rh = (h - BOTTOM) / names.length
  const cw = (w - LEFT) / o.n
  names.forEach((name, r) => {
    c.fillStyle = INK2
    c.textAlign = "right"
    c.fillText(name, LEFT - 5, r * rh + rh / 2 + 4)
    c.fillStyle = FAINT
    c.fillRect(LEFT, r * rh + 3, w - LEFT, rh - 6)
    contact.forEach((col, i) => {
      c.fillStyle = SENSOR_COLOR[sensorStatus(col[r])]
      c.fillRect(xAt(i, contact.length, o.n, w) - cw, r * rh + 3, cw + 0.6, rh - 6)
    })
  })
  c.fillStyle = INK2
  c.textAlign = "left"
  c.fillText(`${o.seconds} s ago`, LEFT, h - 3)
  c.textAlign = "right"
  c.fillText("blue good · amber noisy · red bad · grey off", w, h - 3)
  c.textAlign = "left"
}
