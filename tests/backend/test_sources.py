import numpy as np

from src.backend.sources import MuseSource, decode_accel, decode_eeg, decode_ppg, muse_command


def pack12(values):
    """Twelve 12-bit samples packed two per three bytes, the Muse's way."""
    out = bytearray()
    for a, b in zip(values[0::2], values[1::2]):
        out += bytes([a >> 4, ((a & 0xF) << 4) | (b >> 8), b & 0xFF])
    return bytes(out)


def test_eeg_packets_decode_to_microvolts():
    raw = [2048, 0, 4095, 1000, 2049, 2047, 1, 2, 3, 4, 5, 6]
    seq, uv = decode_eeg((513).to_bytes(2, "big") + pack12(raw))
    assert seq == 513 and np.allclose(uv, 0.48828125 * (np.array(raw) - 2048))


def test_accel_and_ppg_packets_decode():
    xyz = np.array([[16384, -16384, 0], [1, 2, 3], [-1, -2, -3]], dtype=">i2")  # three samples of x, y, z
    acc = decode_accel(b"\x00\x01" + xyz.tobytes())
    assert acc.shape == (3, 3) and np.isclose(acc[0, 0], 1.0, atol=1e-3) and np.isclose(acc[1, 0], -1.0, atol=1e-3)
    ppg = decode_ppg(b"\x00\x01" + bytes([0, 1, 0] * 6))
    assert list(ppg) == [256.0] * 6
    assert muse_command("p50") == b"\x04p50\n"


def test_channels_line_up_by_sequence_number_and_lost_packets_drop_their_block():
    m = MuseSource()
    pkt = lambda seq, v: seq.to_bytes(2, "big") + pack12([v] * 12)  # noqa: E731
    for ch in (2, 0, 3, 1):  # channels arrive in any order
        m._on_eeg(ch, None, pkt(7, 2048 + ch))
    m._on_eeg(0, None, pkt(8, 2048))  # block 8 never completes (the other channels' packets were lost)
    for seq in range(9, 26):
        for ch in range(4):
            m._on_eeg(ch, None, pkt(seq, 2048))
    eeg = m.read()["eeg"]
    assert eeg.shape == (4, 12 * 18)  # blocks 7 and 9-25; block 8 dropped
    assert np.allclose(eeg[:, 0], 0.48828125 * np.arange(4))  # block 7's channels in TP9, AF7, AF8, TP10 order
    assert m.read()["eeg"].shape == (4, 0)  # read hands each sample over once


def test_battery_comes_from_telemetry():
    m = MuseSource()
    assert m.battery is None
    m._on_telemetry(None, b"\x00\x07" + (0x8000).to_bytes(2, "big") + bytes(16))
    assert m.battery == 64.0  # 0x8000 / 512


def test_samples_keep_the_headbands_timing_through_wraparound_lost_packets_and_bluetooth_jitter(monkeypatch):
    m, now, rng = MuseSource(), [100.0], np.random.default_rng(0)
    monkeypatch.setattr("src.backend.sources.time.monotonic", lambda: now[0])
    pkt = lambda seq, v: seq.to_bytes(2, "big") + pack12([v] * 12)  # noqa: E731
    sent = [u for u in range(65530, 65560) if u != 65540]  # the packet number wraps at 65536; one packet lost
    for u in sent:
        now[0] = 100.0 + (u - 65530 + 1) * 12 / 256 + 0.02 + rng.uniform(0, 0.03)  # 20-50 ms after its last sample
        for ch in range(4):
            m._on_eeg(ch, None, pkt(u % 65536, 2048))
    t = m.read()["eeg_t"]
    truth = np.concatenate([100.0 + (u - 65530) * 12 / 256 + np.arange(12) / 256 for u in sent])
    assert len(t) == len(truth)
    assert np.all(np.abs(t - truth - 0.02) < 0.03)  # the lag Bluetooth always adds, give or take its jitter
