import base64
import json
import urllib.parse

import pytest

from src.backend import actions

MOM = {"name": "Mom", "phone": "+15550000000", "telegram_chat_id": "42"}
CREDS = {"TELEGRAM_BOT_TOKEN": "t", "TWILIO_ACCOUNT_SID": "AC1", "TWILIO_AUTH_TOKEN": "a", "TWILIO_FROM_NUMBER": "+15551111111"}


def boom(*a):
    pytest.fail("sent something it shouldn't have")


def test_demo_mode_is_the_default_and_sends_nothing(monkeypatch):
    monkeypatch.delenv("ACTIONS_DRY_RUN", raising=False)
    for k, v in CREDS.items():
        monkeypatch.setenv(k, v)
    assert "demo mode" in actions.send_text(MOM, "Hi", post=boom)
    assert "demo mode" in actions.place_call(MOM, "Hi", post=boom)


def test_live_text_and_call(monkeypatch):
    monkeypatch.setenv("ACTIONS_DRY_RUN", "false")
    for k, v in CREDS.items():
        monkeypatch.setenv(k, v)
    sent = []

    def post(url, data, headers):
        sent.append((url, data, headers))

    assert actions.send_text(MOM, "Come here", post=post) == "Texted Mom"
    url, data, _ = sent[0]
    assert url == "https://api.telegram.org/bott/sendMessage" and json.loads(data) == {"chat_id": "42", "text": "Come here"}
    assert actions.place_call(MOM, "Tom & <Jerry>", post=post) == "Calling Mom"
    url, data, headers = sent[1]
    form = urllib.parse.parse_qs(data.decode())
    assert url == "https://api.twilio.com/2010-04-01/Accounts/AC1/Calls.json"
    assert form["To"] == ["+15550000000"] and form["Twiml"] == ["<Response><Say>Tom &amp; &lt;Jerry&gt;</Say></Response>"]
    assert headers["Authorization"] == "Basic " + base64.b64encode(b"AC1:a").decode()


def test_live_mode_without_details_says_what_is_missing(monkeypatch):
    monkeypatch.setenv("ACTIONS_DRY_RUN", "false")
    for k in CREDS:
        monkeypatch.delenv(k, raising=False)
    assert "no Telegram" in actions.send_text({"name": "Nurse"}, "Hi", post=boom)
    assert "no phone" in actions.place_call({"name": "Nurse"}, "Hi", post=boom)


def test_contacts_file(tmp_path):
    assert actions.load_contacts(tmp_path / "missing.json") == actions.DEMO_CONTACTS
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps([{"name": "Dad"}, {"phone": "+1"}]))
    with pytest.raises(ValueError):
        actions.load_contacts(bad)
    assert actions.help_contact([{"name": "A"}, {"name": "B", "help": True}])["name"] == "B"
    assert actions.help_contact([{"name": "A"}])["name"] == "A"
