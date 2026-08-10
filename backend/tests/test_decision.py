from types import SimpleNamespace

from app.agents.decision import decide_source, heuristic_plan


class FakeLLM:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, prompt: str):
        return SimpleNamespace(content=self.content)


def test_heuristic_news_defaults_to_guardian():
    assert heuristic_plan("What has the Guardian reported about OpenAI?") == "GUARDIAN"
    assert heuristic_plan("Latest climate stories") == "GUARDIAN"


def test_heuristic_explicit_web_request():
    assert heuristic_plan("Search the web for more on this") == "BOTH"
    assert heuristic_plan("What do other outlets say about it?") == "BOTH"


def test_heuristic_non_news_question():
    assert heuristic_plan("How do I configure nginx for SSE?") == "WEB"
    assert heuristic_plan("What is the definition of quantitative easing?") == "WEB"


async def test_web_disabled_forces_guardian():
    decision = await decide_source(
        "search the web for details", llm=FakeLLM('{"plan": "WEB"}'), web_available=False
    )
    assert decision["plan"] == "GUARDIAN"


async def test_llm_plan_is_used():
    decision = await decide_source(
        "Explain the background of this policy",
        llm=FakeLLM('{"plan": "BOTH", "web_query": "policy background", "reason": "needs context"}'),
    )
    assert decision["plan"] == "BOTH"
    assert decision["web_query"] == "policy background"


async def test_explicit_web_request_overrides_llm_guardian():
    decision = await decide_source(
        "What do other outlets say about the merger?", llm=FakeLLM('{"plan": "GUARDIAN"}')
    )
    assert decision["plan"] == "BOTH"


async def test_bad_llm_output_falls_back_to_heuristic():
    decision = await decide_source("Latest AI news", llm=FakeLLM("not json at all"))
    assert decision["plan"] == "GUARDIAN"


async def test_web_query_defaults_to_question():
    decision = await decide_source("How do I reset a Postgres password?", llm=None)
    assert decision["plan"] == "WEB"
    assert decision["web_query"]
