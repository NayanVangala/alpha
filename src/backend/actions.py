"""Texts (Telegram) and calls (Twilio) to the wearer's people.

Demo mode unless ACTIONS_DRY_RUN=false: nothing leaves the laptop, the board
just says what it would have sent. No SMS: US carriers block unregistered
numbers, and a Telegram bot works in minutes.
"""

import base64
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

CONTACTS = Path("data/contacts.json")  # gitignored: [{"name", "phone"?, "telegram_chat_id"?, "help"?}]
DEMO_CONTACTS = [{"name": "Mom", "help": True}, {"name": "Nurse"}]
MAX_CONTACTS = 6


def load_contacts(path=CONTACTS):
    if not path.exists():
        return DEMO_CONTACTS
    contacts = json.loads(path.read_text())
    if not 1 <= len(contacts) <= MAX_CONTACTS or not all(c.get("name") for c in contacts):
        raise ValueError(f"{path}: 1 to {MAX_CONTACTS} contacts, each with a name")
    return contacts


def help_contact(contacts):
    return next((c for c in contacts if c.get("help")), contacts[0])


def dry_run():
    return os.environ.get("ACTIONS_DRY_RUN", "true").lower() != "false"


def _post(url, data, headers):
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=10) as r:
        return r.status


def send_text(contact, text, post=_post):
    """Sends (or, in demo mode, describes) a Telegram message. Returns a line for the board's toast."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), contact.get("telegram_chat_id")
    if dry_run() or not (token and chat):
        return f"Would text {contact['name']}: “{text}” ({'demo mode' if dry_run() else 'no Telegram chat set up'})"
    post(f"https://api.telegram.org/bot{token}/sendMessage",
         json.dumps({"chat_id": chat, "text": text}).encode(), {"Content-Type": "application/json"})
    return f"Texted {contact['name']}"


def place_call(contact, text, post=_post):
    """Rings the contact and reads `text` aloud (Twilio). Returns a line for the board's toast."""
    sid, auth, from_ = (os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"))
    phone = contact.get("phone")
    if dry_run() or not (sid and auth and from_ and phone):
        return f"Would call {contact['name']} ({'demo mode' if dry_run() else 'no phone or Twilio set up'})"
    twiml = f"<Response><Say>{escape(text)}</Say></Response>"
    basic = base64.b64encode(f"{sid}:{auth}".encode()).decode()
    post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
         urllib.parse.urlencode({"To": phone, "From": from_, "Twiml": twiml}).encode(),
         {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    return f"Calling {contact['name']}"
