from app.agents.router import classify, heuristic_classify
from app.agents.state import default_conversation_state, merge_with_previous


def test_heuristic_latest_news():
    result = heuristic_classify("Latest OpenAI news today")
    assert result["intent"] == "LATEST_NEWS"
    assert "OpenAI" in result["entities"]


def test_heuristic_comparison():
    result = heuristic_classify("Compare OpenAI and Anthropic coverage")
    assert result["intent"] == "COMPARISON"


def test_heuristic_timeline():
    result = heuristic_classify("Create a timeline of NVIDIA developments")
    assert result["intent"] == "TIMELINE"


def test_heuristic_source_lookup():
    result = heuristic_classify("Which article supports the second point?")
    assert result["intent"] == "SOURCE_LOOKUP"


async def test_classify_without_llm_sets_dates_and_freshness():
    result = await classify("latest AI stories this week", default_conversation_state(), llm=None)
    assert result["intent"] in ("LATEST_NEWS", "ENTITY_RESEARCH")
    assert result["freshness"] is True
    assert result["from_date"] and result["to_date"]


def test_follow_up_inherits_previous_slots():
    previous = {
        "topic": "semiconductors",
        "entities": ["NVIDIA"],
        "date_range": {"from_date": "2026-08-01", "to_date": "2026-08-08"},
        "active_article_id": "",
        "previous_intent": "ENTITY_RESEARCH",
        "last_sources": [],
    }
    router_output = {
        "intent": "FOLLOW_UP",
        "entities": ["AMD"],
        "topics": [],
        "from_date": "",
        "to_date": "",
        "is_follow_up": True,
    }
    merged = merge_with_previous(router_output, previous)
    # topic entity swapped, date range inherited, substantive intent restored
    assert merged["entities"] == ["AMD"]
    assert merged["from_date"] == "2026-08-01"
    assert merged["to_date"] == "2026-08-08"
    assert merged["intent"] == "ENTITY_RESEARCH"


def test_active_article_carries_over():
    previous = {**default_conversation_state(), "active_article_id": "technology/2026/aug/07/a"}
    merged = merge_with_previous({"intent": "ARTICLE_QA", "entities": []}, previous)
    assert merged["active_article_id"] == "technology/2026/aug/07/a"
