import importlib.util
import re
from pathlib import Path

import numpy as np

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "train_personal.py"
spec = importlib.util.spec_from_file_location("train_personal", SCRIPT)
train = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train)
FS = 256


def synthetic_take(seed=0):
    """A labeled take with blinks on AF7/AF8, 10 Hz alpha behind the ears while closed, and muscle bursts for bites."""
    rng = np.random.default_rng(seed)
    segs, cues, pos = [], [], 0
    for name, _, secs, cue_list in train.plan():
        segs.append({"name": name, "start": pos, "end": pos + int(secs * FS)})
        cues += [{"seg": name, "word": w, "idx": pos + int(t * FS)} for t, w in cue_list]
        pos += int(secs * FS) + FS  # a one second gap between segments
    eeg = rng.normal(0, 8, (4, pos))
    t = np.arange(pos) / FS
    pulse = lambda at, amp: amp * np.exp(-(((t - at) / 0.07) ** 2))  # noqa: E731
    for c in cues:
        at = c["idx"] / FS
        if c["word"] in ("blink", "double"):
            for ch in (1, 2):
                eeg[ch] += pulse(at + 0.2, 150) + (pulse(at + 0.45, 150) if c["word"] == "double" else 0)
        if c["word"] == "bite":
            lo, hi = c["idx"], c["idx"] + int(0.7 * FS)
            eeg[[0, 3], lo:hi] += rng.normal(0, 70, (2, hi - lo))
    closes = [c["idx"] for c in cues if c["word"] == "close"]
    opens = [c["idx"] for c in cues if c["word"] == "open"]
    for a, b in zip(closes, opens):
        eeg[[0, 3], a:b] += 28 * np.sin(2 * np.pi * 10 * t[a:b])
    nat = next(s for s in segs if s["name"] == "natural")
    for at in np.linspace(nat["start"] / FS + 2, nat["end"] / FS - 2, 6):  # natural blinks to calibrate on
        for ch in (1, 2):
            eeg[ch] += pulse(at, 120)
    return eeg, segs, cues


def test_the_training_analysis_finds_the_cued_blinks_closures_and_bites():
    eeg, segs, cues = synthetic_take()
    personal, report = train.analyze(eeg, segs, cues)
    text = "\n".join(report)
    blink = int(re.search(r"best line caught (\d+)/20", text).group(1))
    eyes = int(re.search(r"Eyes closed:.*best .*caught (\d+)/8", text).group(1))
    bite = int(re.search(r"Bite:.*best .*caught (\d+)/10", text).group(1))
    assert blink >= 18 and eyes >= 7 and bite >= 9, text
    assert set(personal) <= {"blink", "eyes", "clench"}  # only constants the board knows how to apply
