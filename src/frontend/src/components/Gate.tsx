import { motion } from "motion/react"
import { AlphaLogo } from "@/components/AlphaLogo"
import { RollText } from "@/components/RollText"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { FlickeringGrid } from "@/components/ui/flickering-grid"
import { Progress } from "@/components/ui/progress"
import { useDevices } from "@/hooks/useDevices"
import type { Headband } from "@/lib/api"
import { cn } from "@/lib/utils"

const CALIBRATE_S = 20
const signal = (rssi?: number | null) =>
  rssi == null ? "" : rssi > -60 ? " · strong signal" : rssi > -75 ? " · good signal" : " · weak signal, move closer"

/** No board until a headband is connected and has learned the wearer's bite and blinks. */
export function Gate({ h, onConnectClick }: { h: Headband; onConnectClick: () => void }) {
  const { devices, scanning, connectingTo, error: shownError, rescan, connect } = useDevices(h, onConnectClick)
  const calibrating = h.phase === "connected" && h.calibrating

  const title: [string, string?][] = calibrating
    ? [["Hold still while it "], ["learns you.", "text-ultramarine"]]
    : h.phase === "connecting"
      ? [["Connecting to "], [`${h.device?.name ?? "the headband"}…`, "text-ultramarine"]]
      : [["Put your headband on, "], ["then connect it.", "text-ultramarine"]]
  const left = h.calibrate_left ?? CALIBRATE_S

  return (
    <div className="fixed inset-0 z-[25] grid place-items-center overflow-y-auto bg-background px-[var(--pad-x)] py-8">
      <FlickeringGrid
        className="pointer-events-none fixed inset-0 [mask-image:radial-gradient(80%_80%_at_85%_15%,#000_0%,transparent_70%)]"
        squareSize={6}
        gridGap={8}
        color="#0004f6"
        maxOpacity={0.22}
        flickerChance={0.08}
      />
      <div className="relative grid w-[min(680px,100%)] gap-[22px]">
        <AlphaLogo />
        <RollText
          key={title.map((p) => p[0]).join("")}
          parts={title}
          className="m-0 text-display font-medium leading-[0.98] tracking-[-0.05em]"
        />
        <p className="m-0 max-w-[46ch] text-body text-muted-foreground">
          {calibrating
            ? "Twenty seconds sitting upright, jaw relaxed, eyes open, reading this screen. Don't stare into space: the board learns your normal, awake brain waves, and your eyes-closed brake is measured against them."
            : "Hold the Muse's button until the lights sweep. Alpha opens once it's connected and has learned your jaw and blinks."}
        </p>

        {calibrating ? (
          <div className="grid gap-4">
            <p className="m-0 text-countdown font-medium leading-[0.9] tracking-[-0.06em] tabular-nums">
              {Math.ceil(left)}
              <small className="ml-2.5 text-body font-normal tracking-[-0.01em] text-muted-foreground">seconds</small>
            </p>
            <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
              {["Sit upright", "Jaw relaxed", "Read, eyes open"].map((x) => (
                <li key={x} className="rounded-full bg-card px-3 py-1.5 text-label">
                  {x}
                </li>
              ))}
            </ul>
            <Progress value={(left / CALIBRATE_S) * 100} className="h-2.5 rounded-xs bg-border" />
          </div>
        ) : (
          <div className="rounded-lg bg-card" aria-live="polite">
            <div className="flex items-baseline justify-between border-b px-[22px] pb-3.5 pt-[18px] text-label text-muted-foreground">
              <b className="font-medium text-foreground">Headbands nearby</b>
              <Button
                type="button"
                variant="link"
                className="h-auto p-0 text-label font-normal text-muted-foreground underline underline-offset-[0.18em]"
                onClick={rescan}
              >
                Scan again
              </Button>
            </div>
            {scanning ? (
              <p className="m-0 px-[22px] pb-[22px] pt-[18px] text-label text-muted-foreground">Looking for headbands…</p>
            ) : devices && !devices.length ? (
              <p className="m-0 px-[22px] pb-[22px] pt-[18px] text-label text-muted-foreground">
                <strong className="font-medium text-foreground">No headbands found.</strong> Turn the Muse on, keep it near this
                computer, and scan again.
              </p>
            ) : (
              (devices ?? []).map((d, i) => (
                <motion.div
                  key={d.name}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                  className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 border-t px-[22px] py-4 first:border-t-0"
                >
                  <div>
                    <div className={cn("font-medium tracking-[-0.02em]", !d.supported && "text-muted-foreground")}>{d.name}</div>
                    <div className="text-label text-muted-foreground">
                      {d.brand}
                      {d.simulated ? " · for testing" : signal(d.rssi)}
                    </div>
                  </div>
                  {d.supported ? (
                    <Button type="button" className="h-[46px] rounded-sm px-[18px] text-label font-medium" disabled={!!connectingTo} onClick={() => connect(d.name)}>
                      {connectingTo === d.name ? "Connecting…" : "Connect"}
                    </Button>
                  ) : (
                    <Badge variant="outline" className="rounded-full text-tag">
                      Support coming
                    </Badge>
                  )}
                </motion.div>
              ))
            )}
          </div>
        )}

        <p className={cn("m-0 min-h-[1.4em] text-label", shownError ? "font-medium text-foreground" : "text-muted-foreground")} aria-live="polite">
          {shownError}
        </p>
        <p className="m-0 text-label text-muted-foreground">
          Your picks go to Claude for sentence ideas and confirmed sentences to ElevenLabs for the voice. Texts and calls go out
          only when you confirm. In conversation mode, what people say is transcribed by Chrome's speech service. Nothing else
          leaves this computer.
        </p>
      </div>
    </div>
  )
}
