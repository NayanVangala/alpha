"""Find EEG headbands nearby over Bluetooth LE.

Only the Muse 2 is supported. Other headbands are listed so people can see
their device was found, marked as not supported yet; the app never claims
they work.
"""

import re

from bleak import BleakScanner

# advertised-name patterns -> brand; first match wins. Muse S advertises "MuseS-", Muse 2 "Muse-".
BRANDS = [
    (re.compile(r"^MuseS-", re.I), "Muse S", False),
    (re.compile(r"^Muse-", re.I), "Muse 2", True),
    (re.compile(r"^Ganglion", re.I), "OpenBCI Ganglion", False),
    (re.compile(r"^(Crown|Neurosity)", re.I), "Neurosity Crown", False),
    (re.compile(r"^BrainBit", re.I), "BrainBit", False),
    (re.compile(r"^Callibri", re.I), "Callibri", False),
    (re.compile(r"^(EPOC|Insight|MN8|Emotiv)", re.I), "Emotiv", False),
    (re.compile(r"^Mendi", re.I), "Mendi", False),
    (re.compile(r"^enophone", re.I), "Enophone", False),
]

SIMULATED = {"name": "Muse-SIM", "brand": "Simulated Muse 2", "supported": True, "rssi": None, "simulated": True}


def classify(name):
    """(brand, supported) for an advertised name, or None if it isn't an EEG headband."""
    for pattern, brand, supported in BRANDS:
        if name and pattern.match(name):
            return brand, supported
    return None


def scan(seconds=4.0, simulated=False):
    """Headbands in range, strongest signal first. With `simulated`, only the labeled simulator."""
    if simulated:
        return [SIMULATED]
    from .sources import on_ble  # the shared Bluetooth loop: a scan on its own loop breaks the connection after it

    found = on_ble(BleakScanner.discover(timeout=seconds, return_adv=True), timeout=seconds + 10)
    devices = {}
    for device, adv in found.values():
        name = adv.local_name or device.name
        kind = classify(name)
        if kind and (name not in devices or adv.rssi > devices[name]["rssi"]):
            devices[name] = {"name": name, "brand": kind[0], "supported": kind[1], "rssi": adv.rssi, "simulated": False}
    return sorted(devices.values(), key=lambda d: (not d["supported"], -d["rssi"]))
