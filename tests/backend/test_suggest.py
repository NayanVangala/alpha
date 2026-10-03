import json
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from src.backend import suggest


def client_returning(found=None, stop="tool_use", error=None):
    """A fake client: Claude answers through the forced `answer` tool, so `found` is the tool's input."""
    def create(**kw):
        if error:
            raise error
        client.kw = kw
        content = [NS(type="text", text="")] + ([NS(type="tool_use", name="answer", input=found)] if found is not None else [])
        return NS(stop_reason=stop, usage=NS(input_tokens=1, output_tokens=1), content=content)

    client = NS(messages=NS(create=create))
    return client


def test_up_to_three_fresh_options_and_what_is_sent():
    c = client_returning({"options": [
        "My back really hurts.", "My back hurts a lot.", "My back really hurts.", "Could you help with my back?", "A fourth one."]})
    got = suggest.options(["I need", "Pain", "Back", "A lot"], "My back hurts a lot.", recent=["Yes."], client=c,
                          voice=["Water, please.", "Thanks, love."], hour=9)
    assert got == ["My back really hurts.", "Could you help with my back?", "A fourth one."]  # no repeats, no plain phrase
    assert c.kw["model"] == suggest.MODEL == "claude-haiku-4-5-20251001"
    assert c.kw["tool_choice"] == {"type": "tool", "name": "answer"}
    body = json.loads(c.kw["messages"][0]["content"])
    assert body == {"picked": "I need > Pain > Back > A lot", "plain_sentence": "My back hurts a lot.", "said_recently": ["Yes."],
                    "how_they_talk": ["Water, please.", "Thanks, love."], "part_of_day": "morning"}


@pytest.mark.parametrize("client", [
    client_returning({"options": ["Nope."]}, stop="refusal"),
    client_returning({"options": ["cut"]}, stop="max_tokens"),
    client_returning(None),
    client_returning({"other": []}),
    client_returning(error=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))),
    client_returning(error=TypeError("Could not resolve authentication method. Expected either api_key...")),
])
def test_anything_wrong_means_just_the_plain_phrase(client):
    assert suggest.options(["Answer", "Yes"], "Yes.", client=client) == []


def test_other_type_errors_are_real_bugs():
    with pytest.raises(TypeError):
        suggest.options(["Answer", "Yes"], "Yes.", client=client_returning(error=TypeError("unexpected keyword")))


def test_replies_send_the_conversation_and_come_back_distinct():
    c = client_returning({"replies": ["Yes, please.", "Not right now.", "Yes, please.", "Is it cold?"]})
    got = suggest.replies("Do you want some water?", [("me", "I'm thirsty."), ("them", "Do you want some water?")], client=c)
    assert got == ["Yes, please.", "Not right now.", "Is it cold?"]
    body = json.loads(c.kw["messages"][0]["content"])
    assert body["they_just_said"] == "Do you want some water?"
    assert body["conversation_so_far"] == [{"who": "the person you speak for", "said": "I'm thirsty."},
                                           {"who": "them", "said": "Do you want some water?"}]
    assert c.kw["system"] == suggest.REPLY_SYSTEM
