"""测试 SQLite 元数据存储：UPSERT 保留状态、级联删除子表"""
import pytest

from core.document import Chunk, ContentTag, Document
from storage.metadata_store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(tmp_path / "meta.db")
    yield s
    s.close()


def _doc(doc_id="d1"):
    return Document(
        id=doc_id,
        title="论文标题",
        chunks=[Chunk(id=f"{doc_id}_c1", text="正文")],
        content_tags=[ContentTag(tag_type="domain", value="人工智能")],
    )


class TestRegisterDocument:
    def test_creates_trackable_row(self, store):
        """回归：导入前先登记，状态更新才有行可改"""
        store.register_document("d1", "input/papers/a.pdf")
        assert store.get_ingest_status("d1") == "pending"

        incomplete = store.get_incomplete_docs()
        assert len(incomplete) == 1
        assert incomplete[0]["file_path"] == "input/papers/a.pdf"

    def test_status_update_persists_before_save_document(self, store):
        store.register_document("d1", "input/papers/a.pdf")
        store.update_ingest_status("d1", "failed", "PDF 无法解析")

        incomplete = store.get_incomplete_docs()
        assert incomplete[0]["status"] == "failed"
        assert incomplete[0]["error_message"] == "PDF 无法解析"

    def test_idempotent_preserves_title_and_status(self, store):
        store.save_document(_doc())
        store.update_ingest_status("d1", "completed")

        store.register_document("d1", "input/papers/a.pdf")

        assert store.get_document("d1").title == "论文标题"
        assert store.get_ingest_status("d1") == "completed"


class TestSaveDocumentUpsert:
    def test_new_document_status_pending(self, store):
        store.save_document(_doc())
        assert store.get_ingest_status("d1") == "pending"

    def test_resave_preserves_status(self, store):
        """回归：INSERT OR REPLACE 会把 completed 打回 pending"""
        store.save_document(_doc())
        store.update_ingest_status("d1", "completed")
        assert store.get_ingest_status("d1") == "completed"

        # 再次保存（例如人工修正标签）不应重置状态
        store.save_document(_doc())
        assert store.get_ingest_status("d1") == "completed"

    def test_resave_preserves_error_message(self, store):
        store.save_document(_doc())
        store.update_ingest_status("d1", "failed", "embedding 超时")

        store.save_document(_doc())

        incomplete = store.get_incomplete_docs()
        assert len(incomplete) == 1
        assert incomplete[0]["status"] == "failed"
        assert incomplete[0]["error_message"] == "embedding 超时"

    def test_resave_updates_content_fields(self, store):
        store.save_document(_doc())
        updated = _doc()
        updated.title = "改后的标题"
        store.save_document(updated)
        assert store.get_document("d1").title == "改后的标题"


class TestDeleteDocumentCascade:
    def test_delete_removes_all_child_rows(self, store):
        store.save_document(_doc())
        store.save_parents([
            Chunk(id="p1", text="父块", metadata={"doc_id": "d1"})
        ])

        assert store.conn.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0] == 1
        assert store.conn.execute(
            "SELECT COUNT(*) FROM content_tags"
        ).fetchone()[0] == 1
        assert store.conn.execute(
            "SELECT COUNT(*) FROM parents"
        ).fetchone()[0] == 1

        store.delete_document("d1")

        for table in ("documents", "chunks", "content_tags", "parents"):
            remaining = store.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            assert remaining == 0, f"{table} 仍残留 {remaining} 行"


class TestSessionPersistence:
    def test_create_and_list_sessions(self, store):
        session_id = store.create_session(title="第一次会话")

        assert store.session_exists(session_id)
        sessions = store.list_sessions()
        assert sessions[0]["id"] == session_id
        assert sessions[0]["title"] == "第一次会话"
        assert sessions[0]["message_count"] == 0

    def test_explicit_session_id_not_overwritten(self, store):
        assert store.create_session(session_id="abc") == "abc"
        assert store.create_session(session_id="abc", title="新标题") == "abc"
        assert store.list_sessions()[0]["title"] == ""

    def test_append_and_read_messages_in_order(self, store):
        session_id = store.create_session()
        store.append_message(session_id, "user", "写引言")
        store.append_message(session_id, "assistant", "好的")

        assert store.get_messages(session_id) == [
            {"role": "user", "content": "写引言"},
            {"role": "assistant", "content": "好的"},
        ]
        assert store.count_messages(session_id) == 2

    def test_get_messages_limit_keeps_latest(self, store):
        session_id = store.create_session()
        for i in range(5):
            store.append_message(session_id, "user", f"m{i}")

        assert [m["content"] for m in store.get_messages(session_id, limit=2)] == [
            "m3",
            "m4",
        ]

    def test_empty_content_messages_filtered(self, store):
        session_id = store.create_session()
        store.append_message(session_id, "assistant", "   ")

        assert store.get_messages(session_id) == []

    def test_writing_context_roundtrip_and_overwrite(self, store):
        session_id = store.create_session()
        assert store.get_writing_context(session_id) is None

        store.save_writing_context(
            session_id,
            {
                "topic": "AI 教育",
                "framework": "引言/方法",
                "ideas": "突出痛点",
                "requirements": "3000 字",
                "sections": [{"title": "引言", "content": "正文"}],
            },
        )
        saved = store.get_writing_context(session_id)
        assert saved["topic"] == "AI 教育"
        assert saved["sections"] == [{"title": "引言", "content": "正文"}]

        # 整体覆盖：未提供的字段回到空值
        store.save_writing_context(session_id, {"topic": "改后"})
        assert store.get_writing_context(session_id)["topic"] == "改后"
        assert store.get_writing_context(session_id)["sections"] == []

    def test_delete_session_cascades(self, store):
        session_id = store.create_session()
        store.append_message(session_id, "user", "hi")
        store.save_writing_context(session_id, {"topic": "t"})

        store.delete_session(session_id)

        assert not store.session_exists(session_id)
        assert store.get_messages(session_id) == []
        assert store.get_writing_context(session_id) is None
        assert (
            store.conn.execute(
                "SELECT COUNT(*) FROM session_messages"
            ).fetchone()[0]
            == 0
        )

    def test_library_reset_keeps_sessions(self, store):
        """论文库 reset 不应清掉写作会话（两者生命周期独立）"""
        session_id = store.create_session()
        store.append_message(session_id, "user", "hi")

        store.reset()

        assert store.session_exists(session_id)
        assert store.count_messages(session_id) == 1


class TestReset:
    def test_reset_clears_all_tables(self, store):
        """回归：reset 不清 SQLite 会让 status 残留 completed，重置后导入被跳过"""
        store.save_document(_doc())
        store.save_parents([
            Chunk(id="p1", text="父块", metadata={"doc_id": "d1"})
        ])
        store.update_ingest_status("d1", "completed")

        store.reset()

        for table in ("documents", "chunks", "content_tags", "parents"):
            remaining = store.conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            assert remaining == 0, f"{table} 仍残留 {remaining} 行"
        assert store.get_ingest_status("d1") is None
