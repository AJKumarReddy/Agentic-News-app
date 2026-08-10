"""Agent graph state and the persistent conversation state schema."""

from typing import Any, TypedDict

INTENTS = [
    "LATEST_NEWS",
    "TOPIC_SUMMARY",
    "ARTICLE_QA",
    "ARTICLE_SEARCH",
    "ENTITY_RESEARCH",
    "COMPARISON",
    "TIMELINE",
    "FOLLOW_UP",
    "FACT_LOOKUP",
    "TREND_ANALYSIS",
    "SOURCE_LOOKUP",
]


class AgentState(TypedDict, total=False):
    # Inputs
    query: str
    conversation_state: dict[str, Any]  # persisted memory (topic, entities, ...)
    conversation_summary: str  # short textual summary of recent turns

    # Router outputs
    intent: str
    entities: list[str]
    topics: list[str]
    from_date: str | None
    to_date: str | None
    section: str | None
    freshness: bool
    output_format: str
    search_queries: list[str]

    # Pipeline artifacts
    guardian_found: int
    articles_indexed: int
    evidence: list[dict[str, Any]]  # reranked chunks as dicts
    sources: list[dict[str, Any]]  # deduplicated citation list
    relaxed_note: str  # set when date/section filters had to be widened
    answer: str
    steps: list[str]


def default_conversation_state() -> dict[str, Any]:
    return {
        "topic": "",
        "entities": [],
        "date_range": {},
        "active_article_id": "",
        "previous_intent": "",
        "last_sources": [],
    }


def merge_with_previous(
    router_output: dict[str, Any], previous: dict[str, Any]
) -> dict[str, Any]:
    """Resolve follow-ups: inherit missing slots from the previous turn.

    'What about AMD?' after an NVIDIA question keeps the date range and
    intent while swapping the entity.
    """
    merged = dict(router_output)
    is_follow_up = merged.get("intent") == "FOLLOW_UP" or merged.get("is_follow_up")

    if is_follow_up:
        if not merged.get("from_date") and previous.get("date_range"):
            merged["from_date"] = previous["date_range"].get("from_date")
            merged["to_date"] = previous["date_range"].get("to_date")
        if not merged.get("entities") and previous.get("entities"):
            merged["entities"] = previous["entities"]
        if not merged.get("topics") and previous.get("topic"):
            merged["topics"] = [previous["topic"]]
        if merged.get("intent") == "FOLLOW_UP" and previous.get("previous_intent"):
            # Re-use the substantive intent from last turn (e.g. ENTITY_RESEARCH)
            substantive = previous["previous_intent"]
            if substantive not in ("FOLLOW_UP", ""):
                merged["intent"] = substantive
    if not merged.get("active_article_id"):
        merged["active_article_id"] = previous.get("active_article_id", "")
    return merged
