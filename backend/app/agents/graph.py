"""Controlled LangGraph agent.

This is a constrained graph, not an open-ended autonomous agent: the router
classifies intent, conditional edges pick the tool path, and synthesis is
always grounded in the evidence collected by earlier nodes.

    classify ──► fetch_fresh ──► retrieve ──► synthesize ──► END
        │                          ▲
        └── (no freshness needed) ─┘
"""

import logging
import re
from datetime import date, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
from app.agents.dateparse import clean_search_query
from app.agents.decision import decide_source
from app.agents.router import classify
from app.agents.state import AgentState
from app.core.config import get_settings
from app.core.logging import log_event
from app.llm.client import get_chat_model, response_text
from app.llm.prompts import SYSTEM_PROMPT, build_synthesis_prompt
from app.rag.vector_store import RetrievalFilters, ScoredChunk

logger = logging.getLogger(__name__)

# Intents answered Guardian-API-first (fresh articles fetched and indexed)
FRESH_INTENTS = {
    "LATEST_NEWS",
    "ARTICLE_SEARCH",
    "ARTICLE_QA",
    "ENTITY_RESEARCH",
    "COMPARISON",
    "TIMELINE",
    "TOPIC_SUMMARY",
    "TREND_ANALYSIS",
}

MAX_EVIDENCE_CHARS = 14000  # hard cap on retrieval context sent to the LLM
WEB_EVIDENCE_SHARE = 0.35  # portion of the cap reserved for web sources when present
SEARCH_LOOKBACK_DAYS = 3  # fetch wider than we filter, so narrow windows aren't empty
RELAX_WINDOW_DAYS = 14  # first fallback window when a strict date filter finds nothing


def route_after_classify(state: AgentState) -> str:
    """The single routing policy: which node follows classification.
    Also used by the chat service to announce pipeline progress."""
    if state.get("intent") == "SOURCE_LOOKUP":
        return "retrieve"
    if state.get("intent") in FRESH_INTENTS or state.get("freshness"):
        return "fetch_fresh"
    return "retrieve"


def _advance(state: AgentState, *steps: str) -> dict[str, Any]:
    return {"steps": state.get("steps", []) + list(steps)}


def _build_filters(state: AgentState) -> RetrievalFilters:
    filters = RetrievalFilters.from_iso(
        state.get("from_date"),
        state.get("to_date"),
        sections=[state["section"]] if state.get("section") else None,
    )
    intent = state.get("intent", "")
    conv = state.get("conversation_state", {})
    if intent == "ARTICLE_QA" and conv.get("active_article_id"):
        filters.article_ids = [conv["active_article_id"]]
    if intent == "SOURCE_LOOKUP" and conv.get("last_sources"):
        filters.article_ids = [s["article_id"] for s in conv["last_sources"] if s.get("article_id")]
    return filters


def _chunks_to_evidence(groups: dict[str, list[ScoredChunk]]) -> tuple[list[dict], list[dict]]:
    """Number sources per unique article and build evidence entries.

    Returns (evidence_items, sources). Chunks from the same article share a
    citation number. URLs are the real Guardian webUrls — never synthesized.
    """
    sources: list[dict] = []
    source_index: dict[str, int] = {}
    evidence: list[dict] = []
    for group_name, chunks in groups.items():
        for scored in chunks:
            chunk = scored.chunk
            if chunk.article_id not in source_index:
                source_index[chunk.article_id] = len(sources) + 1
                sources.append(
                    {
                        "n": len(sources) + 1,
                        "type": "guardian",
                        "source": "The Guardian",
                        "article_id": chunk.article_id,
                        "headline": chunk.headline,
                        "url": chunk.url,
                        "published_at": chunk.published_at.isoformat() if chunk.published_at else "",
                        "section": chunk.section,
                        "author": chunk.author,
                    }
                )
            evidence.append(
                {
                    "n": source_index[chunk.article_id],
                    "type": "guardian",
                    "source": "The Guardian",
                    "group": group_name,
                    "article_id": chunk.article_id,
                    "headline": chunk.headline,
                    "published_at": chunk.published_at.isoformat() if chunk.published_at else "",
                    "section": chunk.section,
                    "text": chunk.text,
                    "score": scored.score,
                }
            )
    return evidence, sources


def _web_to_evidence(
    results: list, evidence: list[dict], sources: list[dict]
) -> tuple[list[dict], list[dict]]:
    """Append web results after the Guardian sources, continuing the citation
    numbering. Web entries are explicitly typed so the model and the UI can
    never present them as Guardian journalism."""
    seen_urls = {s["url"] for s in sources}
    for result in results:
        if not result.url or result.url in seen_urls:
            continue
        seen_urls.add(result.url)
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
                "article_id": "",
                "headline": result.title,
                "published_at": result.published_date or "",
                "section": "",
                "text": result.content,
                "score": result.score,
            }
        )
    return evidence, sources


def _format_evidence_entry(item: dict, header: str = "") -> str:
    origin = "The Guardian" if item.get("type") == "guardian" else item.get("source", "web")
    return (
        f"{header}[{item['n']}] {item['headline']} "
        f"({item['published_at'][:10]}, {origin})\n{item['text']}\n"
    )


def _fill(items: list[dict], budget: int, web_header: bool = False) -> tuple[list[str], int]:
    lines: list[str] = []
    used = 0
    current_group = None
    for item in items:
        header = ""
        if web_header and current_group is None:
            current_group = "web"
            header = (
                "--- NON-GUARDIAN WEB SOURCES (supplementary; attribute to the "
                "named site, never to The Guardian) ---\n"
            )
        elif not web_header and item["group"] != "default" and item["group"] != current_group:
            current_group = item["group"]
            header = f"--- Evidence about: {current_group} ---\n"
        entry = _format_evidence_entry(item, header)
        if used + len(entry) > budget:
            break
        lines.append(entry)
        used += len(entry)
    return lines, used


def _evidence_block(evidence: list[dict]) -> str:
    """Render evidence within the context cap.

    Guardian and web evidence get separate budgets: Guardian chunks are long
    and appear first, so a single shared budget silently starved out every web
    source — the model then never saw the web evidence it was told to cite.
    """
    guardian = [e for e in evidence if e.get("type") != "web"]
    web = [e for e in evidence if e.get("type") == "web"]
    if not web:
        lines, _ = _fill(guardian, MAX_EVIDENCE_CHARS)
        return "\n".join(lines)

    web_budget = min(int(MAX_EVIDENCE_CHARS * WEB_EVIDENCE_SHARE), sum(len(_format_evidence_entry(e)) for e in web) + 200)
    guardian_lines, guardian_used = _fill(guardian, MAX_EVIDENCE_CHARS - web_budget)
    # hand any unspent Guardian budget back to the web section
    web_lines, _ = _fill(web, MAX_EVIDENCE_CHARS - guardian_used, web_header=True)
    return "\n".join(guardian_lines + web_lines)


def build_agent_graph(session: AsyncSession, router_llm=None, synthesis_llm=None):
    """Compile the agent graph bound to a DB session for this request."""
    settings = get_settings()

    async def classify_node(state: AgentState) -> dict[str, Any]:
        llm = router_llm
        if llm is None and settings.openai_api_key:
            llm = get_chat_model(temperature=0, max_tokens=500)
        result = await classify(state["query"], state.get("conversation_state", {}), llm=llm)
        queries = result.get("search_queries") or []
        if not queries:
            queries = [", ".join(result.get("entities", []) + result.get("topics", [])) or state["query"][:80]]
        return {
            "intent": result.get("intent", "TOPIC_SUMMARY"),
            "entities": result.get("entities", []),
            "topics": result.get("topics", []),
            "from_date": result.get("from_date") or None,
            "to_date": result.get("to_date") or None,
            "section": result.get("section") or None,
            "freshness": bool(result.get("freshness")),
            "output_format": result.get("output_format", ""),
            "search_queries": queries[:3],
            **_advance(state, "classify"),
        }

    async def decide_source_node(state: AgentState) -> dict[str, Any]:
        """Decision agent: Guardian, web, or both."""
        llm = router_llm
        if llm is None and settings.openai_api_key:
            llm = get_chat_model(temperature=0, max_tokens=200)
        decision = await decide_source(
            state["query"],
            llm=llm,
            web_available=bool(settings.tavily_api_key),
            today=date.today().isoformat(),
        )
        return {
            "evidence_plan": decision["plan"],
            "web_query": decision.get("web_query", ""),
            **_advance(state, "decide_source"),
        }

    async def web_search_node(state: AgentState) -> dict[str, Any]:
        """Supplementary web evidence, appended after any Guardian sources."""
        query = state.get("web_query") or state["query"]
        results = await tools.search_web(
            query, days=30 if state.get("freshness") else None
        )
        evidence, sources = _web_to_evidence(
            results, list(state.get("evidence", [])), list(state.get("sources", []))
        )
        return {
            "evidence": evidence,
            "sources": sources,
            "web_used": bool(results),
            **_advance(state, "web_search"),
        }

    async def fetch_fresh_node(state: AgentState) -> dict[str, Any]:
        """Freshness path: query the Guardian API first, index unseen articles.
        An active article (from "Ask AI about this article") is always fetched
        and indexed too, regardless of how the intent was classified."""
        intent = state.get("intent", "")
        conv = state.get("conversation_state", {})

        queries = list(state.get("search_queries", []))
        if intent == "COMPARISON" and state.get("entities"):
            queries = state["entities"][:3]
        # "today"/"latest" belong in the date filter, not the keyword query
        queries = list(dict.fromkeys(clean_search_query(q) for q in queries if q.strip()))
        order_by = "newest" if state.get("freshness") or intent == "LATEST_NEWS" else "relevance"
        active_id = conv.get("active_article_id")

        # A same-day window can be nearly empty early in the publishing day, so
        # fetch a wider slice than we filter on — retrieval still ranks by recency.
        search_from = state.get("from_date")
        if search_from:
            search_from = (date.fromisoformat(search_from) - timedelta(days=SEARCH_LOOKBACK_DAYS)).isoformat()

        stats = await tools.fetch_and_index(
            session,
            queries,
            article_ids=[active_id] if active_id else None,
            from_date=search_from,
            to_date=state.get("to_date"),
            section=state.get("section"),
            order_by=order_by,
        )
        return {
            "guardian_found": stats["found"],
            "articles_indexed": stats["indexed"] + stats["updated"],
            **_advance(state, "fetch_fresh"),
        }

    async def retrieve_node(state: AgentState) -> dict[str, Any]:
        intent = state.get("intent", "")
        filters = _build_filters(state)
        freshness = bool(state.get("freshness"))

        if intent == "COMPARISON" and len(state.get("entities", [])) >= 2:
            groups = await tools.compare_articles(
                session, state["entities"], state.get("from_date"), state.get("to_date")
            )
        elif intent == "TIMELINE":
            topic = ", ".join(state.get("entities", []) or state.get("topics", [])) or state["query"]
            groups = {"default": await tools.build_timeline(session, topic, state.get("from_date"))}
        else:
            groups = {
                "default": await tools.retrieve_rag(
                    session, state["query"], filters=filters, freshness=freshness, rerank=True
                )
            }

        # A narrow window (e.g. "today" early in the publishing day) can match
        # nothing even when relevant coverage exists. Widen rather than
        # reporting no evidence — the answer states which period it covers.
        relaxed_note = ""
        if not any(groups.values()) and (filters.from_date or filters.sections):
            for window, note in (
                (RELAX_WINDOW_DAYS, f"the last {RELAX_WINDOW_DAYS} days"),
                (None, "all indexed Guardian reporting"),
            ):
                wider = RetrievalFilters(article_ids=filters.article_ids)
                if window is not None and filters.from_date:
                    wider.from_date = filters.from_date - timedelta(days=window)
                fallback = await tools.retrieve_rag(
                    session, state["query"], filters=wider, freshness=True, rerank=True
                )
                if fallback:
                    groups = {"default": fallback}
                    relaxed_note = (
                        "No Guardian articles were found for the exact period requested; "
                        f"the evidence below is drawn from {note} instead. Say so in your answer "
                        "and give the date of each item."
                    )
                    break

        evidence, sources = _chunks_to_evidence(groups)
        log_event(logger, "retrieve_node", intent=intent, evidence=len(evidence), relaxed=bool(relaxed_note))
        return {
            "evidence": evidence,
            "sources": sources,
            "relaxed_note": relaxed_note,
            **_advance(state, "retrieve", "rerank"),
        }

    async def synthesize_node(state: AgentState) -> dict[str, Any]:
        prompt = build_synthesis_prompt(
            question=state["query"],
            evidence_block=_evidence_block(state.get("evidence", [])),
            intent=state.get("intent", "TOPIC_SUMMARY"),
            conversation_summary=state.get("conversation_summary", ""),
            output_format=state.get("output_format", ""),
            coverage_note=state.get("relaxed_note", ""),
            has_web_sources=bool(state.get("web_used")),
        )
        llm = synthesis_llm or get_chat_model(temperature=0.2, streaming=True, max_tokens=1800)
        response = await llm.ainvoke(
            [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
        )
        answer = response_text(response)
        # Keep only sources actually cited in the answer
        cited = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
        sources = state.get("sources", [])
        cited_sources = [s for s in sources if s["n"] in cited] or sources[:3]
        log_event(
            logger,
            "agent_answer",
            intent=state.get("intent"),
            agent_tools_called=state.get("steps", []),
            sources=len(cited_sources),
        )
        return {
            "answer": answer,
            "sources": cited_sources,
            **_advance(state, "synthesize"),
        }

    def route_after_decision(state: AgentState) -> str:
        """WEB-only questions skip Guardian retrieval entirely."""
        if state.get("evidence_plan") == "WEB":
            return "web_search"
        return route_after_classify(state)

    def route_after_retrieve(state: AgentState) -> str:
        """Top up with web sources when the plan asked for them, or when
        Guardian evidence came back too thin to answer on."""
        if not settings.tavily_api_key:
            return "synthesize"
        if state.get("evidence_plan") == "BOTH":
            return "web_search"
        if len(state.get("sources", [])) <= settings.web_search_threshold:
            return "web_search"
        return "synthesize"

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("decide_source", decide_source_node)
    graph.add_node("fetch_fresh", fetch_fresh_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "decide_source")
    graph.add_conditional_edges(
        "decide_source",
        route_after_decision,
        {"fetch_fresh": "fetch_fresh", "retrieve": "retrieve", "web_search": "web_search"},
    )
    graph.add_edge("fetch_fresh", "retrieve")
    graph.add_conditional_edges(
        "retrieve", route_after_retrieve, {"web_search": "web_search", "synthesize": "synthesize"}
    )
    graph.add_edge("web_search", "synthesize")
    graph.add_edge("synthesize", END)
    return graph.compile()


async def run_agent(
    session: AsyncSession,
    query: str,
    conversation_state: dict[str, Any] | None = None,
    conversation_summary: str = "",
) -> AgentState:
    """Non-streaming entry point (used by tests, evaluation, stream=false)."""
    settings = get_settings()
    graph = build_agent_graph(session)
    initial: AgentState = {
        "query": query,
        "conversation_state": conversation_state or {},
        "conversation_summary": conversation_summary,
        "steps": [],
    }
    return await graph.ainvoke(initial, config={"recursion_limit": settings.max_agent_iterations + 4})
