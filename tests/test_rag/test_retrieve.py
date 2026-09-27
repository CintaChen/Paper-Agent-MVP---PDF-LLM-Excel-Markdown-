"""测试混合检索"""
from types import SimpleNamespace

import pytest

from core.document import Chunk, SearchResult
from rag.retrieve import HybridRetriever


class TestHybridRetriever:
    def test_init(self):
        pass

    def test_retrieve(self):
        pass


def _retriever(parent_lookup):
    """构造只注入 metadata_store 的检索器（跳过 Milvus/BM25 初始化）"""
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.metadata_store = SimpleNamespace(get_parent=parent_lookup)
    return retriever


def _result(chunk_id, parent_id=None, rank=1):
    metadata = {"parent_id": parent_id} if parent_id else {}
    return SearchResult(
        chunk=Chunk(id=chunk_id, text="正文", metadata=metadata),
        score=1.0,
        source="rerank",
        rank=rank,
    )


class TestExpandToParents:
    def test_keeps_child_when_parent_missing(self):
        """回归：父文档缺失时不得丢弃子块结果"""
        retriever = _retriever(lambda parent_id: None)

        expanded = retriever._expand_to_parents([_result("c1", parent_id="p1")])

        assert len(expanded) == 1
        assert expanded[0].chunk.id == "c1"

    def test_keeps_child_without_parent_id(self):
        retriever = _retriever(lambda parent_id: None)

        expanded = retriever._expand_to_parents([_result("c1")])

        assert [r.chunk.id for r in expanded] == ["c1"]

    def test_expands_to_parent_when_found(self):
        parent = Chunk(id="p1", text="完整父块")
        retriever = _retriever(lambda parent_id: parent)

        expanded = retriever._expand_to_parents([_result("c1", parent_id="p1")])

        assert len(expanded) == 1
        assert expanded[0].chunk.id == "p1"
        assert expanded[0].source == "parent_expanded"

    def test_dedupes_same_parent(self):
        parent = Chunk(id="p1", text="完整父块")
        retriever = _retriever(lambda parent_id: parent)

        expanded = retriever._expand_to_parents([
            _result("c1", parent_id="p1", rank=1),
            _result("c2", parent_id="p1", rank=2),
        ])

        assert [r.chunk.id for r in expanded] == ["p1"]

