import { FlickeringGrid } from "@/components/ui/flickering-grid"

// The letter from scripts/make_logo.py (viewBox 0 0 120 120): a round bowl, a hooked stem, a small tail.
const BOWL = { cx: 55, cy: 59, r: 19 }
const STEM = "M81 37C76 39 74 43 74 49C74 60 74 64 74 71C74 77 78 81 84 81"

function Letter({ stroke, width }: { stroke: string; width: number }) {
  return (
    <g fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round">
      <circle {...BOWL} />
      <path d={STEM} />
    </g>
  )
}

/**
 * Alpha's logo, live: the letter with an aura of flickering pixels rippling off it like brainwaves.
 * The pixels are drawn at whole device pixels, so they stay sharp at any size or screen density
 * (the static SVG's 2-unit dither cells blur into noise when scaled by a fraction).
 */
export function AlphaLogo({ size = 168, ground = "#f2f2f2" }: { size?: number; ground?: string }) {
  return (
    <div role="img" aria-label="Alpha" className="relative shrink-0" style={{ width: size, height: size }}>
      <FlickeringGrid
        className="absolute inset-0 [mask-composite:intersect] [mask-image:radial-gradient(circle_at_50%_50%,#000_34%,transparent_71%),repeating-radial-gradient(circle_at_50%_50%,#000_0_7px,rgba(0,0,0,0.12)_7px_13px)]"
        squareSize={3}
        gridGap={1}
        color="#0004f6"
        maxOpacity={0.9}
        flickerChance={0.35}
      />
      {/* a ground-coloured outline cut round the strokes keeps the letter crisp against the pixels */}
      <svg viewBox="4 8 112 112" className="absolute inset-0 size-full" aria-hidden>
        <Letter stroke={ground} width={21} />
        <Letter stroke="#0004f6" width={9} />
      </svg>
    </div>
  )
}
