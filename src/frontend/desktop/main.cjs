// Alpha's floating window: a small always-on-top board that sits over VS Code or any terminal (Mac and Windows),
// so the wearer can answer Claude Code without leaving it. It shows the board server's page in compact form (?hud).
// Run the board server first, then: cd src/frontend && npm run hud
const { app, BrowserWindow, globalShortcut, screen, session, systemPreferences } = require("electron")

const ALPHA = process.env.ALPHA_URL || "http://localhost:8000"
const W = 460
const H = 560

// The keyboard stand-in, global so it works while VS Code or the terminal keeps focus.
// Arrows read like the gestures: left/right glance, down = bite down, up = go back.
const KEYS = {
  "Control+Alt+Left": "glance_left",
  "Control+Alt+Right": "glance_right",
  "Control+Alt+Down": "clench",
  "Control+Alt+Up": "double_blink",
  "Control+Alt+H": "long_clench",
}

function post(path, body) {
  fetch(`${ALPHA}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).catch(() => {}) // board not running or no headband: nothing to do
}
const send = (kind) => post("/api/input", { kind })

// Ctrl+Opt+E: eyes closed, the brake. A key press can't be held like real eyes, so it stands in for a
// 2.5 s closure: the simulator shuts its eyes (its alpha swells on the meter) and the brake comes on at 1.5 s.
function closeEyes() {
  post("/api/sim/eyes", { closed: true }) // refused with a real headband, which reads your actual eyes
  setTimeout(() => send("eyes_closed"), 1500)
  setTimeout(() => post("/api/sim/eyes", { closed: false }), 2500)
}

// macOS: only a Dock-less (accessory) app can float over another app's full-screen Space, e.g. a full-screen VS Code
if (process.platform === "darwin") app.dock.hide()

app.whenReady().then(() => {
  // The camera brake needs the webcam: allowed for Alpha's own page only, and macOS is asked the first time it's used.
  const ours = (wc) => wc.getURL().startsWith(ALPHA)
  session.defaultSession.setPermissionCheckHandler((wc, permission) => permission === "media" && ours(wc))
  session.defaultSession.setPermissionRequestHandler(async (wc, permission, done) => {
    if (permission !== "media" || !ours(wc)) return done(false)
    done(process.platform === "darwin" ? await systemPreferences.askForMediaAccess("camera") : true)
  })
  const { workArea } = screen.getPrimaryDisplay()
  const win = new BrowserWindow({
    width: W,
    height: H,
    minWidth: 360,
    minHeight: 240,
    x: workArea.x + workArea.width - W - 16,
    y: workArea.y + workArea.height - H - 16,
    frame: false,
    transparent: true,
    hasShadow: false, // the page draws its own
    alwaysOnTop: true,
    fullscreenable: false,
    title: "Alpha",
    webPreferences: { backgroundThrottling: false }, // keep polling at full speed under other windows
  })
  win.setAlwaysOnTop(true, "screen-saver") // above full-screen windows too
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true }) // follows you to every Space
  const load = () => win.loadURL(`${ALPHA}/board?hud`)
  win.webContents.on("did-fail-load", (_e, code, why) => {
    console.log(`Can't reach Alpha at ${ALPHA} (${why}); retrying`) // board server not up yet: keep trying
    setTimeout(load, 1500)
  })
  win.webContents.on("did-finish-load", () => console.log(`Alpha's floating window is showing ${ALPHA}`))
  load()

  globalShortcut.register("Control+Alt+Q", () => app.quit()) // close the window; so does its × button
  globalShortcut.register("Control+Alt+E", closeEyes)
  const taken = Object.entries(KEYS).filter(([key, kind]) => !globalShortcut.register(key, () => send(kind)))
  if (taken.length) console.warn("These keys belong to another app:", taken.map(([key]) => key).join(", "))
})

app.on("will-quit", () => globalShortcut.unregisterAll())
app.on("window-all-closed", () => app.quit())
