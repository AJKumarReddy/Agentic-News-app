from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories import ConversationRepository
from app.database.session import get_session
from app.services.chat_service import chat_once, chat_stream

router = APIRouter(tags=["chat"])


def client_id_header(x_client_id: str = Header(default="", max_length=64)) -> str:
    """Anonymous per-browser id scoping conversations to their creator."""
    return x_client_id


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=36)
    article_id: str | None = Field(default=None, max_length=512)
    stream: bool = True


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
            {"role": m.role, "content": m.content, "sources": m.sources, "created_at": m.created_at}
            for m in messages
        ],
    }
