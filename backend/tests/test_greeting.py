"""The greeting path end to end: understand → greet → END.

Mirrors test_decline.py, and the guarantee is the same shape — negative. "hi"
must not reach a search tool, the synthesis model, or the resolver. Asserting
on the reply text alone would miss a regression that says hello politely while
still spending a publisher request and an LLM call to do it.

The understanding model here would route anything to a search, so these tests
also prove the deterministic check overrides the model rather than asking it
nicely.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents.graph import build_agent_graph
from app.agents.scope import GREETING_MESSAGE, is_greeting


class RoutesToNews:
    """Understanding model that would search the newsrooms for anything.

    Reaching this at all is a failure for a greeting: resolution invents a
    searchable question out of a fragment, which is how "hi" became "What are
    the latest news updates from The Guardian?" and returned an article about
    water storage.
    """

    async def ainvoke(self, prompt):
        raise AssertionError("a greeting must not reach the understanding model")


class ExplodingLLM:
    """Synthesis model that must never be reached."""

    async def ainvoke(self, messages):
        raise AssertionError("the greeting path must not call the synthesis model")


@pytest.fixture
def searches(monkeypatch):
    """Records any retrieval the greeting path attempts — it must stay empty."""
    calls: list[str] = []

    def trap(name, result):
        async def recorded(*args, **kwargs):
            calls.append(name)
            return result

        return recorded

    monkeypatch.setattr(graph_module.tools, "fetch_and_index", trap("fetch_and_index", {}))
    monkeypatch.setattr(graph_module.tools, "retrieve_rag", trap("retrieve_rag", []))
    monkeypatch.setattr(graph_module.tools, "search_web", trap("search_web", []))
    monkeypatch.setattr(graph_module.tools, "get_source_article", trap("get_source_article", None))
    return calls


async def run(query: str, **initial):
    graph = build_agent_graph(
        session=None, understanding_llm=RoutesToNews(), synthesis_llm=ExplodingLLM()
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": {}, "history": [], "steps": [], **initial}
    )


@pytest.mark.parametrize("greeting", ["hi", "Hello", "hey there", "good morning", "thanks!"])
async def test_a_greeting_never_searches(searches, greeting):
    final = await run(greeting)
    assert final["mode"] == "GREET"
    assert searches == []


async def test_greeting_answers_with_the_fixed_message(searches):
    final = await run("hi")
    assert final["answer"] == GREETING_MESSAGE
    # an empty source list is what stops the UI implying this came from
    # journalism — the bug report showed a citation attached to "hi"
    assert final["sources"] == []


async def test_a_question_that_merely_opens_politely_still_searches():
    """The failure mode in the other direction: swallowing a real question
    because it began with a hello."""
    assert is_greeting("hi, what happened in Gaza today") is False
    assert is_greeting("hello, compare coverage of the tariff deal") is False


def test_greeting_detection_does_not_catch_news_questions():
    # each of these begins with letters the pattern could over-match on
    for question in (
        "history of the EU single market",
        "hint of a rate cut in the latest minutes",
        "great resignation coverage",
        "okinawa base protests",
        "nice attack anniversary reporting",
        "yemen ceasefire latest",
    ):
        assert is_greeting(question) is False, question


def test_long_messages_are_never_greetings():
    """The length cap is the backstop: whatever a message opens with, past a
    short phrase it is a question and must be searched."""
    assert is_greeting("hi " + "a" * 60) is False


async def test_the_fixed_reply_is_streamed_not_dumped():
    """A greeting has no model behind it, so nothing streams it naturally. It
    is replayed in pieces instead — otherwise it appears instantly while every
    other answer types out, and reads as a different kind of thing happening."""
    from app.services.chat_service import _replay_fixed_answer

    chunks = [chunk async for chunk in _replay_fixed_answer(GREETING_MESSAGE)]

    # one token per event, the way the synthesis model emits them — batching
    # them into groups still arrived in visible lumps rather than typing
    assert len(chunks) == len(GREETING_MESSAGE.split(" "))
    # the reader must receive exactly the message, spaces and blank lines intact
    assert "".join(chunks) == GREETING_MESSAGE


async def test_replay_handles_a_one_word_answer():
    from app.services.chat_service import _replay_fixed_answer

    assert "".join([c async for c in _replay_fixed_answer("Hello")]) == "Hello"
