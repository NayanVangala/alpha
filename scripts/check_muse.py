"""Muse tuning session: about 2.5 minutes of prompts while wearing the headband, all of it recorded.

  uv run python -m scripts.check_muse [--serial Muse-XXXX] [--who sam]   record a session, then check it
  uv run python -m scripts.check_muse --replay data/muse_check_*.npz    check a saved session again (after tuning)
  uv run python -m scripts.check_muse --all                             score every saved session: how many people
                                                                        each gesture works for

Recordings are EEG from someone's head: ask before recording, keep them in data/ (never committed), and delete
anyone's on request.

rein's real detectors run over the recording, calibrated on its first 20 s the way the app calibrates,
and each step shows what fired against what was asked: bites, a held bite, double blinks, glances, eyes
closed, and things that must fire nothing (reading, turning the head, talking). The numbers underneath
(glance swing and polarity, alpha with eyes shut vs open, jaw level) are what the thresholds get tuned from.
Close the board app first: the headband talks to one program at a time.
"""

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfiltfilt

from src.backend.gestures import Gestures
from src.backend.signals import CHANNELS, CONTACT_UV, EEG_FS, BlinkDetector, ClenchDetector, EyesClosedDetector, band_rms

# (instruction, seconds, cue word or None, cue times in s from the step start, gesture expected per cue)
STEPS = [
    ("Sit still, eyes open, jaw relaxed, blink normally (rein calibrates on this)", 20, None, [], None),
    ("Bite down briefly (half a second) each time you see BITE", 12, "BITE", [2, 6, 10], "clench"),
    ("Hold a bite from HOLD until it says relax (help gesture)", 6, "HOLD", [1], "long_clench"),
    ("Look far LEFT when you see LEFT, then straight back", 12, "LEFT", [2, 6, 10], "glance_left"),
    ("Look far RIGHT when you see RIGHT, then straight back", 12, "RIGHT", [2, 6, 10], "glance_right"),
    ("Read this silently, line by line: 'rein lets someone who can't move or speak write code with Claude. "
     "Their eyes point, their jaw says yes, and their brain hits the brakes.' (nothing should fire)", 10, None, [], None),
    ("Close your eyes at CLOSE and keep them shut until OPEN", 20, "CLOSE", [2, 12], "eyes_closed"),
    ("Turn your head slowly left and right, then nod (nothing should fire)", 8, None, [], None),
    ("Talk out loud: count from one to ten, twice (no bites should fire)", 8, None, [], None),
]
# what the Mac says out loud at the start of each step, so the wearer can follow with eyes shut or away
SPOKEN = [
    "Sit still and relax for twenty seconds. Blink normally.",
    "Bite down briefly each time I say bite.",
    "Hold a bite when I say hold, until I say relax.",
    "Look far left when I say left, then straight back.",
    "Look far right when I say right, then straight back.",
    "Read some text on your screen silently, like this chat, until I say the next step.",
    "Close your eyes when I say close, and open them when I say open.",
    "Turn your head slowly left and right, then nod.",
    "Count out loud from one to ten, twice.",
]


def say(text):
    if shutil.which("say"):
        subprocess.Popen(["say", "-r", "210", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def record(source, serial, who=""):
    eeg, accel, marks, n = [], [], [], 0

    last_data = [time.time()]

    def pull():
        nonlocal n
        d = source.read()
        if d["eeg"].shape[1]:
            eeg.append(d["eeg"])
            accel.append(d["accel"])
            n += d["eeg"].shape[1]
            last_data[0] = time.time()
        elif time.time() - last_data[0] > 3:
            say("The headband stopped sending. It may need charging.")
            raise RuntimeError("the headband stopped sending for 3 s: low battery, or out of range?")

    print(f"Connecting to {serial or 'the nearest Muse'} over Bluetooth (can take ~10 s)…")
    for attempt in range(6):  # about a minute: it may still be off, or asleep after sitting idle
        try:
            source.start()
            break
        except RuntimeError:
            if attempt == 5:
                raise
            if attempt == 0:
                say("I can't find the headband. Hold its button until the lights sweep.")
                print("Can't find it yet: hold the Muse's button until its lights sweep…", flush=True)
    try:
        t_end = time.time() + 3
        while time.time() < t_end:  # let the stream settle
            time.sleep(0.1)
            pull()
        eeg.clear(), accel.clear()
        n = 0
        for i, (what, secs, cue, at, _) in enumerate(STEPS, 1):
            print(f"\n[{i}/{len(STEPS)}] {what}  ({secs} s)", flush=True)
            say(SPOKEN[i - 1])
            if at:  # let the instruction finish before the first cue
                t_end = time.time() + 2.5
                while time.time() < t_end:
                    time.sleep(0.05)
                    pull()
            start, cues, t0 = n, [], time.time()
            pending = list(at)
            while time.time() - t0 < secs:
                time.sleep(0.05)
                pull()
                if pending and time.time() - t0 >= pending[0]:
                    pending.pop(0)
                    cues.append(n)
                    print(f"\a   >>> {cue} <<<", flush=True)
                    say(cue.lower())
                    if cue == "CLOSE":
                        print("       (keep them shut…)", flush=True)
                        shut = time.time()
                        while time.time() - shut < 6:
                            time.sleep(0.05)
                            pull()
                        print("\a   >>> OPEN <<<", flush=True)
                        say("open")
            if cue == "HOLD":
                print("   relax", flush=True)
                say("relax")
            marks.append((start, n, cues))
    finally:
        source.stop()
    say("Done. Thank you.")
    tag = f"{who.strip().lower().replace(' ', '-')}_" if who.strip() else ""
    out = Path("data") / f"muse_check_{tag}{time.strftime('%Y%m%d_%H%M%S')}.npz"
    out.parent.mkdir(exist_ok=True)
    np.savez(out, eeg=np.concatenate(eeg, axis=1), accel=np.concatenate(accel, axis=1),
             marks=np.array([(a, b) for a, b, _ in marks]), cues=np.array([c for _, _, cs in marks for c in cs] or [0]),
             cue_step=np.array([k for k, (_, _, cs) in enumerate(marks) for _ in cs] or [0]),
             steps=np.array([step[0] for step in STEPS]))
    print(f"\nSaved the recording to {out}")
    return out


def check(path, quiet=False):
    """Prints the step-by-step check (unless quiet) and returns {step: True if it came out right}."""
    out = sys.stdout
    if quiet:
        sys.stdout = open("/dev/null", "w")
    try:
        return _check(path)
    finally:
        if quiet:
            sys.stdout.close()
            sys.stdout = out


def _check(path):
    rec = np.load(path)
    if "steps" in rec and [str(n) for n in rec["steps"]] != [step[0] for step in STEPS]:
        raise ValueError("recorded with a different set of steps")
    eeg, marks = rec["eeg"], [tuple(m) for m in rec["marks"]]
    rest = eeg[:, marks[0][0] : marks[0][1]]
    secs = eeg.shape[1] / EEG_FS
    print(f"\n=== {path}: {secs:.0f} s of EEG ({eeg.shape[1]} samples; ~{eeg.shape[1] / max(secs, 1):.0f}/s expected 256) ===")

    print(f"\nSensor contact while still (1-30 Hz RMS; good is {CONTACT_UV[0]}-{CONTACT_UV[1]} uV):")
    for name, rms in zip(CHANNELS, band_rms(rest)):
        print(f"  {name:17} {rms:7.1f} uV  {'ok' if CONTACT_UV[0] <= rms <= CONTACT_UV[1] else 'CHECK: adjust the band'}")

    # calibrate the way the app does, on the still 20 s
    blinks, clench, eyes = BlinkDetector(), ClenchDetector(), EyesClosedDetector()
    blinks.calibrate(rest[1], rest[2])
    clench.calibrate(rest)
    eyes.calibrate(rest)
    g = Gestures(clench.threshold_uv, eyes.threshold)
    stream_blinks = BlinkDetector(blinks.threshold_uv, blinks.sign)
    events, levels = [], []
    for i in range(0, eeg.shape[1], 64):
        c = eeg[:, i : i + 64]
        for kind, _ in g.feed(c, stream_blinks.feed(c[1], c[2])):
            events.append((i + c.shape[1], kind))
        levels.append((i, g.eyes.level))
    print(f"\nCalibrated: blink {blinks.threshold_uv:.0f} uV (polarity {blinks.sign:+d}), bite {clench.threshold_uv:.0f} uV, "
          f"eyes-closed alpha share {eyes.threshold:.2f}")

    print("\nStep by step (what fired vs what was asked):")
    ok_all, results = True, {}
    for k, (start, end) in enumerate(marks):
        what, _, _, at, want = STEPS[k]
        until = marks[k + 1][0] if k + 1 < len(marks) else end + 3 * EEG_FS  # bites report after release
        fired = [kind for idx, kind in events if start <= idx < until]
        if want:
            n_want = len(at)
            good = sum(1 for f in fired if f == want)
            extra = [f for f in fired if f != want]
            verdict = "OK" if good == n_want and not extra else "CHECK"
            print(f"  {verdict:5} {what[:58]:58} wanted {n_want} {want}, got {good}" + (f"; also {extra}" if extra else ""))
        else:
            unwanted = [f for f in fired if f != "double_blink"] if k == 0 else fired
            verdict = "OK" if not unwanted else "CHECK"
            print(f"  {verdict:5} {what[:58]:58} " + ("nothing fired" if not unwanted else f"fired {unwanted}"))
        ok_all &= verdict == "OK"
        results[what.split(" (")[0][:40]] = verdict == "OK"

    # the numbers the thresholds get tuned from
    lp = butter(2, 6, fs=EEG_FS, output="sos")
    h = sosfiltfilt(lp, eeg[1] - eeg[2])  # AF7 - AF8: swings one way for left, the other for right

    def swing(k):
        start, end = marks[k]
        if end <= start:
            return 0.0, 0.0  # no data in that step
        seg = h[start:end] - np.median(h[start:end])
        return seg.max(), seg.min()

    left, right, read = (swing(next(i for i, s in enumerate(STEPS) if s[0].startswith(p))) for p in ("Look far LEFT", "Look far RIGHT", "Read"))
    print("\nGlances (AF7 minus AF8, low-passed; the detector fires past 60 uV with polarity +1 = left goes up):")
    print(f"  look left : peak +{left[0]:.0f} / {left[1]:.0f} uV")
    print(f"  look right: peak +{right[0]:.0f} / {right[1]:.0f} uV")
    print(f"  reading   : peak +{read[0]:.0f} / {read[1]:.0f} uV   (must stay under the threshold)")
    polarity = 1 if left[0] > -left[1] else -1
    print(f"  -> left swings {'up' if polarity == 1 else 'DOWN: flip GlanceDetector sign to -1'}")

    share = lambda a, b: [eyes.share(eeg[[0, 3], i : i + EEG_FS]) for i in range(a, b - EEG_FS, EEG_FS // 2)]  # noqa: E731
    k_eyes = next(i for i, s in enumerate(STEPS) if s[0].startswith("Close your eyes"))
    closed = [s for c in (rec["cues"][rec["cue_step"] == k_eyes]) for s in share(c + EEG_FS, c + 5 * EEG_FS)]
    print(f"\nEyes (alpha's share of 4-30 Hz behind the ears): open {np.median(share(*marks[0])):.2f}, "
          f"shut {np.median(closed) if closed else float('nan'):.2f}; brake line {eyes.threshold:.2f} "
          f"(= {EyesClosedDetector.RISE} x open). Shut/open ratio {np.median(closed) / np.median(share(*marks[0])) if closed else float('nan'):.1f}x")
    print("\nAll steps OK." if ok_all else "\nSome steps need tuning: send me the file name above.")
    return results


def score_all():
    paths = sorted(Path("data").glob("muse_check_*.npz"))
    if not paths:
        sys.exit("No sessions in data/ yet.")
    scores = {}
    for path in paths:
        try:
            for step, ok in check(path, quiet=True).items():
                scores.setdefault(step, []).append(ok)
        except Exception as e:  # an older session recorded with different steps
            print(f"skipped {path.name}: {e}")
    print(f"{len(paths)} session(s). Gesture by gesture, how many came out right:")
    for step, oks in scores.items():
        print(f"  {sum(oks):>3}/{len(oks):<3} {step}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial", default="", help="Muse name, e.g. Muse-1A2B (default: the first one found)")
    ap.add_argument("--replay", help="check a saved recording instead of recording a new one")
    ap.add_argument("--who", default="", help="whose session this is, for the file name (ask them first)")
    ap.add_argument("--all", action="store_true", help="score every saved session")
    args = ap.parse_args()
    if args.all:
        score_all()
        return
    if args.replay:
        check(args.replay)
        return
    from src.backend.sources import MuseSource

    try:
        path = record(MuseSource(args.serial), args.serial, args.who)
    except KeyboardInterrupt:
        sys.exit("\nStopped.")
    except RuntimeError as e:
        sys.exit(f"\nStopped: {e}")
    check(path)


if __name__ == "__main__":
    main()
