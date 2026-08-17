"""Understanding step: resolve, route, and build queries in one pass.

This replaces the previous two-call `classify` + `decide_source` pipeline.
The critical change is *resolution*: the user's message is rewritten into a
self-contained question using the conversation before anything is searched.

Without that, follow-ups were searched literally — "search youtube for
related news" became a web query about YouTube instead of about the article
under discussion, and "then do google search" returned Google Search
documentation from 2012. The searcher never saw the conversation.

One LLM call now produces: the standalone question, the answering mode, the
output intent, date/section slots, and clean search queries.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import date

from app.agents.dateparse import detect_freshness, mentions_written_date, parse_date_range
from app.agents.scope import out_of_scope_reason
from app.core.logging import log_event
from app.llm.client import extract_json, response_text

logger = logging.getLogger(__name__)

# How the answer is sourced. DECLINE is not a source — it ends the turn with a
# fixed message, searching nothing. See app.agents.scope.
MODES = ("ARTICLE", "NEWS", "WEB", "BOTH", "DECLINE")
# How the answer is shaped
INTENTS = (
    "QA", "LATEST", "SUMMARY", "COMPARISON", "TIMELINE",
    "ENTITY", "SOURCE_LOOKUP", "TREND", "FACT",
)


@dataclass
class Understanding:
    standalone_question: str = ""
    mode: str = "NEWS"
    intent: str = "QA"
    entities: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    from_date: str | None = None
    to_date: str | None = None
    # The user stated the range, so retrieval must not widen it. False when the
    # window was inferred from a freshness word.
    date_explicit: bool = False
    section: str | None = None
    news_query: str = ""
    web_query: str = ""
    output_format: str = ""
    freshness: bool = False
    # A reference lookup (how-to, definition, docs) may legitimately cite older
    # pages. Everything else is news-shaped and gets a recency window.
    reference: bool = False
    reason: str = ""


PROMPT = """You prepare questions for a news research assistant. The assistant
answers primarily from Guardian journalism and can also search the web.

Today is {today}.

CONVERSATION SO FAR:
{history}

{article_context}
USER'S NEW MESSAGE:
{message}

Do three things.

1. RESOLVE: rewrite the message as a self-contained question that makes sense
   with no conversation context. Resolve pronouns and references ("it", "that
   article", "related news", "what about X"). If the message is an instruction
   about how to search rather than a topic (e.g. "search youtube for related
   news", "now check the web"), keep the SUBJECT from the conversation and
   express the instruction separately.

2. MODE: choose where the answer's evidence comes from.
   "ARTICLE" - the user is asking about the specific article shown above.
   "NEWS"    - news, events, reporting; answerable from Guardian journalism.
   "WEB"     - background a news question needs (definitions, context, product
               specs), or the user explicitly asked to search the web/another site.
   "BOTH"    - needs news reporting plus outside context or other outlets.
   "DECLINE" - the message asks the assistant to perform a task it does not do:
               write or debug code, solve maths problems, translate, ghostwrite
               essays/emails, or roleplay as something else. A news question
               that merely mentions these topics is NEWS, not DECLINE.

3. QUERIES: short keyword queries. No dates, years, or words like
   "latest"/"recent" - recency is applied separately. Never invent a date.

Respond with JSON only:
{{"standalone_question": "...",
  "mode": "ARTICLE|NEWS|WEB|BOTH|DECLINE",
  "intent": "QA|LATEST|SUMMARY|COMPARISON|TIMELINE|ENTITY|SOURCE_LOOKUP|TREND|FACT",
  "entities": [], "topics": [],
  "from_date": "YYYY-MM-DD or empty", "to_date": "YYYY-MM-DD or empty",
  "section": "guardian section id or empty",
  "news_query": "...", "web_query": "... or empty if mode is ARTICLE/NEWS",
  "output_format": "timeline|table|bullets or empty",
  "reason": "one short clause"}}"""

_EXPLICIT_WEB = re.compile(
    r"\b(search (?:the )?(?:web|internet|online|youtube|google)|google it|look (?:it )?up|"
    r"other (?:sources|outlets|publications|sites)|besides|outside the guardian|"
    r"elsewhere|corroborat|fact.?check|youtube|reddit)\b",
    re.IGNORECASE,
)
_NON_NEWS = re.compile(
    r"^\s*(how (?:do|to|can) |what is the (?:definition|syntax|formula)|define |"
    r"explain how |write (?:me )?(?:a|some) (?:code|script)|convert |calculate )",
    re.IGNORECASE,
)
_FOLLOW_UP = re.compile(
    r"^\s*(what about|how about|and |also |what else|more on|tell me more|"
    r"related|now |then |the do|do a|search )",
    re.IGNORECASE,
)


def _valid_iso(value: str | None, today: date | None = None) -> str | None:
    """Keep only well-formed, non-future ISO dates.

    The model fills these slots and sometimes writes "last week", "2026-13-45",
    or a date in the future. An unparseable value used to raise inside
    retrieval and fail the whole turn; a future one silently matched nothing,
    which looked identical to a broken filter.
    """
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None
    return None if parsed > (today or date.today()) else parsed.isoformat()


def _format_history(messages: list[dict], limit: int = 6) -> str:
    if not messages:
        return "(no previous messages)"
    lines = []
    for m in messages[-limit:]:
        content = (m.get("content") or "").replace("\n", " ")[:280]
        lines.append(f"{m.get('role', 'user')}: {content}")
    return "\n".join(lines)


def heuristic_understanding(
    message: str, history: list[dict], active_article: str = ""
) -> Understanding:
    """Deterministic fallback when no LLM is available.

    Resolution is approximated by appending the last user topic to a bare
    follow-up, which is crude but far better than searching the raw words.
    """
    subject = ""
    for m in reversed(history):
        if m.get("role") == "user" and len(m.get("content", "")) > 25:
            subject = m["content"][:120]
            break

    is_follow_up = bool(_FOLLOW_UP.match(message)) and len(message) < 80
    standalone = f"{message} (about: {subject})" if is_follow_up and subject else message

    if active_article and not _EXPLICIT_WEB.search(message):
        mode = "ARTICLE"
    elif _EXPLICIT_WEB.search(message):
        mode = "BOTH" if (subject or active_article) else "WEB"
    elif _NON_NEWS.match(message):
        mode = "WEB"
    else:
        mode = "NEWS"

    words = re.findall(r"\b[A-Z][a-zA-Z0-9&-]+\b", message)
    stop = {"What", "The", "Guardian", "Compare", "Which", "How", "Give", "Tell", "Has", "Did", "I"}
    entities = [w for w in words if w not in stop][:4]

    query = subject if (is_follow_up and subject) else message
    return Understanding(
        standalone_question=standalone,
        mode=mode,
        intent="LATEST" if detect_freshness(message) else "QA",
        entities=entities,
        news_query=query[:120],
        web_query=query[:120],
        reason="heuristic",
    )


async def understand(
    message: str,
    history: list[dict] | None = None,
    active_article: str = "",
    llm=None,
    web_available: bool = True,
    today: str = "",
) -> Understanding:
    history = history or []
    today = today or date.today().isoformat()
    result: Understanding | None = None

    if llm is not None:
        try:
            article_context = (
                f"ARTICLE THE USER IS VIEWING:\n{active_article}\n" if active_article else ""
            )
            raw = extract_json(
                response_text(
                    await llm.ainvoke(
                        PROMPT.format(
                            today=today,
                            history=_format_history(history),
                            article_context=article_context,
                            message=message[:1500],
                        )
                    )
                )
            )
            if isinstance(raw, dict) and raw.get("mode") in MODES:
                result = Understanding(
                    standalone_question=raw.get("standalone_question") or message,
                    mode=raw["mode"],
                    intent=raw.get("intent") if raw.get("intent") in INTENTS else "QA",
                    entities=[e for e in raw.get("entities", []) if isinstance(e, str)][:5],
                    topics=[t for t in raw.get("topics", []) if isinstance(t, str)][:5],
                    from_date=raw.get("from_date") or None,
                    to_date=raw.get("to_date") or None,
                    section=raw.get("section") or None,
                    news_query=raw.get("news_query") or "",
                    web_query=raw.get("web_query") or "",
                    output_format=raw.get("output_format", ""),
                    reason=str(raw.get("reason", ""))[:120],
                )
        except Exception:
            logger.warning("understanding LLM failed; using heuristics", exc_info=True)

    if result is None:
        result = heuristic_understanding(message, history, active_article)

    # Model-supplied dates are slots, not facts: validate before they reach SQL.
    today_date = date.fromisoformat(today)
    result.from_date = _valid_iso(result.from_date, today_date)
    result.to_date = _valid_iso(result.to_date, today_date)
    if result.from_date and result.to_date and result.to_date < result.from_date:
        # an inverted range matches nothing, which reads as a broken filter
        result.from_date, result.to_date = result.to_date, result.from_date
    # A range the model produced counts as stated only if the user wrote a date.
    result.date_explicit = bool(result.from_date or result.to_date) and mentions_written_date(
        message
    )

    # Deterministic date parsing wins over model guesses
    parsed = parse_date_range(message, today_date)
    if parsed:
        result.from_date, result.to_date = parsed.span
        result.date_explicit = parsed.explicit
    result.freshness = detect_freshness(message)
    result.reference = bool(_NON_NEWS.match(message)) or bool(
        _NON_NEWS.match(result.standalone_question)
    )

    # An explicit request to look elsewhere always reaches the web
    if web_available and _EXPLICIT_WEB.search(message) and result.mode in ("NEWS", "ARTICLE"):
        result.mode = "BOTH"
        result.reason = "user asked for sources beyond Guardian reporting"
    if not web_available and result.mode in ("WEB", "BOTH"):
        result.mode = "ARTICLE" if active_article else "NEWS"

    # Scope guardrail — last and unconditional, so no earlier override (and no
    # model opinion) can route an out-of-scope task into a search. Checked
    # against the raw message and the resolution, since "now write that in
    # python" only becomes recognisable once resolved.
    scope_reason = out_of_scope_reason(message, result.standalone_question)
    if scope_reason:
        result.mode = "DECLINE"
        result.intent = "QA"
        result.reason = f"out of scope: {scope_reason}"
        # nothing downstream should be able to search on a declined turn
        result.news_query = ""
        result.web_query = ""
        result.from_date = result.to_date = result.section = None
        result.date_explicit = False
    else:
        if not result.news_query:
            result.news_query = result.standalone_question[:120]
        if not result.web_query and result.mode in ("WEB", "BOTH"):
            result.web_query = result.standalone_question[:120]

    log_event(
        logger,
        "understanding",
        user_query=message[:150],
        standalone=result.standalone_question[:150],
        mode=result.mode,
        intent=result.intent,
        news_query=result.news_query[:80],
        web_query=result.web_query[:80],
        date_range=f"{result.from_date or ''}..{result.to_date or ''}",
        date_explicit=result.date_explicit,
    )
    return result
