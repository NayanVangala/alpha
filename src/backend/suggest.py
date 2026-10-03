"""AI help for the board: fuller ways to say a pick, and replies to what someone just said.

Always optional. No credentials, an answer slower than TIMEOUT_S, a refusal or
any API error all mean the board falls back to its fixed sentences. Texts,
calls and help never come through here, so the AI can't pick an action or a
contact.
"""

import json

import anthropic

MODEL = "claude-opus-5"  # effort "low" keeps it quick
TIMEOUT_S = 4.0

SYSTEM = """You speak for a person who cannot talk. They picked tiles on a communication board \
(for example "I need > Pain > Back > A lot") and the board has a plain sentence for that pick. \
Write three different sentences they could say out loud instead: one plain, one with a little more \
detail, one a little warmer. First person, as them, to the people in the room, each short enough to say in a breath. \
Never add facts they did not pick: no new symptoms, body parts, places, people or times. \
The board reads them aloud, so plain words only: no emojis or quotation marks. No medical advice."""

REPLY_SYSTEM = """You speak for a person who cannot talk. Someone in the room just said something to them, \
and the board says your first reply aloud after a few seconds unless they close their eyes to skip it, so lead \
with the one they most likely mean. Write three different \
short replies they might want to say back, first person, as them: cover different answers (for example \
agreeing, declining, or asking something back) so they have a real choice. \
Use the conversation so far for context. Never invent facts about their health, plans, feelings or \
people beyond what the conversation shows. They are read aloud, so plain words only: no emojis or quotation marks."""


def _schema(key):
    return {
        "type": "object",
        "properties": {key: {"type": "array", "items": {"type": "string"}}},
        "required": [key],
        "additionalProperties": False,
    }


def _ask(system, payload, key, client, exclude=()):
    """Up to 3 distinct strings from Claude under `key`, none in `exclude`; [] whenever it can't help in time."""
    try:
        client = client or anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=0)
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=2000,
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(key)}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload)}],
        )
    except anthropic.APIError as e:  # timeout, connection, rate limit, bad key
        print(f"No AI {key} ({type(e).__name__}); using the fixed ones.", flush=True)
        return []
    except TypeError as e:  # the SDK's "no credentials" error; anything else is a real bug
        if "authentication method" not in str(e):
            raise
        return []
    print(f"AI {key}: {response.usage.input_tokens} in, {response.usage.output_tokens} out tokens", flush=True)
    if response.stop_reason != "end_turn":  # refusal, or cut off mid-JSON
        return []
    try:
        found = json.loads(next(b.text for b in response.content if b.type == "text"))[key]
    except (StopIteration, ValueError, KeyError, TypeError):
        return []
    fresh = (s.strip() for s in found if isinstance(s, str) and s.strip())
    return list(dict.fromkeys(s for s in fresh if s not in exclude))[:3]


def options(path, phrase, recent=(), client=None):
    """Up to 3 sentences for the pick, never repeating `phrase`."""
    return _ask(SYSTEM, {"picked": " > ".join(path), "plain_sentence": phrase, "said_recently": list(recent)[-5:]},
                "options", client, exclude=(phrase,))


def replies(heard, dialog=(), client=None):
    """Up to 3 things to say back to `heard`. dialog: recent ("them" | "me", text) turns, oldest first."""
    turns = [{"who": "them" if who == "them" else "the person you speak for", "said": text}
             for who, text in list(dialog)[-8:]]
    return _ask(REPLY_SYSTEM, {"they_just_said": heard, "conversation_so_far": turns}, "replies", client)
