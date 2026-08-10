"""Chat orchestration: conversation persistence, structured memory, and SSE
streaming of agent progress + LLM tokens.

SSE event types sent to the frontend:
  status  {stage, detail}      — pipeline progress ("Searching The Guardian…")
  token   {delta}              — incremental answer text
  sources {sources: [...]}     — numbered Guardian citations
  state   {conversation_id}    — ids for follow-up requests
  done    {}                   — stream complete
  error   {detail}             — something failed
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.graph import build_agent_graph, route_after_classify, run_agent
from app.agents.state import default_conversation_state
from app.core.logging import Timer, log_event
from app.core.security import sanitize_user_text
from app.database.repositories import ConversationRepository

logger = logging.getLogger(__name__)

_STAGE_LABELS = {
    "classify": "Understanding your question…",
    "fetch_fresh": "Searching The Guardian for current reporting…",
    "retrieve": "Retrieving and ranking relevant Guardian coverage…",
    "synthesize": "Writing a grounded answer…",
}


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def _summarize_history(messages: list, max_turns: int = 4, max_chars: int = 1200) -> str:
    """Compact recent turns for the LLM instead of resending full history."""
    recent = messages[-max_turns * 2 :]
    lines = []
    for message in recent:
        text = message.content[:300].replace("\n", " ")
        lines.append(f"{message.role}: {text}")
    summary = "\n".join(lines)
    return summary[-max_chars:]


def _updated_state(previous: dict, final_state: dict) -> dict:
    entities = final_state.get("entities") or previous.get("entities", [])
    topics = final_state.get("topics") or []
    return {
        "topic": (topics[0] if topics else previous.get("topic", "")),
        "entities": entities,
        "date_range": {
            "from_date": final_state.get("from_date") or "",
            "to_date": final_state.get("to_date") or "",
        },
        "active_article_id": previous.get("active_article_id", ""),
        "previous_intent": final_state.get("intent", ""),
        "last_sources": final_state.get("sources", [])[:10],
    }


async def _prepare(
    session: AsyncSession,
    message: str,
    conversation_id: str | None,
    article_id: str | None,
    client_id: str = "",
):
    repo = ConversationRepository(session)
    # ownership-checked: another client's conversation id starts a fresh chat
    conversation = await repo.get(conversation_id, user_id=client_id) if conversation_id else None
    if conversation is None:
        conversation = await repo.create(title=message[:60], user_id=client_id)
    state = conversation.state or default_conversation_state()
    if article_id:
        state["active_article_id"] = article_id
    history = await repo.get_recent_messages(conversation.id, n=8)
    await repo.add_message(conversation, "user", message)
    return repo, conversation, state, _summarize_history(history)


async def chat_once(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    article_id: str | None = None,
    client_id: str = "",
) -> dict[str, Any]:
    """Non-streaming chat used by tests, evaluation, and stream=false clients."""
    message = sanitize_user_text(message)
    repo, conversation, conv_state, summary = await _prepare(
        session, message, conversation_id, article_id, client_id
    )
    with Timer() as timer:
        final = await run_agent(session, message, conv_state, summary)
    answer = final.get("answer", "")
    sources = final.get("sources", [])
    conversation.state = _updated_state(conv_state, final)
    await repo.add_message(conversation, "assistant", answer, sources)
    await session.commit()
    log_event(logger, "chat_complete", intent=final.get("intent"), total_latency=timer.ms)
    return {
        "conversation_id": conversation.id,
        "answer": answer,
        "sources": sources,
        "intent": final.get("intent", ""),
        "steps": final.get("steps", []),
    }


async def chat_stream(
    session: AsyncSession,
    message: str,
    conversation_id: str | None = None,
    article_id: str | None = None,
    client_id: str = "",
) -> AsyncGenerator[str, None]:
    """SSE generator streaming pipeline status and answer tokens."""
    message = sanitize_user_text(message)
    try:
        repo, conversation, conv_state, summary = await _prepare(
            session, message, conversation_id, article_id, client_id
        )
        yield _sse("state", {"conversation_id": conversation.id})

        graph = build_agent_graph(session)
        initial = {
            "query": message,
            "conversation_state": conv_state,
            "conversation_summary": summary,
            "steps": [],
        }

        final_state: dict[str, Any] = dict(initial)
        streamed_any_token = False
        yield _sse("status", {"stage": "classify", "detail": _STAGE_LABELS["classify"]})

        async for mode, payload in graph.astream(initial, stream_mode=["updates", "messages"]):
            if mode == "messages":
                chunk, metadata = payload
                if metadata.get("langgraph_node") == "synthesize" and getattr(chunk, "content", ""):
                    streamed_any_token = True
                    yield _sse("token", {"delta": chunk.content})
            elif mode == "updates":
                for node_name, update in payload.items():
                    if update:
                        final_state.update(update)
                    # announce the next stage; classification defers to the graph's own routing
                    if node_name == "classify":
                        next_stage = route_after_classify(update or {})
                    else:
                        next_stage = {"fetch_fresh": "retrieve", "retrieve": "synthesize"}.get(node_name)
                    if next_stage:
                        yield _sse("status", {"stage": next_stage, "detail": _STAGE_LABELS.get(next_stage, "")})

        answer = final_state.get("answer", "")
        if answer and not streamed_any_token:
            # Model tokens were not surfaced by the graph stream — send whole answer
            yield _sse("token", {"delta": answer})

        sources = final_state.get("sources", [])
        yield _sse("sources", {"sources": sources})

        conversation.state = _updated_state(conv_state, final_state)
        await repo.add_message(conversation, "assistant", answer, sources)
        await session.commit()
        yield _sse("done", {})
    except Exception:
        logger.exception("chat_stream failed")
        yield _sse("error", {"detail": "The assistant hit an internal error. Please try again."})
