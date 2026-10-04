import type { CameraBrake } from "@/hooks/useCameraBrake"
import { isNarrating, setNarrating } from "@/lib/speech"
import { useState, type MouseEvent, type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { BlinkLight } from "@/components/Chrome"

/** A seamless sidebar button. Blurs after click so Space (a bite) can't press it again. */
function SideButton({
  onClick,
  pressed,
  disabled,
  title,
  children,
}: {
  onClick: () => void
  children: ReactNode
  pressed?: boolean
  disabled?: boolean
  title?: string
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      disabled={disabled}
      title={title}
      onClick={(e: MouseEvent<HTMLButtonElement>) => {
        e.currentTarget.blur()
        onClick()
      }}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
        "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
        "disabled:pointer-events-none disabled:opacity-50",
        pressed && "bg-ultramarine/10 font-medium text-ultramarine hover:bg-ultramarine/15 hover:text-ultramarine",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-1.5 shrink-0 rounded-full transition-colors",
          pressed ? "bg-ultramarine" : "bg-border",
        )}
      />
      {children}
    </button>
  )
}

function SideLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
    >
      <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-border" />
      {children}
    </a>
  )
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5">
      <p className="px-3 pb-1 text-[0.68rem] font-medium uppercase tracking-[0.08em] text-muted-foreground/70">{label}</p>
      {children}
    </div>
  )
}

export type SidebarProps = {
  status: string
  live: boolean
  listen: { supported: boolean; listening: boolean; toggle: () => void }
  nerdOpen: boolean
  blinks: number
  camera: CameraBrake
  onRecalibrate: () => void
  onDisconnect: () => void
  onNerd: () => void
}

/** Left sidebar: status, controls, device and views. On small screens it becomes a top bar. */
export function Sidebar({ status, live, listen, nerdOpen, blinks, camera, onRecalibrate, onDisconnect, onNerd }: SidebarProps) {
  const [narrating, setNarr] = useState(isNarrating)
  return (
    <aside
      aria-label="rein controls"
      className={cn(
        "z-10 flex shrink-0 gap-1 overflow-x-auto border-b bg-card px-3 py-2",
        "md:sticky md:top-0 md:h-screen md:w-60 md:flex-col md:gap-5 md:overflow-y-auto md:overflow-x-visible md:border-b-0 md:border-r md:px-4 md:py-6",
      )}
    >
      <div className="flex items-center gap-2.5 px-1 md:px-3">
        <span className="text-[1.15rem] font-semibold tracking-[-0.03em]">
          rein<span className="text-ultramarine">.</span>
        </span>
        <span className={cn("size-2 rounded-full", live ? "bg-ultramarine" : "bg-idle")} aria-label={live ? "live" : "idle"} />
      </div>

      <div className="hidden min-w-0 md:block" aria-live="polite">
        <p className="truncate px-3 text-xs text-muted-foreground" title={status}>
          {status}
        </p>
        <div className="px-3 pt-1 text-xs text-muted-foreground">
          <BlinkLight n={blinks} />
        </div>
      </div>

      <div className="hidden md:block">
        <Section label="Controls">
          <SideButton
            onClick={listen.toggle}
            pressed={listen.listening}
            disabled={!listen.supported}
            title={listen.supported ? undefined : "Conversation mode needs Chrome or Edge"}
          >
            {listen.listening ? "Listening" : "Listen"}
          </SideButton>
          <SideButton
            onClick={() => {
              setNarrating(!narrating)
              setNarr(!narrating)
            }}
            pressed={narrating}
            title="Reads each of Claude's questions aloud, and says when it's stopped"
          >
            Narration
          </SideButton>
          <SideButton
            onClick={camera.toggle}
            pressed={camera.state === "on" || camera.state === "starting"}
            title={camera.message || "The webcam sees your eyes close and brakes Claude. Uses your camera."}
          >
            Camera brake{camera.state === "starting" ? "…" : camera.state === "error" ? " (!)" : ""}
          </SideButton>
        </Section>
      </div>

      <div className="hidden md:block">
        <Section label="Device">
          <SideButton onClick={onRecalibrate}>Recalibrate</SideButton>
          <SideButton onClick={onDisconnect}>Disconnect</SideButton>
        </Section>
      </div>

      <div className="hidden md:block">
        <Section label="Views">
          <SideButton onClick={onNerd} pressed={nerdOpen}>
            Stats for nerds
          </SideButton>
          <SideLink href="/gaze">Gaze</SideLink>
          <SideLink href="/">Slides</SideLink>
        </Section>
      </div>

      {/* small screens: the essentials in a horizontal bar */}
      <div className="flex items-center gap-1 md:hidden" aria-live="polite">
        <SideButton onClick={listen.toggle} pressed={listen.listening} disabled={!listen.supported}>
          {listen.listening ? "Listening" : "Listen"}
        </SideButton>
        <SideButton onClick={onNerd} pressed={nerdOpen}>
          Stats
        </SideButton>
        <SideButton
          onClick={camera.toggle}
          pressed={camera.state === "on" || camera.state === "starting"}
          title={camera.message || undefined}
        >
          Camera{camera.state === "error" ? " (!)" : ""}
        </SideButton>
        <SideLink href="/gaze">Gaze</SideLink>
      </div>
    </aside>
  )
}
