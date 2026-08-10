"""Chat orchestration: conversation persistence, memory, and SSE streaming.

SSE event types sent to the frontend:
  state    {conversation_id}       — ids for follow-up requests
  status   {stage, detail}         — pipeline progress
  token    {delta}                 — incremental answer text
  route    {route, intent, standalone_question}
                                   — the routing agent's decision
  sources  {sources: [...]}        — numbered citations
  notice   {detail}                — retrieval metadata (e.g. widened window),
                                     shown as a UI badge, never as answer prose
  done     {}
  error    {detail}
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_agent_graph, run_agent
from app.agents.state import default_conversation_state
from app.core.logging import Timer, log_event
from app.core.security import sanitize_user_text
from app.database.repositories import ConversationRepository

logger = logging.getLogger(__name__)

_STAGE_LABELS = {
    "understand": "Understanding your question…",
    "article_evidence": "Reading the article…",
    "news_evidence": "Searching news coverage…",
    "web_evidence": "Searching the web…",
    "synthesize": "Writing the answer…",
}

_NEXT_STAGE = {
    "ARTICLE": "article_evidence",
    "NEWS": "news_evidence",
    "BOTH": "news_evidence",
    "WEB": "web_evidence",
}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def _updated_state(previous: dict, final: dict) -> dict:
    topics = final.get("topics") or []
    return {
        "topic": topics[0] if topics else previous.get("topic", ""),
        "entities": final.get("entities") or previous.get("entities", []),
        "date_range": {
            "from_date": final.get("from_date") or "",
            "to_date": final.get("to_date") or "",
        },
        "active_article_id": previous.get("active_article_id", ""),
        "active_article_headline": previous.get("active_article_headline", ""),
        "previous_intent": final.get("intent", ""),
        "last_sources": final.get("sources", [])[:10],
    }


async def _prepare(
    session: AsyncSession,
    message: str,
    conversation_id: str | None,
    article_id: str | None,
    client_id: str = "",
):
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id=client_id) if conversation_id else None
    if conversation is None:
        conversation = await repo.create(title=message[:60], user_id=client_id)
    state = conversation.state or default_conversation_state()
    if article_id:
        state["active_article_id"] = article_id

    # Real turns, not a flattened summary: the understanding step needs to
    # resolve references like "related news" against what was actually said.
    previous = await repo.get_recent_messages(conversation.id, n=6)
    history = [{"role": m.role, "content": m.content} for m in previous]

    await repo.add_message(conversation, "user", message)
    return repo, conversation, state, history


async def detect_route(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    article_id: str | None = None,
    client_id: str = "",
) -> dict[str, Any]:
    """Routing decision only — what the agent understood and where it would
    look. Runs no search and writes nothing to the conversation."""
    from app.agents.understand import understand
    from app.core.config import get_settings
    from app.llm.client import get_chat_model

    message = sanitize_user_text(message)
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id=client_id) if conversation_id else None
    history: list[dict[str, Any]] = []
    active_article = article_id or ""
    if conversation is not None:
        history = [
            {"role": m.role, "content": m.content}
            for m in await repo.get_recent_messages(conversation.id, n=6)
        ]
        active_article = active_article or (conversation.state or {}).get("active_article_id", "")

    settings = get_settings()
    llm = get_chat_model(temperature=0, max_tokens=600) if settings.openai_api_key else None
    result = await understand(
        message,
        history=history,
        active_article=active_article,
        llm=llm,
        web_available=bool(settings.tavily_api_key),
    )
    return {
        "message": message,
        "standalone_question": result.standalone_question,
        "route": result.mode,
        "intent": result.intent,
        "entities": result.entities,
        "topics": result.topics,
        "date_range": {"from": result.from_date, "to": result.to_date},
        "section": result.section,
        "news_query": result.news_query,
        "web_query": result.web_query,
        "freshness": result.freshness,
        "reference": result.reference,
        "reason": result.reason,
    }


async def chat_once(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    article_id: str | None = None,
    client_id: str = "",
) -> dict[str, Any]:
    """Non-streaming chat (tests, evaluation, stream=false clients)."""
    message = sanitize_user_text(message)
    repo, conversation, conv_state, history = await _prepare(
        session, message, conversation_id, article_id, client_id
    )
    with Timer() as timer:
        final = await run_agent(session, message, conv_state, history)
    answer = final.get("answer", "")
    sources = final.get("sources", [])
    conversation.state = _updated_state(conv_state, final)
    await repo.add_message(conversation, "assistant", answer, sources)
    await session.commit()
    log_event(logger, "chat_complete", mode=final.get("mode"), total_latency=timer.ms)
    return {
        "conversation_id": conversation.id,
        "answer": answer,
        "sources": sources,
        "mode": final.get("mode", ""),
        "intent": final.get("intent", ""),
        "notice": final.get("notice", ""),
        "steps": final.get("steps", []),
    }


async def chat_stream(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    article_id: str | None = None,
    client_id: str = "",
) -> AsyncGenerator[str, None]:
    message = sanitize_user_text(message)
    try:
        repo, conversation, conv_state, history = await _prepare(
            session, message, conversation_id, article_id, client_id
        )
        yield _sse("state", {"conversation_id": conversation.id})
        yield _sse("status", {"stage": "understand", "detail": _STAGE_LABELS["understand"]})

        graph = build_agent_graph(session)
        initial = {
            "query": message,
            "conversation_state": conv_state,
            "history": history,
            "steps": [],
        }

        final_state: dict[str, Any] = dict(initial)
        streamed_any = False

        async for stream_mode, payload in graph.astream(
            initial, stream_mode=["updates", "messages"]
        ):
            if stream_mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") == "synthesize" and getattr(chunk, "content", ""):
                    streamed_any = True
                    yield _sse("token", {"delta": chunk.content})
            else:
                for node_name, update in payload.items():
                    if update:
                        final_state.update(update)
                    if node_name == "understand":
                        # surface the routing decision so the UI can show it
                        yield _sse(
                            "route",
                            {
                                "route": (update or {}).get("mode", "NEWS"),
                                "intent": (update or {}).get("intent", "QA"),
                                "standalone_question": (update or {}).get("standalone_question", ""),
                            },
                        )
                        stage = _NEXT_STAGE.get((update or {}).get("mode", "NEWS"), "news_evidence")
                    elif node_name == "news_evidence":
                        stage = "web_evidence" if final_state.get("mode") == "BOTH" else "synthesize"
                    elif node_name in ("article_evidence", "web_evidence"):
                        stage = "synthesize"
                    else:
                        stage = None
                    if stage:
                        yield _sse("status", {"stage": stage, "detail": _STAGE_LABELS.get(stage, "")})

        answer = final_state.get("answer", "")
        if answer and not streamed_any:
            yield _sse("token", {"delta": answer})

        if final_state.get("notice"):
            yield _sse("notice", {"detail": final_state["notice"]})
        yield _sse("sources", {"sources": final_state.get("sources", [])})

        conversation.state = _updated_state(conv_state, final_state)
        await repo.add_message(conversation, "assistant", answer, final_state.get("sources", []))
        await session.commit()
        yield _sse("done", {})
    except Exception:
        logger.exception("chat_stream failed")
        yield _sse("error", {"detail": "The assistant hit an internal error. Please try again."})
