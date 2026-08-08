"""Modular reranking layer.

Initial retrieval returns 15–20 candidates; the reranker narrows them to the
5–8 chunks handed to the LLM. Three implementations:
  - LLMReranker (default): one cheap LLM call scoring relevance
  - CohereReranker: Cohere's rerank endpoint (needs COHERE_API_KEY)
  - NoopReranker: keeps hybrid ordering (RERANKER=none)
"""

import json
import logging
import re
from abc import ABC, abstractmethod

from app.core.config import get_settings
from app.core.logging import Timer, log_event
from app.rag.vector_store import ScoredChunk

logger = logging.getLogger(__name__)


class Reranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]: ...


class NoopReranker(Reranker):
    async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        return candidates[:top_n]


class LLMReranker(Reranker):
    PROMPT = (
        "You are a relevance ranker for news retrieval. Given a user query and "
        "numbered passages, return a JSON array of the passage numbers ordered "
        "from most to least relevant to the query. Include only genuinely "
        "relevant passages, at most {top_n}. Respond with JSON only, e.g. [3,1,7].\n\n"
        "Query: {query}\n\nPassages:\n{passages}"
    )

    def __init__(self, llm=None):
        self._llm = llm

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI

            settings = get_settings()
            self._llm = ChatOpenAI(
                model=settings.chat_model, api_key=settings.openai_api_key, temperature=0
            )
        return self._llm

    async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        if len(candidates) <= top_n:
            return candidates
        passages = "\n\n".join(
            f"[{i + 1}] ({s.chunk.headline}) {s.chunk.text[:600]}" for i, s in enumerate(candidates)
        )
        prompt = self.PROMPT.format(top_n=top_n, query=query[:1000], passages=passages)
        try:
            response = await self._get_llm().ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            match = re.search(r"\[[\d,\s]*\]", content)
            order = json.loads(match.group(0)) if match else []
            picked: list[ScoredChunk] = []
            seen: set[int] = set()
            for number in order:
                idx = int(number) - 1
                if 0 <= idx < len(candidates) and idx not in seen:
                    picked.append(candidates[idx])
                    seen.add(idx)
            if picked:
                return picked[:top_n]
        except Exception:
            logger.warning("LLM reranker failed; falling back to hybrid order", exc_info=True)
        return candidates[:top_n]


class CohereReranker(Reranker):
    def __init__(self):
        import cohere  # optional dependency: pip install cohere

        self._client = cohere.AsyncClient(get_settings().cohere_api_key)

    async def rerank(self, query: str, candidates: list[ScoredChunk], top_n: int) -> list[ScoredChunk]:
        if not candidates:
            return []
        response = await self._client.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=[s.chunk.text[:2000] for s in candidates],
            top_n=top_n,
        )
        return [candidates[r.index] for r in response.results]


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is None:
        choice = get_settings().reranker.lower()
        if choice == "cohere" and get_settings().cohere_api_key:
            _reranker = CohereReranker()
        elif choice == "none":
            _reranker = NoopReranker()
        else:
            _reranker = LLMReranker()
    return _reranker


async def rerank_chunks(query: str, candidates: list[ScoredChunk], top_n: int | None = None) -> list[ScoredChunk]:
    top_n = top_n or get_settings().rag_final_top_k
    with Timer() as timer:
        results = await get_reranker().rerank(query, candidates, top_n)
    log_event(logger, "reranking", candidates=len(candidates), kept=len(results), reranking_latency=timer.ms)
    return results
