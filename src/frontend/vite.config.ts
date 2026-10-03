import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// The FastAPI server serves dist/: `npm run build` once, or `npm run dev` to rebuild on every save.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { rolldownOptions: { input: { main: "index.html", gaze: "gaze.html" } } },
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
})
