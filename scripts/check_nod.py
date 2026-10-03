"""Teach rein which of the Muse's gyroscope axes your nods and shakes swing about.

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
    """Gyro and accelerometer for `seconds`: two (3, n) arrays."""
    gyro, accel, end = [], [], time.time() + seconds
    while time.time() < end:
        time.sleep(0.05)
        d = source.read()
        for out, key in ((gyro, "gyro"), (accel, "accel")):
            if d.get(key) is not None and d[key].shape[1]:
                out.append(d[key])
    return (np.hstack(gyro) if gyro else np.empty((3, 0)), np.hstack(accel) if accel else np.empty((3, 0)))


def main():
    source = MuseSource()
    print("Connecting to the Muse (can take ~10 s)…", flush=True)
    for attempt in range(6):  # about a minute: it may still be off, or asleep
        try:
            source.start()
            break
        except RuntimeError:
            if attempt == 5:
                raise
            if attempt == 0:
                say("I can't find the headband. Hold its button until the lights sweep.")
    try:
        record(source, 3)  # settle
        say("Look at the screen. Nod yes, chin all the way down to your chest and back up, ten times, starting now.")
        record(source, 1)  # a beat to react
        nods, nods_a = record(source, 8)
        say("Stop. Now turn your head all the way left, then all the way right, ten times, starting now.")
        record(source, 1)
        shakes, shakes_a = record(source, 8)
        say("Stop. Now sit completely still, looking at the screen.")
        record(source, 2)
        still, still_a = record(source, 5)
    finally:
        source.stop()
    if min(nods.shape[1], shakes.shape[1], still.shape[1]) < IMU_FS * 3:
        sys.exit(f"Not enough gyroscope data came through (nods {nods.shape[1]}, shakes {shakes.shape[1]}, still {still.shape[1]} samples; "
                 f"about {8 * IMU_FS}, {8 * IMU_FS} and {5 * IMU_FS} expected): the stream dropped out, so power-cycle the headband and rerun.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    Path("data").mkdir(exist_ok=True)
    np.savez(f"data/nod_check_{stamp}.npz", nods=nods, shakes=shakes, still=still, nods_a=nods_a, shakes_a=shakes_a, still_a=still_a)
    for name, g in (("nodding", nods), ("shaking", shakes), ("still", still)):  # what each second looked like
        per = [np.round(np.sqrt(np.mean(np.square(g[:, i : i + IMU_FS] - g[:, i : i + IMU_FS].mean(axis=1, keepdims=True)), axis=1))) for i in range(0, g.shape[1] - IMU_FS + 1, IMU_FS)]
        print(f"  {name:8} per second, x/y/z RMS: " + "  ".join("/".join(f"{int(v)}" for v in row) for row in per))
    for name, a in (("nodding", nods_a), ("shaking", shakes_a), ("still", still_a)):
        if a.shape[1]:
            print(f"  accel swing while {name:8} (peak-to-peak g, x/y/z): {np.round(np.ptp(a, axis=1), 2)}")
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
