import json
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from src.backend import suggest


def client_returning(text="{}", stop="end_turn", error=None):
    def create(**kw):
        if error:
            raise error
        client.kw = kw
        return NS(stop_reason=stop, usage=NS(input_tokens=1, output_tokens=1), content=[NS(type="thinking", thinking=""), NS(type="text", text=text)])

    client = NS(beta=NS(messages=NS(create=create)))
    return client


def test_up_to_three_fresh_options_and_what_is_sent():
    c = client_returning(json.dumps({"options": [
        "My back really hurts.", "My back hurts a lot.", "My back really hurts.", "Could you help with my back?", "A fourth one."]}))
    got = suggest.options(["I need", "Pain", "Back", "A lot"], "My back hurts a lot.", recent=["Yes."], client=c)
    assert got == ["My back really hurts.", "Could you help with my back?", "A fourth one."]  # no repeats, no plain phrase
    assert c.kw["model"] == suggest.MODEL and c.kw["output_config"]["effort"] == "low" and c.kw["fallbacks"] == "default"
    body = json.loads(c.kw["messages"][0]["content"])
    assert body == {"picked": "I need > Pain > Back > A lot", "plain_sentence": "My back hurts a lot.", "said_recently": ["Yes."]}


@pytest.mark.parametrize("client", [
    client_returning(stop="refusal"),
    client_returning(stop="max_tokens", text='{"options": ["cut'),
    client_returning(text="not json"),
    client_returning(text='{"other": []}'),
    client_returning(error=anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com"))),
    client_returning(error=TypeError("Could not resolve authentication method. Expected either api_key...")),
])
def test_anything_wrong_means_just_the_plain_phrase(client):
    assert suggest.options(["Answer", "Yes"], "Yes.", client=client) == []


def test_other_type_errors_are_real_bugs():
    with pytest.raises(TypeError):
        suggest.options(["Answer", "Yes"], "Yes.", client=client_returning(error=TypeError("unexpected keyword")))


def test_replies_send_the_conversation_and_come_back_distinct():
    c = client_returning(json.dumps({"replies": ["Yes, please.", "Not right now.", "Yes, please.", "Is it cold?"]}))
    got = suggest.replies("Do you want some water?", [("me", "I'm thirsty."), ("them", "Do you want some water?")], client=c)
    assert got == ["Yes, please.", "Not right now.", "Is it cold?"]
    body = json.loads(c.kw["messages"][0]["content"])
    assert body["they_just_said"] == "Do you want some water?"
    assert body["conversation_so_far"] == [{"who": "the person you speak for", "said": "I'm thirsty."},
                                           {"who": "them", "said": "Do you want some water?"}]
    assert c.kw["system"] == suggest.REPLY_SYSTEM
