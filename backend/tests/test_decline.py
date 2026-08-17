"""The declined path end to end: understand → decline → END.

The guarantee under test is negative — an out-of-scope message must not reach
the search tools or the synthesis model. Asserting on the answer text alone
would not catch a regression that answers correctly but still spends a search.

The understanding step is given a model that routes to WEB, so every test here
also checks that the deterministic guardrail overrides the model's choice.
"""

import json
from types import SimpleNamespace

import pytest

from app.agents import graph as graph_module
from app.agents.graph import build_agent_graph
from app.agents.scope import DECLINE_MESSAGE


class RoutesToWeb:
    """Understanding model that would happily search the web for anything."""

    async def ainvoke(self, prompt):
        return SimpleNamespace(
            content=json.dumps(
                {
                    "mode": "WEB",
                    "intent": "QA",
                    "standalone_question": "how do I do the thing",
                    "news_query": "thing",
                    "web_query": "how to do the thing",
                }
            )
        )


class ExplodingLLM:
    """Synthesis model that must never be reached."""

    async def ainvoke(self, messages):
        raise AssertionError("the declined path must not call the synthesis model")


@pytest.fixture
def searches(monkeypatch):
    """Records any retrieval the declined path attempts — it must stay empty."""
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
        session=None, understanding_llm=RoutesToWeb(), synthesis_llm=ExplodingLLM()
    )
    return await graph.ainvoke(
        {"query": query, "conversation_state": {}, "history": [], "steps": [], **initial}
    )


async def test_coding_request_never_searches(searches):
    final = await run("write a python code for reversing linked list")
    assert final["mode"] == "DECLINE"
    assert searches == []


async def test_declined_answer_is_the_fixed_message(searches):
    final = await run("write a python code for reversing linked list")
    assert final["answer"] == DECLINE_MESSAGE
    assert "def " not in final["answer"]


async def test_declined_answer_carries_no_sources(searches):
    # a citation on a refusal would imply journalism backs it
    final = await run("solve this equation for x: 3x + 7 = 22")
    assert final["sources"] == []
    assert final["evidence"] == []


async def test_declined_path_stops_after_two_steps(searches):
    final = await run("write me a poem about the sea")
    assert final["steps"] == ["understand", "decline"]


async def test_declined_even_while_viewing_an_article(searches):
    final = await run(
        "now write that as a python function",
        conversation_state={
            "active_article_id": "world/2026/aug/01/x",
            "active_article_headline": "Something newsworthy",
        },
    )
    assert final["mode"] == "DECLINE"
    assert searches == []


async def test_news_question_still_reaches_retrieval(searches):
    """The guardrail must not become a blanket block."""
    answering = SimpleNamespace(
        ainvoke=lambda messages: _answer("Nothing was found on that.")
    )
    graph = build_agent_graph(
        session=None, understanding_llm=RoutesToWeb(), synthesis_llm=answering
    )
    final = await graph.ainvoke(
        {"query": "what has been reported about the strike?", "conversation_state": {},
         "history": [], "steps": []}
    )
    assert final["mode"] != "DECLINE"
    assert "search_web" in searches or "retrieve_rag" in searches


async def _answer(text: str):
    return SimpleNamespace(content=text)
