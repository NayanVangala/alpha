"""Measure how fast and how reliably your closed eyes stop Claude, to set the autopilot ring.

  1. Start the board (uv run --env-file .env python -m src.backend.server), open it, connect the headband and let it calibrate.
  2. PYTHONPATH=. uv run python scripts/closure_check.py

It talks to the running board over HTTP (so it never fights it for Bluetooth), says "close" and "open" ten times,
and records when the eyes-closed detector fires after each cue. It prints your delays, misses and false stops, and
the ring length that would let your veto win: the slowest typical delay plus two seconds.
"""

import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
TRIES = 10
HOLD_S = 14.0  # how long each closure may take before it counts as a miss


def say(text):
    print(f"  {text}", flush=True)
    subprocess.run(["say", text], check=False)


def events():
    """eyes-closed events as absolute times (the board reports them relative to now)."""
    now = time.time()
    n = httpx.get(f"{BASE}/api/nerd", timeout=3).json()
    return {round(now + t, 1) for t, kind in n.get("events", []) if kind == "eyes_closed"}


def main():
    try:
        st = httpx.get(f"{BASE}/api/state", timeout=3).json()
    except httpx.HTTPError:
        sys.exit("The board isn't running on :8000.")
    if st.get("phase") != "connected" or st.get("calibrating"):
        sys.exit("Connect the headband on the board and let it finish calibrating first.")
    seen, results, outside = events(), [], 0
    say("Ten eye closures. Keep your eyes open and relaxed until I say close. Close them gently, and open when I say open.")
    time.sleep(3)
    for i in range(1, TRIES + 1):
        time.sleep(random.uniform(6, 9))  # eyes open, relaxed
        for t in events() - seen:  # a stop fired while the eyes were meant to be open
            outside += 1
            seen.add(t)
        say(f"Close. {i} of {TRIES}")
        cue, delay = time.time(), None
        while time.time() - cue < HOLD_S and delay is None:
            time.sleep(0.25)
            fresh = events() - seen
            if fresh:
                seen |= fresh
                delay = max(0.0, min(fresh) - cue)
        say("Open.")
        results.append(delay)
        print(f"     {'caught after %.1f s' % delay if delay is not None else 'MISSED'}", flush=True)
        time.sleep(3)
    got = sorted(d for d in results if d is not None)
    out = {"delays": results, "false_stops": outside}
    print(f"\nCaught {len(got)} of {TRIES}; {outside} stop(s) fired while your eyes were open.")
    if got:
        p90 = got[min(len(got) - 1, math.ceil(0.9 * len(got)) - 1)]
        out.update(median=got[len(got) // 2], p90=p90, ring_s=math.ceil(p90 + 2))
        print(f"Delay: median {out['median']:.1f} s, slowest typical {p90:.1f} s.")
        print(f"A ring of {out['ring_s']} s would let your veto win (board.py AUTO_S and TALK_S are 6 s now).")
    if len(got) < 7:
        print("Fewer than 7 of 10: the brain brake isn't reliable on this headband fit yet. Re-seat it and try again.")
    Path("data").mkdir(exist_ok=True)
    Path(f"data/closure_check_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(json.dumps(out))
    say("Done. Thank you.")


if __name__ == "__main__":
    main()
