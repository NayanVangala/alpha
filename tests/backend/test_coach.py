import numpy as np

from src.backend.coach import DEMO_TIMING, SAMPLE_EVERY_S, TIMING, Coach, open_db
from src.backend.signals import EEG_FS


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


class Headband:
    """Quiet, upright wearer who never blinks. `silent` = Bluetooth delivering nothing."""

    def __init__(self):
        self.silent = False
        self.starts = 0
        self.rng = np.random.default_rng(0)

    def start(self):
        self.starts += 1

    def stop(self):
        pass

    def read(self):
        if self.silent:
            return {"eeg": np.empty((4, 0)), "accel": np.empty((3, 0)), "ppg": np.empty((3, 0))}
        return {
            "eeg": self.rng.normal(0, 8, (4, EEG_FS // 4)),
            "accel": np.tile([[0.0], [0.0], [1.0]], (1, 13)),
            "ppg": self.rng.normal(0, 1, (3, 16)),
        }


def make(tmp_path, timing=TIMING):
    clock, band, nudges = Clock(), Headband(), []
    c = Coach(band, open_db(tmp_path / "c.db"), timing=timing, nudge=lambda title, msg: nudges.append(title),
              app_name=lambda: "Zoom", clock=clock, sleep=clock.sleep)
    c.want_calibration = False
    return c, clock, band, nudges


def run(c, clock, seconds):
    for _ in range(int(seconds / 0.25)):
        clock.sleep(0.25)
        c.step()


def rows(c, table):
    return c.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_low_blink_nudge_respects_cooldown_and_samples_keep_cadence(tmp_path):
    c, clock, _, nudges = make(tmp_path)
    run(c, clock, 400)
    assert nudges.count("Your eyes are drying out") == 1  # at 120 s; next not before 420 s
    assert rows(c, "samples") == 400 // SAMPLE_EVERY_S - 1  # first row lands one period after data starts
    assert c.state["blink_rate"] == 0 and c.state["live"]


def test_bluetooth_drop_shows_nothing_logs_nothing_nudges_nothing(tmp_path):
    c, clock, band, nudges = make(tmp_path, DEMO_TIMING)  # 45 s blink window would nudge mid-outage
    run(c, clock, 30)
    samples = rows(c, "samples")
    band.silent = True
    run(c, clock, 60)
    assert not c.state["live"]
    assert c.state["blink_rate"] is None and c.state["hr"] is None and c.state["tilt"] is None
    assert not c.state["clenching"]
    assert rows(c, "samples") - samples <= 1  # at most one row inside the 2 s grace period
    assert nudges == []


def test_reconnects_while_silent(tmp_path):
    c, clock, band, _ = make(tmp_path)
    band.silent = True
    for _ in range(4 * 40):
        clock.sleep(0.25)
        c.step()
        c._maybe_reconnect()
    assert band.starts >= 2  # retried every 15 s


def test_calibration_reports_missing_data(tmp_path):
    c, _, band, _ = make(tmp_path)
    band.silent = True
    c.calibrate()
    assert c.state["calibration_note"].startswith("Barely got data")
    band.silent = False
    c.calibrate()
    assert c.state["calibration_note"].startswith("Calibrated")
    assert not c.state["calibrating"]


def test_step_survives_empty_first_read(tmp_path):
    c, clock, band, _ = make(tmp_path)
    band.silent = True
    clock.sleep(0.25)
    c.step()  # used to crash the coach thread
    band.silent = False
    run(c, clock, 5)
    assert c.state["live"]


def test_recalibrating_forgets_the_previous_wearer(tmp_path):
    c, clock, _, _ = make(tmp_path)
    run(c, clock, 60)
    assert c.state["blink_rate"] == 0 and c.state["hr"] is None  # quiet wearer: never blinked
    c.state["hr"] = 88.0
    c.calibrate()
    assert c.state["blink_rate"] is None and c.state["hr"] is None and len(c.ppg) == 0
    run(c, clock, 5)
    assert c.state["blink_rate"] is None  # nothing shown until the new wearer has warmed up


def test_unconnected_muse_reads_as_silent():
    from src.backend.sources import MuseSource

    d = MuseSource().read()  # never started, like after a failed reconnect
    assert d["eeg"].shape == (4, 0) and d["accel"].shape == (3, 0) and d["ppg"].shape == (3, 0)


def test_a_saved_calibration_skips_the_20_s_one_and_reports_back(tmp_path):
    c, clock, band, _ = make(tmp_path)
    kept = []
    c.on_calibrated = kept.append
    c.calibrate()
    band.silent = True
    c.calibrate()  # no data: nothing worth keeping
    assert len(kept) == 1
    again = Coach(Headband(), open_db(tmp_path / "d.db"), calibration=kept[0], clock=clock, sleep=clock.sleep)
    assert not again.want_calibration and again.calibration == kept[0]
    assert again.state["calibration_note"].startswith("Using your saved calibration")
