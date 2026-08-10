"""Controlled LangGraph agent with four answering modes.

    understand ──┬── ARTICLE ─→ article_evidence ─┐
                 ├── NEWS ────→ news_evidence ────┤
                 ├── WEB ─────→ web_evidence ─────┼─→ synthesize
                 └── BOTH ────→ news_evidence ─→ web_evidence ─┘

Each mode does only the work it needs. Answering about an article the user is
already viewing does not search, filter, or rerank anything — the article is
known. That separation is deliberate: a single shared path previously leaked
news-retrieval machinery (date windows, relaxation notices) into article
answers where it made no sense.
"""

import logging
import re
from datetime import date, datetime, time, timedelta
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
from app.agents.state import AgentState
from app.agents.understand import understand
from app.core.config import get_settings
from app.core.logging import log_event
from app.llm.client import get_chat_model, response_text
from app.llm.prompts import SYSTEM_PROMPT, build_synthesis_prompt
from app.rag.vector_store import RetrievalFilters, ScoredChunk
from app.websearch.client import requested_domains

logger = logging.getLogger(__name__)

MAX_EVIDENCE_CHARS = 14000
WEB_EVIDENCE_SHARE = 0.35
ARTICLE_BODY_CHARS = 12000
SEARCH_LOOKBACK_DAYS = 3
RELAX_WINDOW_DAYS = 14


# ── evidence assembly ────────────────────────────────────────────────

def _guardian_source(chunk) -> dict:
    return {
        "type": "guardian",
        "source": "The Guardian",
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
                sources.append({"n": len(sources) + 1, **_guardian_source(chunk)})
            evidence.append(
                {
                    "n": index[chunk.article_id],
                    "type": "guardian",
                    "source": "The Guardian",
                    "group": group_name,
                    "headline": chunk.headline,
                    "published_at": chunk.published_at.isoformat() if chunk.published_at else "",
                    "text": chunk.text,
                }
            )
    return evidence, sources


def _web_to_evidence(results, evidence: list[dict], sources: list[dict]):
    """Append web results after Guardian sources, continuing the numbering."""
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
    origin = "The Guardian" if item.get("type") == "guardian" else item.get("source", "web")
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
                "--- WEB SOURCES (not Guardian journalism; attribute to the named site) ---\n"
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
    """Guardian and web evidence get separate budgets — a single shared cap
    let long Guardian chunks starve out every web source before the model
    ever saw them."""
    guardian = [e for e in evidence if e.get("type") != "web"]
    web = [e for e in evidence if e.get("type") == "web"]
    if not web:
        lines, _ = _fill(guardian, MAX_EVIDENCE_CHARS)
        return "\n".join(lines)
    web_budget = min(
        int(MAX_EVIDENCE_CHARS * WEB_EVIDENCE_SHARE),
        sum(len(_format_entry(e)) for e in web) + 200,
    )
    guardian_lines, guardian_used = _fill(guardian, MAX_EVIDENCE_CHARS - web_budget)
    web_lines, _ = _fill(web, MAX_EVIDENCE_CHARS - guardian_used, web_header=True)
    return "\n".join(guardian_lines + web_lines)


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
            "section": result.section,
            "news_query": result.news_query,
            "web_query": result.web_query,
            "output_format": result.output_format,
            "freshness": result.freshness,
            "reference": result.reference,
            **_advance(state, "understand"),
        }

    async def article_evidence_node(state: AgentState) -> dict[str, Any]:
        """The article is known — read it directly. No search, no filters."""
        article_id = state.get("conversation_state", {}).get("active_article_id", "")
        article = await tools.get_guardian_article(article_id) if article_id else None
        if article is None:
            return {"evidence": [], "sources": [], **_advance(state, "article_evidence")}
        source = {
            "n": 1,
            "type": "guardian",
            "source": "The Guardian",
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
        if intent == "COMPARISON" and len(state.get("entities", [])) >= 2:
            groups = await tools.compare_articles(
                session, state["entities"], state.get("from_date"), state.get("to_date")
            )
        elif intent == "TIMELINE":
            topic = ", ".join(state.get("entities", []) or state.get("topics", [])) or question
            groups = {"default": await tools.build_timeline(session, topic, state.get("from_date"))}
        else:
            groups = {
                "default": await tools.retrieve_rag(
                    session, question, filters=filters, freshness=state.get("freshness", False)
                )
            }

        # Widen rather than returning nothing when a narrow window misses.
        # The widening is reported as UI metadata, never as prose in the answer.
        notice = ""
        if not any(groups.values()) and (filters.from_date or filters.sections):
            for window, label in (
                (RELAX_WINDOW_DAYS, f"Last {RELAX_WINDOW_DAYS} days"),
                (None, "All indexed reporting"),
            ):
                wider = RetrievalFilters(article_ids=filters.article_ids)
                if window is not None and filters.from_date:
                    wider.from_date = filters.from_date - timedelta(days=window)
                fallback = await tools.retrieve_rag(session, question, filters=wider, freshness=True)
                if fallback:
                    groups = {"default": fallback}
                    notice = f"Results from {label}"
                    break

        evidence, sources = _chunks_to_evidence(groups)
        log_event(
            logger, "news_evidence", found=stats.get("found", 0), sources=len(sources), widened=bool(notice)
        )
        return {
            "evidence": evidence,
            "sources": sources,
            "notice": notice,
            **_advance(state, "news_evidence"),
        }

    async def web_evidence_node(state: AgentState) -> dict[str, Any]:
        query = state.get("web_query") or state["standalone_question"]
        # Recency is the default: this is a news assistant, and stale
        # documentation pages were being cited as current reporting. Only
        # explicit reference lookups (how-to, definitions) skip the window.
        days = None if state.get("reference") else 30
        # honor sites the user named explicitly, even filtered ones
        results = await tools.search_web(
            query,
            days=days,
            news_like=bool(days),
            allow_domains=requested_domains(state["query"]),
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
            widened=bool(state.get("notice")),
            has_web=bool(state.get("web_used")),
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
        },
    )
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
