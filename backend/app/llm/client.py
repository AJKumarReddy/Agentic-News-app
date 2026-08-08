from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def get_chat_model(temperature: float = 0.2, streaming: bool = False, max_tokens: int | None = 1500) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model=settings.chat_model,
        api_key=settings.openai_api_key,
        temperature=temperature,
        streaming=streaming,
        max_tokens=max_tokens,
        timeout=60,
        max_retries=2,
    )
