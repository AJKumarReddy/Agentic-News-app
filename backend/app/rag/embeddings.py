"""Embedding abstraction — swap providers by implementing EmbeddingProvider."""

import logging
from abc import ABC, abstractmethod

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.core.logging import Timer, log_event

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    model_name: str
    dimensions: int

    @abstractmethod
    async def embed_texts(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self.embed_texts([text])
        return vectors[0]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    BATCH_SIZE = 96

    def __init__(self, model: str | None = None, dimensions: int | None = None):
        settings = get_settings()
        self.model_name = model or settings.embedding_model
        self.dimensions = dimensions or settings.embedding_dimensions
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        with Timer() as timer:
            for start in range(0, len(texts), self.BATCH_SIZE):
                batch = [t[:32000] for t in texts[start : start + self.BATCH_SIZE]]
                response = await self._client.embeddings.create(
                    model=self.model_name, input=batch, dimensions=self.dimensions
                )
                vectors.extend(item.embedding for item in response.data)
        log_event(logger, "embeddings_created", count=len(texts), latency_ms=timer.ms)
        return vectors


_provider: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIEmbeddingProvider()
    return _provider
