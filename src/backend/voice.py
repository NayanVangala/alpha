"""Spoken output: ElevenLabs when ELEVENLABS_API_KEY is set; otherwise the page uses the browser voice."""

import hashlib
import json
import os
import time
import urllib.request
from pathlib import Path

CACHE = Path("data/audio_cache")
API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # a stock voice; set ELEVENLABS_VOICE_ID to the wearer's cloned voice
DEFAULT_MODEL = "eleven_flash_v2_5"  # the low-latency model
PAUSE_S = 60  # after a failure, use the browser voice for a minute instead of stalling every sentence

_failed_at = -1e9


def _fetch(key, voice, model, text):
    req = urllib.request.Request(
        API.format(voice=voice),
        data=json.dumps({"text": text, "model_id": model}).encode(),
        headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        return r.read()


def speech_file(text, fetch=_fetch, clock=time.monotonic):
    """Path to an mp3 of `text`, or None when the browser voice should say it instead."""
    global _failed_at
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None
    voice = os.environ.get("ELEVENLABS_VOICE_ID", DEFAULT_VOICE)
    model = os.environ.get("ELEVENLABS_MODEL", DEFAULT_MODEL)
    path = CACHE / (hashlib.sha256(f"{voice}|{model}|{text}".encode()).hexdigest() + ".mp3")
    if path.exists():
        return path
    if clock() - _failed_at < PAUSE_S:
        return None
    try:
        audio = fetch(key, voice, model, text)
    except OSError as e:  # URLError, HTTPError (bad key, no credits) and timeouts are all OSErrors
        _failed_at = clock()
        print(f"ElevenLabs failed, using the browser voice for {PAUSE_S} s: {e}", flush=True)
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(audio)
    tmp.replace(path)  # a half-written file never looks cached
    return path
