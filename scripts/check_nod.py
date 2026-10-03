"""Teach Alpha which of the Muse's gyroscope axes your nods and shakes swing about.

  PYTHONPATH=. uv run python scripts/check_nod.py

Spoken, about 40 seconds: nod yes for a while, then shake no, then sit still. It writes data/head_axes.json
(read by the coach) and says how clearly the two movements separate. Run it with the headband on.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.backend.signals import IMU_FS, NodShakeDetector
from src.backend.sources import MuseSource

OUT = Path("data/head_axes.json")


def say(text):
    print(f"\n{text}", flush=True)
    subprocess.run(["say", text], check=False)


def record(source, seconds):
    got, end = [], time.time() + seconds
    while time.time() < end:
        time.sleep(0.05)
        g = source.read().get("gyro")
        if g is not None and g.shape[1]:
            got.append(g)
    return np.hstack(got) if got else np.empty((3, 0))


def main():
    source = MuseSource()
    print("Connecting to the Muse (can take ~10 s)…", flush=True)
    source.start()
    try:
        record(source, 3)  # settle
        say("Nod yes, slowly, again and again, until I say stop.")
        nods = record(source, 8)
        say("Stop. Now shake your head no, again and again.")
        shakes = record(source, 8)
        say("Stop. Sit still.")
        still = record(source, 5)
    finally:
        source.stop()
    if min(nods.shape[1], shakes.shape[1], still.shape[1]) < IMU_FS * 3:
        sys.exit("Not enough gyroscope data came through: is the headband sending it?")
    rms = lambda g: np.sqrt(np.mean(np.square(g - g.mean(axis=1, keepdims=True)), axis=1))  # noqa: E731
    n, s, q = rms(nods), rms(shakes), rms(still)
    nod_axis, shake_axis = int(np.argmax(n)), int(np.argmax(s))
    print(f"\nSwing size by axis (deg/s RMS)  x / y / z\n  nodding : {np.round(n, 1)}\n  shaking : {np.round(s, 1)}\n  still   : {np.round(q, 1)}")
    if nod_axis == shake_axis:
        sys.exit(f"Nodding and shaking both move axis {nod_axis} most: they can't be told apart. Try bigger, slower movements.")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"nod": nod_axis, "shake": shake_axis}))
    print(f"\nNod = axis {nod_axis}, shake = axis {shake_axis}. Saved {OUT}.")
    d, hits = NodShakeDetector(nod_axis, shake_axis), {"nod": 0, "shake": 0, "still": 0}
    for name, g in (("nod", nods), ("shake", shakes), ("still", still)):
        d = NodShakeDetector(nod_axis, shake_axis)
        for i in range(0, g.shape[1], 13):
            for kind in d.feed(g[:, i : i + 13]):
                hits[name if name == "still" else kind] += 1 if name == "still" or kind == name else 0
    print(f"Replayed through the detector: {hits['nod']} nods, {hits['shake']} shakes, {hits['still']} false while still.")


if __name__ == "__main__":
    main()
