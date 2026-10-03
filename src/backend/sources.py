"""Data sources: the real Muse 2 over Bluetooth LE, or a simulator for building without it.

Both return new samples since the last read(); any array may be empty:
  {"eeg": (4, n) uV [TP9, AF7, AF8, TP10], "eeg_t": (n,) time.monotonic() each EEG sample was taken,
   "accel": (3, n), "ppg": (3, n)}
"""

import asyncio
import threading
import time
from collections import deque
from functools import partial

import numpy as np
from bleak import BleakClient, BleakScanner
from scipy.signal import lfilter

from .signals import EEG_FS, IMU_FS, PPG_FS

MUSE_UUID = "273e00{:02x}-4c4d-454d-96be-f03bac821358"  # the Muse's characteristics: 0x01 control, 0x03-0x06 EEG...
EEG_CHARS = (0x03, 0x04, 0x05, 0x06)  # TP9, AF7, AF8, TP10
ACCEL_CHAR = 0x0A
PPG_CHARS = (0x0F, 0x10, 0x11)
TELEMETRY_CHAR = 0x0B  # battery and temperature, every few seconds


_ble_loop = None
_ble_lock = threading.Lock()


def ble_loop():
    """The one event loop every Bluetooth call in this process runs on.

    On macOS, bleak's CoreBluetooth objects belong to the loop that made them. A connection made on a fresh
    loop after a scan on another one stopped getting data after a couple of seconds, every time.
    """
    global _ble_loop
    with _ble_lock:
        if _ble_loop is None:
            _ble_loop = asyncio.new_event_loop()
            threading.Thread(target=_ble_loop.run_forever, name="bluetooth", daemon=True).start()
        return _ble_loop


def on_ble(coro, timeout=None):
    """Run a coroutine on the Bluetooth loop and wait for its result."""
    return asyncio.run_coroutine_threadsafe(coro, ble_loop()).result(timeout)


def muse_command(text):
    """A control command as the Muse wants it: a length byte, the text, a newline."""
    return bytes([len(text) + 1]) + (text + "\n").encode()


def decode_eeg(data):
    """One EEG packet: a 16-bit sequence number, then twelve 12-bit samples. Returns (seq, microvolts)."""
    a = np.frombuffer(bytes(data[2:20]), np.uint8).astype(np.int32).reshape(6, 3)
    raw = np.empty(12, np.int32)
    raw[0::2] = (a[:, 0] << 4) | (a[:, 1] >> 4)
    raw[1::2] = ((a[:, 1] & 0xF) << 8) | a[:, 2]
    return int.from_bytes(bytes(data[:2]), "big"), 0.48828125 * (raw - 2048)


def decode_accel(data):
    """Three accelerometer samples, x y z each, in g: returns (3 axes, 3 samples)."""
    return np.frombuffer(bytes(data[2:20]), ">i2").reshape(3, 3).T * 0.0000610352


def decode_ppg(data):
    """Six 24-bit optical (heart-rate) samples."""
    b = np.frombuffer(bytes(data[2:20]), np.uint8).astype(np.int64).reshape(6, 3)
    return ((b[:, 0] << 16) | (b[:, 1] << 8) | b[:, 2]).astype(float)


class MuseSource:
    """The Muse 2, spoken to directly over Bluetooth LE (the protocol muselsl and muse-js use).

    BrainFlow's Muse connection hangs on macOS 26 right after finding the headband, while a plain bleak
    connection takes about 2 s. A background thread runs the Bluetooth loop; read() hands over what arrived.
    """

    FIND_S, CONNECT_S = 10, 20

    def __init__(self, serial_number=""):
        self.name = serial_number  # e.g. "Muse-3889"; empty: the first Muse found
        self.lock = threading.Lock()
        self.task = self.stopping = None
        self.connected, self.error = False, None
        self.battery = None  # percent, from the headband's telemetry
        self.packets, self.last_packet = 0, None  # for diagnosing a stream that goes quiet
        self._clear()

    def _clear(self):
        self.blocks, self.eeg, self.eeg_t, self.accel, self.ppg = {}, [], [], [], [[], [], []]
        self.seq_hi = None  # highest packet number so far, unwrapped past 65535
        self.offsets = deque(maxlen=640)  # ~30 s of (arrival - sample clock): the smallest is the true offset

    def start(self):
        """Connect and start streaming; raises if the headband can't be reached."""
        self._clear()
        self.connected, self.error = False, None
        ready = threading.Event()
        self.task = asyncio.run_coroutine_threadsafe(self._run(ready), ble_loop())
        ready.wait(self.FIND_S + self.CONNECT_S + 5)
        if not self.connected:
            self.stop()
            raise RuntimeError(self.error or "the headband didn't answer")

    async def _run(self, ready):
        self.stopping = asyncio.Event()
        try:
            if self.name:
                device = await BleakScanner.find_device_by_name(self.name, timeout=self.FIND_S)
            else:
                device = await BleakScanner.find_device_by_filter(
                    lambda d, adv: (adv.local_name or d.name or "").startswith("Muse-"), timeout=self.FIND_S)
            if device is None:
                raise RuntimeError("not found nearby; is it on, with its lights sweeping?")
            async with BleakClient(device, timeout=self.CONNECT_S, disconnected_callback=lambda _: self.stopping.set()) as c:
                for i, n in enumerate(EEG_CHARS):
                    await c.start_notify(MUSE_UUID.format(n), partial(self._on_eeg, i))
                await c.start_notify(MUSE_UUID.format(ACCEL_CHAR), self._on_accel)
                for i, n in enumerate(PPG_CHARS):
                    await c.start_notify(MUSE_UUID.format(n), partial(self._on_ppg, i))
                await c.start_notify(MUSE_UUID.format(TELEMETRY_CHAR), self._on_telemetry)
                for text in ("h", "p50", "s", "d"):  # pause, the EEG + heart-rate preset, start, resume
                    await c.write_gatt_char(MUSE_UUID.format(0x01), muse_command(text), response=False)
                    await asyncio.sleep(0.1)
                self.connected = True
                ready.set()
                await self.stopping.wait()
                if c.is_connected:
                    await c.write_gatt_char(MUSE_UUID.format(0x01), muse_command("h"), response=False)
        except Exception as e:  # out of range, switched off, Bluetooth off: start() reports it
            self.error = str(e) or type(e).__name__
        finally:
            self.connected = False
            ready.set()

    def stream(self):
        """Packets received so far, and seconds since the last one (None before any)."""
        return {"packets": self.packets, "quiet_s": None if self.last_packet is None else round(time.monotonic() - self.last_packet, 1),
                "connected": self.connected, "error": self.error}

    def _on_eeg(self, channel, _, data):
        now = time.monotonic()
        self.packets += 1
        self.last_packet = now
        seq, uv = decode_eeg(data)
        with self.lock:
            # the four channels' packets share a sequence number; the 5th slot is when the first one arrived
            block = self.blocks.setdefault(seq, [None] * 4 + [now])
            block[channel] = uv
            if all(b is not None for b in block[:4]):
                self.eeg.append(np.vstack(block[:4]))
                self.eeg_t.append(self._sample_times(seq, block[4]))
                del self.blocks[seq]
            elif len(self.blocks) > 16:  # a channel's packet was lost: drop that block rather than misalign
                del self.blocks[min(self.blocks)]

    def _sample_times(self, seq, arrived):
        """When each of a packet's 12 samples was taken, on time.monotonic().

        The packet number counts samples on the headband's own clock, so a late or lost packet can't shift the
        times; that clock is pinned to this computer's by the earliest-arriving recent packet (the one Bluetooth
        delayed least). Good to a few ms, which lining EEG up with on-screen flashes needs.
        """
        if self.seq_hi is None:
            self.seq_hi = seq
        d = (seq - self.seq_hi) % 65536
        n = self.seq_hi + (d - 65536 if d >= 32768 else d)  # a packet slightly out of order counts back
        self.seq_hi = max(self.seq_hi, n)
        start = n * 12 / EEG_FS
        self.offsets.append(arrived - (start + 12 / EEG_FS))  # it can only arrive after its last sample
        return min(self.offsets) + start + np.arange(12) / EEG_FS

    def _on_accel(self, _, data):
        with self.lock:
            self.accel.append(decode_accel(data))

    def _on_telemetry(self, _, data):
        self.battery = int.from_bytes(bytes(data[2:4]), "big") / 512  # percent, as muse-js reads it

    def _on_ppg(self, channel, _, data):
        with self.lock:
            self.ppg[channel].append(decode_ppg(data))

    def read(self):
        with self.lock:
            eeg, eeg_t, accel, ppg = self.eeg, self.eeg_t, self.accel, self.ppg
            self.eeg, self.eeg_t, self.accel, self.ppg = [], [], [], [[], [], []]
        ppg = [np.concatenate(p) if p else np.empty(0) for p in ppg]
        n = min(len(p) for p in ppg)
        return {
            "eeg": np.hstack(eeg) if eeg else np.empty((4, 0)),
            "eeg_t": np.concatenate(eeg_t) if eeg_t else np.empty(0),
            "accel": np.hstack(accel) if accel else np.empty((3, 0)),
            "ppg": np.vstack([p[:n] for p in ppg]) if n else np.empty((3, 0)),
        }

    def stop(self):
        if self.task and not self.task.done():
            if self.stopping:
                ble_loop().call_soon_threadsafe(self.stopping.set)
            try:
                self.task.result(5)
            except Exception:  # timed out or failed: it's on its way down either way
                self.task.cancel()


class SimSource:
    """Fake headband: noise with a 1/f drift and a 10 Hz alpha rhythm, ~15 blinks/min, a 2-4 s clench
    about every 45 s, slow slouching, 70 bpm pulse.

    `eyes_closed` (the board's E key in simulator mode) swells the alpha rhythm the way shutting the eyes
    does, so the real detector and the board's alpha meter react to it.
    """

    def __init__(self, seed=None):
        self.rng = np.random.default_rng(seed)
        self.t0 = self.last = None
        self.clench_until = 0.0
        self.pending_blink = np.zeros(0)
        self.drift_zi = np.zeros((4, 1))
        self.eyes_closed = False

    def start(self):
        self.t0 = self.last = time.monotonic()

    def stop(self):
        pass

    def read(self):
        now = time.monotonic()
        dt, self.last = now - self.last, now
        n = int(dt * EEG_FS)
        elapsed = now - self.t0
        eeg = self.rng.normal(0, 8, (4, n))

        # brain-like background: slow 1/f drift, plus alpha (10 Hz) that waxes and wanes, strongest behind the ears
        drift, self.drift_zi = lfilter([0.05], [1, -0.95], self.rng.normal(0, 30, (4, n)), axis=1, zi=self.drift_zi)
        ts = (elapsed - dt) + np.arange(n) / EEG_FS
        swell = 22 if self.eyes_closed else 3 + 2 * np.sin(2 * np.pi * ts / 7)  # eyes open: a gentle wax and wane
        alpha = swell * np.sin(2 * np.pi * 10 * ts)
        eeg += drift + np.outer([1.0, 0.4, 0.4, 1.0], alpha)

        # blinks: 200 uV bump on AF7+AF8, carried over chunk edges
        tail = np.zeros(n + EEG_FS)
        tail[: len(self.pending_blink)] += self.pending_blink[: n + EEG_FS]
        t = np.arange(int(0.5 * EEG_FS)) / EEG_FS
        shape = 200 * np.exp(-0.5 * ((t - 0.25) / 0.06) ** 2)
        for i in np.flatnonzero(self.rng.random(n) < 15 / 60 / EEG_FS):
            tail[i : i + len(shape)] += shape
        eeg[1:3] += tail[:n]
        self.pending_blink = tail[n:]

        # clench: sustained EMG noise for 2-4 s
        if elapsed > self.clench_until and self.rng.random() < dt / 45:
            self.clench_until = elapsed + self.rng.uniform(2, 4)
        if elapsed < self.clench_until:
            eeg += self.rng.normal(0, 80, (4, n))

        # posture: head drifts forward ~1 degree per minute, noisy
        tilt = np.radians(min(40, elapsed / 60) + self.rng.normal(0, 0.5))
        k = int(dt * IMU_FS)
        accel = np.tile([[0.0], [np.sin(tilt)], [np.cos(tilt)]], (1, k)) + self.rng.normal(0, 0.01, (3, k))

        # PPG: pulse on the middle optical channel only, like one good LED
        m = int(dt * PPG_FS)
        tp = (elapsed - dt) + np.arange(m) / PPG_FS
        ppg = self.rng.normal(0, 0.2, (3, m))
        ppg[1] += np.sin(2 * np.pi * 70 / 60 * tp)
        return {"eeg": eeg, "eeg_t": now - dt + np.arange(n) / EEG_FS, "accel": accel, "ppg": ppg}
