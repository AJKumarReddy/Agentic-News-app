from types import SimpleNamespace

from app.rag.reranker import LLMReranker, NoopReranker
from app.rag.vector_store import ScoredChunk


def candidates(n: int = 6) -> list[ScoredChunk]:
    return [
        ScoredChunk(
            chunk=SimpleNamespace(id=i, headline=f"Headline {i}", text=f"Chunk text {i}"),
            score=1.0 - i * 0.1,
        )
        for i in range(n)
    ]


class FakeLLM:
    def __init__(self, content: str):
        self.content = content

    async def ainvoke(self, prompt: str):
        return SimpleNamespace(content=self.content)


async def test_noop_keeps_order_and_truncates():
    result = await NoopReranker().rerank("q", candidates(), top_n=3)
    assert [s.chunk.id for s in result] == [0, 1, 2]


async def test_llm_reranker_reorders():
    reranker = LLMReranker(llm=FakeLLM("[3, 1, 5]"))
    result = await reranker.rerank("query", candidates(), top_n=3)
    assert [s.chunk.id for s in result] == [2, 0, 4]


async def test_llm_reranker_bad_output_falls_back():
    reranker = LLMReranker(llm=FakeLLM("I cannot rank these."))
    result = await reranker.rerank("query", candidates(), top_n=3)
    assert [s.chunk.id for s in result] == [0, 1, 2]


async def test_llm_reranker_ignores_out_of_range_ids():
    reranker = LLMReranker(llm=FakeLLM("[99, 2, 2, 1]"))
    result = await reranker.rerank("query", candidates(), top_n=3)
    assert [s.chunk.id for s in result] == [1, 0]


async def test_small_candidate_set_skips_llm():
    reranker = LLMReranker(llm=None)  # would crash if invoked
    result = await reranker.rerank("query", candidates(2), top_n=5)
    assert len(result) == 2
