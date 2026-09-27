"""测试 BM25 索引的增量构建、跨文档检索与持久化"""
from core.document import Chunk
from storage.keyword_store import BM25Store


def _chunk(cid, text):
    return Chunk(id=cid, text=text)


class TestIncrementalBuild:
    def test_cross_document_search(self):
        """回归：build_index 覆盖 chunk_map 导致跨文档检索 KeyError"""
        store = BM25Store()
        store.build_index([_chunk("a", "apple banana")])
        store.build_index([_chunk("b", "cherry date")])

        assert set(store.chunk_map) == {"a", "b"}
        assert store.total_docs == 2

        hits = store.search("apple")
        assert [h.chunk.id for h in hits] == ["a"]

    def test_no_keyerror_on_multi_term_query(self):
        store = BM25Store()
        store.build_index([_chunk("a", "alpha beta")])
        store.build_index([_chunk("b", "gamma delta")])

        # 不应抛出异常
        results = store.search("alpha beta gamma")
        assert isinstance(results, list)
        assert {h.chunk.id for h in results} == {"a", "b"}

    def test_avg_doc_len_over_all_docs(self):
        store = BM25Store()
        store.build_index([_chunk("a", "one two three")])
        store.build_index([_chunk("b", "four")])

        assert store.total_docs == 2
        assert store.avg_doc_len == 2.0  # (3 + 1) / 2

    def test_rebuild_same_chunk_id_is_idempotent(self):
        store = BM25Store()
        store.build_index([_chunk("a", "apple")])
        store.build_index([_chunk("a", "apple")])

        assert store.total_docs == 1
        assert store.doc_lengths == {"a": 1}

    def test_empty_index_search_returns_empty(self):
        store = BM25Store()
        assert store.search("anything") == []


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path):
        path = tmp_path / "bm25.json"

        store = BM25Store()
        store.build_index([_chunk("a", "apple banana"), _chunk("b", "cherry")])
        store.save_index(str(path))

        loaded = BM25Store()
        loaded.load_index(str(path))

        assert set(loaded.chunk_map) == {"a", "b"}
        assert loaded.doc_lengths == store.doc_lengths
        assert [h.chunk.id for h in loaded.search("cherry")] == ["b"]
        assert [h.chunk.id for h in loaded.search("apple")] == ["a"]

    def test_reset_clears_all_state(self):
        store = BM25Store()
        store.build_index([_chunk("a", "apple")])

        store.reset()

        assert store.chunk_map == {}
        assert store.doc_lengths == {}
        assert store.index == {}
        assert store.total_docs == 0
        assert store.search("apple") == []

    def test_reset_removes_persisted_file(self, tmp_path, monkeypatch):
        """回归：只清内存不清文件，重启后 load_index 会把旧索引读回来"""
        from config.settings import settings

        path = tmp_path / "bm25.json"
        monkeypatch.setattr(settings, "bm25_index_path", path)

        store = BM25Store()
        store.build_index([_chunk("a", "apple")])
        store.save_index()
        assert path.exists()

        store.reset()

        assert not path.exists()
        assert store.search("apple") == []
