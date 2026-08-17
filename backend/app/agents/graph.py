"""Controlled LangGraph agent with four answering modes and a refusal.

    understand ──┬── ARTICLE ─→ article_evidence ─┐
                 ├── NEWS ────→ news_evidence ────┤
                 ├── WEB ─────→ web_evidence ─────┼─→ synthesize
                 ├── BOTH ────→ news_evidence ─→ web_evidence ─┘
                 └── DECLINE ─→ decline ─→ END

DECLINE short-circuits everything: no search, no LLM call, no sources. It is
the terminal node for requests this assistant does not serve — see
app.agents.scope for what qualifies and why the check is deterministic.

Each mode does only the work it needs. Answering about an article the user is
already viewing does not search, filter, or rerank anything — the article is
known. That separation is deliberate: a single shared path previously leaked
news-retrieval machinery (date windows, relaxation notices) into article
answers where it made no sense.
"""

import logging
import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
from app.agents.scope import DECLINE_MESSAGE
from app.agents.state import AgentState
from app.agents.understand import understand
from app.core.config import get_settings
from app.core.logging import log_event
from app.llm.client import get_chat_model, response_text
from app.llm.prompts import SYSTEM_PROMPT, build_synthesis_prompt
from app.rag.vector_store import RetrievalFilters, ScoredChunk
from app.websearch.client import requested_domains, within_range

logger = logging.getLogger(__name__)

MAX_EVIDENCE_CHARS = 14000
WEB_EVIDENCE_SHARE = 0.35
ARTICLE_BODY_CHARS = 12000
SEARCH_LOOKBACK_DAYS = 3
RELAX_WINDOW_DAYS = 14
# Recency window for web search when the question names no period. This is a
# news assistant; stale documentation pages were being cited as reporting.
WEB_DEFAULT_DAYS = 30
# Tavily rejects an unbounded lookback, so a range older than this simply
# returns no web evidence — publisher retrieval still answers, and a result
# outside the requested range is worse than one fewer source.
WEB_MAX_DAYS = 365


# ── evidence assembly ────────────────────────────────────────────────

def _publisher_source(chunk) -> dict:
    """Citation entry for indexed journalism, whichever publisher it came from."""
    return {
        "type": "publisher",
        "source": getattr(chunk, "source", "") or "The Guardian",
        "source_id": getattr(chunk, "source_id", "") or "guardian",
        "article_id": chunk.article_id,
        "headline": chunk.headline,
        "url": chunk.url,
        "published_at": chunk.published_at.isoformat() if chunk.published_at else "",
        "section": chunk.section,
        "author": chunk.author,
    }


def _chunks_to_evidence(groups: dict[str, list[ScoredChunk]]) -> tuple[list[dict], list[dict]]:
    """Number sources per unique article; chunks from one article share a number."""
    sources: list[dict] = []
    index: dict[str, int] = {}
    evidence: list[dict] = []
    for group_name, chunks in groups.items():
        for scored in chunks:
            chunk = scored.chunk
            if chunk.article_id not in index:
                index[chunk.article_id] = len(sources) + 1
                sources.append({"n": len(sources) + 1, **_publisher_source(chunk)})
            evidence.append(
                {
                    "n": index[chunk.article_id],
                    "type": "publisher",
                    "source": getattr(chunk, "source", "") or "The Guardian",
                    "group": group_name,
                    "headline": chunk.headline,
                    "published_at": chunk.published_at.isoformat() if chunk.published_at else "",
                    "text": chunk.text,
                }
            )
    return evidence, sources


def _web_to_evidence(results, evidence: list[dict], sources: list[dict]):
    """Append web results after publisher sources, continuing the numbering."""
    seen = {s["url"] for s in sources}
    for result in results:
        if not result.url or result.url in seen:
            continue
        seen.add(result.url)
        number = len(sources) + 1
        sources.append(
            {
                "n": number,
                "type": "web",
                "source": result.source or "web",
                "article_id": "",
                "headline": result.title,
                "url": result.url,
                "published_at": result.published_date or "",
                "section": "",
                "author": "",
            }
        )
        evidence.append(
            {
                "n": number,
                "type": "web",
                "source": result.source or "web",
                "group": "web",
                "headline": result.title,
                "published_at": result.published_date or "",
                "text": result.content,
            }
        )
    return evidence, sources


def _format_entry(item: dict, header: str = "") -> str:
    origin = item.get("source") or ("web" if item.get("type") == "web" else "The Guardian")
    published = (item.get("published_at") or "")[:10]
    return f"{header}[{item['n']}] {item['headline']} ({published}, {origin})\n{item['text']}\n"


def _fill(items: list[dict], budget: int, web_header: bool = False) -> tuple[list[str], int]:
    lines: list[str] = []
    used = 0
    current_group = None
    for item in items:
        header = ""
        if web_header and current_group is None:
            current_group = "web"
            header = (
                "--- WEB SOURCES (not from a news publisher we index; "
                "attribute to the named site) ---\n"
            )
        elif not web_header and item["group"] not in ("default", "article") and item["group"] != current_group:
            current_group = item["group"]
            header = f"--- Evidence about: {current_group} ---\n"
        entry = _format_entry(item, header)
        if used + len(entry) > budget:
            break
        lines.append(entry)
        used += len(entry)
    return lines, used


def _evidence_block(evidence: list[dict]) -> str:
    """Publisher and web evidence get separate budgets — a single shared cap
    let long publisher chunks starve out every web source before the model
    ever saw them."""
    publisher = [e for e in evidence if e.get("type") != "web"]
    web = [e for e in evidence if e.get("type") == "web"]
    if not web:
        lines, _ = _fill(publisher, MAX_EVIDENCE_CHARS)
        return "\n".join(lines)
    web_budget = min(
        int(MAX_EVIDENCE_CHARS * WEB_EVIDENCE_SHARE),
        sum(len(_format_entry(e)) for e in web) + 200,
    )
    publisher_lines, publisher_used = _fill(publisher, MAX_EVIDENCE_CHARS - web_budget)
    web_lines, _ = _fill(web, MAX_EVIDENCE_CHARS - publisher_used, web_header=True)
    return "\n".join(publisher_lines + web_lines)


def _window_label(state: AgentState) -> str:
    """The requested period, phrased for a UI notice."""
    start, end = state.get("from_date"), state.get("to_date")
    if start and end:
        return start if start == end else f"{start} to {end}"
    if start:
        return f"since {start}"
    if end:
        return f"up to {end}"
    return "that period"


def _web_days(state: AgentState) -> int | None:
    """Tavily's recency window for this turn.

    Tavily only expresses "the last N days", so a historical range is requested
    as a lookback reaching back to its start and the results are filtered to the
    range afterwards. Without this the web leg ran a flat 30-day window and
    returned last month's pages for a question about March.
    """
    from_date = state.get("from_date")
    if from_date:
        # a stated period outranks the reference exemption
        try:
            span = (date.today() - date.fromisoformat(from_date)).days + 1
            return min(WEB_MAX_DAYS, max(1, span))
        except ValueError:
            pass
    if state.get("reference"):
        return None  # a reference lookup may legitimately cite older pages
    return WEB_DEFAULT_DAYS


def _build_filters(state: AgentState) -> RetrievalFilters:
    filters = RetrievalFilters.from_iso(
        state.get("from_date"),
        state.get("to_date"),
        sections=[state["section"]] if state.get("section") else None,
    )
    conv = state.get("conversation_state", {})
    if state.get("intent") == "SOURCE_LOOKUP" and conv.get("last_sources"):
        filters.article_ids = [s["article_id"] for s in conv["last_sources"] if s.get("article_id")]
    return filters


def _advance(state: AgentState, *steps: str) -> dict[str, Any]:
    return {"steps": state.get("steps", []) + list(steps)}


def build_agent_graph(session: AsyncSession, understanding_llm=None, synthesis_llm=None):
    settings = get_settings()

    async def understand_node(state: AgentState) -> dict[str, Any]:
        llm = understanding_llm
        if llm is None and settings.openai_api_key:
            llm = get_chat_model(temperature=0, max_tokens=600)
        conv = state.get("conversation_state", {})
        result = await understand(
            state["query"],
            history=state.get("history", []),
            active_article=conv.get("active_article_headline", "") or conv.get("active_article_id", ""),
            llm=llm,
            web_available=bool(settings.tavily_api_key),
        )
        return {
            "standalone_question": result.standalone_question,
            "mode": result.mode,
            "intent": result.intent,
            "entities": result.entities,
            "topics": result.topics,
            "from_date": result.from_date,
            "to_date": result.to_date,
            "date_explicit": result.date_explicit,
            "section": result.section,
            "news_query": result.news_query,
            "web_query": result.web_query,
            "output_format": result.output_format,
            "freshness": result.freshness,
            "reference": result.reference,
            "reason": result.reason,
            **_advance(state, "understand"),
        }

    async def decline_node(state: AgentState) -> dict[str, Any]:
        """Out of scope: answer with the fixed message and stop.

        No LLM and no retrieval — a generated refusal could still drift into
        answering, and an empty source list keeps the UI from implying this
        text was sourced from journalism.
        """
        log_event(logger, "declined", reason=state.get("reason", ""), user_query=state["query"][:150])
        return {
            "answer": DECLINE_MESSAGE,
            "evidence": [],
            "sources": [],
            **_advance(state, "decline"),
        }

    async def article_evidence_node(state: AgentState) -> dict[str, Any]:
        """The article is known — read it directly. No search, no filters."""
        article_id = state.get("conversation_state", {}).get("active_article_id", "")
        article = await tools.get_source_article(article_id) if article_id else None
        if article is None:
            return {"evidence": [], "sources": [], **_advance(state, "article_evidence")}
        source = {
            "n": 1,
            "type": "publisher",
            "source": article.source,
            "source_id": article.source_id,
            "article_id": article.article_id,
            "headline": article.headline,
            "url": article.url,
            "published_at": article.published_at.isoformat() if article.published_at else "",
            "section": article.section,
            "author": article.author,
        }
        evidence = [
            {
                "n": 1,
                "type": "guardian",
                "source": "The Guardian",
                "group": "article",
                "headline": article.headline,
                "published_at": source["published_at"],
                "text": article.body_text[:ARTICLE_BODY_CHARS],
            }
        ]
        return {"evidence": evidence, "sources": [source], **_advance(state, "article_evidence")}

    async def news_evidence_node(state: AgentState) -> dict[str, Any]:
        """Guardian path: fetch fresh articles, index, retrieve, rerank."""
        intent = state.get("intent", "QA")
        queries = [state.get("news_query") or state["standalone_question"]]
        if intent == "COMPARISON" and len(state.get("entities", [])) >= 2:
            queries = state["entities"][:3]

        search_from = state.get("from_date")
        if search_from:
            search_from = (
                date.fromisoformat(search_from) - timedelta(days=SEARCH_LOOKBACK_DAYS)
            ).isoformat()
        active_id = state.get("conversation_state", {}).get("active_article_id")

        stats = await tools.fetch_and_index(
            session,
            queries,
            article_ids=[active_id] if active_id else None,
            from_date=search_from,
            to_date=state.get("to_date"),
            section=state.get("section"),
            order_by="newest" if state.get("freshness") or intent == "LATEST" else "relevance",
        )

        question = state["standalone_question"]
        filters = _build_filters(state)
        # Every branch retrieves under the same filters. They used to be rebuilt
        # per intent from a subset of the slots, which is how TIMELINE lost its
        # end date and COMPARISON lost its section.
        if intent == "COMPARISON" and len(state.get("entities", [])) >= 2:
            groups = await tools.compare_articles(session, state["entities"], filters=filters)
        elif intent == "TIMELINE":
            topic = ", ".join(state.get("entities", []) or state.get("topics", [])) or question
            groups = {"default": await tools.build_timeline(session, topic, filters=filters)}
        else:
            groups = {
                "default": await tools.retrieve_rag(
                    session, question, filters=filters, freshness=state.get("freshness", False)
                )
            }

        # Widening only ever applies to a window *we* inferred. A range the user
        # stated is a constraint: if nothing was published in it, the honest
        # answer is that nothing was published in it. Silently answering from
        # outside the window is what made date filtering look broken.
        notice = ""
        if not any(groups.values()) and (filters.from_date or filters.sections):
            if state.get("date_explicit"):
                # Scoped to newsroom reporting: the web leg may still find
                # sources inside the same window, and this notice sits beside
                # their citations.
                notice = f"No newsroom coverage in {_window_label(state)}"
            else:
                # Loosen one constraint at a time, widest last, so the answer
                # stays as close to what was asked as the index allows.
                ladder: list[tuple[str, RetrievalFilters]] = []
                if filters.from_date:
                    ladder.append(
                        (
                            f"Last {RELAX_WINDOW_DAYS} days",
                            replace(
                                filters,
                                from_date=filters.from_date - timedelta(days=RELAX_WINDOW_DAYS),
                            ),
                        )
                    )
                ladder.append(
                    ("All indexed reporting", replace(filters, from_date=None, to_date=None))
                )
                if filters.sections:
                    ladder.append(
                        (
                            "All sections",
                            replace(filters, from_date=None, to_date=None, sections=[]),
                        )
                    )
                for label, wider in ladder:
                    fallback = await tools.retrieve_rag(
                        session, question, filters=wider, freshness=True
                    )
                    if fallback:
                        groups = {"default": fallback}
                        notice = f"Results from {label}"
                        break

        evidence, sources = _chunks_to_evidence(groups)
        log_event(
            logger,
            "news_evidence",
            found=stats.get("found", 0),
            sources=len(sources),
            date_range=f"{state.get('from_date') or ''}..{state.get('to_date') or ''}",
            date_explicit=bool(state.get("date_explicit")),
            widened=bool(notice) and not state.get("date_explicit"),
        )
        return {
            "evidence": evidence,
            "sources": sources,
            "notice": notice,
            **_advance(state, "news_evidence"),
        }

    async def web_evidence_node(state: AgentState) -> dict[str, Any]:
        query = state.get("web_query") or state["standalone_question"]
        days = _web_days(state)
        # honor sites the user named explicitly, even filtered ones
        results = await tools.search_web(
            query,
            days=days,
            news_like=bool(days),
            allow_domains=requested_domains(state["query"]),
        )
        # Tavily's window only bounds the start, and it bounds it loosely. The
        # requested range is enforced here so a web citation can't fall outside
        # the period the publisher results were held to.
        if state.get("from_date") or state.get("to_date"):
            results = within_range(
                results,
                state.get("from_date"),
                state.get("to_date"),
                # an undated page can't be shown to fall inside a stated range
                keep_undated=not state.get("date_explicit"),
            )
        evidence, sources = _web_to_evidence(
            results, list(state.get("evidence", [])), list(state.get("sources", []))
        )
        return {
            "evidence": evidence,
            "sources": sources,
            "web_used": bool(results),
            **_advance(state, "web_evidence"),
        }

    async def synthesize_node(state: AgentState) -> dict[str, Any]:
        prompt = build_synthesis_prompt(
            question=state.get("standalone_question") or state["query"],
            original_message=state["query"],
            evidence_block=_evidence_block(state.get("evidence", [])),
            mode=state.get("mode", "NEWS"),
            intent=state.get("intent", "QA"),
            output_format=state.get("output_format", ""),
            widened=bool(state.get("notice")) and not state.get("date_explicit"),
            has_web=bool(state.get("web_used")),
            # only a stated period is a constraint worth naming to the model
            date_window=_window_label(state) if state.get("date_explicit") else "",
        )
        llm = synthesis_llm or get_chat_model(temperature=0.2, streaming=True, max_tokens=1800)
        answer = response_text(
            await llm.ainvoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
        )
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        sources = state.get("sources", [])
        # Article mode cites once by design, so keep the article either way
        kept = [s for s in sources if s["n"] in cited]
        if not kept:
            kept = sources[:1] if state.get("mode") == "ARTICLE" else sources[:3]
        log_event(
            logger,
            "agent_answer",
            mode=state.get("mode"),
            intent=state.get("intent"),
            agent_tools_called=state.get("steps", []),
            sources=len(kept),
        )
        return {"answer": answer, "sources": kept, **_advance(state, "synthesize")}

    def route_after_understand(state: AgentState) -> str:
        return {
            "ARTICLE": "article_evidence",
            "WEB": "web_evidence",
            "NEWS": "news_evidence",
            "BOTH": "news_evidence",
            "DECLINE": "decline",
        }.get(state.get("mode", "NEWS"), "news_evidence")

    def route_after_news(state: AgentState) -> str:
        if not settings.tavily_api_key:
            return "synthesize"
        if state.get("mode") == "BOTH":
            return "web_evidence"
        # top up only when Guardian retrieval came back too thin to answer on
        if len(state.get("sources", [])) <= settings.web_search_threshold:
            return "web_evidence"
        return "synthesize"

    graph = StateGraph(AgentState)
    graph.add_node("understand", understand_node)
    graph.add_node("decline", decline_node)
    graph.add_node("article_evidence", article_evidence_node)
    graph.add_node("news_evidence", news_evidence_node)
    graph.add_node("web_evidence", web_evidence_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("understand")
    graph.add_conditional_edges(
        "understand",
        route_after_understand,
        {
            "article_evidence": "article_evidence",
            "news_evidence": "news_evidence",
            "web_evidence": "web_evidence",
            "decline": "decline",
        },
    )
    graph.add_edge("decline", END)
    graph.add_edge("article_evidence", "synthesize")
    graph.add_conditional_edges(
        "news_evidence", route_after_news, {"web_evidence": "web_evidence", "synthesize": "synthesize"}
    )
    graph.add_edge("web_evidence", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


async def run_agent(
    session: AsyncSession,
    query: str,
    conversation_state: dict[str, Any] | None = None,
    history: list[dict] | None = None,
) -> AgentState:
    settings = get_settings()
    graph = build_agent_graph(session)
    initial: AgentState = {
        "query": query,
        "conversation_state": conversation_state or {},
        "history": history or [],
        "steps": [],
    }
    return await graph.ainvoke(initial, config={"recursion_limit": settings.max_agent_iterations + 4})
