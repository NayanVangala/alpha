"""Coach loop: read the headband, run the detectors, log events per frontmost app, nudge."""

import sqlite3
import time
import traceback
from collections import deque

import numpy as np

from .activity import frontmost_app, notify
from .gestures import Gestures
from .signals import (
    CHANNELS,
    EEG_FS,
    PPG_FS,
    BlinkDetector,
    ClenchDetector,
    EyesClosedDetector,
    PostureTracker,
    band_powers,
    band_rms,
    contact,
    heart_rate,
    spectrum,
)

TICK_S = 0.25
CALIBRATE_S = 20
NOISY_REST_FRAC = 0.05  # more of the still 20 s than this over the bite line = noisy contact or a tense jaw
SAMPLE_EVERY_S = 5  # one samples row per this many seconds of live data
LOW_BLINKS_PER_MIN = 7  # healthy is ~15; screens drop it to ~5
SLOUCH_DEG = 15
STALE_S = 2  # no EEG for this long = headband isn't sending
OFF_S = 3  # every sensor off the skin this long = the headband has been taken off
RECONNECT_EVERY_S = 15
APP_REFRESH_S = 1
NERD_WINDOW_S = 30  # how far back the Stats for nerds charts reach

# Everything a live demo wants shorter; --demo swaps in DEMO_TIMING.
TIMING = {
    "blink_window_s": 120,
    "slouch_hold_s": 30,
    "clench_hold_s": 3,  # nudge while still clenching, not only after release
    "blink_every_s": 300,
    "clench_every_s": 60,
    "posture_every_s": 300,
    "break_every_s": 20 * 60,  # 20-20-20 rule
}
DEMO_TIMING = {
    "blink_window_s": 45,
    "slouch_hold_s": 10,
    "clench_hold_s": 2,
    "blink_every_s": 30,
    "clench_every_s": 15,
    "posture_every_s": 30,
    "break_every_s": 3 * 60,
}


def open_db(path):
    path.parent.mkdir(exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.executescript(
        """
        PRAGMA journal_mode = WAL;
        CREATE TABLE IF NOT EXISTS events (ts REAL, kind TEXT, value REAL, app TEXT);
        CREATE TABLE IF NOT EXISTS samples (ts REAL, app TEXT, tilt REAL, hr REAL);
        CREATE INDEX IF NOT EXISTS events_ts ON events (ts);
        CREATE INDEX IF NOT EXISTS samples_ts ON samples (ts);
        """
    )
    return db


class Coach:
    def __init__(self, source, db, timing=TIMING, nudge=notify, app_name=frontmost_app, clock=time.time, sleep=time.sleep,
                 on_gesture=None, calibration=None, on_calibrated=None, on_presence=None):
        self.source, self.db, self.t = source, db, timing
        self.on_calibrated = on_calibrated  # gets self.calibration after each calibration with real data
        self.on_gesture = on_gesture  # board input: (kind, ago_s)
        self.on_presence = on_presence  # board: the headband came off or went quiet (reason)
        self.off_since, self.lost_told, self.presence_at = None, False, 0.0
        self.nudge, self.app_name, self.clock, self.sleep = nudge, app_name, clock, sleep
        self.want_calibration = True
        self.running = True
        self.blinks, self.clench, self.posture = BlinkDetector(), ClenchDetector(), PostureTracker()
        self.eyes_threshold = None  # alpha share for eyes closed; set by calibrate()
        self.gestures = Gestures(self.clench.threshold_uv)
        self.blink_times = deque()
        self.eeg_tail = deque(maxlen=2 * EEG_FS)
        self.nerd = None  # latest Stats for nerds snapshot
        self.muscle, self.events, self.fs_log = deque(), deque(), deque()
        self.ppg = deque(maxlen=12 * PPG_FS)
        now = clock()
        self.cooldown = {"break": now}
        self.last_data = self.last_reconnect = now
        self.app_at = -1e9
        self.live_since = self.slouch_since = None
        self.last_sample = 0.0
        self.state = {
            "app": "",
            "live": False,
            "calibrating": False,
            "calibrate_until": None,
            "calibration_note": "",
            "blink_rate": None,
            "last_blink": 0.0,
            "clenching": False,
            "tilt": 0.0,
            "hr": None,
            "loose_sensors": None,
            "error": None,
            "limits": {"low_blinks": LOW_BLINKS_PER_MIN, "slouch_deg": SLOUCH_DEG},
        }
        if calibration:
            self.use_calibration(calibration)

    @property
    def calibration(self):
        """This wearer's thresholds, as plain JSON, to reuse after a reconnect."""
        return {"blink": [self.blinks.threshold_uv, self.blinks.sign], "clench": self.clench.threshold_uv,
                "eyes": self.eyes_threshold, "upright": [float(v) for v in self.posture.upright]}

    def use_calibration(self, cal):
        """Start from a saved calibration instead of a fresh 20 s one (the wearer can still recalibrate)."""
        self.blinks = BlinkDetector(*cal["blink"])
        self.clench = ClenchDetector(cal["clench"])
        self.posture.upright = np.array(cal["upright"], float)
        self.eyes_threshold = cal["eyes"]
        self.gestures = Gestures(cal["clench"], cal["eyes"])
        self.want_calibration = False
        self.state["calibration_note"] = "Using your saved calibration. Recalibrate if the headband moved."

    def run(self):
        """Loop until stop(). Errors show on the dashboard instead of silently killing the thread."""
        while self.running:
            try:
                if self.want_calibration:
                    self.calibrate()
                self.step()
                self.state["error"] = None
            except Exception as e:  # a live demo has to survive any single bad read
                traceback.print_exc()
                self.state["error"] = f"{type(e).__name__}: {e}"
                if self.state["calibrating"]:  # failed mid-calibration: retry instead of "Calibrating" forever
                    self.state.update(calibrating=False, calibrate_until=None)
                    self.want_calibration = True
                self.sleep(1)
            self._maybe_reconnect()
            self.sleep(TICK_S)

    def stop(self):
        self.running = False

    def calibrate(self, seconds=CALIBRATE_S):
        """Learn this wearer's thresholds from `seconds` sitting upright, jaw relaxed, blinking normally."""
        self.want_calibration = False
        end = self.clock() + seconds
        self.state.update(calibrating=True, calibrate_until=end, calibration_note="")
        chunks = []
        while self.clock() < end and self.running:
            self.sleep(TICK_S)
            chunks.append(self.source.read())
            if chunks[-1]["eeg"].shape[1]:
                self.last_data = self.clock()
        eeg = np.concatenate([np.empty((4, 0))] + [c["eeg"] for c in chunks], axis=1)
        accel = np.concatenate([np.empty((3, 0))] + [c["accel"] for c in chunks], axis=1)

        blinks, clench, posture, eyes = BlinkDetector(), ClenchDetector(), PostureTracker(), EyesClosedDetector()
        enough = eeg.shape[1] >= 0.8 * seconds * EEG_FS
        if not enough:
            note = "Barely got data from the headband, so default settings are in use. Check it's on and connected, then recalibrate."
        else:
            missed = [
                what
                for what, ok in (
                    ("clear blinks", blinks.calibrate(eeg[1], eeg[2])),
                    ("jaw data", clench.calibrate(eeg)),
                    ("head position", posture.calibrate(accel)),
                    ("eyes-open alpha", eyes.calibrate(eeg)),
                )
                if not ok
            ]
            note = "Calibrated." if not missed else f"Calibrated, but didn't catch {' or '.join(missed)}; using defaults for those."
            if clench.rest_burst_frac > NOISY_REST_FRAC:
                note += " The jaw sensors were noisy while you sat still: relax your jaw, make sure the band is snug and damp, then recalibrate."
        self.blinks, self.clench, self.posture = blinks, clench, posture
        self.eyes_threshold = eyes.threshold
        self.gestures = Gestures(clench.threshold_uv, self.eyes_threshold)
        self.blink_times.clear()
        self.ppg.clear()  # nothing from the previous wearer carries over
        self.live_since = self.slouch_since = None
        self.cooldown = {"break": self.clock()}
        self.state.update(calibrating=False, calibrate_until=None, calibration_note=note,
                          blink_rate=None, hr=None, loose_sensors=None)
        if enough and self.on_calibrated:
            self.on_calibrated(self.calibration)

    def _log(self, kind, value, app):
        self.db.execute("INSERT INTO events (ts, kind, value, app) VALUES (?,?,?,?)", (self.clock(), kind, value, app))

    def _maybe_nudge(self, key, title, msg, app):
        now = self.clock()
        if now - self.cooldown.get(key, -1e9) >= self.t[f"{key}_every_s"]:
            self.cooldown[key] = now
            self.nudge(title, msg)
            self._log("nudge_" + key, 0, app)

    def _go_stale(self):
        """Headband silent: show nothing rather than frozen numbers, and don't log or nudge."""
        if self.state["live"]:
            self._lost("Headband stopped sending")
            # restart the streaming filters (keeping calibration) so the gap can't look like a blink
            self.blinks = BlinkDetector(self.blinks.threshold_uv, self.blinks.sign)
            self.clench = ClenchDetector(self.clench.threshold_uv)
            self.gestures = Gestures(self.clench.threshold_uv, self.eyes_threshold)
        self.live_since = self.slouch_since = None
        self.blink_times.clear()
        self.nerd = None
        self.state.update(live=False, blink_rate=None, clenching=False, tilt=None, hr=None, loose_sensors=None, alpha=None)

    def _lost(self, reason):
        """Tell the board once per outage: the agent is held back until the wearer is back."""
        if not self.lost_told:
            self.lost_told = True
            if self.on_presence:
                self.on_presence(reason)

    def _presence(self, now, loose):
        """`loose`: no sensor on the skin. For OFF_S that means the band is off."""
        if not loose:
            self.off_since, self.lost_told = None, False
            return
        if self.off_since is None:
            self.off_since = now
        if now - self.off_since >= OFF_S:
            self._lost("Headband taken off")

    def _maybe_reconnect(self):
        now = self.clock()
        if now - self.last_data > RECONNECT_EVERY_S and now - self.last_reconnect > RECONNECT_EVERY_S:
            self.last_reconnect = now
            try:
                self.source.stop()
                self.source.start()
            except Exception as e:  # keep trying; the dashboard shows why
                self.state["error"] = f"Reconnecting to the headband failed: {e}"

    def step(self):
        now = self.clock()
        d = self.source.read()
        if now - self.app_at >= APP_REFRESH_S:
            self.app_at, self.state["app"] = now, self.app_name()
        app = self.state["app"]

        eeg = d["eeg"]
        if eeg.shape[1]:
            self.last_data = now
        if now - self.last_data > STALE_S:
            self._go_stale()
            return
        if self.live_since is None:
            self.live_since = self.last_sample = now
        self.state["live"] = True
        self.eeg_tail.extend(eeg.T)
        if now - self.presence_at >= 1.0:
            self.presence_at = now
            ok = contact(np.array(self.eeg_tail).T)
            self._presence(now, ok is not None and not any(ok))

        window = self.t["blink_window_s"]
        new_blinks = self.blinks.feed(eeg[1], eeg[2])
        for _ in new_blinks:
            self.blink_times.append(now)
            self.state["last_blink"] = now
            self._log("blink", 1, app)
        while self.blink_times and now - self.blink_times[0] > window:
            self.blink_times.popleft()
        live_for = now - self.live_since
        if live_for >= window / 4:
            self.state["blink_rate"] = len(self.blink_times) / (min(window, live_for) / 60)
        if live_for >= window and self.state["blink_rate"] < LOW_BLINKS_PER_MIN:
            self._maybe_nudge("blink", "Your eyes are drying out",
                              f"{len(self.blink_times)} blinks in the last {window / 60:g} min. Close your eyes slowly 5 times.", app)

        for _, dur in self.clench.feed(eeg):
            self._log("clench", dur, app)
        self.state["clenching"] = self.clench.active
        if self.clench.holding_s >= self.t["clench_hold_s"]:
            self._maybe_nudge("clench", "Jaw check",
                              f"You've been clenching for {self.clench.holding_s:.0f}s. Lips together, teeth apart.", app)
        self.events.extend((now, "blink") for _ in new_blinks)
        for kind, ago in self.gestures.feed(eeg, new_blinks):
            self.events.append((now, kind))
            if self.on_gesture:
                self.on_gesture(kind, ago)
        self.state["alpha"] = self.gestures.eyes.level  # live, for the board's aura and brake meter
        self.state["muscle"] = self.gestures.clench.level  # live bite level, 1.0 = the bite threshold
        self.state["battery"] = getattr(self.source, "battery", None)

        tilt = self.posture.feed(d["accel"])
        self.state["tilt"] = tilt
        if tilt > SLOUCH_DEG:
            self.slouch_since = self.slouch_since or now
            if now - self.slouch_since > self.t["slouch_hold_s"]:
                self._maybe_nudge("posture", "Head's drifting forward", f"{tilt:.0f} degrees off upright. Sit back, chin in.", app)
        else:
            self.slouch_since = None

        self._maybe_nudge("break", "20-20-20", "Look at something 20 feet away for 20 seconds.", app)

        self.ppg.extend(np.atleast_2d(d["ppg"]).T)
        if now - self.last_sample >= SAMPLE_EVERY_S:
            # fixed cadence, so per-app minutes = rows x SAMPLE_EVERY_S stays exact
            self.last_sample = max(self.last_sample + SAMPLE_EVERY_S, now - SAMPLE_EVERY_S)
            self.state["hr"] = heart_rate(np.array(self.ppg).T) if self.ppg else None
            ok = contact(np.array(self.eeg_tail).T)
            self.state["loose_sensors"] = None if ok is None else [n for n, good in zip(CHANNELS, ok) if not good]
            self.db.execute("INSERT INTO samples (ts, app, tilt, hr) VALUES (?,?,?,?)", (now, app, tilt, self.state["hr"]))
        self.db.commit()
        self.fs_log.append((now, eeg.shape[1]))
        self._snapshot(now)

    def _snapshot(self, now):
        """Numbers for the board's Stats for nerds panel.

        Built in this thread and swapped in whole, so the server never reads a half-updated buffer.
        """
        eeg = np.array(self.eeg_tail).T
        if eeg.ndim != 2 or eeg.shape[1] < EEG_FS:
            return
        cutoff = now - NERD_WINDOW_S
        for log in (self.muscle, self.events):
            while log and log[0][0] < cutoff:
                log.popleft()
        while self.fs_log and now - self.fs_log[0][0] > 2:
            self.fs_log.popleft()
        span = now - self.fs_log[0][0] if len(self.fs_log) > 1 else 0
        # the clench detector's own measure: >30 Hz muscle level over the last quarter second
        level, _ = self.gestures.clench._muscle(eeg[:, -EEG_FS // 2 :])
        self.muscle.append((now, float(np.sqrt(np.mean(np.square(level[-EEG_FS // 4 :]))))))
        freqs, psd = spectrum(eeg)
        keep = (freqs >= 1) & (freqs <= 60)
        self.nerd = {
            "live": True,
            "fs": round(sum(n for _, n in list(self.fs_log)[1:]) / span, 1) if span else None,
            "age_ms": round((now - self.last_data) * 1000),
            "channels": ["TP9", "AF7", "AF8", "TP10"],
            "raw": [np.round(ch[::2], 1).tolist() for ch in eeg[:, -2 * EEG_FS :]],  # last 2 s, every other sample
            "raw_s": 2,
            "freqs": freqs[keep].tolist(),
            "psd": np.round(psd[:, keep].mean(axis=0), 4).tolist(),
            "bands": {k: np.round(v, 2).tolist() for k, v in band_powers(freqs, psd).items()},
            "muscle": [[round(t - now, 2), round(m, 1)] for t, m in self.muscle],
            "threshold": round(self.gestures.clench.threshold_uv, 1),
            "events": [[round(t - now, 2), k] for t, k in self.events],
            "window_s": NERD_WINDOW_S,
            "contact_uv": np.round(band_rms(eeg[:, -EEG_FS:]), 1).tolist(),
            "tilt": self.state["tilt"],
            "hr": self.state["hr"],
            "blink_rate": self.state["blink_rate"],
        }
