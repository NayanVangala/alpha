import numpy as np
import pytest

from src.backend.signals import (
    EEG_FS,
    IMU_FS,
    PPG_FS,
    BlinkDetector,
    ClenchDetector,
    PostureTracker,
    band_powers,
    contact,
    heart_rate,
    spectrum,
)


def bump(n, center_s, width_s, amp, fs=EEG_FS):
    t = np.arange(n) / fs
    return amp * np.exp(-0.5 * ((t - center_s) / width_s) ** 2)


def fake_eeg(rng, seconds, blinks=(), glances=(), clenches=(), chews=()):
    """(4, n) microvolts: TP9, AF7, AF8, TP10."""
    n = seconds * EEG_FS
    eeg = rng.normal(0, 8, (4, n))
    for t in blinks:
        b = bump(n, t, 0.06, 200)
        eeg[1] += b
        eeg[2] += b
    for t in glances:  # opposite polarity on AF7 vs AF8
        g = bump(n, t, 0.15, 150)
        eeg[1] += g
        eeg[2] -= g
    for start, dur in list(clenches) + list(chews):
        a, b = int(start * EEG_FS), int((start + dur) * EEG_FS)
        eeg[:, a:b] += rng.normal(0, 80, (4, b - a))
    return eeg


def stream(feed, data, chunk=64):
    out = []
    for i in range(0, data.shape[-1], chunk):
        out += feed(data[..., i : i + chunk])
    return out


@pytest.mark.parametrize("seed", range(20))
def test_blinks_counted_once_and_glances_ignored(seed):
    blinks = [2, 4.5, 7, 9.2, 12, 15]
    eeg = fake_eeg(np.random.default_rng(seed), 18, blinks=blinks, glances=[5.8, 10.5, 13.5])
    det = BlinkDetector()
    found = [i / EEG_FS for i in stream(lambda c: det.feed(c[1], c[2]), eeg)]
    assert len(found) == len(blinks), found
    assert all(abs(a - b) < 0.1 for a, b in zip(found, blinks))


@pytest.mark.parametrize("seed", range(10))
def test_blink_calibration_handles_flipped_polarity(seed):
    eeg = fake_eeg(np.random.default_rng(seed), 20, blinks=[2, 5, 8, 11, 14, 17])
    eeg[1:3] *= -1
    det = BlinkDetector()
    assert det.calibrate(eeg[1], eeg[2])
    assert det.sign == -1
    assert len(stream(lambda c: det.feed(c[1], c[2]), eeg)) == 6


def test_blink_calibration_without_blinks_keeps_defaults():
    eeg = fake_eeg(np.random.default_rng(0), 20)
    dip = bump(eeg.shape[1], 10, 0.1, 300)  # headband adjusted, no blinks
    eeg[1] -= dip
    eeg[2] -= dip
    det = BlinkDetector()
    assert not det.calibrate(eeg[1], eeg[2])
    assert (det.sign, det.threshold_uv) == (1, 90.0)


@pytest.mark.parametrize("seed", range(10))
def test_clench_counts_sustained_not_chewing(seed):
    rng = np.random.default_rng(seed)
    eeg = fake_eeg(rng, 20, clenches=[(3, 2.5), (12, 1.5)], chews=[(8, 0.3), (9, 0.3), (10, 0.3)])
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 5))
    events = stream(det.feed, eeg)
    assert len(events) == 2, events
    (s1, d1), (s2, d2) = events
    assert abs(s1 / EEG_FS - 3) < 0.3 and abs(d1 - 2.5) < 0.4
    assert abs(s2 / EEG_FS - 12) < 0.3 and abs(d2 - 1.5) < 0.4


def test_clench_calibration_survives_a_clench_while_calibrating():
    rng = np.random.default_rng(0)
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 20, clenches=[(5, 3)]))  # talked or clenched during calibration
    assert len(stream(det.feed, fake_eeg(rng, 10, clenches=[(3, 3)]))) == 1


def test_clench_shows_active_only_once_held():
    rng = np.random.default_rng(0)
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 5))
    active = []
    for chunk in np.split(fake_eeg(rng, 6, chews=[(1, 0.4)], clenches=[(3, 2)]), 6 * 4, axis=1):
        det.feed(chunk)
        active.append(det.active)
    assert not any(active[:12])  # chewing at 1 s never reads as clenching
    assert any(active[12:])


def test_one_loose_electrode_is_not_a_clench():
    rng = np.random.default_rng(0)
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 5))
    eeg = fake_eeg(rng, 10)
    eeg[0, 2 * EEG_FS : 8 * EEG_FS] += rng.normal(0, 300, 6 * EEG_FS)  # TP9 lost skin contact
    assert stream(det.feed, eeg) == []


def test_mains_hum_is_not_a_clench():
    rng = np.random.default_rng(0)
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 5))
    eeg = fake_eeg(rng, 10) + 40 * np.sin(2 * np.pi * 60 * np.arange(10 * EEG_FS) / EEG_FS)
    assert stream(det.feed, eeg) == []


def test_detectors_survive_empty_and_nan_chunks():
    rng = np.random.default_rng(0)
    assert BlinkDetector().feed(np.empty(0), np.empty(0)) == []
    assert ClenchDetector().feed(np.empty((4, 0))) == []
    p = PostureTracker()
    assert p.feed(np.empty((3, 0))) == 0.0
    assert not p.calibrate(np.empty((3, 0)))
    c = ClenchDetector()
    c.calibrate(fake_eeg(rng, 5))
    eeg = fake_eeg(rng, 10, clenches=[(5, 3)])
    eeg[:, 100] = np.nan  # one bad sample must not disable detection for the session
    assert len(stream(c.feed, eeg)) == 1


def test_posture_tilt_angle():
    p = PostureTracker()
    upright = np.tile([[0.0], [0.1], [0.99]], (1, IMU_FS * 2))
    assert p.calibrate(upright)
    assert p.feed(upright) < 1
    a = np.radians(25)
    slouch = np.tile([[0.0], [0.1 + np.sin(a)], [np.cos(a)]], (1, IMU_FS * 3))
    assert 20 < p.feed(slouch) < 32
    assert 20 < p.feed(np.empty((3, 0))) < 32  # no new data keeps the last reading


@pytest.mark.parametrize("seed", range(20))
def test_heart_rate_real_pulse_vs_noise(seed):
    rng = np.random.default_rng(seed)
    t = np.arange(12 * PPG_FS) / PPG_FS
    pulse = np.sin(2 * np.pi * 72 / 60 * t) + rng.normal(0, 0.2, len(t))
    assert abs(heart_rate(pulse) - 72) < 3
    assert heart_rate(rng.normal(0, 1, len(t))) is None  # sensor off the skin: no fake pulse
    assert heart_rate(pulse[:PPG_FS]) is None


def test_heart_rate_picks_the_channel_with_a_pulse():
    rng = np.random.default_rng(0)
    t = np.arange(12 * PPG_FS) / PPG_FS
    ppg = rng.normal(0, 0.3, (3, len(t)))
    ppg[2] += np.sin(2 * np.pi * 66 / 60 * t)
    assert abs(heart_rate(ppg) - 66) < 3


def test_contact_flags_flat_and_noisy_electrodes():
    rng = np.random.default_rng(0)
    eeg = fake_eeg(rng, 2)
    assert contact(eeg) == [True] * 4
    eeg[0] = 800.0  # flat: electrode lifted
    eeg[3] += rng.normal(0, 400, eeg.shape[1])  # noisy: poor contact
    assert contact(eeg) == [False, True, True, False]
    assert contact(eeg[:, :10]) is None


@pytest.mark.parametrize("hz, band", [(10, "alpha"), (40, "gamma"), (2, "delta")])
def test_band_powers_put_a_rhythm_in_its_band(hz, band):
    t = np.arange(4 * EEG_FS) / EEG_FS
    eeg = np.tile(20 * np.sin(2 * np.pi * hz * t), (4, 1)) + np.random.default_rng(0).normal(0, 1, (4, len(t)))
    bands = band_powers(*spectrum(eeg))
    assert max(bands, key=lambda b: bands[b][0]) == band
    assert bands[band][0] == pytest.approx(20**2 / 2, rel=0.15)  # a sine's power is amplitude^2 / 2


def test_the_simulator_closing_its_eyes_raises_alpha_past_the_line():
    import time

    from src.backend.signals import EyesClosedDetector
    from src.backend.sources import SimSource

    sim, det = SimSource(seed=0), EyesClosedDetector()
    sim.t0 = sim.last = time.monotonic() - 20
    assert det.calibrate(sim.read()["eeg"])  # 20 s, eyes open
    sim.eyes_closed = True
    sim.last = time.monotonic() - 3
    eeg = sim.read()["eeg"]
    assert any(det.feed(eeg[:, i : i + 64]) for i in range(0, eeg.shape[1], 64)) and det.level > 1


def test_clench_level_is_the_live_fraction_of_the_threshold():
    rng = np.random.default_rng(0)
    det = ClenchDetector()
    det.calibrate(fake_eeg(rng, 5))
    det.feed(fake_eeg(rng, 1))
    assert 0.1 < det.level < 1.0  # relaxed: below the line
    det.feed(fake_eeg(rng, 2, clenches=[(0.2, 1.5)]))
    stream(det.feed, fake_eeg(rng, 1, clenches=[(0, 1)]))
    assert det.level > 1.0  # biting: over it
