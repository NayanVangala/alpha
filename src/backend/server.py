"""Dashboard server: serves the UI, scans for headbands, runs the coach for the connected one.

  uv run python -m src.backend.server           # real Bluetooth scan (Muse 2)
  uv run python -m src.backend.server --sim     # the scan offers a labeled simulated Muse instead
  add --demo for short timers on stage, then open http://localhost:8000
"""

import argparse
import itertools
import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Annotated, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import actions
from . import claude_code as cc
from .board import MAX_TILES, SCAN_S, Board, load_menu
from .coach import DEMO_TIMING, SAMPLE_EVERY_S, TIMING, Coach, open_db
from .history import open_history, record, suggestions
from .scan import scan
from .sources import MuseSource, SimSource
from .suggest import options as ai_options
from .suggest import replies as ai_replies
from .voice import speech_file

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
UI = FRONTEND / "dist"  # the board's React app, built by `npm run build` in src/frontend
DATA = Path("data")
app = FastAPI()
# only answer to our own host names, so a DNS-rebinding page can't read the log
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
contacts = actions.load_contacts()


def act(kind, text, to):
    """The board confirmed a text, a call or help: run it off the request thread, then report back."""
    def run():
        c = actions.help_contact(contacts) if kind == "help" else next(c for c in contacts if c["name"] == to)
        steps = [actions.send_text, actions.place_call] if kind == "help" else \
            [actions.send_text if kind == "text" else actions.place_call]
        notes = []
        for step in steps:  # help still calls if the text fails
            try:
                notes.append(step(c, text))
            except OSError as e:
                notes.append(f"Couldn't reach {c['name']}: {e}")
        board.notify(" · ".join(notes))
    threading.Thread(target=run, daemon=True).start()


def suggest(path, phrase, token, recent):
    """Ask the AI for fuller sentences off the request thread; the board always hears back."""
    def run():
        found = []
        try:
            found = ai_options(path, phrase, recent)
        finally:  # even a crash answers, so the board isn't left on "Finding"
            board.options_ready(token, found)
    threading.Thread(target=run, daemon=True).start()


def suggest_replies(heard, dialog, token):
    """Ask the AI for replies to what was just said, off the request thread; the board always hears back."""
    def run():
        found = []
        try:
            found = ai_replies(heard, dialog)
        finally:
            board.replies_ready(token, found)
    threading.Thread(target=run, daemon=True).start()


history = open_history()
# outside the session, so the keyboard works with no headband
board = Board(load_menu(contacts=contacts), act=act, suggest=suggest,
              remember=lambda sentence, action, to: record(history, sentence, action, to),
              recall=lambda: suggestions(history), reply=suggest_replies)


class Session:
    """The one headband connection: locked -> connecting -> connected -> locked."""

    def __init__(self, simulated=False, timing=TIMING):
        self.simulated, self.timing = simulated, timing
        self.phase, self.device, self.error = "locked", None, None
        self.devices, self.scanning = [], False
        self.source = self.coach = None
        self.db_path = DATA / ("sim.db" if simulated else "coach.db")  # rehearsals never mix into real data

    def scan(self):
        self.scanning, self.error = True, None
        try:
            self.devices = scan(simulated=self.simulated)
        except Exception as e:  # Bluetooth off or permission denied
            self.devices, self.error = [], f"Couldn't scan Bluetooth: {e}. Check Bluetooth is on and allowed for this terminal."
        finally:
            self.scanning = False
        return self.devices

    def connect(self, name):
        device = next((d for d in self.devices if d["name"] == name), None)
        if device is None or not device["supported"]:
            raise HTTPException(400, f"{name} isn't a supported headband. Scan again and pick a Muse 2.")
        if self.phase != "locked":
            raise HTTPException(409, "Already connected. Disconnect first.")
        self.phase, self.device, self.error = "connecting", device, None
        threading.Thread(target=self._connect, args=(device,), daemon=True).start()

    def _connect(self, device):
        source = SimSource() if device["simulated"] else MuseSource(device["name"])
        try:
            source.start()
        except Exception as e:  # out of range, already paired elsewhere, Bluetooth off
            self.phase, self.device = "locked", None
            self.error = f"Couldn't connect to {device['name']}: {e}. Make sure it's on and close to this Mac, then try again."
            return
        # a headband that dropped mid-demo reconnects with its last calibration instead of 20 s of sitting still
        cal_file, real = self.db_path.parent / "calibration.json", not device["simulated"]
        try:
            saved = json.loads(cal_file.read_text()) if real else {}
        except (OSError, ValueError):
            saved = {}

        def keep(cal):
            saved[device["name"]] = cal
            cal_file.write_text(json.dumps(saved))

        # the simulator's random long clenches would keep opening the help countdown; use the keyboard with it
        coach = Coach(source, open_db(self.db_path), timing=self.timing,
                      nudge=lambda *a: None,  # Alpha isn't the old posture coach: no pop-ups over a conversation
                      on_gesture=board.handle if real else None,
                      calibration=saved.get(device["name"]), on_calibrated=keep if real else None)
        coach.state.update(simulated=device["simulated"], demo=self.timing is DEMO_TIMING)
        self.source, self.coach, self.phase = source, coach, "connected"
        threading.Thread(target=coach.run, daemon=True).start()

    def disconnect(self):
        if self.coach:
            self.coach.stop()
        if self.source:
            try:
                self.source.stop()
            except Exception:  # already gone; nothing left to release
                pass
        self.phase, self.device, self.source, self.coach = "locked", None, None, None


session = Session()


@app.middleware("http")
async def same_origin_writes(request: Request, call_next):
    """Any site open in the browser can POST here; only the dashboard itself may."""
    origin = request.headers.get("origin")
    if request.method != "GET" and origin not in (None, f"http://{request.headers.get('host')}"):
        return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)
    return await call_next(request)


def query(sql, args=()):
    with closing(sqlite3.connect(session.db_path)) as db:
        return db.execute(sql, args).fetchall()


def running_coach():
    if session.coach is None:
        raise HTTPException(409, "Connect a headband first.")
    return session.coach


@app.get("/")
@app.get("/board")
def board_page():
    """The board. It stays behind its connect screen until a headband is connected and calibrated."""
    if not (UI / "index.html").exists():
        return Response("Build the board first: cd src/frontend && npm install && npm run build", 503, media_type="text/plain")
    return FileResponse(UI / "index.html", headers={"Cache-Control": "no-cache"})  # a reload always gets the newest build


app.mount("/assets", StaticFiles(directory=UI / "assets", check_dir=False), name="assets")


@app.get("/alpha-logo.svg")
@app.get("/alpha-mark.svg")
def logo(request: Request):
    """Alpha's logo (scripts/make_logo.py draws both)."""
    return FileResponse(FRONTEND / "public" / request.url.path.lstrip("/"), media_type="image/svg+xml")


@app.get("/coach")
def coach_page():
    """The earlier Screen Body Coach dashboard."""
    return FileResponse(FRONTEND / "coach.html")


def headband():
    """Where the connection stands, for the board's connect screen."""
    out = {"phase": session.phase, "device": session.device, "error": session.error, "scanning": session.scanning,
           "live": False, "calibrating": False, "calibrate_left": None, "alpha": None, "muscle": None, "battery": None}
    if session.coach is not None:
        st = session.coach.state
        until = st.get("calibrate_until")
        out.update(live=st.get("live", False), calibrating=st.get("calibrating", False), alpha=st.get("alpha"),
                   muscle=st.get("muscle"), battery=st.get("battery"), stream=session.source.stream() if hasattr(session.source, "stream") else None,
                   error=st.get("error") or session.error,
                   calibrate_left=max(0.0, until - time.time()) if until else None)
    return out


@app.get("/api/board")
def board_state():
    return {**board.state(), "headband": headband(), "claude_code": armed()}


class InputRequest(BaseModel):
    kind: Literal["clench", "long_clench", "double_blink", "glance_left", "glance_right", "eyes_closed"]
    ago: float = Field(0.0, ge=0, le=5)  # seconds since the clench began


@app.post("/api/input")
def board_input(req: InputRequest):
    """The board page's keyboard stand-in; the headband feeds board.handle directly.

    Refused until a headband (or the labeled simulator) is connected: the board is gated on the connection.
    """
    if session.phase != "connected":
        raise HTTPException(409, "Connect a headband first.")
    board.handle(req.kind, req.ago, by="keys")
    return {**board.state(), "headband": headband()}


class AskRequest(BaseModel):
    kind: Literal["permission", "next"]
    title: str = Field(min_length=1, max_length=120)
    detail: str = Field("", max_length=2000)
    options: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(min_length=1, max_length=MAX_TILES)
    auto: bool = False  # safe for the autopilot to run the first option by itself


ask_ids = itertools.count(1)


@app.post("/api/agent/ask")
def agent_ask(req: AskRequest):
    """A coding agent's question for the wearer (Claude Code, through src/backend/claude_code.py's hooks).

    Refused until a headband is connected, so the hook steps aside and Claude Code asks on its own screen.
    """
    if session.phase != "connected":
        raise HTTPException(409, "Connect a headband first.")
    qid = next(ask_ids)
    board.ask(qid, req.kind, req.title, req.detail, req.options, req.auto)
    return {"id": qid}


class SimEyesRequest(BaseModel):
    closed: bool


@app.post("/api/sim/eyes")
def sim_eyes(req: SimEyesRequest):
    """Simulator only: holding E shuts its eyes, so its alpha swells for the real detector and the meter."""
    if not isinstance(session.source, SimSource):
        raise HTTPException(409, "Only the simulated headband can close its eyes on command.")
    session.source.eyes_closed = req.closed
    return {"closed": req.closed}


ARM_S = 5  # the floating window repeats "I'm open" every 2 s; Alpha drives Claude Code only meanwhile
armed_until = 0.0


def armed():
    """Drive Claude Code from Alpha? Only while the floating window is open and a headband is connected."""
    return time.monotonic() < armed_until and session.phase == "connected"


@app.post("/api/agent/arm")
def agent_arm():
    """The floating window is open: drive Claude Code from Alpha for the next few seconds."""
    global armed_until
    armed_until = time.monotonic() + ARM_S
    return {"armed": armed()}


def local_ask(kind, title, detail, options, auto=False):
    """Put a Claude Code question on the board and wait for the wearer's pick: None if there isn't one."""
    qid = next(ask_ids)
    board.ask(qid, kind, title, detail, options, auto)
    deadline = time.monotonic() + cc.WAIT_S
    while time.monotonic() < deadline:
        done, answer = board.answer_of(qid)
        if done:
            return answer
        time.sleep(0.25)
    return None


HOOKS = {
    "SessionStart": lambda event: cc.on_session_start(event),
    "PreToolUse": lambda event: cc.on_pre_tool(event, board.braked),
    "PermissionRequest": lambda event: cc.on_permission(event, local_ask),
    "Stop": lambda event: cc.on_stop(event, local_ask),
}


@app.post("/api/hooks")
def claude_code_hook(event: dict):
    """Claude Code POSTs every hook event here (the Alpha plugin). An empty answer means "carry on as usual"."""
    handler = HOOKS.get(event.get("hook_event_name")) if armed() else None
    out = handler(event) if handler else None
    return out or Response(status_code=200)


@app.get("/api/agent/brake")
def agent_brake():
    """Checked by Claude Code's PreToolUse hook before every step: on while the wearer's closed eyes hold it."""
    return {"on": board.braked()}


@app.get("/api/agent/answer/{qid}")
def agent_answer(qid: int):
    """Polled by the hook: done once the wearer picked (answer) or went back (answer null)."""
    done, answer = board.answer_of(qid)
    return {"done": done, "answer": answer}


class HeardRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


@app.post("/api/heard")
def heard(req: HeardRequest):
    """Conversation mode: the board page's speech recognition heard someone say this."""
    if session.phase != "connected":
        raise HTTPException(409, "Connect a headband first.")
    board.heard(req.text.strip())
    return {**board.state(), "headband": headband()}


@app.get("/api/speech/{out_id}")
def speech(out_id: int):
    """Audio for something the board just said. 204 tells the page to use the browser voice.

    Only board outputs are voiced, so another site can't spend the ElevenLabs credits.
    """
    text = board.text_of(out_id)
    if text is None:
        raise HTTPException(404, "The board didn't say that.")
    path = speech_file(text)
    return FileResponse(path, media_type="audio/mpeg") if path else Response(status_code=204)


@app.get("/api/nerd")
def nerd():
    """Live signal numbers for the board's Stats for nerds panel."""
    snap = getattr(session.coach, "nerd", None)
    if not snap:
        return {"live": False, "phase": session.phase}
    return {**snap, "age_ms": round((time.time() - session.coach.last_data) * 1000)}  # as of this request


@app.get("/api/state")
def state():
    s = session
    out = {"phase": s.phase, "device": s.device, "error": s.error, "scanning": s.scanning, "simulated_scan": s.simulated}
    if s.coach is None:
        return out
    ((clenches, clench_s),) = query(
        "SELECT COUNT(*), COALESCE(SUM(value), 0) FROM events WHERE kind = 'clench' AND ts > ?", (time.time() - 3600,)
    )
    return {**s.coach.state, **out, "error": s.coach.state["error"] or s.error,
            "clenches_hour": clenches, "clench_seconds_hour": clench_s}


@app.post("/api/scan")
def scan_devices():
    return {"devices": session.scan(), "error": session.error}


class ConnectRequest(BaseModel):
    name: str


@app.post("/api/connect")
def connect(req: ConnectRequest):
    session.connect(req.name)
    return {"ok": True}


@app.post("/api/disconnect")
def disconnect():
    session.disconnect()
    return {"ok": True}


@app.post("/api/calibrate")
def calibrate():
    running_coach().want_calibration = True
    return {"ok": True}


def app_summary(hours=8):
    if not session.db_path.exists():
        return []
    since = time.time() - hours * 3600
    rows = query(
        """
        WITH s AS (SELECT app, COUNT(*) * ? / 60.0 AS minutes, AVG(tilt) AS tilt, AVG(hr) AS hr
                   FROM samples WHERE ts > ? GROUP BY app),
             e AS (SELECT app, SUM(kind = 'blink') AS blinks, SUM(kind = 'clench') AS clenches,
                          COALESCE(SUM(CASE WHEN kind = 'clench' THEN value END), 0) AS clench_s,
                          SUM(kind LIKE 'nudge_%') AS nudges
                   FROM events WHERE ts > ? GROUP BY app)
        SELECT s.app, ROUND(s.minutes, 1), ROUND(COALESCE(e.blinks, 0) / s.minutes, 1),
               ROUND(COALESCE(e.clenches, 0) * 60 / s.minutes, 1), ROUND(COALESCE(e.clench_s, 0), 1),
               ROUND(s.tilt, 1), ROUND(s.hr), COALESCE(e.nudges, 0)
        FROM s LEFT JOIN e USING (app) WHERE s.minutes >= 0.5 ORDER BY s.minutes DESC
        """,
        (SAMPLE_EVERY_S, since, since),
    )
    keys = ["app", "minutes", "blinks_per_min", "clenches_per_hour", "clench_seconds", "avg_tilt", "avg_hr", "nudges"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/apps")
def apps(hours: float = 8):
    return app_summary(min(hours, 24))


def main():
    global session
    ap = argparse.ArgumentParser()
    ap.add_argument("--sim", action="store_true", help="offer a labeled simulated headband instead of scanning Bluetooth")
    ap.add_argument("--demo", action="store_true", help="short timers, so every nudge shows within about a minute")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--scan", action="store_true", help="the highlight steps on its own, for wearers whose glances don't read")
    args = ap.parse_args()
    if args.scan:
        board.scan_s = SCAN_S

    session = Session(simulated=args.sim, timing=DEMO_TIMING if args.demo else TIMING)
    print(f"Alpha: http://localhost:{args.port}", flush=True)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        session.disconnect()


if __name__ == "__main__":
    main()
