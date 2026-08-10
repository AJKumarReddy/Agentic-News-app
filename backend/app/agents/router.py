"""Intent classification and slot extraction.

An LLM classifier extracts intent/entities/dates; deterministic rules
override the date range for well-known phrases and provide a full fallback
when no LLM is available (tests, degraded mode).
"""

import json
import logging
import re
from typing import Any

from app.agents.dateparse import detect_freshness, parse_date_range
from app.agents.state import INTENTS, merge_with_previous
from app.core.logging import log_event
from app.llm.client import extract_json, response_text

logger = logging.getLogger(__name__)

ROUTER_PROMPT = """You are an intent router for a Guardian news research assistant.
Classify the user message and extract slots. Respond with JSON only:

{{
  "intent": "one of {intents}",
  "entities": ["named entities such as companies, people, countries"],
  "topics": ["broad topics such as artificial intelligence, climate"],
  "from_date": "YYYY-MM-DD or empty",
  "to_date": "YYYY-MM-DD or empty",
  "section": "guardian section id like technology, politics, business, environment, world — or empty",
  "is_follow_up": true/false,
  "output_format": "requested format such as timeline, table, bullet list — or empty",
  "search_queries": ["1-3 short Guardian search queries that would find relevant articles"]
}}

Conversation context (previous turn): {context}
Today's date: {today}
User message: {message}"""

_COMPARE_RE = re.compile(r"\b(compare|versus|vs\.?|difference between)\b", re.IGNORECASE)
_TIMELINE_RE = re.compile(r"\b(timeline|chronolog|sequence of events)\b", re.IGNORECASE)
_SOURCE_RE = re.compile(r"\b(which article|what source|supports? (that|the)|citation for)\b", re.IGNORECASE)
_FOLLOWUP_RE = re.compile(r"^\s*(what about|how about|and\b|also\b|what else)", re.IGNORECASE)


def heuristic_classify(message: str) -> dict[str, Any]:
    """Rule-based fallback classifier used when the LLM is unavailable."""
    lowered = message.lower()
    if _SOURCE_RE.search(message):
        intent = "SOURCE_LOOKUP"
    elif _TIMELINE_RE.search(message):
        intent = "TIMELINE"
    elif _COMPARE_RE.search(message):
        intent = "COMPARISON"
    elif _FOLLOWUP_RE.search(message):
        intent = "FOLLOW_UP"
    elif detect_freshness(message) and any(w in lowered for w in ("latest", "breaking", "today", "news")):
        intent = "LATEST_NEWS"
    elif "summar" in lowered:
        intent = "TOPIC_SUMMARY"
    else:
        intent = "ENTITY_RESEARCH"
    # Crude entity guess: capitalized tokens not starting the sentence
    words = re.findall(r"\b[A-Z][a-zA-Z0-9&-]+\b", message)
    stop = {"What", "The", "Guardian", "Compare", "Which", "How", "Give", "Create", "Tell", "Has", "Did"}
    entities = [w for w in words if w not in stop]
    return {
        "intent": intent,
        "entities": entities[:4],
        "topics": [],
        "from_date": "",
        "to_date": "",
        "section": "",
        "is_follow_up": intent == "FOLLOW_UP",
        "output_format": "",
        "search_queries": [message[:80]],
    }


async def classify(
    message: str,
    previous_state: dict[str, Any],
    llm=None,
    today: str = "",
) -> dict[str, Any]:
    from datetime import date

    today = today or date.today().isoformat()
    raw: dict[str, Any] | None = None

    if llm is not None:
        try:
            context = json.dumps(
                {
                    "topic": previous_state.get("topic", ""),
                    "entities": previous_state.get("entities", []),
                    "date_range": previous_state.get("date_range", {}),
                    "previous_intent": previous_state.get("previous_intent", ""),
                    "active_article_id": previous_state.get("active_article_id", ""),
                }
            )
            prompt = ROUTER_PROMPT.format(
                intents=", ".join(INTENTS), context=context, today=today, message=message[:2000]
            )
            raw = extract_json(response_text(await llm.ainvoke(prompt)))
        except Exception:
            logger.warning("LLM router failed; using heuristic classifier", exc_info=True)

    if raw is None or raw.get("intent") not in INTENTS:
        raw = heuristic_classify(message)

    # Deterministic date parsing overrides the LLM for known phrases
    parsed = parse_date_range(message)
    if parsed:
        raw["from_date"], raw["to_date"] = parsed

    raw["freshness"] = detect_freshness(message)
    merged = merge_with_previous(raw, previous_state)

    log_event(
        logger,
        "intent_classified",
        user_query=message[:200],
        intent=merged.get("intent"),
        entities=merged.get("entities"),
        date_range={"from": merged.get("from_date"), "to": merged.get("to_date")},
    )
    return merged
