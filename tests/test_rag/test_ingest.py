"""测试导入流水线：失败状态可追踪（断点续传的前提）

只注入 metadata_store 与 reader，跳过 Milvus / Embedding / LLM 依赖。
"""
import pytest

from core.document import Document
from rag.ingest import IngestPipeline
from storage.metadata_store import SQLiteStore


class FakeReader:
    """可控的读取器：按需抛错，并记录 read 调用"""

    def __init__(self, doc_id="doc1", error=None):
        self.doc_id = doc_id
        self.error = error
        self.read_calls = []

    def _make_doc_id(self, file_path):
        return self.doc_id

    def read(self, file_path):
        self.read_calls.append(file_path)
        if self.error:
            raise self.error
        raise AssertionError("本测试不应走到读取成功分支")


def _pipeline(store, reader):
    pipeline = IngestPipeline.__new__(IngestPipeline)
    pipeline.metadata_store = store
    pipeline.reader = reader
    return pipeline


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "meta.db")
    yield s
    s.close()


class TestIngestFailureTracking:
    def test_failure_records_status_and_path(self, store):
        """回归：早前 UPDATE 无行可改，失败记录丢失、无法重试"""
        reader = FakeReader(error=RuntimeError("PDF 无法解析"))
        pipeline = _pipeline(store, reader)

        with pytest.raises(RuntimeError):
            pipeline.ingest("input/papers/a.pdf")

        assert store.get_ingest_status("doc1") == "failed"

        incomplete = store.get_incomplete_docs()
        assert len(incomplete) == 1
        assert incomplete[0]["status"] == "failed"
        assert incomplete[0]["file_path"] == "input/papers/a.pdf"
        assert "PDF 无法解析" in incomplete[0]["error_message"]

    def test_retry_failed_can_find_and_reingest(self, store):
        """retry_failed 应能发现失败项并按 file_path 重试"""
        reader = FakeReader(error=RuntimeError("PDF 无法解析"))
        pipeline = _pipeline(store, reader)

        with pytest.raises(RuntimeError):
            pipeline.ingest("input/papers/a.pdf")

        # retry_failed 内部吞掉单篇异常，但必须能找到失败项并再次读取
        assert pipeline.retry_failed() == []
        assert reader.read_calls == [
            "input/papers/a.pdf",
            "input/papers/a.pdf",
        ]


class TestIngestSkipCompleted:
    def test_completed_document_returns_none_without_reading(self, store):
        store.save_document(Document(id="doc1", title="已导入"))
        store.update_ingest_status("doc1", "completed")

        reader = FakeReader(error=RuntimeError("不应被调用"))
        pipeline = _pipeline(store, reader)

        assert pipeline.ingest("input/papers/a.pdf") is None
        assert reader.read_calls == []
