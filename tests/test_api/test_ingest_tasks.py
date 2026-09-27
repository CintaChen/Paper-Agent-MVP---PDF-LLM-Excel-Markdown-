"""测试导入任务：进度事件、后台执行、轮询与 WebSocket 流"""
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from api.ingest_tasks import IngestTaskManager, manager
from api.routes import ingest as ingest_route
from config.settings import settings

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


class FakePipeline:
    """记录调用并上报进度；skipped=True 时模拟断点续传跳过"""

    def __init__(self, skipped: bool = False, fail: bool = False):
        self.skipped = skipped
        self.fail = fail
        self.calls = []

    def ingest(self, file_path, force=False, progress=None):
        self.calls.append({"file_path": file_path, "force": force})
        if progress:
            progress("reading", 10, "解析完成")
            progress("embedding", 60, "向量化 1/2")
        if self.fail:
            raise RuntimeError("embedding 服务不可用")
        if self.skipped:
            if progress:
                progress("skipped", 100, "该文件已导入完成，跳过")
            return None
        if progress:
            progress("completed", 100, "导入完成")
        return SimpleNamespace(id="d1", title="测试论文", total_pages=3, chunks=[1, 2, 3])


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(ingest_route.router, prefix="/api/v1/ingest")
    return app


def _wait_finished(client: TestClient, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snapshot = client.get(f"/api/v1/ingest/tasks/{task_id}").json()["data"]
        if snapshot["status"] != "running":
            return snapshot
        time.sleep(0.05)
    raise AssertionError(f"任务 {task_id} 超时未结束")


class TestTaskModel:
    def test_events_carry_increasing_seq_and_percent(self):
        task = IngestTaskManager().create("a.pdf", "/tmp/a.pdf")
        task.append("reading", 5, "开始")
        task.append("reading", 15, "解析完成")

        snapshot = task.snapshot()
        assert [event["seq"] for event in snapshot["events"]] == [1, 2]
        assert snapshot["percent"] == 15
        assert snapshot["stage"] == "reading"
        assert snapshot["status"] == "running"

    def test_snapshot_since_filters_old_events(self):
        task = IngestTaskManager().create("a.pdf", "/tmp/a.pdf")
        task.append("reading", 5, "一")
        task.append("reading", 15, "二")

        assert [e["message"] for e in task.snapshot(since=1)["events"]] == ["二"]

    def test_finish_completed_sets_percent_100(self):
        task = IngestTaskManager().create("a.pdf", "/tmp/a.pdf")
        task.finish("completed", result={"title": "T"})

        snapshot = task.snapshot()
        assert snapshot["status"] == "completed"
        assert snapshot["percent"] == 100
        assert snapshot["result"] == {"title": "T"}
        assert snapshot["finished_at"] is not None

    def test_wait_events_returns_immediately_after_finish(self):
        task = IngestTaskManager().create("a.pdf", "/tmp/a.pdf")
        task.append("reading", 5, "一")
        task.finish("completed")

        # 已结束：不再等待，直接返回剩余事件
        started = time.time()
        events = task.wait_events(since=0, timeout=5.0)
        assert time.time() - started < 1.0
        assert len(events) == 1


class TestTaskExecution:
    def test_success_records_result(self):
        def runner(progress):
            progress("reading", 20, "解析中")
            return SimpleNamespace(id="x", title="标题", total_pages=1, chunks=[1])

        task = manager.create("ok.pdf", "/tmp/ok.pdf")
        manager.run(task, runner)
        snapshot = _wait_task(manager, task.id)

        assert snapshot["status"] == "completed"
        assert snapshot["result"]["title"] == "标题"
        assert snapshot["percent"] == 100

    def test_failure_is_captured_not_raised(self):
        def runner(progress):
            progress("embedding", 30, "向量化…")
            raise RuntimeError("Ollama 未启动")

        task = manager.create("bad.pdf", "/tmp/bad.pdf")
        manager.run(task, runner)
        snapshot = _wait_task(manager, task.id)

        assert snapshot["status"] == "failed"
        assert "Ollama 未启动" in snapshot["error"]
        assert any(event["level"] == "error" for event in snapshot["events"])

    def test_none_result_marks_skipped(self):
        task = manager.create("dup.pdf", "/tmp/dup.pdf")
        manager.run(task, lambda progress: None)
        snapshot = _wait_task(manager, task.id)

        assert snapshot["status"] == "skipped"


def _wait_task(mgr: IngestTaskManager, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        task = mgr.get(task_id)
        if task and task.is_finished:
            return task.snapshot()
        time.sleep(0.02)
    raise AssertionError(f"任务 {task_id} 超时未结束")


class TestUploadRoute:
    @pytest.fixture
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "input_dir", tmp_path)
        monkeypatch.setattr(ingest_route, "_pipeline", FakePipeline())
        return TestClient(_app())

    def test_upload_returns_task_id_and_completes(self, client):
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("paper.pdf", b"%PDF-1.4 fake", "application/pdf")},
        )
        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["task_id"]
        assert payload["filename"] == "paper.pdf"

        snapshot = _wait_finished(client, payload["task_id"])
        assert snapshot["status"] == "completed"
        assert snapshot["result"]["title"] == "测试论文"
        assert [e["stage"] for e in snapshot["events"]][:2] == ["reading", "embedding"]

    def test_upload_rejects_non_pdf(self, client):
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400

    def test_upload_rejects_empty_file(self, client):
        response = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("empty.pdf", b"", "application/pdf")},
        )
        assert response.status_code == 400

    def test_unknown_task_returns_404(self, client):
        assert client.get("/api/v1/ingest/tasks/nope").status_code == 404

    def test_failed_import_reported_in_snapshot(self, tmp_path, monkeypatch):
        monkeypatch.setattr(settings, "input_dir", tmp_path)
        monkeypatch.setattr(ingest_route, "_pipeline", FakePipeline(fail=True))
        client = TestClient(_app())

        task_id = client.post(
            "/api/v1/ingest/upload",
            files={"file": ("bad.pdf", b"%PDF-1.4", "application/pdf")},
        ).json()["data"]["task_id"]

        snapshot = _wait_finished(client, task_id)
        assert snapshot["status"] == "failed"
        assert "embedding 服务不可用" in snapshot["error"]


class TestProgressWebSocket:
    def test_streams_progress_then_done(self):
        def runner(progress):
            progress("reading", 10, "解析中")
            progress("embedding", 55, "向量化 1/2")
            return SimpleNamespace(id="d1", title="标题", total_pages=2, chunks=[1])

        task = manager.create("ws.pdf", "/tmp/ws.pdf")
        manager.run(task, runner)

        with TestClient(_app()).websocket_connect(
            f"/api/v1/ingest/ws/{task.id}"
        ) as websocket:
            received = []
            while True:
                event = websocket.receive_json()
                received.append(event)
                if event["type"] == "done":
                    break

        types = [event["type"] for event in received]
        assert types[:2] == ["progress", "progress"]
        assert types[-1] == "done"

        assert received[0]["stage"] == "reading"
        assert received[1]["percent"] == 55

        done = received[-1]
        assert done["status"] == "completed"
        assert done["result"]["title"] == "标题"

    def test_unknown_task_closes_connection(self):
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with TestClient(_app()).websocket_connect(
                "/api/v1/ingest/ws/missing"
            ) as websocket:
                websocket.receive_json()
