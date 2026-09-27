"""回归测试：标签路由顺序、导入接口对已完成文件（doc=None）的处理

只挂载目标路由到最小 FastAPI 应用，避免 api.app 导入时构造重量级依赖。
"""
import pytest
from fastapi import FastAPI

from core.document import ContentTag, Document
from storage.metadata_store import SQLiteStore

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture
def tags_client(tmp_path, monkeypatch):
    """挂载 tags 路由，并把存储替换为临时 SQLite

    注意：不为请求线程预建连接——sqlite3 默认禁止跨线程复用连接，
    而 TestClient 在独立线程运行事件循环。这里改为「每次调用新建连接」，
    所有连接指向同一个临时文件（已提交的写入对其他连接可见）。
    """
    from api.routes import tags as tags_route

    db_path = tmp_path / "tags.db"

    def _new_store():
        return SQLiteStore(db_path)

    monkeypatch.setattr(tags_route, "get_store", _new_store)

    app = FastAPI()
    app.include_router(tags_route.router, prefix="/api/v2/tags")
    client = TestClient(app)

    seed = SQLiteStore(db_path)
    yield client, seed
    seed.close()


class TestTagRouteOrdering:
    def test_stats_reachable(self, tags_client):
        """回归：/stats 曾被 /{doc_id} 抢先匹配，返回 404"""
        client, seed = tags_client
        seed.save_document(
            Document(
                id="d1",
                title="论文",
                content_tags=[ContentTag(tag_type="domain", value="人工智能")],
            )
        )

        response = client.get("/api/v2/tags/stats")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["domains"][0]["value"] == "人工智能"

    def test_search_reachable(self, tags_client):
        """回归：/search 同样被 /{doc_id} 抢占"""
        client, seed = tags_client
        seed.save_document(
            Document(
                id="d1",
                title="论文",
                content_tags=[ContentTag(tag_type="domain", value="人工智能")],
            )
        )

        response = client.get(
            "/api/v2/tags/search", params={"tag_type": "domain", "value": "人工智能"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["data"]["total"] == 1
        assert body["data"]["results"][0]["doc_id"] == "d1"

    def test_doc_id_route_still_works(self, tags_client):
        client, _ = tags_client
        response = client.get("/api/v2/tags/not-exist")
        assert response.status_code == 404
        assert response.json()["detail"] == "文档不存在"


class FakePipeline:
    def __init__(self, result):
        self._result = result
        self.calls = []

    def ingest(self, file_path):
        self.calls.append(file_path)
        return self._result


@pytest.fixture
def ingest_app_factory(monkeypatch):
    from api.routes import ingest as ingest_route

    def _build(result):
        app = FastAPI()
        app.include_router(ingest_route.router, prefix="/api/v1/ingest")
        pipeline = FakePipeline(result)
        monkeypatch.setattr(ingest_route, "get_pipeline", lambda: pipeline)
        return TestClient(app), pipeline

    return _build


class TestIngestSkipsCompletedFile:
    def test_file_already_ingested_returns_skipped(self, ingest_app_factory):
        """回归：ingest() 返回 None 时直接取 doc.id 会 500"""
        client, _ = ingest_app_factory(None)

        response = client.post(
            "/api/v1/ingest/file", json={"file_path": "input/papers/a.pdf"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert body["data"]["skipped"] is True

    def test_file_success_path(self, ingest_app_factory):
        doc = Document(id="d1", title="论文", total_pages=3)
        client, pipeline = ingest_app_factory(doc)

        response = client.post(
            "/api/v1/ingest/file", json={"file_path": "input/papers/a.pdf"}
        )

        assert response.status_code == 200
        assert response.json()["data"]["id"] == "d1"
        assert pipeline.calls == ["input/papers/a.pdf"]
