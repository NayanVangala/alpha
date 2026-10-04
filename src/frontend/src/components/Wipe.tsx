import { type CSSProperties, useEffect, useMemo, useRef } from "react"

const COLS = 20
const ROWS = 12

/**
 * Page change: the screen goes solid ultramarine, then clears in a ragged left-to-right sweep of blocks
 * (about 0.6 s). It also runs once on load, sweeping away the blue the page starts under.
 */
export function Wipe({ page }: { page: string | null }) {
  const ref = useRef<HTMLDivElement>(null)
  const last = useRef<string | null>(null)
  const delays = useMemo(
    () => Array.from({ length: COLS * ROWS }, (_, i) => ((i % COLS) / COLS) * 0.28 + Math.random() * 0.08),
    [],
  )

  useEffect(() => {
    // never leave the page blue if the server doesn't answer
    const t = setTimeout(() => {
      document.getElementById("boot")?.remove()
      ref.current?.classList.remove("cover")
    }, 2500)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    const el = ref.current
    if (page === null || !el || page === last.current) return
    const first = last.current === null
    last.current = page
    if (first) document.getElementById("boot")?.remove() // the first page is drawn underneath now
    el.classList.add("cover")
    void el.offsetWidth // commit the solid frame before the sweep starts
    el.classList.remove("cover")
  }, [page])

  return (
    <div
      ref={ref}
      className="wipe cover"
      aria-hidden
      style={{ gridTemplate: `repeat(${ROWS}, 1fr) / repeat(${COLS}, 1fr)` }}
    >
      {delays.map((d, i) => (
        <span key={i} style={{ "--d": `${d}s` } as CSSProperties} />
      ))}
    </div>
  )
}
