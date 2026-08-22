import json
import re
from functools import lru_cache
from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


@lru_cache(maxsize=8)
def get_chat_model(
    temperature: float = 0.2,
    streaming: bool = False,
    max_tokens: int | None = 1500,
    model: str | None = None,
) -> ChatOpenAI:
    """Cached per configuration so HTTP connection pools are reused across requests.

    `model` is part of the cache key, so the tiers in app/llm/routing.py each
    keep their own pooled client rather than rebuilding one per request.
    """
    settings = get_settings()
    return ChatOpenAI(
        model=model or settings.chat_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
        streaming=streaming,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=2,
    )


def response_text(response: Any) -> str:
    """Unwrap a chat-model response to plain text."""
    return response.content if hasattr(response, "content") else str(response)


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str, pattern: re.Pattern | None = None, default: Any = None) -> Any:
    """Pull the first JSON value out of LLM output; return default on failure."""
    match = (pattern or _JSON_OBJECT_RE).search(text)
    if not match:
        return default
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return default
