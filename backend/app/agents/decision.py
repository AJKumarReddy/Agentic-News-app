"""Evidence-source decision agent.

Decides where a question should be answered from before any fetching happens:

  GUARDIAN  — news, current events, "what has the Guardian reported"; the
              default, since this is a Guardian research assistant
  WEB       — clearly outside news reporting (definitions, how-to, technical
              docs, product specs) or the user explicitly asked to search
              the web / other sources
  BOTH      — needs Guardian reporting plus external context, or the user
              wants corroboration beyond the Guardian

An LLM makes the call; deterministic rules decide when the LLM is
unavailable and override the obvious explicit cases. Web search is only
ever reachable when TAVILY_API_KEY is configured — otherwise every plan
collapses to GUARDIAN.
"""

import logging
import re

from app.core.logging import log_event
from app.llm.client import extract_json, response_text

logger = logging.getLogger(__name__)

PLANS = ("GUARDIAN", "WEB", "BOTH")

DECISION_PROMPT = """You route questions for a Guardian News Research Assistant.
Decide where the answer's evidence should come from.

"GUARDIAN" — news and current events, anything about what has been reported,
             political/business/climate/tech news, timelines of events.
             This is the default: prefer it whenever Guardian journalism
             could plausibly answer the question.
"WEB"      — the question is not about news reporting at all (definitions,
             how-to instructions, documentation, product specifications,
             reference facts), or the user explicitly asks to search the web
             or use sources other than the Guardian.
"BOTH"     — needs Guardian reporting AND outside context (background,
             technical detail, other outlets' coverage, verification).

Respond with JSON only: {{"plan": "GUARDIAN|WEB|BOTH", "web_query": "a short
web search query, or empty if plan is GUARDIAN", "reason": "one short clause"}}

User question: {question}"""

# Explicit user requests that deterministically force web involvement
_EXPLICIT_WEB = re.compile(
    r"\b(search (?:the )?(?:web|internet|online)|google it|look (?:it )?up online|"
    r"other (?:sources|outlets|publications)|besides the guardian|outside the guardian|"
    r"beyond the guardian|elsewhere|corroborat|fact.?check|what do other)\b",
    re.IGNORECASE,
)

# Signals the question isn't news reporting at all
_NON_NEWS = re.compile(
    r"^\s*(how (?:do|to|can) |what is the (?:definition|syntax|formula)|define |"
    r"explain how |write (?:me )?(?:a|some) (?:code|script|function)|"
    r"convert |calculate |translate )",
    re.IGNORECASE,
)


def heuristic_plan(question: str) -> str:
    if _EXPLICIT_WEB.search(question):
        return "BOTH"
    if _NON_NEWS.search(question):
        return "WEB"
    return "GUARDIAN"


async def decide_source(question: str, llm=None, web_available: bool = True) -> dict:
    """Return {"plan", "web_query", "reason"}. Falls back to heuristics."""
    if not web_available:
        return {"plan": "GUARDIAN", "web_query": "", "reason": "web search not configured"}

    decision: dict | None = None
    if llm is not None:
        try:
            raw = extract_json(
                response_text(await llm.ainvoke(DECISION_PROMPT.format(question=question[:1000])))
            )
            if isinstance(raw, dict) and raw.get("plan") in PLANS:
                decision = raw
        except Exception:
            logger.warning("decision agent LLM failed; using heuristics", exc_info=True)

    if decision is None:
        decision = {"plan": heuristic_plan(question), "web_query": "", "reason": "heuristic"}

    # An explicit user request to look beyond the Guardian always wins
    if _EXPLICIT_WEB.search(question) and decision["plan"] == "GUARDIAN":
        decision["plan"] = "BOTH"
        decision["reason"] = "user explicitly asked for sources beyond the Guardian"

    if decision["plan"] != "GUARDIAN" and not decision.get("web_query"):
        decision["web_query"] = question[:200]

    log_event(
        logger,
        "source_decision",
        plan=decision["plan"],
        reason=str(decision.get("reason", ""))[:120],
    )
    return decision
