import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import { Hud } from "./Hud"
import "./index.css"

// ?hud: the small always-on-top window from desktop/main.cjs, with no page wipe and a see-through background
const hud = new URLSearchParams(location.search).has("hud")
if (hud) {
  document.documentElement.classList.add("hud")
  document.getElementById("boot")?.remove()
}

createRoot(document.getElementById("root")!).render(<StrictMode>{hud ? <Hud /> : <App />}</StrictMode>)
