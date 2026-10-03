"""Streaming detectors for the Muse 2's reliable non-brain signals.

Muse 2 layout (BrainFlow MUSE_2_BOARD):
  EEG  256 Hz  TP9, AF7, AF8, TP10 (microvolts)
  IMU   52 Hz  accel x/y/z
  PPG   64 Hz  3 optical channels (needs board.config_board("p50"))

Each detector takes chunks as they arrive (possibly empty, when Bluetooth
delivered nothing) and returns events, so the same code runs on the live
headband, on the simulator, and in tests.
"""

from collections import deque

import numpy as np
from scipy.signal import butter, find_peaks, iirnotch, sosfilt, sosfilt_zi, sosfiltfilt, tf2sos, welch

EEG_FS = 256
IMU_FS = 52
PPG_FS = 64
CHANNELS = ("behind left ear", "left forehead", "right forehead", "behind right ear")
MAINS_HZ = 60  # ponytail: US wall power; set 50 in Europe. Mains hum lands inside the clench band.
CONTACT_UV = (1.0, 150.0)  # ponytail: guessed skin-contact band; tune with scripts/check_muse.py
# Classic EEG bands. Gamma stops below the mains hum; on a forehead headband it is mostly jaw muscle.
BANDS = (("delta", 1, 4), ("theta", 4, 8), ("alpha", 8, 13), ("beta", 13, 30), ("gamma", 30, 50))


def finite(x):
    """Float copy with non-finite samples replaced by the median of the row's finite ones.

    One NaN would otherwise poison filter state for the rest of the session.
    """
    x = np.array(x, float)
    for row in np.atleast_2d(x):  # views into x
        bad = ~np.isfinite(row)
        if bad.any():
            row[bad] = np.median(row[~bad]) if not bad.all() else 0.0
    return x


class BlinkDetector:
    """Blinks = big same-sign deflection on both forehead channels (AF7, AF8).

    Using the AF7+AF8 average cancels left/right glances, which swing the two
    channels in opposite directions.
    """

    REFRACTORY_S = 0.3

    def __init__(self, threshold_uv=90.0, sign=1, fs=EEG_FS):
        self.threshold_uv = threshold_uv
        self.sign = sign
        self.fs = fs
        self.sos = butter(2, [0.5, 10], btype="band", fs=fs, output="sos")
        self.buf = deque(maxlen=int(4 * fs))
        self.n_seen = 0  # absolute index of the next incoming sample
        self.last_counted = -(10**9)

    def _peaks(self, x, height):
        return find_peaks(
            x, height=height, distance=int(self.REFRACTORY_S * self.fs), width=(0.04 * self.fs, 0.5 * self.fs)
        )

    def calibrate(self, af7, af8):
        """Set polarity and threshold from ~20 s of normal blinking.

        Keeps the defaults unless one polarity shows at least 3 blinks, so a
        blink-free window or one headband bump can't flip the sign.
        """
        x = sosfiltfilt(self.sos, (finite(af7) + finite(af8)) / 2)
        best = None
        for sign in (1, -1):
            heights = self._peaks(sign * x, 40)[1]["peak_heights"]
            if len(heights) >= 3 and (best is None or np.median(heights) > best[1]):
                best = (sign, float(np.median(heights)))
        if best:
            self.sign, self.threshold_uv = best[0], 0.5 * best[1]
        return best is not None

    def feed(self, af7, af8):
        """Returns absolute sample indices of newly detected blinks."""
        x = (finite(af7) + finite(af8)) / 2
        self.buf.extend(x)
        self.n_seen += len(x)
        if len(self.buf) < self.fs:
            return []
        y = self.sign * sosfiltfilt(self.sos, np.fromiter(self.buf, float))
        start = self.n_seen - len(y)
        edge = int(0.5 * self.fs)  # filtfilt is unreliable near both ends of the buffer
        new = []
        for p in self._peaks(y, self.threshold_uv)[0]:
            i = start + p
            # re-filtering the grown buffer can shift a counted peak by a sample; the refractory gap stops a recount
            if p >= edge and i < self.n_seen - edge and i > self.last_counted + self.REFRACTORY_S * self.fs:
                new.append(i)
                self.last_counted = i
        return new


class GlanceDetector:
    """Deliberate left/right glances = the two forehead channels (AF7, AF8) swinging opposite ways.

    The eye is a small battery (front positive), so looking left pushes the left
    forehead channel up and the right one down, and they stay there until the
    eyes come back. A blink moves both the same way, so it can't pass. The rest
    level follows electrode drift only while the eyes are at rest, so a run of
    glances the same way can't drag it along.
    """

    STEP = 8  # keep 1 sample in 8: 32 Hz is plenty for eye movements
    HOLD_S = 0.15  # off centre at least this long, so a noise spike isn't a glance
    STUCK_S = 3.0  # "away" longer than this means the level itself moved (electrode shift): re-centre
    DRIFT_S = 2.0  # how fast the rest level follows drift

    # ponytail: threshold and sign are guesses until the Muse arrives; tune with scripts/check_muse.py,
    # and flip `sign` if left and right come out swapped
    def __init__(self, threshold_uv=60.0, sign=1, fs=EEG_FS):
        self.threshold_uv, self.sign, self.fs = threshold_uv, sign, fs
        self.sos = butter(2, 6, fs=fs, output="sos")  # eye movements are slow; this drops jaw muscle and alpha
        self.zi = self.rest = self.away = None  # away: seconds off centre since the last glance, else None
        self.n_seen = 0
        self.held = 0.0

    def feed(self, af7, af8):
        """Returns "left" or "right" for each new glance."""
        x = finite(np.vstack([af7, af8]))
        if x.shape[1] == 0:
            return []
        if self.zi is None:
            self.zi = sosfilt_zi(self.sos)[:, None, :] * x[:, :1][None, :, :]
        y, self.zi = sosfilt(self.sos, x, axis=1, zi=self.zi)
        first = (-self.n_seen) % self.STEP  # keep the 1-in-STEP pick lined up across chunks
        self.n_seen += x.shape[1]
        dt, out = self.STEP / self.fs, []
        for level in y[:, first :: self.STEP].T:
            if self.rest is None:
                self.rest = level.copy()
            da, db = level - self.rest
            h = self.sign * (da - db)  # > 0: looking left
            if self.away is not None:  # wait for the eyes to come back before the next glance
                self.away += dt
                if abs(h) < self.threshold_uv / 2:
                    self.away = None
                elif self.away > self.STUCK_S:
                    self.rest, self.away = level.copy(), None
                continue
            self.held = self.held + dt if abs(h) > self.threshold_uv and da * db < 0 else 0.0
            if self.held >= self.HOLD_S:
                out.append("left" if h > 0 else "right")
                self.held, self.away = 0.0, 0.0
            elif abs(h) < self.threshold_uv / 2:
                self.rest += (level - self.rest) * (dt / self.DRIFT_S)
        return out


class EyesClosedDetector:
    """Eyes closed = the alpha rhythm (8-13 Hz) swelling behind the ears (TP9, TP10).

    With the eyes shut the visual cortex idles and alpha grows: the one brain signal Alpha uses, and only as a
    brake. The forehead pair is left out because blinks and eye movements swamp it. The measure is alpha's
    share of 4-30 Hz power over the last second; a jaw clench floods that range with muscle noise, so it
    lowers the share rather than faking a closure.
    """

    WINDOW_S = 1.0
    HOLD_S = 1.5  # share above the threshold this long counts as a deliberate closure
    # tuned on a real Muse (data/muse_check_20261002_195641.npz): shares jump around window to window, so the
    # median of the last four updates (about a second) is what's compared; 1.7x the eyes-open share caught both
    # closures and nothing during reading, talking, head turns or bites
    RISE = 1.7
    SMOOTH = 4
    DEFAULT = 0.45  # until calibrated

    def __init__(self, threshold=None, fs=EEG_FS):
        self.threshold = threshold or self.DEFAULT
        self.fs = fs
        n = int(self.WINDOW_S * fs)
        self.buf = np.zeros((2, 0))  # the last second of TP9 and TP10
        self.hann = np.hanning(n)
        f = np.fft.rfftfreq(n, 1 / fs)
        self.alpha_bins, self.broad_bins = (f >= 8) & (f < 13), (f >= 4) & (f < 30)
        self.n_seen = 0
        self.since = None  # sample index where the share went above the threshold
        self.fired = False
        self.level = None  # latest smoothed share as a fraction of the threshold: 1.0 means eyes closed
        self.recent = deque(maxlen=self.SMOOTH)

    def share(self, tp):
        """tp: (2, n) TP9 and TP10. Alpha's share of 4-30 Hz power, averaged over the two."""
        tp = tp - tp.mean(axis=1, keepdims=True)
        power = np.abs(np.fft.rfft(tp * self.hann, axis=1)) ** 2
        alpha = power[:, self.alpha_bins].sum(axis=1)
        broad = power[:, self.broad_bins].sum(axis=1)
        return float(np.mean(alpha / np.maximum(broad, 1e-9)))

    def calibrate(self, eeg):
        """Threshold from the eyes-open calibration window: RISE x the typical share, within sane bounds."""
        tp = finite(eeg)[[0, 3]]
        n = int(self.WINDOW_S * self.fs)
        # the same overlapping 1 s windows, a quarter second apart, that feed() looks at
        shares = [self.share(tp[:, i : i + n]) for i in range(0, tp.shape[1] - n + 1, n // 4)]
        if len(shares) < 20:
            return False
        self.threshold = min(0.8, max(0.3, self.RISE * float(np.median(shares))))
        return True

    def feed(self, eeg):
        """eeg: (4, n) chunk. True once per closure, after the eyes have stayed shut for HOLD_S."""
        tp = finite(eeg)[[0, 3]]
        n = len(self.hann)
        self.buf = np.concatenate([self.buf, tp], axis=1)[:, -n:]
        self.n_seen += tp.shape[1]
        if self.buf.shape[1] < n:
            return False
        self.recent.append(self.share(self.buf))
        s = float(np.median(self.recent))
        self.level = s / self.threshold
        if s < 0.8 * self.threshold:  # clearly open again: ready for the next closure
            self.since, self.fired = None, False
        elif s > self.threshold:
            if self.since is None:
                self.since = self.n_seen
            if not self.fired and (self.n_seen - self.since) / self.fs >= self.HOLD_S:
                self.fired = True
                return True
        return False


class ClenchDetector:
    """Jaw clench (a bite) = sustained >30 Hz muscle noise behind the ears (TP9, TP10), over the jaw muscles.

    Talking and chewing make short bursts; a clench holds for `min_s`. The level is the lower of the two ear
    channels, so one loose, noisy electrode can't fake a bite. The forehead pair is left out: on a real Muse
    its contact noise ran 100-200 uV and buried bites that lifted the ear channels from 4 to 30-60 uV.
    """

    def __init__(self, threshold_uv=40.0, min_s=1.0, fs=EEG_FS):
        self.threshold_uv = threshold_uv
        self.min_samples = int(min_s * fs)
        self.fs = fs
        notches = [tf2sos(*iirnotch(f, 30, fs=fs)) for f in (MAINS_HZ, 2 * MAINS_HZ) if f < fs / 2]
        self.sos = np.vstack([butter(4, 30, btype="high", fs=fs, output="sos"), *notches])
        self.win = int(0.25 * fs)
        self.zi = None
        self.pending = np.empty((2, 0))
        self.n_seen = 0
        self.run_start = None  # sample index where the current burst began
        self.below = 0
        self.level = None  # latest window level as a fraction of the threshold: 1.0 means biting
        self.rest_burst_frac = 0.0  # share of calibration windows already over the threshold: noise or tension

    def _muscle(self, eeg, zi=None):
        """Per-sample muscle signal behind each ear, (2, n); the filter starts settled so DC offset isn't a burst."""
        if zi is None:
            zi = sosfilt_zi(self.sos)[:, None, :] * eeg[:, :1][None, :, :]
        hp, zi = sosfilt(self.sos, eeg, axis=1, zi=zi)
        return hp[[0, 3]], zi

    def _windows(self, level):
        """0.25 s window levels: each ear's RMS, then the lower of the two."""
        n = level.shape[1] // self.win
        rms = np.sqrt(np.mean(np.square(level[:, : n * self.win].reshape(2, n, self.win)), axis=2))
        return rms.min(axis=0)

    def calibrate(self, relaxed_eeg):
        """Threshold from ~20 s with the jaw relaxed: 3x the typical 0.25 s window level.

        Median over windows, so a swallow, a word, or a headband adjustment
        during calibration barely moves it.
        """
        eeg = finite(relaxed_eeg)
        if eeg.ndim != 2 or eeg.shape[1] < 2 * self.win:
            return False
        level, _ = self._muscle(eeg)
        # 3x: on two real sessions every bite and hold cleared it with margin, and nothing else did
        windows = self._windows(level)
        self.threshold_uv = max(15.0, 3 * float(np.median(windows)))
        self.rest_burst_frac = float(np.mean(windows > self.threshold_uv))  # 0.00 on clean sessions, 0.16 on a loose, tense one
        return True

    @property
    def holding_s(self):
        """Seconds the current burst has lasted (0 when relaxed)."""
        return 0.0 if self.run_start is None else (self.n_seen - self.run_start) / self.fs

    @property
    def active(self):
        """True only once a burst has lasted long enough to count as a clench."""
        return self.holding_s * self.fs >= self.min_samples

    def feed(self, eeg):
        """eeg: (4, n) chunk. Returns finished clenches as (start_idx, duration_s)."""
        eeg = finite(eeg)
        if eeg.ndim != 2 or eeg.shape[1] == 0:
            return []
        level, self.zi = self._muscle(eeg, self.zi)
        self.pending = np.concatenate([self.pending, level], axis=1)
        events = []
        while self.pending.shape[1] >= self.win:
            w, self.pending = self.pending[:, : self.win], self.pending[:, self.win :]
            v = self._windows(w)[0]
            self.level = v / self.threshold_uv
            if v > self.threshold_uv:
                if self.run_start is None:
                    self.run_start = self.n_seen
                self.below = 0
            elif self.run_start is not None:
                self.below += self.win
                if self.below >= 2 * self.win:  # 0.5 s of quiet ends the burst
                    length = self.n_seen - self.below + self.win - self.run_start
                    if length >= self.min_samples:
                        events.append((self.run_start, length / self.fs))
                    self.run_start, self.below = None, 0
            self.n_seen += self.win
        return events


class PostureTracker:
    """Head tilt = angle between the current gravity vector and the calibrated upright one."""

    def __init__(self, fs=IMU_FS):
        self.upright = np.array([0.0, 0.0, 1.0])
        self.buf = deque(maxlen=int(2 * fs))
        self.tilt = 0.0

    def calibrate(self, accel):
        """accel: (3, n) recorded sitting upright, looking at the screen. False if there was no usable data."""
        a = np.asarray(accel, float)
        if a.ndim != 2 or a.shape[1] == 0 or not np.all(np.isfinite(a)):
            return False
        g = a.mean(axis=1)
        if not np.linalg.norm(g):
            return False
        self.upright = g
        return True

    def feed(self, accel):
        """accel: (3, n), possibly empty. Returns the current tilt in degrees (2 s average)."""
        a = np.asarray(accel, float)
        if a.ndim == 2 and a.shape[1]:
            self.buf.extend(v for v in a.T if np.all(np.isfinite(v)))
        if self.buf:
            g = np.mean(self.buf, axis=0)
            norm = np.linalg.norm(g) * np.linalg.norm(self.upright)
            if norm:
                self.tilt = float(np.degrees(np.arccos(np.clip(np.dot(g, self.upright) / norm, -1, 1))))
        return self.tilt


def _pulse(ppg, fs):
    """(bpm, irregularity) from ~10 s of one PPG channel, or None if there's no clean pulse."""
    x = finite(ppg)
    if len(x) < 5 * fs:
        return None
    x = sosfiltfilt(butter(2, [0.7, 3.5], btype="band", fs=fs, output="sos"), x)
    if not np.std(x):
        return None
    peaks, _ = find_peaks(x, distance=int(0.33 * fs), prominence=0.5 * np.std(x))
    if len(peaks) < 4:
        return None
    ibi = np.diff(peaks) / fs
    bpm, irregular = 60 / np.median(ibi), np.std(ibi) / np.mean(ibi)
    # band-passed noise has peaks too; a real pulse is regular and in human range
    if irregular > 0.15 or not 40 <= bpm <= 180:
        return None
    return float(bpm), float(irregular)


def heart_rate(ppg, fs=PPG_FS):
    """BPM from ~10 s of PPG, or None. Given (channels, n), the most regular channel wins."""
    rows = np.atleast_2d(np.asarray(ppg, float))
    pulses = [p for p in (_pulse(r, fs) for r in rows) if p]
    return min(pulses, key=lambda p: p[1])[0] if pulses else None


def band_rms(eeg, fs=EEG_FS):
    """Per-channel 1-30 Hz RMS in microvolts."""
    x = finite(eeg)
    y = sosfiltfilt(butter(2, [1, 30], btype="band", fs=fs, output="sos"), x, axis=1)
    return np.sqrt(np.mean(np.square(y), axis=1))


def contact(eeg, fs=EEG_FS):
    """Per-channel skin contact from the last ~2 s (True = good), or None with too little data.

    A dry electrode off the skin reads either nearly flat or very noisy.
    """
    x = np.asarray(eeg, float)
    if x.ndim != 2 or x.shape[1] < fs:
        return None
    return [bool(CONTACT_UV[0] <= r <= CONTACT_UV[1]) for r in band_rms(x, fs)]


def spectrum(eeg, fs=EEG_FS):
    """Welch power spectral density per channel: (freqs in Hz, psd in uV^2/Hz), 1 Hz bins."""
    x = finite(eeg)
    return welch(x, fs=fs, nperseg=min(fs, x.shape[-1]), axis=-1)


def band_powers(freqs, psd):
    """{band: power in uV^2 per channel}, the PSD summed over each band."""
    df = freqs[1] - freqs[0]
    return {name: psd[..., (freqs >= lo) & (freqs < hi)].sum(axis=-1) * df for name, lo, hi in BANDS}


class NodShakeDetector:
    """Head nods (yes) and shakes (no) from the Muse's gyroscope.

    A nod swings the head about one axis and a shake about another. Each needs two clear swings past MIN_RATE
    within WIN_S, mostly on its own axis, so reading, turning to look, or a bite's jolt fire nothing. The axes are
    the Muse's pitch and yaw rates by default (guessed); scripts/check_nod.py measures them from a few real nods
    and shakes and saves them to data/head_axes.json.
    """

    MIN_RATE = 40.0  # deg/s a swing must reach
    WIN_S = 1.6
    REFRACTORY_S = 1.5
    DOMINANCE = 2.0  # the watched axis must carry this much more motion than the other one

    def __init__(self, nod_axis=1, shake_axis=2, fs=IMU_FS):
        self.axes = {"nod": nod_axis, "shake": shake_axis}
        self.fs = fs
        self.buf = np.empty((3, 0))
        self.quiet_until = 0.0
        self.n_seen = 0

    @staticmethod
    def _swings(x, floor):
        """Number of runs of one sign that reach `floor`: a nod down and back up is two."""
        sign = np.sign(x)
        runs = np.flatnonzero(np.diff(sign) != 0) + 1
        return sum(1 for seg in np.split(x, runs) if len(seg) and np.max(np.abs(seg)) >= floor)

    def feed(self, gyro):
        """gyro: (3, n) deg/s. Returns ['nod'] or ['shake'] once per head movement."""
        g = finite(np.asarray(gyro, float))
        if g.ndim != 2 or g.shape[0] != 3 or g.shape[1] == 0:
            return []
        self.n_seen += g.shape[1]
        self.buf = np.hstack([self.buf, g])[:, -int(self.WIN_S * self.fs):]
        if self.n_seen / self.fs < self.quiet_until or self.buf.shape[1] < self.fs // 2:
            return []
        k = max(1, self.fs // 10)
        x = np.apply_along_axis(lambda v: np.convolve(v, np.ones(k) / k, "same"), 1, self.buf)  # ~0.1 s smoothing
        rms = np.sqrt(np.mean(np.square(x), axis=1))
        for kind, other in (("nod", "shake"), ("shake", "nod")):
            a, b = self.axes[kind], self.axes[other]
            if rms[a] >= self.DOMINANCE * rms[b] and self._swings(x[a], self.MIN_RATE) >= 2:
                self.quiet_until = self.n_seen / self.fs + self.REFRACTORY_S
                self.buf = np.empty((3, 0))
                return [kind]
        return []
