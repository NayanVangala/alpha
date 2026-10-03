import numpy as np
import pytest

from src.backend.coach import Coach, open_db
from src.backend.gestures import Gestures
from src.backend.signals import EEG_FS, BlinkDetector
from tests.backend.test_coach import Clock, Headband
from tests.backend.test_signals import fake_eeg


def run(eeg, chunk=64):
    """Feed chunks the way the coach does: blink indices from a BlinkDetector, then gestures."""
    blinks, gestures, out = BlinkDetector(), Gestures(), []
    for i in range(0, eeg.shape[1], chunk):
        c = eeg[:, i : i + chunk]
        out += gestures.feed(c, blinks.feed(c[1], c[2]))
    return out


def kinds(out):
    return [k for k, _ in out]


@pytest.mark.parametrize("seed", range(10))
def test_tap_clench_reports_its_onset(seed):
    out = run(fake_eeg(np.random.default_rng(seed), 8, clenches=[(3, 0.8)]))
    assert kinds(out) == ["clench"]
    assert 0.8 <= out[0][1] <= 2.0  # fires after 0.5 s of quiet; ago reaches back to the onset


@pytest.mark.parametrize("seed", range(10))
def test_chewing_is_not_a_clench(seed):
    assert run(fake_eeg(np.random.default_rng(seed), 8, chews=[(2, 0.3), (4, 0.3), (6, 0.3)])) == []


@pytest.mark.parametrize("seed", range(10))
def test_long_clench_fires_once_while_still_held(seed):
    eeg = fake_eeg(np.random.default_rng(seed), 10, clenches=[(3, 4)])
    assert kinds(run(eeg[:, : 6 * EEG_FS])) == ["long_clench"]  # 3 s in, jaw still closed
    assert kinds(run(eeg)) == ["long_clench"]  # releasing it doesn't add a tap


@pytest.mark.parametrize("seed", range(10))
def test_double_blink_needs_two_quick_blinks(seed, monkeypatch):
    eeg = fake_eeg(np.random.default_rng(seed), 12, blinks=[3, 3.4, 7, 9.5])
    assert kinds(run(eeg)) == []  # off for the headband: eyes closed does its jobs
    monkeypatch.setattr("src.backend.gestures.HEADBAND_DOUBLE_BLINK", True)
    assert kinds(run(eeg)) == ["double_blink"]


class Scripted(Headband):
    """Plays back a recording, a quarter second per read."""

    def __init__(self, eeg):
        super().__init__()
        self.eeg, self.i = eeg, 0

    def read(self):
        d = super().read()
        n = EEG_FS // 4
        d["eeg"], self.i = self.eeg[:, self.i : self.i + n], self.i + n
        return d


def test_coach_passes_headband_gestures_to_the_board(tmp_path):
    clock, got = Clock(), []
    band = Scripted(fake_eeg(np.random.default_rng(0), 10, clenches=[(3, 4)]))
    c = Coach(band, open_db(tmp_path / "c.db"), nudge=lambda *a: None, app_name=lambda: "Chrome",
              clock=clock, sleep=clock.sleep, on_gesture=lambda kind, ago: got.append(kind))
    c.want_calibration = False
    for _ in range(40):  # 10 s
        c.step()
        clock.sleep(0.25)
    assert got == ["long_clench"]


def test_coach_snapshot_for_stats_for_nerds(tmp_path):
    clock = Clock()
    band = Scripted(fake_eeg(np.random.default_rng(0), 10, clenches=[(3, 4)]))
    c = Coach(band, open_db(tmp_path / "c.db"), nudge=lambda *a: None, app_name=lambda: "Chrome",
              clock=clock, sleep=clock.sleep)  # no board attached: gestures are still logged for the panel
    c.want_calibration = False
    for _ in range(40):
        c.step()
        clock.sleep(0.25)
    n = c.nerd
    assert n["live"] and len(n["raw"]) == 4 and all(len(ch) == EEG_FS for ch in n["raw"])
    assert set(n["bands"]) == {"delta", "theta", "alpha", "beta", "gamma"} and len(n["freqs"]) == len(n["psd"])
    assert "long_clench" in [k for _, k in n["events"]] and n["fs"] == pytest.approx(EEG_FS, rel=0.05)
    assert max(m for _, m in n["muscle"]) > n["threshold"]  # the clench shows on the jaw chart


def look(eeg, start, dur, side, uv=150):
    """Eyes held to one side for `dur` s: AF7 and AF8 swing apart (left pushes AF7 up)."""
    a, b = int(start * EEG_FS), int((start + dur) * EEG_FS)
    s = 1 if side == "left" else -1
    eeg[1, a:b] += s * uv / 2
    eeg[2, a:b] -= s * uv / 2
    return eeg


@pytest.mark.parametrize("seed", range(10))
def test_glances_left_and_right(seed, monkeypatch):
    monkeypatch.setattr("src.backend.gestures.HEADBAND_GLANCES", True)  # the detector itself; off for the headband
    eeg = fake_eeg(np.random.default_rng(seed), 10)
    look(look(eeg, 2, 0.5, "left"), 5, 0.5, "right")
    assert kinds(run(eeg)) == ["glance_left", "glance_right"]  # coming back to centre isn't a glance


@pytest.mark.parametrize("seed", range(10))
def test_quick_glances_the_same_way_each_count(seed, monkeypatch):
    monkeypatch.setattr("src.backend.gestures.HEADBAND_GLANCES", True)  # the detector itself; off for the headband
    eeg = fake_eeg(np.random.default_rng(seed), 10)
    for t in (2, 3, 4, 5):
        look(eeg, t, 0.5, "right")
    assert kinds(run(eeg)) == ["glance_right"] * 4


@pytest.mark.parametrize("seed", range(10))
def test_a_held_look_is_one_glance_and_blinks_are_none(seed, monkeypatch):
    monkeypatch.setattr("src.backend.gestures.HEADBAND_GLANCES", True)  # the detector itself; off for the headband
    eeg = fake_eeg(np.random.default_rng(seed), 12, blinks=[2, 8.5, 10])
    assert kinds(run(look(eeg, 4, 2.5, "left"))) == ["glance_left"]


def alpha(eeg, start, dur, uv=20):
    """Eyes shut for `dur` s: a 10 Hz rhythm swells behind the ears (TP9, TP10)."""
    a, b = int(start * EEG_FS), int((start + dur) * EEG_FS)
    eeg[[0, 3], a:b] += uv * np.sin(2 * np.pi * 10 * np.arange(b - a) / EEG_FS)
    return eeg


@pytest.mark.parametrize("seed", range(10))
def test_eyes_closed_fires_once_per_closure_and_not_for_a_glimpse(seed):
    rng = np.random.default_rng(seed)
    assert kinds(run(alpha(alpha(fake_eeg(rng, 14), 2, 3), 8, 3))) == ["eyes_closed", "eyes_closed"]
    assert kinds(run(alpha(fake_eeg(rng, 10), 3, 0.8))) == []  # under 1.5 s: not a deliberate closure


def test_eyes_closed_threshold_comes_from_eyes_open_calibration():
    from src.backend.signals import EyesClosedDetector

    d = EyesClosedDetector()
    assert d.calibrate(fake_eeg(np.random.default_rng(1), 20))
    assert 0.3 <= d.threshold <= 0.8 and not EyesClosedDetector().calibrate(fake_eeg(np.random.default_rng(1), 2))


def test_headband_glances_are_off_until_a_wearer_shows_clean_looks():
    eeg = look(fake_eeg(np.random.default_rng(0), 6), 2, 0.5, "left")
    assert kinds(run(eeg)) == []
