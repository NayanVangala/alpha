import { AnimatePresence, motion } from "motion/react"
import { useEffect, useRef, useState } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, type Nerd } from "@/lib/api"

const INK = "#201D1D"
const INK2 = "#57524F"
const RULE = "rgba(32, 29, 29, 0.12)"
const BLUE = "#0004F6"
const FAINT = "rgba(32, 29, 29, 0.045)"
const BAND_HZ: Record<string, string> = { delta: "1–4", theta: "4–8", alpha: "8–13", beta: "13–30", gamma: "30–50" }
const CH_WHERE = ["behind left ear", "left forehead", "right forehead", "behind right ear"]
const EVENT_NAME: Record<string, string> = {
  clench: "Bite",
  long_clench: "Long bite",
  double_blink: "Double blink",
  blink: "Blink",
  glance_left: "Glance left",
  glance_right: "Glance right",
  eyes_closed: "Eyes closed (brake)",
}

function surface(canvas: HTMLCanvasElement): [CanvasRenderingContext2D, number, number] {
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

function tip(c: CanvasRenderingContext2D, w: number, x: number, y: number, lines: string[]) {
  const pad = 6
  const lh = 15
  const tw = Math.max(...lines.map((l) => c.measureText(l).width)) + 2 * pad
  const th = lines.length * lh + 2 * pad - 3
  const bx = Math.min(Math.max(4, x + 10), w - tw - 4)
  const by = Math.max(4, y - th - 8)
  c.fillStyle = INK
  c.beginPath()
  c.roundRect(bx, by, tw, th, 4)
  c.fill()
  c.fillStyle = "#fff"
  lines.forEach((l, i) => c.fillText(l, bx + pad, by + pad + 10 + i * lh))
}

function drawRaw(canvas: HTMLCanvasElement, n: Nerd) {
  const [c, w, h] = surface(canvas)
  const rh = h / n.raw.length
  const left = 118
  n.raw.forEach((ch, r) => {
    const top = r * rh
    const mid = top + rh / 2
    const span = Math.max(50, ...ch.map(Math.abs)) // at least +/-50 uV so noise isn't blown up
    c.strokeStyle = RULE
    c.lineWidth = 1
    c.beginPath()
    c.moveTo(left, mid)
    c.lineTo(w, mid)
    c.stroke()
    c.fillStyle = INK
    c.fillText(n.channels[r], 0, mid - 2)
    c.fillStyle = INK2
    c.fillText(CH_WHERE[r], 0, mid + 12)
    c.fillText(`±${Math.round(span)}`, w - 34, top + 12)
    c.strokeStyle = BLUE
    c.lineWidth = 1.5
    c.beginPath()
    ch.forEach((v, i) => {
      const x = left + (i / (ch.length - 1)) * (w - left - 38)
      const y = mid - (v / span) * (rh / 2 - 4)
      if (i) c.lineTo(x, y)
      else c.moveTo(x, y)
    })
    c.stroke()
  })
}

function drawBands(canvas: HTMLCanvasElement, n: Nerd, hover: number | null) {
  const [c, w, h] = surface(canvas)
  const names = Object.keys(n.bands)
  const bottom = h - 34
  const top = 18
  // TP9 and TP10: blinks swamp the forehead pair, while rhythms and jaw muscle show best behind the ears
  const avg = names.map((b) => (n.bands[b][0] + n.bands[b][3]) / 2)
  const total = avg.reduce((a, b) => a + b, 0) || 1
  const slot = w / names.length
  const bw = Math.min(56, slot - 18)
  const most = Math.max(...avg) / total || 1 // tallest bar fills the height
  c.strokeStyle = RULE
  c.beginPath()
  c.moveTo(0, bottom + 0.5)
  c.lineTo(w, bottom + 0.5)
  c.stroke()
  names.forEach((b, i) => {
    const share = avg[i] / total
    const x = i * slot + (slot - bw) / 2
    const bh = Math.max(2, (share / most) * (bottom - top))
    c.fillStyle = BLUE
    c.beginPath()
    c.roundRect(x, bottom - bh, bw, bh, [4, 4, 0, 0])
    c.fill()
    c.fillStyle = INK
    c.textAlign = "center"
    c.fillText(`${Math.round(share * 100)}%`, x + bw / 2, bottom - bh - 6)
    c.fillText(b[0].toUpperCase() + b.slice(1), x + bw / 2, bottom + 15)
    c.fillStyle = INK2
    c.fillText(`${BAND_HZ[b]} Hz`, x + bw / 2, bottom + 29)
    c.textAlign = "left"
  })
  if (hover !== null && names[hover]) {
    const b = names[hover]
    tip(c, w, hover * slot + slot / 2, top + 30, [
      `${b}: ${avg[hover].toFixed(1)} µV² behind the ears`,
      ...n.bands[b].map((v, k) => `${n.channels[k]}  ${v.toFixed(1)} µV²`),
    ])
  }
}

function drawSpectrum(canvas: HTMLCanvasElement, n: Nerd, hover: number | null) {
  const [c, w, h] = surface(canvas)
  const f = n.freqs
  const db = n.psd.map((p) => 10 * Math.log10(Math.max(p, 1e-4)))
  const left = 34
  const bottom = h - 18
  const top = 16
  const lo = Math.floor(Math.min(...db) / 5) * 5
  const hi = Math.ceil(Math.max(...db) / 5) * 5 || lo + 5
  const X = (hz: number) => left + ((hz - f[0]) / (f[f.length - 1] - f[0])) * (w - left - 4)
  const Y = (v: number) => bottom - ((v - lo) / (hi - lo || 1)) * (bottom - top)
  Object.entries(BAND_HZ).forEach(([b, r], i) => {
    const [a, z] = r.split("–").map(Number)
    if (i % 2 === 0) {
      c.fillStyle = FAINT
      c.fillRect(X(a), top, X(z) - X(a), bottom - top)
    }
    c.fillStyle = INK2
    c.textAlign = "center"
    c.fillText(b[0].toUpperCase(), (X(a) + X(z)) / 2, top - 4)
    c.textAlign = "left"
  })
  c.fillStyle = INK2
  ;[lo, hi].forEach((v) => c.fillText(`${v} dB`, 0, Y(v) + 4))
  ;[1, 10, 20, 30, 40, 50, 60].forEach((hz) => {
    c.textAlign = hz === 60 ? "right" : "center"
    c.fillText(hz === 60 ? "60 Hz" : String(hz), X(hz), h - 3)
    c.textAlign = "left"
  })
  c.strokeStyle = BLUE
  c.lineWidth = 2
  c.lineJoin = "round"
  c.beginPath()
  f.forEach((hz, i) => (i ? c.lineTo(X(hz), Y(db[i])) : c.moveTo(X(hz), Y(db[i]))))
  c.stroke()
  if (hover !== null) {
    const i = f.reduce((best, hz, k) => (Math.abs(X(hz) - hover) < Math.abs(X(f[best]) - hover) ? k : best), 0)
    c.strokeStyle = INK2
    c.lineWidth = 1
    c.beginPath()
    c.moveTo(X(f[i]), top)
    c.lineTo(X(f[i]), bottom)
    c.stroke()
    c.fillStyle = BLUE
    c.beginPath()
    c.arc(X(f[i]), Y(db[i]), 4, 0, 7)
    c.fill()
    tip(c, w, X(f[i]), Y(db[i]), [`${f[i]} Hz`, `${n.psd[i].toFixed(2)} µV²/Hz`])
  }
}

function drawJaw(canvas: HTMLCanvasElement, n: Nerd) {
  const [c, w, h] = surface(canvas)
  const win = n.window_s
  const pts = n.muscle
  const left = 34
  const bottom = h - 16
  const top = 8
  const hi = Math.max(n.threshold * 2, ...pts.map((p) => p[1])) * 1.05
  const X = (t: number) => left + ((t + win) / win) * (w - left - 4)
  const Y = (v: number) => bottom - (v / hi) * (bottom - top)
  c.fillStyle = INK2
  c.fillText("0", 18, bottom + 4)
  c.fillText(`${Math.round(hi)}`, 0, top + 8)
  ;[-30, -20, -10, 0].forEach((t) => {
    c.textAlign = t ? "center" : "right"
    c.fillText(t ? `${t} s` : "now", X(t), h - 2)
  })
  c.textAlign = "left"
  c.strokeStyle = INK
  c.lineWidth = 1
  c.setLineDash([4, 4])
  c.beginPath()
  c.moveTo(left, Y(n.threshold))
  c.lineTo(w - 4, Y(n.threshold))
  c.stroke()
  c.setLineDash([])
  c.strokeStyle = BLUE
  c.lineWidth = 2
  c.beginPath()
  pts.forEach(([t, v], i) => (i ? c.lineTo(X(t), Y(v)) : c.moveTo(X(t), Y(v))))
  c.stroke()
  n.events
    .filter((e) => e[1] === "clench" || e[1] === "long_clench")
    .forEach(([t, k]) => {
      const s = k === "long_clench" ? 10 : 8
      c.fillStyle = INK
      c.fillRect(X(t) - s / 2, Y(n.threshold) - s / 2, s, s)
    })
}

const fmt = (v: number | null | undefined, d = 0) => (v == null ? "–" : Number(v).toFixed(d))

function Section({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="m-0 mb-2 text-label font-semibold">
        {title} <span className="font-normal text-muted-foreground">· {note}</span>
      </h3>
      {children}
    </section>
  )
}

/** Live numbers from the headband, drawn on canvas: raw EEG, band shares, spectrum, jaw level, events. */
export function NerdPanel({ open }: { open: boolean }) {
  const [nerd, setNerd] = useState<Nerd | null>(null)
  const raw = useRef<HTMLCanvasElement>(null)
  const bands = useRef<HTMLCanvasElement>(null)
  const spec = useRef<HTMLCanvasElement>(null)
  const jaw = useRef<HTMLCanvasElement>(null)
  const hoverSpec = useRef<number | null>(null)
  const hoverBand = useRef<number | null>(null)

  useEffect(() => {
    if (!open) return
    let alive = true
    const tick = () => api.nerd().then((n) => alive && setNerd(n), () => alive && setNerd(null))
    void tick()
    const id = setInterval(tick, 200)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [open])

  useEffect(() => {
    if (!nerd?.live) return
    if (raw.current) drawRaw(raw.current, nerd)
    if (bands.current) drawBands(bands.current, nerd, hoverBand.current)
    if (spec.current) drawSpectrum(spec.current, nerd, hoverSpec.current)
    if (jaw.current) drawJaw(jaw.current, nerd)
  }, [nerd])

  const live = !!nerd?.live
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          aria-label="Stats for nerds"
          initial={{ x: 28, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 28, opacity: 0 }}
          transition={{ duration: 0.35, ease: [0.625, 0.05, 0, 1] }}
          className="fixed inset-y-0 right-0 z-[5] grid w-[min(500px,42vw)] content-start gap-[22px] overflow-y-auto border-l bg-card px-[22px] pb-7 pt-5 max-[900px]:w-full"
        >
          <header className="flex items-baseline justify-between gap-3">
            <h2 className="m-0 text-body font-semibold tracking-[-0.02em]">Stats for nerds</h2>
            {live && <p className="m-0 text-label text-ultramarine">Live</p>}
          </header>
          {!live ? (
            <p className="m-0 text-label text-muted-foreground">
              The headband isn't sending data right now. Check it's on, charged and close to the computer; it reconnects on its own.
            </p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2">
                {(
                  [
                    [fmt(nerd!.fs), "samples / s"],
                    [fmt(nerd!.age_ms), "ms since last packet"],
                    [fmt(nerd!.hr), "heart bpm"],
                    [fmt(nerd!.blink_rate), "blinks / min"],
                    [fmt(nerd!.tilt), "head tilt °"],
                    [fmt(nerd!.threshold), "bite µV"],
                  ] as const
                ).map(([v, label]) => (
                  <div key={label} className="grid gap-0.5 rounded-sm bg-background px-3 py-2.5">
                    <b className="text-title font-medium leading-none tracking-[-0.04em] tabular-nums">{v}</b>
                    <span className="text-tag text-muted-foreground">{label}</span>
                  </div>
                ))}
              </div>
              <Section title="Raw EEG" note="last 2 s, microvolts">
                <canvas ref={raw} className="block h-44 w-full" role="img" aria-label="Raw EEG, four channels" />
              </Section>
              <Section title="Brainwave bands" note="share of 1–50 Hz power, behind the ears">
                <canvas
                  ref={bands}
                  className="block h-[150px] w-full"
                  role="img"
                  aria-label="Band power bars"
                  onMouseMove={(e) => {
                    hoverBand.current = Math.floor(e.nativeEvent.offsetX / (e.currentTarget.clientWidth / 5))
                    if (nerd) drawBands(e.currentTarget, nerd, hoverBand.current)
                  }}
                  onMouseLeave={() => (hoverBand.current = null)}
                />
                <ul className="mt-2 grid list-disc gap-0.5 pl-[18px] text-label text-muted-foreground">
                  <li><b className="font-semibold text-foreground">Alpha</b> rises when you close your eyes. Try it for 10 seconds.</li>
                  <li><b className="font-semibold text-foreground">Gamma</b> on a headband is mostly jaw muscle. It's what the bite detector watches.</li>
                  <li><b className="font-semibold text-foreground">Delta</b> on the forehead is mostly blinks and eye movement.</li>
                </ul>
                <details className="mt-2 text-label">
                  <summary className="cursor-pointer text-muted-foreground">Numbers</summary>
                  <Table className="text-label">
                    <TableHeader>
                      <TableRow>
                        <TableHead>Band</TableHead>
                        {nerd!.channels.map((ch) => <TableHead key={ch}>{ch}</TableHead>)}
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {Object.entries(nerd!.bands).map(([b, vals]) => (
                        <TableRow key={b}>
                          <TableCell>{b} ({BAND_HZ[b]} Hz)</TableCell>
                          {vals.map((v, k) => <TableCell key={k} className="tabular-nums">{v.toFixed(1)}</TableCell>)}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </details>
              </Section>
              <Section title="Spectrum" note="average of 4 channels, 1–60 Hz">
                <canvas
                  ref={spec}
                  className="block h-[150px] w-full"
                  role="img"
                  aria-label="Power spectrum"
                  onMouseMove={(e) => {
                    hoverSpec.current = e.nativeEvent.offsetX
                    if (nerd) drawSpectrum(e.currentTarget, nerd, hoverSpec.current)
                  }}
                  onMouseLeave={() => (hoverSpec.current = null)}
                />
              </Section>
              <Section title="Jaw muscle" note="above 30 Hz, last 30 s">
                <canvas ref={jaw} className="block h-[120px] w-full" role="img" aria-label="Jaw muscle level against the bite threshold" />
                <p className="m-0 mt-1.5 text-label text-muted-foreground">Dashed line: this wearer's bite threshold. Squares: bites picked up.</p>
              </Section>
              <Section title="Events" note="last 30 s">
                <ul className="m-0 grid list-none gap-0.5 p-0 text-label text-muted-foreground">
                  {nerd!.events.length ? (
                    nerd!.events.slice(-8).reverse().map(([t, k], i) => (
                      <li key={i} className="flex justify-between">
                        <b className="font-medium text-foreground">{EVENT_NAME[k] ?? k}</b>
                        <span>{Math.abs(t).toFixed(1)} s ago</span>
                      </li>
                    ))
                  ) : (
                    <li>Nothing yet.</li>
                  )}
                </ul>
              </Section>
            </>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  )
}
