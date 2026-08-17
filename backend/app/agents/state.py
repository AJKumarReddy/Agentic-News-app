"""Agent graph state and the persistent conversation state schema."""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Inputs
    query: str  # the user's raw message
    history: list[dict[str, Any]]  # recent turns: {role, content}
    conversation_state: dict[str, Any]  # persisted memory

    # Understanding step
    standalone_question: str  # resolved, self-contained question
    mode: str  # ARTICLE | NEWS | WEB | BOTH | DECLINE (out of scope)
    intent: str  # QA | LATEST | SUMMARY | COMPARISON | TIMELINE | ...
    reason: str  # why this mode was chosen — logged, never shown
    entities: list[str]
    topics: list[str]
    from_date: str | None
    to_date: str | None
    date_explicit: bool  # user stated the range — retrieval must not widen it
    section: str | None
    news_query: str
    web_query: str
    output_format: str
    freshness: bool
    reference: bool  # reference lookup — older pages are acceptable

    # Evidence
    evidence: list[dict[str, Any]]
    sources: list[dict[str, Any]]
    notice: str  # UI metadata (e.g. widened window) — never prose in the answer
    web_used: bool

    # Output
    answer: str
    steps: list[str]


def default_conversation_state() -> dict[str, Any]:
    return {
        "topic": "",
        "entities": [],
        "date_range": {},
        "active_article_id": "",
        "active_article_headline": "",
        "previous_intent": "",
        "last_sources": [],
    }
