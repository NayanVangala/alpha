import { FlickeringGrid } from "@/components/ui/flickering-grid"

// The mark from public/rein-mark.svg (viewBox 4 4 56 50): an r with a pixel for its period.
const STEM = "M14 14V44"
const ARC = "M14 30C14 20 21 15 33 15"

function Letter({ stroke, width, dot }: { stroke: string; width: number; dot: string }) {
  return (
    <>
      <g fill="none" stroke={stroke} strokeWidth={width} strokeLinecap="round" strokeLinejoin="round">
        <path d={STEM} />
        <path d={ARC} />
      </g>
      <rect x="40" y="34" width="11" height="11" fill={dot} stroke={stroke} strokeWidth={width === 10 ? 0 : width - 10} />
    </>
  )
}

/**
 * rein's logo, live: the letter with an aura of flickering pixels rippling off it like brainwaves.
 * The pixels are drawn at whole device pixels, so they stay sharp at any size or screen density
 * (the static SVG's 2-unit dither cells blur into noise when scaled by a fraction).
 */
export function ReinLogo({ size = 168, ground = "#f2f2f2" }: { size?: number; ground?: string }) {
  return (
    <div role="img" aria-label="rein." className="relative shrink-0" style={{ width: size, height: size }}>
      <FlickeringGrid
        className="absolute inset-0 [mask-composite:intersect] [mask-image:radial-gradient(circle_at_50%_50%,#000_34%,transparent_71%),repeating-radial-gradient(circle_at_50%_50%,#000_0_7px,rgba(0,0,0,0.12)_7px_13px)]"
        squareSize={3}
        gridGap={1}
        color="#0004f6"
        maxOpacity={0.9}
        flickerChance={0.35}
      />
      {/* a ground-coloured outline cut round the strokes keeps the letter crisp against the pixels */}
      <svg viewBox="-8 -4 76 62" className="absolute inset-0 size-full" aria-hidden>
        <Letter stroke={ground} width={20} dot={ground} />
        <Letter stroke="#201d1d" width={10} dot="#0004f6" />
      </svg>
    </div>
  )
}
