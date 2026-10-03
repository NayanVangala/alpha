"""Does the eyes-closed brake work for people other than us? Checked on 109 people from PhysioNet.

  uv run python -m scripts.eval_physionet [--subjects 109]

The EEG Motor Movement/Imagery dataset (https://physionet.org/content/eegmmidb/1.0.0/) has, for each of 109
volunteers, one minute with eyes open (run 1) and one with eyes closed (run 2), on a 64-electrode research cap.
Muse-like signals are rebuilt from it: the electrodes nearest the Muse's (ear spots, AF7, AF8), each referenced
to Fpz, the Muse's reference. Alpha's EyesClosedDetector is calibrated on the first 20 s eyes open, exactly as
the app calibrates, then counts false brakes over the remaining 40 s with eyes open, and whether (and how fast)
it catches the closed minute. Files are cached in data/physionet/ (about 280 MB for everyone).
"""

import argparse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

from src.backend.signals import EEG_FS, EyesClosedDetector

CACHE = Path("data/physionet")
URL = "https://physionet.org/files/eegmmidb/1.0.0/S{s:03d}/S{s:03d}R{r:02d}.edf"
EARS = {"T9/T10": ("T9", "T10"), "TP7/TP8": ("Tp7", "Tp8")}  # the cap has no TP9/TP10; these are nearest


def fetch(subject, run):
    path = CACHE / f"S{subject:03d}R{run:02d}.edf"
    if not path.exists() or path.stat().st_size < 1000:
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL.format(s=subject, r=run), path)
    return path


def read_edf(path):
    """A minimal EDF reader: {label: microvolts}, and the sampling rate."""
    raw = path.read_bytes()
    n_rec, rec_s, ns = int(raw[236:244]), float(raw[244:252]), int(raw[252:256])
    field = lambda off, width: [raw[256 + off * ns + i * width : 256 + off * ns + (i + 1) * width].decode().strip()  # noqa: E731
                                for i in range(ns)]
    labels = [s.strip(".") for s in field(0, 16)]
    # per-signal header fields, in EDF order: label 16, transducer 80, unit 8, phys min 8, phys max 8,
    # dig min 8, dig max 8, prefilter 80, samples per record 8, reserved 32
    offs = {"pmin": 16 + 80 + 8, "pmax": 16 + 80 + 16, "dmin": 16 + 80 + 24, "dmax": 16 + 80 + 32, "n": 16 + 80 + 40 + 80}
    get = lambda key: np.array([float(raw[256 + offs[key] * ns + i * 8 : 256 + offs[key] * ns + (i + 1) * 8]) for i in range(ns)])  # noqa: E731
    pmin, pmax, dmin, dmax, n = get("pmin"), get("pmax"), get("dmin"), get("dmax"), get("n").astype(int)
    data = np.frombuffer(raw[256 * (ns + 1) :], "<i2")
    rec = data[: n_rec * n.sum()].reshape(n_rec, n.sum())
    out, start = {}, 0
    for i, label in enumerate(labels):
        x = rec[:, start : start + n[i]].reshape(-1).astype(float)
        out[label] = (x - dmin[i]) * (pmax[i] - pmin[i]) / (dmax[i] - dmin[i]) + pmin[i]
        start += n[i]
    return out, n[0] / rec_s


def muse_like(path, ears):
    """(4, n) at the Muse's 256 Hz: ear, AF7, AF8, ear, each minus Fpz."""
    sig, fs = read_edf(path)
    ref = sig["Fpz"]
    x = np.vstack([sig[ears[0]] - ref, sig["Af7"] - ref, sig["Af8"] - ref, sig[ears[1]] - ref])
    return resample_poly(x, EEG_FS, int(fs), axis=1)


def run_detector(det, eeg):
    """Sample indices where the detector fires, fed in the app's 64-sample chunks."""
    return [i for i in range(0, eeg.shape[1], 64) if det.feed(eeg[:, i : i + 64])]


def evaluate(open_eeg, closed_eeg, rise):
    det = EyesClosedDetector()
    det.RISE = rise
    calibrated = det.calibrate(open_eeg[:, : 20 * EEG_FS])
    false = len(run_detector(det, open_eeg[:, 20 * EEG_FS :]))
    det2 = EyesClosedDetector(det.threshold)  # fresh stream, same calibration
    fired = run_detector(det2, closed_eeg)
    open_share = np.median([det.share(open_eeg[[0, 3], i : i + EEG_FS]) for i in range(0, 20 * EEG_FS, 64)])
    closed_share = np.median([det.share(closed_eeg[[0, 3], i : i + EEG_FS]) for i in range(0, closed_eeg.shape[1] - EEG_FS, 64)])
    return {"calibrated": calibrated, "false": false, "caught": bool(fired),
            "latency": fired[0] / EEG_FS if fired else None, "ratio": closed_share / max(open_share, 1e-9)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", type=int, default=109)
    args = ap.parse_args()
    subjects = range(1, args.subjects + 1)
    with ThreadPoolExecutor(8) as pool:
        paths = list(pool.map(lambda sr: (sr, fetch(*sr)), [(s, r) for s in subjects for r in (1, 2)]))
    print(f"{len(paths)} files ready in {CACHE}/")
    files = {sr: p for sr, p in paths}

    for name, ears in EARS.items():
        data = {s: (muse_like(files[s, 1], ears), muse_like(files[s, 2], ears)) for s in subjects}
        ratios = [evaluate(o, c, EyesClosedDetector.RISE)["ratio"] for o, c in data.values()]
        print(f"\nEar electrodes {name}: alpha share eyes closed / eyes open, per person: median {np.median(ratios):.2f}x, "
              f"{np.mean(np.array(ratios) > 1.2):.0%} of people above 1.2x")
        print(f"  {'brake line':>10}  {'caught closed':>13}  {'no false brake':>14}  {'both':>5}  {'median delay':>12}")
        for rise in (1.3, 1.5, 1.7, 2.0):
            res = [evaluate(o, c, rise) for o, c in data.values()]
            caught = np.mean([r["caught"] for r in res])
            clean = np.mean([r["false"] == 0 for r in res])
            both = np.mean([r["caught"] and r["false"] == 0 for r in res])
            delay = np.median([r["latency"] for r in res if r["latency"] is not None] or [np.nan])
            mark = "  <- Alpha now" if abs(rise - EyesClosedDetector.RISE) < 1e-9 else ""
            print(f"  {rise:>9.1f}x  {caught:>13.0%}  {clean:>14.0%}  {both:>5.0%}  {delay:>10.1f} s{mark}")


if __name__ == "__main__":
    main()
