import pytest

from src.backend import voice


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "CACHE", tmp_path)
    monkeypatch.setattr(voice, "_failed_at", -1e9)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")


def test_no_key_means_the_browser_voice(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY")
    assert voice.speech_file("Hi.", fetch=lambda *a: pytest.fail("no key, no call")) is None


def test_fetches_once_then_serves_the_cache():
    calls = []

    def fetch(key, v, m, text):
        calls.append(text)
        return b"mp3"

    first, again = voice.speech_file("Hi.", fetch=fetch), voice.speech_file("Hi.", fetch=fetch)
    assert first == again and first.read_bytes() == b"mp3" and calls == ["Hi."]


def test_a_failure_pauses_elevenlabs_for_a_while():
    t = [0.0]

    def boom(*a):
        raise OSError("HTTP Error 401")

    assert voice.speech_file("A", fetch=boom, clock=lambda: t[0]) is None
    t[0] = voice.PAUSE_S - 1
    assert voice.speech_file("B", fetch=lambda *a: pytest.fail("still paused"), clock=lambda: t[0]) is None
    t[0] = voice.PAUSE_S + 1
    assert voice.speech_file("B", fetch=lambda *a: b"x", clock=lambda: t[0]) is not None
