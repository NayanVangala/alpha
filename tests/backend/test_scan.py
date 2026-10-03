from src.backend.scan import classify, scan


def test_only_muse_2_is_supported():
    assert classify("Muse-1A2B") == ("Muse 2", True)
    assert classify("MuseS-9F3C") == ("Muse S", False)
    assert classify("Ganglion-0C4E") == ("OpenBCI Ganglion", False)
    assert classify("Crown-a1") == ("Neurosity Crown", False)
    assert classify("AirPods Pro") is None and classify(None) is None


def test_simulated_scan_is_labeled():
    (device,) = scan(simulated=True)
    assert device["simulated"] and device["supported"] and "Simulated" in device["brand"]
