import { type ClassValue, clsx } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

// rein's type scale (index.css). Without this, tailwind-merge reads `text-label` as a colour and drops the real one.
const twMerge = extendTailwindMerge({
  extend: { theme: { text: ["display", "headline", "title", "countdown", "body", "label", "tag"] } },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
