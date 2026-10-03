import type { CameraBrake } from "@/hooks/useCameraBrake"
import { Fragment, type MouseEvent, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import { Kbd } from "@/components/ui/kbd"
import type { BoardState } from "@/lib/api"
import { cn } from "@/lib/utils"

/** A quiet underlined text button. It drops focus after a click, so Space (a bite) can't press it again. */
function TextButton({ onClick, ...props }: { onClick: () => void; children: ReactNode; pressed?: boolean; disabled?: boolean; title?: string }) {
  return (
    <Button
      type="button"
      variant="link"
      aria-pressed={props.pressed}
      disabled={props.disabled}
      title={props.title}
      onClick={(e: MouseEvent<HTMLButtonElement>) => {
        e.currentTarget.blur()
        onClick()
      }}
      className="h-auto p-0 text-label font-normal text-muted-foreground underline underline-offset-[0.18em] aria-pressed:font-semibold aria-pressed:text-ultramarine"
    >
      {props.children}
    </Button>
  )
}

type HeaderProps = {
  status: string
  live: boolean
  listen: { supported: boolean; listening: boolean; toggle: () => void }
  nerdOpen: boolean
  camera: CameraBrake
  onRecalibrate: () => void
  onDisconnect: () => void
  onNerd: () => void
}

export function Header({ status, live, listen, nerdOpen, camera, onRecalibrate, onDisconnect, onNerd }: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-4 px-[var(--pad-x)] pt-5">
      <div className="flex items-center gap-2.5 text-[1.2rem] font-semibold tracking-[-0.03em]">
        <img src="/alpha-mark.svg" alt="" width={34} height={26} />
        <span>Alpha</span>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-label text-muted-foreground" aria-live="polite">
        <span className={cn("size-2 rounded-xs", live ? "bg-ultramarine" : "bg-idle")} />
        <span>{status}</span>
        <TextButton
          onClick={listen.toggle}
          pressed={listen.listening}
          disabled={!listen.supported}
          title={listen.supported ? undefined : "Conversation mode needs Chrome or Edge"}
        >
          {listen.listening ? "Listening" : "Listen"}
        </TextButton>
        <TextButton onClick={onRecalibrate}>Recalibrate</TextButton>
        <TextButton onClick={onDisconnect}>Disconnect</TextButton>
        <TextButton onClick={camera.toggle} pressed={camera.state === "on" || camera.state === "starting"} title={camera.message || "The webcam sees your eyes close and brakes Claude. Uses your camera."}>
          Camera brake{camera.state === "starting" ? "…" : camera.state === "error" ? " (!)" : ""}
        </TextButton>
        {camera.state === "error" && <span className="max-w-[28ch] truncate" title={camera.message}>{camera.message}</span>}
        <TextButton onClick={onNerd} pressed={nerdOpen}>
          Stats for nerds
        </TextButton>
        <a className="underline decoration-1 underline-offset-4 hover:text-foreground" href="/gaze">Gaze</a>
        <a className="underline decoration-1 underline-offset-4 hover:text-foreground" href="/">Slides</a>
      </div>
    </header>
  )
}

/** Where the wearer is, or what someone in the room just said. */
export function Crumbs({ s, hearing }: { s: BoardState; hearing: string }) {
  return (
    <>
      <div className="min-h-[2.2em] px-[var(--pad-x)] pt-5 text-body text-muted-foreground">
        {s.screen === "agent" && s.agent ? (
          <>
            Claude Code › <b className="font-semibold text-foreground">{s.agent.title}</b>
          </>
        ) : s.screen === "replies" && s.heard ? (
          <>
            They said: <b className="font-semibold text-foreground">“{s.heard}”</b>
            {s.thinking && " · thinking of replies…"}
          </>
        ) : (
          ["Home", ...s.path].map((p, i, all) => (
            <Fragment key={i}>
              {i > 0 && " › "}
              {i === all.length - 1 ? <b className="font-semibold text-foreground">{p}</b> : p}
            </Fragment>
          ))
        )}
      </div>
      {hearing && <p className="mx-[var(--pad-x)] mb-0 mt-1.5 text-label text-muted-foreground">Hearing: {hearing}</p>}
    </>
  )
}

const KEYS: [string[], string, string?][] = [
  [["Space"], "bite down"],
  [["Space"], "2.5 s: help", "hold"],
  [["E"], "1.5 s: eyes closed", "hold"],
  [["←", "→"], "glance"],
  [["B"], "go back"],
  [["L"], "listen"],
  [["N"], "stats for nerds"],
]

export function KeysLegend() {
  return (
    <p className="m-0 flex flex-wrap items-center gap-x-5 gap-y-2 px-[var(--pad-x)] pb-5 text-label text-muted-foreground">
      Keyboard stand-in:
      {KEYS.map(([keys, what, before]) => (
        <span key={what} className="flex items-center gap-1.5">
          {before}
          {keys.map((k) => (
            <Kbd key={k} className="bg-card text-foreground">
              {k}
            </Kbd>
          ))}
          {what}
        </span>
      ))}
    </p>
  )
}

/** Browsers only allow sound after a click; reloaded while connected, this is that click. */
export function StartOverlay({ onStart }: { onStart: () => void }) {
  return (
    <button
      type="button"
      onClick={onStart}
      className="fixed inset-0 z-30 grid cursor-pointer place-items-center border-0 bg-background text-foreground"
    >
      <span className="grid gap-3.5 text-center">
        <span className="text-headline font-medium tracking-[-0.05em]">Click to start</span>
        <span className="text-body text-muted-foreground">Lets Alpha speak out loud.</span>
      </span>
    </button>
  )
}
