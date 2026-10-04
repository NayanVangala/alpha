import { AnimatePresence, motion } from "motion/react"
import { useEffect, useRef, useState } from "react"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { api, type Nerd } from "@/lib/api"
import { BLUE, drawHeat, drawSeries, drawStrips, FAINT, INK, INK2, RULE, surface } from "@/lib/charts"
import { cn } from "@/lib/utils"

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
    const hot = b === "alpha"
    if (hot) {
      c.shadowColor = "rgba(0,4,246,0.5)"
      c.shadowBlur = 12
    }
    c.fillStyle = BLUE
    c.beginPath()
    c.roundRect(x, bottom - bh, bw, bh, [4, 4, 0, 0])
    c.fill()
    c.shadowBlur = 0
    c.textAlign = "center"
    c.fillStyle = hot ? BLUE : INK
    if (hot) c.font = `700 12px ${getComputedStyle(document.body).fontFamily}`
    c.fillText(`${Math.round(share * 100)}%`, x + bw / 2, bottom - bh - 6)
    if (hot) c.font = `12px ${getComputedStyle(document.body).fontFamily}`
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
    c.fillStyle = b === "alpha" ? BLUE : INK2
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
  c.lineWidth = 2
  c.setLineDash([6, 4])
  c.beginPath()
  c.moveTo(left, Y(n.threshold))
  c.lineTo(w - 4, Y(n.threshold))
  c.stroke()
  c.setLineDash([])
  c.fillStyle = INK2
  c.textAlign = "right"
  c.fillText("bite line", w - 6, Y(n.threshold) - 7)
  c.textAlign = "left"
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

function Section({
  title,
  note,
  badge,
  accent,
  hot,
  children,
}: {
  title: string
  note: string
  badge?: React.ReactNode
  accent?: boolean
  hot?: boolean
  children: React.ReactNode
}) {
  return (
    <section
      className={cn(
        accent
          ? cn(
              "rounded-lg border p-3.5 ring-1 transition-colors duration-300",
              hot
                ? "border-ultramarine/50 bg-ultramarine/[0.12] ring-ultramarine/40"
                : "border-ultramarine/25 bg-ultramarine/[0.05] ring-ultramarine/15",
            )
          : "border-t border-foreground/[0.08] pt-4",
      )}
    >
      <h3 className="m-0 mb-2 flex flex-wrap items-center gap-2 text-label font-semibold tracking-[-0.01em]">
        {title} <span className="font-normal text-muted-foreground">· {note}</span>
        {badge}
      </h3>
      {children}
    </section>
  )
}

const QUALITY_TEXT = { strong: "Strong", ok: "Good enough", weak: "Weak", lost: "Lost" } as const
const QUALITY_CLASS = { strong: "text-ultramarine", ok: "text-foreground", weak: "text-[#B3261E]", lost: "text-[#B3261E]" } as const
const STATUS_TEXT = { good: "Good", noisy: "Noisy", bad: "Bad", off: "Not touching" } as const
const STATUS_DOT = { good: "bg-ultramarine", noisy: "bg-[#B26A00]", bad: "bg-[#B3261E]", off: "bg-[#B9B6B3]" } as const
const BAND_COLOR: Record<string, string> = { delta: "#B9B6B3", theta: INK2, alpha: BLUE, beta: "#7B7DFF", gamma: INK }
const N = 120 // points in a full history
const SPAN_S = 60

/** Live numbers from the headband, drawn on canvas: raw EEG, band shares, spectrum, jaw level, events. */
export function NerdPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [nerd, setNerd] = useState<Nerd | null>(null)
  const raw = useRef<HTMLCanvasElement>(null)
  const bands = useRef<HTMLCanvasElement>(null)
  const spec = useRef<HTMLCanvasElement>(null)
  const jaw = useRef<HTMLCanvasElement>(null)
  const cv = useRef<Record<string, HTMLCanvasElement | null>>({})
  const chart = (id: string) => (el: HTMLCanvasElement | null) => {
    cv.current[id] = el
  }
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
    const at = (id: string) => cv.current[id]
    const h = nerd.hist
    const last = (a: (number | null)[]) => Math.max(0, ...a.filter((v): v is number => v != null))
    if (h.spec.length && at("spec")) drawHeat(at("spec")!, h.spec, { n: N, seconds: SPAN_S, bin0: 1, band: [8, 13, "alpha"] })
    if (h.bands.length && at("bandt")) {
      const names = Object.keys(h.bands[0])
      const share = h.bands.map((b) => { const tot = names.reduce((t, k) => t + b[k], 0) || 1; return names.map((k) => (100 * b[k]) / tot) })
      drawSeries(at("bandt")!, names.map((k, i) => ({ ys: share.map((r) => r[i]), color: BAND_COLOR[k] ?? INK, label: k, dash: k === "gamma" })),
        { n: N, seconds: SPAN_S, min: 0, max: 100, unit: "% of power" })
    }
    if (at("alpha")) drawSeries(at("alpha")!, [{ ys: h.alpha, color: BLUE, label: "alpha vs your line", width: 2.4 }],
      { n: N, seconds: SPAN_S, min: 0, max: Math.max(1.5, last(h.alpha) * 1.1), mark: { y: 1, label: "brake line" }, unit: "× your line" })
    if (at("contact")) drawStrips(at("contact")!, h.contact, nerd.channels, { n: N, seconds: SPAN_S })
    if (at("ppg")) drawSeries(at("ppg")!, [{ ys: nerd.ppg, color: BLUE, label: "pulse wave" }], { n: Math.max(2, nerd.ppg.length), seconds: 6, unit: "optical" })
    if (at("hr")) drawSeries(at("hr")!, [{ ys: h.hr, color: INK, label: "beats per minute" }], { n: N, seconds: SPAN_S, min: 40, max: 120, unit: "bpm" })
    if (at("gyro")) drawSeries(at("gyro")!, nerd.gyro.map((g, i) => ({ ys: g, color: [INK2, BLUE, INK][i], label: ["x", "y", "z"][i] })),
      { n: Math.max(2, nerd.gyro[0]?.length ?? 2), seconds: 6, unit: "deg/s" })
    if (at("tilt")) drawSeries(at("tilt")!, [{ ys: h.tilt, color: INK, label: "head tilt" }], { n: N, seconds: SPAN_S, unit: "°" })
    if (at("fs")) drawSeries(at("fs")!, [{ ys: h.fs, color: BLUE, label: "samples per second" }],
      { n: N, seconds: SPAN_S, min: 0, max: 300, mark: { y: 256, label: "256 expected" }, unit: "samples/s" })
  }, [nerd])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.code === "Escape") onClose()
    }
    addEventListener("keydown", onKey)
    return () => removeEventListener("keydown", onKey)
  }, [open, onClose])

  const live = !!nerd?.live
  const alphaNow = (() => {
    const a = nerd?.hist.alpha ?? []
    for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i] as number
    return null
  })()
  const alphaOver = alphaNow != null && alphaNow >= 1
  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          aria-label="Stats for nerds"
          initial={{ x: 28, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 28, opacity: 0 }}
          transition={{ duration: 0.35, ease: [0.625, 0.05, 0, 1] }}
          className="fixed inset-y-0 right-0 z-[5] grid w-[min(700px,58vw)] content-start gap-[22px] overflow-y-auto border-l bg-card px-[22px] pb-7 pt-5 max-[900px]:w-full"
        >
          <header className="flex items-center justify-between gap-3">
            <h2 className="m-0 text-body font-semibold tracking-[-0.02em]">Stats for nerds</h2>
            <div className="flex items-center gap-2.5">
              {live && (
                <p className="m-0 inline-flex items-center gap-1.5 rounded-full bg-ultramarine/10 px-2.5 py-1 text-tag font-semibold uppercase tracking-[0.08em] text-ultramarine">
                  <span className="size-1.5 animate-pulse rounded-full bg-ultramarine" />
                  Live
                </p>
              )}
              <button
                type="button"
                onClick={(e) => {
                  e.currentTarget.blur()
                  onClose()
                }}
                aria-label="Close stats"
                title="Close (Esc)"
                className="inline-flex size-8 items-center justify-center rounded-full border bg-background text-xl leading-none text-muted-foreground shadow-xs transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                ×
              </button>
            </div>
          </header>
          {!live ? (
            <p className="m-0 text-label text-muted-foreground">
              The headband isn't sending data right now. Check it's on, charged and close to the computer; it reconnects on its own.
            </p>
          ) : (
            <>
              <section className="grid gap-3 rounded-md bg-background p-3.5 ring-1 ring-foreground/[0.06]" aria-label="Signal quality">
                <div className="flex items-baseline justify-between gap-3">
                  <h3 className="m-0 text-label font-semibold">Connection and signal</h3>
                  <b className={`text-title font-medium leading-none tracking-[-0.04em] ${QUALITY_CLASS[nerd!.quality.overall]}`}>
                    {QUALITY_TEXT[nerd!.quality.overall]}
                  </b>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  {nerd!.quality.sensors.map((sn) => (
                    <div key={sn.name} className="grid gap-1 rounded-sm bg-card px-3 py-2 ring-1 ring-foreground/[0.06]">
                      <div className="flex items-baseline justify-between gap-2">
                        <b className="text-label font-semibold">{sn.name}</b>
                        <span className="text-tag text-muted-foreground tabular-nums">{sn.uv} µV</span>
                      </div>
                      <span className="flex items-center gap-1.5 text-tag text-muted-foreground">
                        <i className={`inline-block size-2 rounded-full ${STATUS_DOT[sn.status]}`} />
                        {STATUS_TEXT[sn.status]} · {sn.where}
                      </span>
                    </div>
                  ))}
                </div>
                <p className="m-0 text-label">
                  <b className="font-semibold">Bite and brake sensors (behind the ears):</b>{" "}
                  <span className={nerd!.quality.brake_ready ? "text-ultramarine" : "text-[#B3261E]"}>{nerd!.quality.brake_ready ? "ready" : "not ready"}</span>
                </p>
                {nerd!.quality.notes.length > 0 && (
                  <ul className="m-0 grid list-disc gap-0.5 pl-[18px] text-label text-muted-foreground">
                    {nerd!.quality.notes.map((t) => <li key={t}>{t}</li>)}
                  </ul>
                )}
              </section>
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
                  <div key={label} className="grid gap-0.5 rounded-sm bg-background px-3 py-2.5 ring-1 ring-foreground/[0.06]">
                    <b className="text-title font-medium leading-none tracking-[-0.04em] tabular-nums">{v}</b>
                    <span className="text-tag text-muted-foreground">{label}</span>
                  </div>
                ))}
              </div>
              <Section title="Raw EEG" note="last 2 s, microvolts">
                <canvas ref={raw} className="block rounded-sm bg-background h-44 w-full" role="img" aria-label="Raw EEG, four channels" />
              </Section>
              <Section title="Brainwaves over time" note="spectrogram, behind the ears, last 60 s">
                <canvas ref={chart("spec")} className="block rounded-sm bg-background h-[210px] w-full" role="img" aria-label="Spectrogram: frequency against time" />
                <p className="m-0 mt-1.5 text-label text-muted-foreground">Brighter is stronger. Close your eyes for 10 seconds and the dashed alpha band (8–13 Hz) lights up.</p>
              </Section>
              <Section title="Band share over time" note="how the five bands trade off, last 60 s">
                <canvas ref={chart("bandt")} className="block rounded-sm bg-background h-[170px] w-full" role="img" aria-label="Band share over time" />
              </Section>
              <Section
                title="Alpha against your brake line"
                note="the brain brake, last 60 s"
                accent
                hot={alphaOver}
                badge={
                  alphaOver ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-ultramarine px-1.5 py-px text-[0.65rem] font-bold uppercase tracking-[0.08em] text-white">
                      <span className="size-1.5 animate-pulse rounded-full bg-white" />
                      past the line
                    </span>
                  ) : undefined
                }
              >
                <canvas ref={chart("alpha")} className="block rounded-sm bg-background h-[150px] w-full" role="img" aria-label="Alpha level against the brake line" />
                <p className="m-0 mt-1.5 text-label text-muted-foreground">Stay above the dashed line for about 1.5 seconds and rein applies the brake.</p>
              </Section>
              <Section title="Brainwave bands" note="share of 1–50 Hz power, behind the ears">
                <canvas
                  ref={bands}
                  className="block rounded-sm bg-background h-[150px] w-full"
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
                  className="block rounded-sm bg-background h-[150px] w-full"
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
                <canvas ref={jaw} className="block rounded-sm bg-background h-[120px] w-full" role="img" aria-label="Jaw muscle level against the bite threshold" />
                <p className="m-0 mt-1.5 text-label text-muted-foreground">Dashed line: this wearer's bite threshold. Squares: bites picked up.</p>
              </Section>
              <Section title="Sensor contact over time" note="each sensor, last 60 s">
                <canvas ref={chart("contact")} className="block rounded-sm bg-background h-[120px] w-full" role="img" aria-label="Sensor contact over time" />
              </Section>
              <Section title="Pulse" note="optical heart sensor">
                <canvas ref={chart("ppg")} className="block rounded-sm bg-background h-[110px] w-full" role="img" aria-label="Pulse wave, last 6 seconds" />
                <canvas ref={chart("hr")} className="mt-2 block rounded-sm bg-background h-[110px] w-full" role="img" aria-label="Heart rate over the last minute" />
              </Section>
              <Section title="Head motion" note="gyroscope and tilt">
                <canvas ref={chart("gyro")} className="block rounded-sm bg-background h-[130px] w-full" role="img" aria-label="Head rotation rates, last 6 seconds" />
                <canvas ref={chart("tilt")} className="mt-2 block rounded-sm bg-background h-[110px] w-full" role="img" aria-label="Head tilt over the last minute" />
              </Section>
              <Section title="Stream health" note="samples per second reaching the computer">
                <canvas ref={chart("fs")} className="block rounded-sm bg-background h-[120px] w-full" role="img" aria-label="Samples per second over the last minute" />
              </Section>
              <Section title="Events" note="last 30 s">
                <ul className="m-0 grid list-none divide-y divide-foreground/[0.06] p-0 text-label text-muted-foreground">
                  {nerd!.events.length ? (
                    nerd!.events.slice(-8).reverse().map(([t, k], i) => (
                      <li key={i} className="flex items-baseline justify-between gap-3 py-1">
                        <b className={cn("font-medium", k === "clench" || k === "long_clench" ? "text-ultramarine" : "text-foreground")}>
                          {EVENT_NAME[k] ?? k}
                        </b>
                        <span className="tabular-nums">{Math.abs(t).toFixed(1)} s ago</span>
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
