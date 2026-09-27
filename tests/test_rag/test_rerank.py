"""测试重排序"""
import pytest
from rag.rerank import Reranker
from core.document import SearchResult, Chunk


class TestReranker:
    def test_rerank_empty_results(self):
        reranker = Reranker(method="cross_encoder")
        results = reranker.rerank("test query", [], top_k=5)
        assert results == []

    def test_rerank_with_results(self, monkeypatch):
        """注入假 CrossEncoder：既不下载模型，又能校验真实重排行为"""
        reranker = Reranker(method="cross_encoder")

        class FakeCrossEncoder:
            def predict(self, pairs):
                # 分数随原顺序递增 → 重排后应完全反转
                return [float(i) for i in range(len(pairs))]

        monkeypatch.setattr(reranker, "_load_model", lambda: FakeCrossEncoder())

        results = [
            SearchResult(
                chunk=Chunk(id=f"test_{i}", text=f"text_{i}", page=1),
                score=float(5 - i),
                source="test",
                rank=i + 1,
            )
            for i in range(5)
        ]

        reranked = reranker.rerank("test", results, top_k=3)

        assert len(reranked) == 3
        assert [r.chunk.id for r in reranked] == ["test_4", "test_3", "test_2"]
        assert all(r.source == "rerank" for r in reranked)
        assert [r.rank for r in reranked] == [1, 2, 3]
