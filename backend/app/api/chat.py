import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin
from app.database.repositories import ConversationRepository
from app.database.session import get_session
from app.services.chat_service import chat_once, chat_stream, detect_route

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


def client_id_header(x_client_id: str = Header(default="", max_length=64)) -> str:
    """Anonymous per-browser id scoping conversations to their creator."""
    return x_client_id


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=36)
    article_id: str | None = Field(default=None, max_length=512)
    stream: bool = True


class IntentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=36)
    article_id: str | None = Field(default=None, max_length=512)


@router.post("/intent", dependencies=[Depends(require_admin)])
async def detect_intent(
    request: IntentRequest,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    """Run only the routing agent and return its decision — no search, no
    answer. Useful for checking why a question went to the web vs the
    Guardian, and for testing routing changes without spending a chat turn.

    Operator-only: it still costs an LLM call per request, and nothing in the
    UI calls it."""
    return await detect_route(session, request.message, request.conversation_id, request.article_id, client_id)


@router.post("/chat")
async def chat(
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    if request.stream:
        return StreamingResponse(
            chat_stream(
                session, request.message, request.conversation_id, request.article_id, client_id
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering for SSE
                "Connection": "keep-alive",
            },
        )
    return await chat_once(
        session, request.message, request.conversation_id, request.article_id, client_id
    )


@router.get("/conversations")
async def list_conversations(
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    repo = ConversationRepository(session)
    conversations = await repo.list_recent(user_id=client_id)
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at,
            "updated_at": c.updated_at,
        }
        for c in conversations
    ]


@router.delete("/conversations", status_code=204)
async def delete_all_conversations(
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    """Clear this client's chat history. Scoped by X-Client-Id, so an empty
    id can never wipe another visitor's conversations."""
    repo = ConversationRepository(session)
    deleted = await repo.delete_all(client_id)
    await session.commit()
    logger.info("cleared %d conversations", deleted)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    repo = ConversationRepository(session)
    if not await repo.delete(conversation_id, user_id=client_id):
        raise HTTPException(404, "Conversation not found")
    await session.commit()


@router.delete("/conversations/{conversation_id}/article", status_code=204)
async def clear_conversation_article(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    """Unpin the article a conversation is anchored to.

    A chat opened from an article keeps answering about it until the pin is
    released, which is right while the reader is still on that piece and wrong
    once they have moved on. Only the reader knows which, so give them the
    control rather than guessing.
    """
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id=client_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    state = dict(conversation.state or {})
    state["active_article_id"] = ""
    state["active_article_headline"] = ""
    conversation.state = state
    await session.commit()


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id, user_id=client_id)
    if conversation is None:
        raise HTTPException(404, "Conversation not found")
    messages = await repo.get_messages(conversation_id)
    return {
        "id": conversation.id,
        "title": conversation.title,
        "state": conversation.state,
        "messages": [
            {
                # the id lets a reopened chat play its answers back
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "sources": m.sources,
                "created_at": m.created_at,
            }
            for m in messages
        ],
    }
