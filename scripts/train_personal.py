"""Tune rein's blink, eyes-closed and bite detectors to your head, from a guided recording (about 6 minutes).

  Disconnect the headband in the board first (this talks to the Muse itself), then:
  PYTHONPATH=. uv run python scripts/train_personal.py            # record, tune, save data/personal.json
  PYTHONPATH=. uv run python scripts/train_personal.py --replay data/personal_train_<stamp>.npz   # re-tune a saved take

It says what to do out loud: hard blinks, double blinks, natural reading, eyes closed and open, bites, then things
that must fire nothing (talking, looking left and right, turning your head). For each detector it tries a grid of
constants, scores hits against false fires, and writes the best to data/personal.json, which the board applies the
next time it calibrates. It only changes a constant when the new one beats the default on your own data.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

from src.backend.gestures import TAP_MIN_S
from src.backend.signals import EEG_FS, BlinkDetector, ClenchDetector, EyesClosedDetector, FastBlink, band_rms

OUT = Path("data/personal.json")
STEP = 64  # samples per chunk when replaying a take through a detector, like the live loop


def plan():
    """(segment, spoken instruction, seconds, [(cue seconds, cue word)])."""
    closed = [(1 + 12 * i, "close") if k == 0 else (8 + 12 * i, "open") for i in range(8) for k in range(2)]
    look = [(2 + 3 * i, "left" if i % 2 == 0 else "right") for i in range(6)]
    return [
        ("rest", "Read the screen silently and stay still.", 15, []),
        ("blink", "Blink hard, once, each time I say blink.", 3 + 3.5 * 12, [(2 + 3.5 * i, "blink") for i in range(12)]),
        ("double", "Double blink, two quick blinks, each time I say double.", 3 + 4 * 8, [(2 + 4 * i, "double") for i in range(8)]),
        ("natural", "Read the screen and blink naturally.", 25, []),
        ("closed", "Close your eyes gently when I say close, and open them when I say open.", 8 * 12, closed),
        ("bite", "Bite down briefly each time I say bite.", 3 + 4 * 10, [(2 + 4 * i, "bite") for i in range(10)]),
        ("talk", "Count out loud from one to ten, twice.", 15, []),
        ("look", "Look far left or far right when I say, then straight back.", 20, look),
        ("turn", "Turn your head slowly left and right.", 10, []),
    ]


def say(text):
    print(f"  {text}", flush=True)
    subprocess.run(["say", text], check=False)


STALL_S = 2.5  # no EEG for this long: the stream has dropped


def contact_ok(eeg_chunks):
    """The ears (TP9, TP10) read like skin: 1-150 uV over the last 2 s."""
    x = np.concatenate(eeg_chunks, axis=1)[:, -2 * EEG_FS :]
    if x.shape[1] < EEG_FS:
        return False
    ears = band_rms(x)[[0, 3]]
    return bool(np.all((ears >= 1.0) & (ears <= 150.0)))


def record():
    from src.backend.sources import MuseSource

    source = MuseSource()

    def connect():
        for attempt in range(8):  # about a minute and a half: it may need its button pressed
            try:
                source.start()
                return
            except RuntimeError:
                if attempt == 7:
                    sys.exit("Couldn't reach the headband. Press its button, wait for the lights, and rerun.")
                if attempt == 0:
                    say("I can't find the headband. Hold its button until the lights sweep.")

    print("Connecting to the Muse (can take ~10 s)...", flush=True)
    connect()
    eeg, n, last = [], 0, [time.time()]

    def pull():
        nonlocal n
        d = source.read()["eeg"]
        if d.shape[1]:
            eeg.append(d)
            n += d.shape[1]
            last[0] = time.time()

    segs, cues = [], []
    try:
        say("Sit still and look at the screen for fifteen seconds while the signal settles.")
        end = time.time() + 15
        last[0] = time.time()
        while time.time() < end:
            time.sleep(0.05)
            pull()
        for waited in range(6):  # until the ears read like skin
            if contact_ok(eeg):
                break
            if waited == 0:
                say("The signal isn't clean yet. Seat the headband snugly and wet the sensors a little.")
            for _ in range(100):
                time.sleep(0.05)
                pull()
        else:
            sys.exit("The ear sensors never read like skin. Re-seat and wet the headband, then rerun.")
        eeg.clear()
        n = 0
        for name, text, secs, cue_list in plan():
            for attempt in range(3):
                keep, kept_n, kept_cues = len(eeg), n, len(cues)
                say(text)
                for _ in range(15):  # a beat to react
                    time.sleep(0.1)
                    pull()
                start, t0, pending, stalled = n, time.time(), list(cue_list), False
                last[0] = time.time()
                while time.time() - t0 < secs:
                    time.sleep(0.05)
                    pull()
                    if time.time() - last[0] > STALL_S:
                        stalled = True
                        break
                    if pending and time.time() - t0 >= pending[0][0]:
                        _, word = pending.pop(0)
                        cues.append({"seg": name, "word": word, "idx": n})
                        say(word)
                if not stalled and n - start >= 0.9 * secs * EEG_FS:
                    segs.append({"name": name, "start": start, "end": n})
                    break
                say("The connection dropped. Repeating that part.")
                del eeg[keep:], cues[kept_cues:]  # throw away the partial part
                n = kept_n
                source.stop()
                connect()
                last[0] = time.time()
            else:
                sys.exit(f"The connection kept dropping during '{name}'. Move closer to the computer and rerun.")
    finally:
        source.stop()
    say("Done. Thank you.")
    return np.concatenate(eeg, axis=1), segs, cues


def _hits(times, windows):
    """How many windows contain at least one time, and how many times fall in no window."""
    got = sum(any(a <= t <= b for t in times) for a, b in windows)
    stray = sum(not any(a <= t <= b for a, b in windows) for t in times)
    return got, stray


def analyze(eeg, segs, cues):
    """Try a grid of constants per detector against the labeled take. Returns (personal overrides, printable report)."""
    S = {s["name"]: (s["start"], s["end"]) for s in segs}
    sec = lambda i: i / EEG_FS  # noqa: E731
    seg_eeg = lambda *names: np.concatenate([eeg[:, S[k][0] : S[k][1]] for k in names], axis=1)  # noqa: E731
    cue_t = lambda *words: [sec(c["idx"]) for c in cues if c["word"] in words]  # noqa: E731
    minutes = lambda *names: sum(sec(S[k][1] - S[k][0]) for k in names) / 60  # noqa: E731
    in_seg = lambda times, *names: [t for t in times if any(sec(S[k][0]) <= t <= sec(S[k][1]) for k in names)]  # noqa: E731
    personal, report = {}, []

    # ---- blinks: deliberate and double blinks should each give an event; talking, looking, turning should give few
    nat = seg_eeg("natural")
    base = BlinkDetector()
    found = base.calibrate(nat[1], nat[2])
    if not found:
        report.append("Blink: couldn't find 3 natural blinks to calibrate on; try again, blinking more clearly.")
    else:
        height = base.threshold_uv / base.FRAC  # the wearer's typical blink height
        windows = [(t - 0.1, t + 1.5) for t in cue_t("blink", "double")]
        best = None
        for frac in (0.2, 0.3, 0.4, 0.5, 0.65, 0.8):
            det = FastBlink(frac * height, base.sign)
            times = [(i + STEP) / EEG_FS for i in range(0, eeg.shape[1], STEP) if det.feed(eeg[1, i : i + STEP], eeg[2, i : i + STEP])]
            got, _ = _hits(times, windows)
            noise = len(in_seg(times, "talk", "look", "turn")) / max(minutes("talk", "look", "turn"), 1e-6)
            score = got / len(windows) - 0.02 * noise
            row = (score, frac, got, noise)
            if frac == BlinkDetector.FRAC:
                default = row
            if best is None or (score, frac) > (best[0], best[1]):
                best = row
        report.append(f"Blink: your typical blink is {height:.0f} uV. Default line caught {default[2]}/{len(windows)} cued blinks "
                      f"({default[3]:.0f}/min while talking, looking, turning); best line caught {best[2]}/{len(windows)} ({best[3]:.0f}/min).")
        if best[2] > 0 and best[0] > default[0] + 0.02:
            personal["blink"] = {"FRAC": best[1]}

    # ---- eyes closed: each closed period should fire once; nothing else should
    closes, opens = cue_t("close"), cue_t("open")
    windows = [(c, o + 1.0) for c, o in zip(closes, opens)]
    base_eeg = seg_eeg("rest", "natural")
    best, default = None, None
    for rise in (1.3, 1.5, 1.7, 2.0):
        for floor in (0.15, 0.2, 0.3):
            det = EyesClosedDetector()
            det.RISE, det.MIN_THRESHOLD = rise, floor
            det.calibrate(base_eeg)
            times = [(i + STEP) / EEG_FS for i in range(0, eeg.shape[1], STEP) if det.feed(eeg[:, i : i + STEP])]
            got, stray = _hits(times, windows)
            row = (got / max(1, len(windows)) - 0.3 * stray, -rise, floor, got, stray, det.threshold)
            if (rise, floor) == (EyesClosedDetector.RISE, EyesClosedDetector.MIN_THRESHOLD):
                default = row
            if best is None or row > best:
                best = row
    if windows and default:
        report.append(f"Eyes closed: default line caught {default[3]}/{len(windows)} closures with {default[4]} false stops; "
                      f"best (rise {-best[1]}, floor {best[2]}) caught {best[3]}/{len(windows)} with {best[4]} false.")
        if best[3] > 0 and best[0] > default[0] + 0.05:
            personal["eyes"] = {"RISE": -best[1], "MIN_THRESHOLD": best[2]}

    # ---- bites
    rest = seg_eeg("rest")
    windows = [(t - 0.1, t + 1.5) for t in cue_t("bite")]
    best, default = None, None
    for k in (2.0, 2.5, 3.0, 4.0, 5.0):
        for floor in (10.0, 15.0, 20.0):
            det = ClenchDetector(min_s=TAP_MIN_S)  # as the live gesture layer builds it
            det.K, det.FLOOR = k, floor
            det.calibrate(rest)
            times = []
            for i in range(0, eeg.shape[1], STEP):
                times += [sec(a) for a, _ in det.feed(eeg[:, i : i + STEP])]
            got, stray = _hits(times, windows)
            quiet = [t for t in times if any(sec(S[x][0]) <= t <= sec(S[x][1]) for x in ("rest", "natural", "look", "turn", "closed"))]
            row = (got / max(1, len(windows)) - 0.3 * len(quiet), k, floor, got, len(quiet))
            if (k, floor) == (ClenchDetector.K, ClenchDetector.FLOOR):
                default = row
            if best is None or row > best:
                best = row
    if windows and default:
        report.append(f"Bite: default line caught {default[3]}/{len(windows)} with {default[4]} false; "
                      f"best (K {best[1]}, floor {best[2]}) caught {best[3]}/{len(windows)} with {best[4]} false.")
        if best[3] > 0 and best[0] > default[0] + 0.05:
            personal["clench"] = {"K": best[1], "FLOOR": best[2]}
    return personal, report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replay", help="re-tune a saved take instead of recording")
    ap.add_argument("--dry", action="store_true", help="print what it would save, don't write data/personal.json")
    args = ap.parse_args()
    if args.replay:
        z = np.load(args.replay, allow_pickle=False)
        eeg, segs, cues = z["eeg"], json.loads(str(z["segs"])), json.loads(str(z["cues"]))
    else:
        eeg, segs, cues = record()
        Path("data").mkdir(exist_ok=True)
        path = Path("data") / f"personal_train_{time.strftime('%Y%m%d_%H%M%S')}.npz"
        np.savez(path, eeg=eeg, segs=json.dumps(segs), cues=json.dumps(cues))
        print(f"\nSaved the take to {path} (re-tune it later with --replay).")
    missing = [name for name, *_ in plan() if name not in {s["name"] for s in segs}]
    if missing:
        sys.exit(f"The take is incomplete (missing: {', '.join(missing)}), so nothing was tuned. Rerun it.")
    personal, report = analyze(eeg, segs, cues)
    print("\n" + "\n".join(report))
    if not personal:
        sys.exit("\nNo constant beat the default on this take, so nothing was changed.")
    print(f"\nBest constants: {json.dumps(personal)}")
    if not args.dry:
        old = json.loads(OUT.read_text()) if OUT.exists() else {}
        OUT.write_text(json.dumps({**old, **personal}, indent=1))
        print(f"Saved {OUT}. Recalibrate on the board and they take effect.")


if __name__ == "__main__":
    main()
