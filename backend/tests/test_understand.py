import json
from types import SimpleNamespace

from app.agents.understand import heuristic_understanding, understand


class FakeLLM:
    """Captures the prompt so we can assert the conversation reaches the model."""

    def __init__(self, payload):
        self.content = payload if isinstance(payload, str) else json.dumps(payload)
        self.prompt = ""

    async def ainvoke(self, prompt: str):
        self.prompt = prompt
        return SimpleNamespace(content=self.content)


ARTICLE_HISTORY = [
    {"role": "user", "content": "Tell me about this article on UK manufacturers facing hacking risk"},
    {"role": "assistant", "content": "A survey found 30% of British manufacturers were hit..."},
]


# ── resolution: the defect that caused literal follow-up searches ──

def test_heuristic_resolves_follow_up_against_history():
    result = heuristic_understanding("search for related news on youtube", ARTICLE_HISTORY)
    # the subject must survive; searching the raw words returns YouTube trivia
    assert "manufacturers" in result.standalone_question.lower()
    assert "manufacturers" in result.news_query.lower() or "manufacturers" in result.web_query.lower()


def test_heuristic_resolves_terse_instruction():
    result = heuristic_understanding("the do google search", ARTICLE_HISTORY)
    assert "manufacturers" in result.standalone_question.lower()


async def test_prompt_contains_conversation():
    llm = FakeLLM({"mode": "BOTH", "standalone_question": "resolved", "web_query": "q"})
    await understand("search youtube for related news", history=ARTICLE_HISTORY, llm=llm)
    assert "UK manufacturers" in llm.prompt


# ── mode selection ────────────────────────────────────────────────

async def test_active_article_selects_article_mode():
    result = await understand(
        "what does it say about JLR?", history=ARTICLE_HISTORY, active_article="UK manufacturers…", llm=None
    )
    assert result.mode == "ARTICLE"


async def test_explicit_web_request_reaches_the_web():
    result = await understand("search youtube for related news", history=ARTICLE_HISTORY, llm=None)
    assert result.mode in ("WEB", "BOTH")


async def test_a_news_question_about_a_site_is_not_a_request_to_search_it():
    """"About YouTube" is a subject; "on YouTube" is an instruction. Matching a
    bare site name skipped newsroom retrieval for the site's own news story."""
    for message in (
        "what is the latest news about YouTube ad policy",
        "Reddit protest coverage this week",
        "how is TikTok being regulated",
    ):
        result = await understand(message, llm=None)
        assert result.mode == "NEWS", message


async def test_an_instruction_to_search_a_site_still_reaches_the_web():
    for message in (
        "search youtube for related news",
        "search for related news on youtube",
        "check reddit for reaction",
    ):
        result = await understand(message, llm=None)
        assert result.mode in ("WEB", "BOTH"), message


async def test_non_news_question_uses_web():
    result = await understand("How do I configure nginx for SSE?", llm=None)
    assert result.mode == "WEB"


async def test_plain_news_question_stays_on_guardian():
    result = await understand("What has been reported about OpenAI this week?", llm=None)
    assert result.mode == "NEWS"


async def test_web_disabled_never_routes_to_web():
    result = await understand(
        "search the web for more", history=ARTICLE_HISTORY, llm=None, web_available=False
    )
    assert result.mode in ("NEWS", "ARTICLE")


async def test_explicit_web_overrides_model_choosing_news():
    llm = FakeLLM({"mode": "NEWS", "standalone_question": "q", "news_query": "q"})
    result = await understand("what do other outlets say?", llm=llm)
    assert result.mode == "BOTH"


# ── slots and queries ─────────────────────────────────────────────

async def test_dates_parsed_deterministically_over_model():
    llm = FakeLLM(
        {"mode": "NEWS", "standalone_question": "q", "news_query": "q", "from_date": "2020-01-01"}
    )
    result = await understand("climate stories this week", llm=llm)
    assert result.from_date != "2020-01-01"  # deterministic parser wins
    assert result.freshness is True


async def test_queries_always_populated():
    result = await understand("Latest AI developments", llm=None)
    assert result.news_query
    assert result.standalone_question


async def test_bad_model_output_falls_back_to_heuristics():
    result = await understand("Latest AI news", llm=FakeLLM("not json"))
    assert result.mode == "NEWS"
    assert result.news_query


# ── scope guardrail ───────────────────────────────────────────────

async def test_coding_request_is_declined():
    result = await understand("write a python code for reversing linked list", llm=None)
    assert result.mode == "DECLINE"


async def test_decline_overrides_the_model_choosing_web():
    # the model's opinion cannot route an out-of-scope task into a search
    llm = FakeLLM({"mode": "WEB", "standalone_question": "how to reverse a linked list", "web_query": "reverse linked list python"})
    result = await understand("write a python code for reversing linked list", llm=llm)
    assert result.mode == "DECLINE"


async def test_decline_overrides_an_explicit_web_request():
    result = await understand("google how to write a sorting function in python", llm=None)
    assert result.mode == "DECLINE"


async def test_declined_turn_carries_no_search_queries():
    result = await understand("write me a function that sorts an array", llm=None)
    assert result.news_query == ""
    assert result.web_query == ""


async def test_declined_turn_ignores_an_active_article():
    result = await understand(
        "now write that as python code",
        history=ARTICLE_HISTORY,
        active_article="UK manufacturers…",
        llm=None,
    )
    assert result.mode == "DECLINE"


async def test_news_about_software_is_not_declined():
    result = await understand("What has been reported about the Python security bug?", llm=None)
    assert result.mode == "NEWS"


async def test_decline_survives_only_in_the_resolution():
    # the raw message is innocuous; the resolved question is not
    llm = FakeLLM(
        {"mode": "WEB", "standalone_question": "write a python script to scrape headlines",
         "web_query": "python scrape headlines"}
    )
    result = await understand("do that", llm=llm)
    assert result.mode == "DECLINE"
