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
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import tools
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


def _evidence_block(evidence: list[dict]) -> str:
    lines: list[str] = []
    used = 0
    current_group = None
    for item in evidence:
        header = ""
        if item["group"] != "default" and item["group"] != current_group:
            current_group = item["group"]
            header = f"--- Evidence about: {current_group} ---\n"
        entry = (
            f"{header}[{item['n']}] {item['headline']} "
            f"({item['published_at'][:10]}, {item['section']})\n{item['text']}\n"
        )
        if used + len(entry) > MAX_EVIDENCE_CHARS:
            break
        lines.append(entry)
        used += len(entry)
    return "\n".join(lines)


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

    async def fetch_fresh_node(state: AgentState) -> dict[str, Any]:
        """Freshness path: query the Guardian API first, index unseen articles."""
        intent = state.get("intent", "")
        conv = state.get("conversation_state", {})
        indexed = 0
        found = 0

        if intent == "ARTICLE_QA" and conv.get("active_article_id"):
            article = await tools.get_guardian_article(conv["active_article_id"])
            if article:
                stats = await tools.index_guardian_articles(session, [article])
                indexed = stats["indexed"] + stats["updated"]
                found = 1
        else:
            queries = list(state.get("search_queries", []))
            if intent == "COMPARISON" and state.get("entities"):
                queries = state["entities"][:3]
            order_by = "newest" if state.get("freshness") or intent == "LATEST_NEWS" else "relevance"
            stats = await tools.fetch_and_index(
                session,
                queries,
                from_date=state.get("from_date"),
                to_date=state.get("to_date"),
                section=state.get("section"),
                order_by=order_by,
            )
            indexed = stats["indexed"] + stats["updated"]
            found = stats["found"]

        return {
            "guardian_found": found,
            "articles_indexed": indexed,
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

        evidence, sources = _chunks_to_evidence(groups)
        return {
            "evidence": evidence,
            "sources": sources,
            **_advance(state, "retrieve", "rerank"),
        }

    async def synthesize_node(state: AgentState) -> dict[str, Any]:
        prompt = build_synthesis_prompt(
            question=state["query"],
            evidence_block=_evidence_block(state.get("evidence", [])),
            intent=state.get("intent", "TOPIC_SUMMARY"),
            conversation_summary=state.get("conversation_summary", ""),
            output_format=state.get("output_format", ""),
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

    graph = StateGraph(AgentState)
    graph.add_node("classify", classify_node)
    graph.add_node("fetch_fresh", fetch_fresh_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("synthesize", synthesize_node)

    graph.set_entry_point("classify")
    graph.add_conditional_edges(
        "classify", route_after_classify, {"fetch_fresh": "fetch_fresh", "retrieve": "retrieve"}
    )
    graph.add_edge("fetch_fresh", "retrieve")
    graph.add_edge("retrieve", "synthesize")
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
