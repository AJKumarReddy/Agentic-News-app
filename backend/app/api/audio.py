"""Answer playback.

The request names a stored message, never text. Accepting text would make this
an open relay for speech synthesis billed to our OpenAI key; naming a message
bounds it to prose the caller already paid to generate, and lets the same
ownership check that guards `GET /conversations/{id}` guard this too.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.chat import client_id_header
from app.core.config import get_settings
from app.core.security import sanitize_user_text
from app.core.text import speakable_text
from app.database.repositories import ConversationRepository
from app.database.session import get_session
from app.services.stt_service import (
    TranscriptionError,
    audio_extension,
    transcribe,
    transcription_enabled,
)
from app.services.tts_service import MEDIA_TYPES, SpeechError, speech_enabled, synthesize

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


class SpeechRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=36)
    message_id: int = Field(ge=1)


@router.post("/speech")
async def speech(
    request: SpeechRequest,
    session: AsyncSession = Depends(get_session),
    client_id: str = Depends(client_id_header),
):
    """Audio for one assistant answer.

    404 — never 403 — for a conversation this client does not own, an unknown
    message, a message belonging to another conversation, and a user-role
    message. The response says nothing about what exists, matching the
    reasoning behind `require_admin`.
    """
    if not speech_enabled():
        raise HTTPException(503, "Speech is not available")

    repo = ConversationRepository(session)
    conversation = await repo.get(request.conversation_id, user_id=client_id)
    if conversation is None:
        raise HTTPException(404, "Not Found")

    message = await repo.get_message(conversation.id, request.message_id)
    if message is None or message.role != "assistant":
        raise HTTPException(404, "Not Found")

    text = speakable_text(message.content)
    if not text:
        # An answer that was entirely a table has nothing to say out loud.
        # Not an error — there is simply no audio, and the caller stays idle.
        return Response(status_code=204)

    try:
        audio = await synthesize(text)
    except SpeechError as exc:
        raise HTTPException(502, f"Could not generate speech: {exc}") from exc

    settings = get_settings()
    return Response(
        content=audio,
        media_type=MEDIA_TYPES.get(settings.tts_format, "application/octet-stream"),
        headers={
            # SecurityHeadersMiddleware applies its no-store with setdefault,
            # so this explicit value survives — replays come from the browser
            # rather than from another round trip.
            "Cache-Control": "private, max-age=86400",
            "Content-Length": str(len(audio)),
        },
    )


@router.post("/transcribe")
async def transcription(request: Request):
    """Text for one spoken question.

    The body is the recording itself rather than a multipart form: the only
    field is the audio, and raw bytes keep `python-multipart` out of the
    dependency list for no loss.

    This one needs no ownership check — unlike `/speech` it reads nothing back
    to the caller, it only hands them their own words. What it does need is a
    ceiling, which BodySizeLimitMiddleware applies per path, and the audio rate
    limit, which `is_audio` already applies to everything under /api/audio/.
    """
    if not transcription_enabled():
        raise HTTPException(503, "Transcription is not available")

    extension = audio_extension(request.headers.get("content-type", ""))
    if extension is None:
        raise HTTPException(415, "Unsupported audio format")

    audio = await request.body()
    settings = get_settings()
    # The middleware rejects on a declared Content-Length; a chunked upload
    # declares none, so the real bytes are checked here as well.
    if len(audio) > settings.stt_max_bytes:
        raise HTTPException(413, "Recording too large")
    if not audio:
        raise HTTPException(400, "No audio was uploaded")

    try:
        text = await transcribe(audio, extension=extension)
    except TranscriptionError as exc:
        raise HTTPException(502, f"Could not transcribe audio: {exc}") from exc

    if not text:
        # Stop pressed without speaking. Not a failure — there is simply
        # nothing to put in the box, and the caller returns to idle.
        return Response(status_code=204)

    return {"text": sanitize_user_text(text)}
