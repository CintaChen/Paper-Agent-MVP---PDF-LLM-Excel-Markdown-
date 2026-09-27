"""测试 RAG 融合策略"""
import pytest
from rag.fusion import reciprocal_rank_fusion, weighted_fusion
from core.document import SearchResult, Chunk


def make_result(chunk_id: str, score: float, rank: int) -> SearchResult:
    return SearchResult(
        chunk=Chunk(id=chunk_id, text=f"text_{chunk_id}", page=1),
        score=score,
        source="test",
        rank=rank,
    )


class TestReciprocalRankFusion:
    def test_basic_fusion(self):
        bm25 = [
            make_result("a", 0.9, 1),
            make_result("b", 0.8, 2),
            make_result("c", 0.7, 3),
        ]
        vector = [
            make_result("b", 0.95, 1),
            make_result("c", 0.85, 2),
            make_result("d", 0.75, 3),
        ]

        results = reciprocal_rank_fusion(bm25, vector, k=60)

        assert len(results) == 4
        # b 在两个结果中都排名靠前，应该排第一
        assert results[0].chunk.id == "b"

    def test_empty_results(self):
        results = reciprocal_rank_fusion([], [], k=60)
        assert results == []

    def test_only_bm25(self):
        bm25 = [make_result("a", 0.9, 1)]
        results = reciprocal_rank_fusion(bm25, [], k=60)
        assert len(results) == 1

    def test_only_vector(self):
        vector = [make_result("a", 0.9, 1)]
        results = reciprocal_rank_fusion([], vector, k=60)
        assert len(results) == 1


class TestWeightedFusion:
    def test_basic_fusion(self):
        bm25 = [
            make_result("a", 10.0, 1),
            make_result("b", 5.0, 2),
        ]
        vector = [
            make_result("b", 0.9, 1),
            make_result("a", 0.8, 2),
        ]

        results = weighted_fusion(bm25, vector, bm25_weight=0.5, vector_weight=0.5)
        assert len(results) == 2
