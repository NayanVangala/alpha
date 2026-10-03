import { Sparkles, X } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { useCallback, useEffect, useRef } from "react"
import { BorderBeam } from "@/components/BorderBeam"
import { Brake } from "@/components/Brake"
import { BrainPanel } from "@/components/Brain"
import { Autopilot, auraOpacity } from "@/components/Mind"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { useBoard } from "@/hooks/useBoard"
import { useCameraBrake } from "@/hooks/useCameraBrake"
import { useDevices } from "@/hooks/useDevices"
import { useKeys } from "@/hooks/useKeys"
import { api, type BoardState, type Gesture, type Headband } from "@/lib/api"
import { cn } from "@/lib/utils"
import { BlinkLight } from "@/components/Chrome"
import { batteryText } from "./App"

const EASE = [0.625, 0.05, 0, 1] as const
const slide = {
  enter: (dir: number) => ({ x: dir * 32, opacity: 0 }),
  center: { x: 0, opacity: 1 },
  exit: (dir: number) => ({ x: dir * -32, opacity: 0 }),
}
const Key = ({ children }: { children: string }) => <b className="font-semibold text-foreground">{children}</b>

/**
 * The floating window (desktop/main.cjs): the same board in a small always-on-top card, for answering
 * Claude Code over VS Code or a terminal. It doesn't speak; the full board in the browser does that.
 */
export function Hud() {
  const { s, setS, lost } = useBoard()
  const camera = useCameraBrake() // runs here, not in a browser tab: this window isn't throttled in the background
  const open = !!s && s.headband.phase === "connected" && !s.headband.calibrating && s.headband.calibration_ok !== false
  const send = useCallback(
    async (kind: Gesture, ago = 0) => {
      const next = await api.input(kind, ago)
      if (next) setS(next)
    },
    [setS],
  )
  useEffect(() => {
    // while this window is open, rein drives Claude Code; closing it hands Claude Code back
    void api.arm().catch(() => {})
    const id = setInterval(() => void api.arm().catch(() => {}), 2000)
    return () => clearInterval(id)
  }, [])
  const simulated = !!s?.headband.device?.simulated
  useKeys({ enabled: open, send, onListen: () => {}, onNerd: () => {}, onEyes: (closed) => simulated && void api.simEyes(closed) })

  const context = !s
    ? ""
    : s.agent
      ? "Claude Code"
      : s.screen === "replies" && s.heard
        ? `“${s.heard}”`
        : ["Home", ...s.path].join(" › ")
  return (
    <div className="h-screen p-2">
      <div className="flex h-full flex-col gap-3 overflow-hidden rounded-xl bg-card p-4 shadow-[0_18px_48px_-22px_rgba(0,0,0,0.5)] ring-1 ring-black/10">
        <header className="flex items-center justify-between gap-3 text-label [-webkit-app-region:drag]">
          <span className="flex min-w-0 items-center gap-2">
            <b className="font-semibold tracking-[-0.03em]">rein<span className="text-ultramarine">.</span></b>
            <span className="truncate text-muted-foreground">· {context}</span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-muted-foreground">
            <span className={cn("size-2 rounded-xs", !lost && s?.headband.live ? "bg-ultramarine" : "bg-idle")} />
            {lost ? "no board" : !open ? "not connected" : s?.brake ? "braked" : s?.claude_code ? "driving Claude" : "live"}
            {open && s?.headband.battery != null && batteryText(s.headband.battery).replace(" · battery ", " · ")}
            {open && <BlinkLight n={s?.headband.blink_n ?? 0} />}
            <button
              type="button"
              aria-pressed={camera.state === "on"}
              title={camera.message || "Camera brake: the webcam sees your eyes close and brakes Claude. Uses your camera."}
              onClick={camera.toggle}
              className={cn(
                "ml-1 cursor-pointer rounded-sm border-0 bg-transparent px-1 text-tag [-webkit-app-region:no-drag]",
                camera.state === "on" ? "font-semibold text-ultramarine" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {camera.state === "on" ? "camera on" : camera.state === "starting" ? "camera…" : camera.state === "error" ? "camera (!)" : "camera"}
            </button>
            <button
              type="button"
              title="Close (⌃⌥Q)"
              aria-label="Close rein's floating window"
              onClick={() => window.close()}
              className="-mr-1 ml-1 grid size-6 cursor-pointer place-items-center rounded-sm border-0 bg-transparent text-muted-foreground hover:bg-muted hover:text-foreground [-webkit-app-region:no-drag]"
            >
              <X className="size-4" aria-hidden />
            </button>
          </span>
        </header>

        {!s ? (
          <p className="m-0 flex flex-1 items-center text-body text-muted-foreground">
            {lost ? "Start rein's board server, then this window connects by itself." : "Starting…"}
          </p>
        ) : !open ? (
          <Connect h={s.headband} />
        ) : s.overlay === "help" ? (
          <div className="relative grid flex-1 place-items-center overflow-hidden rounded-lg bg-ultramarine text-center text-white">
            <FlickeringGrid className="absolute inset-0" squareSize={3} gridGap={3} color="#ffffff" maxOpacity={0.18} flickerChance={0.2} />
            <div className="relative">
              <p className="m-0 text-headline font-medium leading-none tabular-nums">{Math.ceil(s.left_s ?? 0)}</p>
              <p className="m-0 mt-1 text-body">Calling for help · close your eyes to cancel</p>
            </div>
          </div>
        ) : s.overlay === "back" ? (
          <div className="grid flex-1 content-center gap-3">
            <p className="m-0 text-title font-medium tracking-[-0.04em]">Go back?</p>
            <p className="m-0 text-label text-muted-foreground">
              <Key>Bite down</Key> to go back. Do nothing to stay.
            </p>
            <Progress value={((s.left_s ?? 0) / 3) * 100} className="h-2 rounded-xs bg-border" />
          </div>
        ) : (
          <>
            {s.brake && <Brake compact className="px-3 py-1.5" />}
            <BrainPanel compact s={s} />
            {s.agent && (
              <div className="grid gap-1">
                <p className="m-0 text-tag font-semibold uppercase tracking-[0.08em] text-muted-foreground">{s.agent.title}</p>
                <p className={cn("m-0 line-clamp-2 [overflow-wrap:anywhere]", s.agent.kind === "permission" ? "font-mono text-body" : "text-label")}>
                  {s.agent.detail || "Done."}
                </p>
              </div>
            )}
            {s.screen === "confirm" || (s.screen === "options" && s.finding) ? <Sentence s={s} /> : <Cards s={s} />}
          </>
        )}

        <footer className="flex items-center justify-between gap-3 text-tag text-muted-foreground">
          <span>
            <Key>⌃⌥</Key> + <Key>← →</Key> glance · <Key>↓</Key> bite · <Key>↑</Key> back · <Key>E</Key> eyes closed · <Key>H</Key> help
          </span>
        </footer>
      </div>
    </div>
  )
}

function Cards({ s }: { s: BoardState }) {
  const n = s.tiles.length
  const deck = JSON.stringify([s.screen, s.path, s.heard, s.agent?.detail, s.tiles.map((t) => t.label)])
  const last = useRef({ deck, lit: 0, dir: 1 })
  if (!n) return null
  const lit = Math.min(s.lit ?? (last.current.deck === deck ? last.current.lit : 0), n - 1)
  if (last.current.deck !== deck) last.current = { deck, lit, dir: 1 }
  else if (last.current.lit !== lit) last.current = { deck, lit, dir: (lit - last.current.lit + n) % n === 1 ? 1 : -1 }
  const { dir } = last.current
  const tile = s.tiles[lit]
  const side = (t: BoardState["tiles"][number] | null, arrow: string, right = false) => (
    <span className={cn("w-[22%] shrink-0 self-center text-label leading-tight text-muted-foreground [overflow-wrap:anywhere]", right && "text-right")}>
      {t && (right ? `${t.label} ${arrow}` : `${arrow} ${t.label}`)}
    </span>
  )
  return (
    <div className="flex min-h-[110px] flex-1 items-stretch gap-3">
      {side(n > 2 ? s.tiles[(lit - 1 + n) % n] : null, "‹")}
      <div className="relative flex-1 overflow-hidden rounded-lg bg-ultramarine text-white">
        <div className="absolute inset-0 transition-opacity duration-500" style={{ opacity: auraOpacity(s.headband.alpha) }}>
          <FlickeringGrid
            className="absolute inset-0 [mask-image:radial-gradient(120%_100%_at_100%_0%,#000_0%,transparent_65%)]"
            squareSize={3}
            gridGap={3}
            color="#ffffff"
            maxOpacity={0.32}
            flickerChance={0.15}
          />
        </div>
        <BorderBeam />
        <AnimatePresence initial={false} custom={dir} mode="popLayout">
          <motion.div
            key={`${deck}#${lit}`}
            custom={dir}
            variants={slide}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ duration: 0.3, ease: EASE }}
            className="relative z-10 flex h-full flex-col justify-between gap-2 p-4"
          >
            <span className="flex items-center justify-between text-tag font-semibold uppercase tracking-[0.08em] text-white/80">
              <span className="flex items-center gap-1.5">
                {tile.guess && (
                  <>
                    <Sparkles className="size-3" aria-hidden />
                    rein’s guess
                  </>
                )}
              </span>
              <span className="tabular-nums">
                {lit + 1} / {n}
              </span>
            </span>
            <span
              className={cn(
                "font-medium tracking-[-0.04em] [overflow-wrap:anywhere]",
                tile.label.length > 18 ? "text-title leading-[1.05]" : "text-headline leading-none",
              )}
            >
              {tile.label}
            </span>
            {s.auto_s != null && s.auto_total && <Autopilot left={s.auto_s} total={s.auto_total} className="text-label" />}
          </motion.div>
        </AnimatePresence>
      </div>
      {side(n > 1 ? s.tiles[(lit + 1) % n] : null, "›", true)}
    </div>
  )
}

function Sentence({ s }: { s: BoardState }) {
  const text = (s.finding ? s.plain : s.sentence) ?? ""
  return (
    <div className="grid flex-1 content-center gap-2">
      <p className="m-0 text-title font-medium leading-[1.05] tracking-[-0.04em]">{text}</p>
      <p className="m-0 text-label text-muted-foreground">
        <Key>Bite down</Key> to {s.action === "text" ? `send it to ${s.to}` : s.action === "call" ? `call ${s.to}` : "say it"}
        {s.finding ? " now" : ""} · <Key>close your eyes</Key> to go back
      </p>
    </div>
  )
}

function Connect({ h }: { h: Headband }) {
  const { devices, scanning, connectingTo, error, rescan, connect } = useDevices(h)
  if (h.phase === "connected" && h.calibrating) {
    const left = h.calibrate_left ?? 20
    return (
      <div className="grid flex-1 content-center gap-2">
        <p className="m-0 text-headline font-medium leading-none tracking-[-0.05em] tabular-nums">{Math.ceil(left)} s</p>
        <p className="m-0 text-label text-muted-foreground">Hold still while it learns you: sit upright, jaw relaxed, blink normally.</p>
        <Progress value={(left / 20) * 100} className="h-2 rounded-xs bg-border" />
      </div>
    )
  }
  if (h.phase === "connecting") {
    return <p className="m-0 flex flex-1 items-center text-body">Connecting to {h.device?.name ?? "the headband"}…</p>
  }
  const usable = (devices ?? []).filter((d) => d.supported).slice(0, 2)
  return (
    <div className="grid flex-1 content-center gap-2">
      <p className="m-0 text-label text-muted-foreground">
        {scanning ? "Looking for headbands…" : usable.length ? "Put your headband on, then connect it." : "No headband found. Turn the Muse on and keep it close."}
      </p>
      {usable.map((d) => (
        <div key={d.name} className="flex items-center justify-between gap-3 rounded-sm bg-background px-3 py-2">
          <span className="min-w-0 truncate font-medium">
            {d.name}
            <span className="font-normal text-muted-foreground">{d.simulated ? " · for testing" : ""}</span>
          </span>
          <Button type="button" className="h-9 rounded-sm px-4 text-label" disabled={!!connectingTo} onClick={() => connect(d.name)}>
            {connectingTo === d.name ? "Connecting…" : "Connect"}
          </Button>
        </div>
      ))}
      {!scanning && !usable.length && (
        <Button type="button" variant="outline" className="h-9 w-fit rounded-sm text-label" onClick={rescan}>
          Scan again
        </Button>
      )}
      {error && <p className="m-0 text-label font-medium">{error}</p>}
    </div>
  )
}
