"""Board inputs from the headband: a short jaw clench, a long clench, a double blink, a glance left or right,
and eyes closed (alpha rising: the brake for a coding agent).

The keyboard stand-in on the board page sends the same events (arrow keys for
glances), so the board can't tell a headband from a keyboard.
"""

from .signals import EEG_FS, ClenchDetector, EyesClosedDetector, GlanceDetector

TAP_MIN_S = 0.5  # shorter bursts are talking or chewing (0.25 s let every synthetic chew through)
LONG_S = 2.5  # hold this long for the help countdown
DOUBLE_BLINK_S = (0.15, 0.8)  # gap between the two blinks of a deliberate double blink
# Off for the headband: on a real Muse a deliberate double blink came through as one blink, while natural blinks
# often come in close pairs, and a false double blink would cancel a help call. Eyes closed does its jobs
# (go back, cancel help); the keyboard's B still sends one.
HEADBAND_DOUBLE_BLINK = False
# Off for the headband too: on two real sessions, silently reading swung the forehead pair (AF7 - AF8) more than
# deliberately looking left or right did, so no threshold separates them and the highlight would wander. The
# arrow keys still glance. ponytail: turn on per wearer once a tuning session shows clean looks.
HEADBAND_GLANCES = False


class Gestures:
    def __init__(self, clench_threshold_uv=40.0, eyes_threshold=None, fs=EEG_FS):
        self.clench = ClenchDetector(clench_threshold_uv, min_s=TAP_MIN_S, fs=fs)
        self.fs = fs
        self.long_sent = None  # run_start of the burst that already fired long_clench
        self.last_blink = None
        self.glance = GlanceDetector(fs=fs)
        self.eyes = EyesClosedDetector(eyes_threshold, fs=fs)

    def feed(self, eeg, blinks=()):
        """eeg: (4, n) chunk; blinks: sample indices from the coach's BlinkDetector.

        Returns [(kind, ago_s)]. For a clench, ago_s is how long ago it began,
        so the board picks the tile that was lit when the jaw started to close.
        """
        out = []
        c = self.clench
        for start, dur in c.feed(eeg):
            if start == self.long_sent:
                continue  # already fired as long_clench while it was held
            out.append(("long_clench", 0.0) if dur >= LONG_S else ("clench", (c.n_seen - start) / self.fs))
        # fire while still held; below == 0 means the latest window was still clenched
        if c.run_start is not None and c.below == 0 and c.holding_s >= LONG_S and self.long_sent != c.run_start:
            self.long_sent = c.run_start
            out.append(("long_clench", 0.0))
        for i in blinks if HEADBAND_DOUBLE_BLINK else ():
            if self.last_blink is not None and DOUBLE_BLINK_S[0] <= (i - self.last_blink) / self.fs <= DOUBLE_BLINK_S[1]:
                out.append(("double_blink", 0.0))
                self.last_blink = None
            else:
                self.last_blink = i
        for side in self.glance.feed(eeg[1], eeg[2]) if HEADBAND_GLANCES else ():
            if c.run_start is None:  # a clenching jaw shakes the forehead channels too
                out.append((f"glance_{side}", 0.0))
        if eeg.shape[1] and self.eyes.feed(eeg):
            out.append(("eyes_closed", 0.0))
        return out
