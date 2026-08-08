from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.rag.retrieval import recency_boost, rrf_merge
from app.rag.vector_store import ScoredChunk


def scored(chunk_id: int, score: float = 1.0) -> ScoredChunk:
    return ScoredChunk(chunk=SimpleNamespace(id=chunk_id), score=score)


def test_rrf_rewards_presence_in_both_lists():
    vector = [scored(1), scored(2), scored(3)]
    keyword = [scored(2), scored(4)]
    fused = rrf_merge([vector, keyword])
    # chunk 2 appears in both lists → highest fused score
    assert max(fused, key=fused.get) == 2
    assert set(fused) == {1, 2, 3, 4}


def test_rrf_rank_order_matters():
    first = [scored(1), scored(2)]
    fused = rrf_merge([first])
    assert fused[1] > fused[2]


def test_recency_boost_decays():
    now = datetime.now(timezone.utc)
    fresh = recency_boost(now - timedelta(hours=2), weight=0.02)
    old = recency_boost(now - timedelta(days=60), weight=0.02)
    assert fresh > old
    assert old < 0.001


def test_recency_boost_handles_missing_date():
    assert recency_boost(None, weight=0.02) == 0.0


def test_recency_boost_handles_naive_datetime():
    naive = datetime.now() - timedelta(days=1)
    assert recency_boost(naive, weight=0.02) >= 0.0
