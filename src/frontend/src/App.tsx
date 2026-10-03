import { useCallback, useState } from "react"
import { Toaster, toast } from "sonner"
import { Crumbs, Header, KeysLegend, StartOverlay } from "@/components/Chrome"
import { AgentAsk } from "@/components/AgentAsk"
import { BrainPanel } from "@/components/Brain"
import { Brake } from "@/components/Brake"
import { Confirm } from "@/components/Confirm"
import { Deck } from "@/components/Deck"
import { Gate } from "@/components/Gate"
import { NerdPanel } from "@/components/NerdPanel"
import { Overlays } from "@/components/Overlays"
import { Wipe } from "@/components/Wipe"
import { useBoard } from "@/hooks/useBoard"
import { useKeys } from "@/hooks/useKeys"
import { useCameraBrake } from "@/hooks/useCameraBrake"
import { useListening } from "@/hooks/useListening"
import { useOutputs } from "@/hooks/useOutputs"
import { api, type Gesture } from "@/lib/api"
import { unlock } from "@/lib/speech"
import { cn } from "@/lib/utils"

/** " · battery 73%", with a warning when it's low enough to die mid-demo */
export const batteryText = (pct: number | null | undefined) =>
  pct == null ? "" : pct < 20 ? ` · battery LOW ${Math.round(pct)}%, charge it` : ` · battery ${Math.round(pct)}%`

export default function App() {
  const { s, setS, lost } = useBoard()
  const [started, setStarted] = useState(false)
  const [nerdOpen, setNerdOpen] = useState(false)
  const camera = useCameraBrake()
  const open = !!s && s.headband.phase === "connected" && !s.headband.calibrating && s.headband.calibration_ok !== false
  const ready = open && started // nothing reaches the board behind the connect screen or the start click

  const send = useCallback(
    async (kind: Gesture, ago = 0) => {
      const next = await api.input(kind, ago)
      if (next) setS(next)
    },
    [setS],
  )
  const listen = useListening(
    ready,
    async (text) => {
      const next = await api.heard(text)
      if (next) setS(next)
    },
    () => toast("The microphone is blocked. Allow it from the address bar to use conversation mode."),
  )
  const simulated = !!s?.headband.device?.simulated
  useKeys({
    enabled: ready,
    send,
    onListen: listen.toggle,
    onNerd: () => setNerdOpen((v) => !v),
    onEyes: (closed) => simulated && void api.simEyes(closed),
  })
  useOutputs(s)
  const start = () => {
    unlock()
    setStarted(true)
  }

  const page = !s
    ? null
    : !open
      ? `gate|${s.headband.phase}|${s.headband.calibrating}`
      : `${s.screen}|${s.path.join(">")}|${s.heard ?? ""}|${s.finding}|${s.agent?.detail ?? ""}`
  const cards = !!s && (s.screen === "menu" || s.screen === "agent" || ((s.screen === "options" || s.screen === "replies") && !s.finding))
  const h = s?.headband
  const device = h?.device ? h.device.name + (h.device.simulated ? " (simulated)" : "") : "No headband"
  const status = lost
    ? "Lost the server. Is it still running?"
    : `${device} · ${h?.calibrating ? "calibrating" : h?.live ? "live" : "not sending"}${batteryText(h?.battery)}${s?.claude_code ? " · driving Claude Code" : ""}`

  return (
    <>
      <Wipe page={page} />
      {!s && lost && (
        <p className="grid min-h-screen place-items-center text-body text-muted-foreground">Can't reach rein's server. Is it running?</p>
      )}
      {s && !open && <Gate h={s.headband} onConnectClick={start} />}
      {s && open && (
        <div className={cn("flex min-h-screen flex-col", nerdOpen && "min-[901px]:mr-[min(500px,42vw)]")}>
          <Header
            status={status}
            live={!lost && !!h?.live}
            listen={listen}
            nerdOpen={nerdOpen}
            blinks={h?.blink_n ?? 0}
            camera={camera}
            onRecalibrate={() => void api.calibrate()}
            onDisconnect={() => void api.disconnect()}
            onNerd={() => setNerdOpen((v) => !v)}
          />
          <Crumbs s={s} hearing={listen.interim} />
          {s.brake && <Brake className="mx-[var(--pad-x)] mt-3" />}
          {s.claude_code && <BrainPanel s={s} className="mx-[var(--pad-x)] mt-3 max-w-xl" />}
          <main className="flex flex-1 flex-col px-[var(--pad-x)] pb-6 pt-5">
            {s.agent && <AgentAsk agent={s.agent} alpha={s.headband.alpha} />}
            {cards ? <Deck s={s} /> : <Confirm s={s} />}
          </main>
          <KeysLegend />
        </div>
      )}
      {s && open && <Overlays s={s} />}
      {s && open && !started && <StartOverlay onStart={start} />}
      <NerdPanel open={nerdOpen} />
      <Toaster position="bottom-center" offset={84} toastOptions={{ className: "rein-toast" }} />
    </>
  )
}
