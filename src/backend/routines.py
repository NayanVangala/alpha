"""Routines: one bite starts a saved mission, so someone with no hands can begin work without typing a prompt.

A routine is either a Claude Code mission (a Terminal window opens in the project and Claude starts on it, with
every step still supervised by the brake and the bite rules) or a webhook (an n8n workflow, or anything else
that takes a POST). Defaults live here; data/routines.json (gitignored) adds or overrides by name.
"""

import json
import os
import shlex
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import actions

ROOT = Path(__file__).resolve().parents[2]
USER_FILE = Path("data/routines.json")
MAX = 6  # Home allows six tiles, and the routines screen shows these plus nothing else
DEFAULTS = [
    {"name": "Run the tests", "kind": "claude", "dir": "demo/pager",
     "mission": "Run the tests in this project. If any fail, find the cause and fix it, then run them again."},
    {"name": "Research alpha waves", "kind": "claude", "dir": "demo/web",
     "mission": "Open en.wikipedia.org and read the page on alpha waves, then write a five-line summary into notes.md."},
    {"name": "Find lunch", "kind": "claude", "dir": "demo/web",
     "mission": "Using the browser, find a highly-rated wheelchair-accessible restaurant near San Ramon, California. Write its name, address, rating, and one sentence on why it is a good pick into lunch.md in this directory. Then stop."},
    {"name": "Morning briefing", "kind": "claude", "dir": "demo/web",
     "mission": "It is morning. Get today's date. Open https://api.open-meteo.com/v1/forecast?latitude=37.78&longitude=-121.98&current=temperature_2m,weathercode&daily=temperature_2m_max,temperature_2m_min&timezone=America%2FLos_Angeles&temperature_unit=fahrenheit in the browser and read the current temperature and today's high and low. Write a 30-second spoken-style morning briefing (date, weather, whether a jacket is needed) into briefing.md in this directory. Then read it aloud with: say -f briefing.md. That last step will ask the wearer for a bite, which is correct: making sound needs approval. Then stop."},
    {"name": "Room remote", "kind": "claude", "dir": "demo/pager",
     "mission": "You are the wearer's room remote. Set this Mac's system volume to 70 percent with: osascript -e 'set volume output volume 70'. That step will ask the wearer for a bite, which is correct: the room must not change without approval. Do nothing else, then stop."},
    {"name": "Run my n8n workflow", "kind": "webhook", "env": "N8N_WEBHOOK_URL"},
]


def load_routines(path=USER_FILE, env=None):
    """The routines to offer: defaults plus the user's file, a webhook one only when its URL is set. Bad data fails at startup."""
    env = os.environ if env is None else env
    by_name = {r["name"]: r for r in DEFAULTS}
    if path.exists():
        for r in json.loads(path.read_text()):
            by_name[r["name"]] = r
    out = []
    for r in by_name.values():
        if r.get("kind", "claude") == "claude" and not (r.get("mission") and r.get("dir")):
            raise ValueError(f"routine {r.get('name')!r}: a Claude routine needs a mission and a dir")
        if r.get("kind") == "webhook" and not (r.get("url") or env.get(r.get("env", ""))):
            continue  # not set up on this machine: don't offer a tile that can't work
        out.append(r)
    return out[:MAX]


def ranked(routines, db):
    """Most used first (the same history the Home guesses come from); ties keep their order."""
    used = dict(db.execute("SELECT recipient, COUNT(*) FROM said WHERE action = 'routine' GROUP BY recipient").fetchall())
    return sorted(routines, key=lambda r: -used.get(r["name"], 0))


def _applescript(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


def terminal_command(routine):
    """The shell line a Terminal window runs: Claude Code, started on the mission, in the project."""
    return f"cd {shlex.quote(str(ROOT / routine['dir']))} && claude {shlex.quote(routine['mission'])}"


def start(routine, run=subprocess.run, post=None, env=None, platform=None):
    """Start the routine and say what happened, in one line for the board."""
    env = os.environ if env is None else env
    if routine.get("kind") == "webhook":
        url = routine.get("url") or env.get(routine.get("env", ""), "")
        if actions.dry_run():
            return f"Would start {routine['name']} (demo mode: nothing was sent)"
        body = json.dumps({"routine": routine["name"], "source": "alpha"}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return f"Started {routine['name']} ({r.status})"
        except OSError as e:
            return f"Couldn't start {routine['name']}: {e}"
    cmd = terminal_command(routine)
    if (platform or sys.platform) != "darwin":
        return f"Run this to start {routine['name']}: {cmd}"
    script = f'tell application "Terminal" to activate\ntell application "Terminal" to do script "{_applescript(cmd)}"'
    try:
        run(["osascript", "-e", script], check=True, capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return f"Couldn't open Terminal for {routine['name']}: {e}"
    return f"Started {routine['name']}: Claude is working in a new Terminal window"
