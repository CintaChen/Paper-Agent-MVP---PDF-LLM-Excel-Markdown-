"""测试主 Agent 路由（HTTP + WebSocket）

只挂载 agent 路由到一个最小 FastAPI 应用，避免 api.app 导入时
其他路由在模块级构造 Milvus / BM25 / Embedding 等重量级依赖。
"""
import json

import pytest
from fastapi import FastAPI

from agent.orchestrator import OrchestratorResult, ToolStep
from api.routes import agent as agent_route

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


class FakeOrchestrator:
    """记录调用参数并返回预设事件的假 Orchestrator"""

    def __init__(self, events):
        self._events = events
        self.calls = []

    def _record(self, message, context, history, max_iterations):
        self.calls.append(
            {
                "message": message,
                "context": context,
                "history": history,
                "max_iterations": max_iterations,
            }
        )

    def run(self, message, context=None, history=None, max_iterations=None):
        self._record(message, context, history, max_iterations)
        result = None
        for event in self._events:
            if event["type"] == "final":
                result = event["result"]
        return result

    def run_stream(self, message, context=None, history=None, max_iterations=None):
        self._record(message, context, history, max_iterations)
        yield from self._events


def _final_steps():
    return [
        ToolStep(
            iteration=1,
            tool="draft_expand",
            arguments={"section_title": "引言"},
            output="生成的正文",
        )
    ]


def _events():
    result = OrchestratorResult(
        content="最终正文",
        steps=_final_steps(),
        iterations=2,
        stopped_reason="completed",
    )
    return [
        {
            "type": "tool_call",
            "iteration": 1,
            "tool": "draft_expand",
            "arguments": {"section_title": "引言"},
        },
        {
            "type": "tool_result",
            "iteration": 1,
            "tool": "draft_expand",
            "output": "生成的正文",
        },
        {"type": "final", "result": result},
    ]


class FakeStore:
    """内存版会话存储：避免测试写真实 SQLite"""

    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: dict[str, list] = {}
        self.contexts: dict[str, dict] = {}
        self._seq = 0

    def create_session(self, session_id=None, title=""):
        self._seq += 1
        session_id = session_id or f"s{self._seq}"
        self.sessions.setdefault(session_id, {"title": title})
        self.messages.setdefault(session_id, [])
        return session_id

    def session_exists(self, session_id):
        return session_id in self.sessions

    def get_messages(self, session_id, limit=None):
        messages = self.messages.get(session_id, [])
        return messages[-limit:] if limit else list(messages)

    def append_message(self, session_id, role, content):
        self.messages.setdefault(session_id, []).append(
            {"role": role, "content": content}
        )

    def save_writing_context(self, session_id, data):
        self.contexts[session_id] = dict(data)

    def get_writing_context(self, session_id):
        return self.contexts.get(session_id)

    def count_messages(self, session_id):
        return len(self.messages.get(session_id, []))

    def list_sessions(self, limit=50):
        return [
            {
                "id": session_id,
                "title": meta.get("title", ""),
                "message_count": self.count_messages(session_id),
            }
            for session_id, meta in list(self.sessions.items())[:limit]
        ]

    def delete_session(self, session_id):
        self.sessions.pop(session_id, None)
        self.messages.pop(session_id, None)
        self.contexts.pop(session_id, None)


@pytest.fixture
def store():
    return FakeStore()


@pytest.fixture
def client(monkeypatch, store):
    app = FastAPI()
    app.include_router(agent_route.router, prefix="/api/v1/agent")
    monkeypatch.setattr(agent_route, "_orchestrator", FakeOrchestrator(_events()))
    monkeypatch.setattr(agent_route, "_metadata_store", store)
    return TestClient(app)


class TestAgentChatHttp:
    def test_chat_returns_content_and_steps(self, client):
        response = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "请扩写引言",
                "context": {
                    "topic": "AI 教育",
                    "framework": "引言/方法/结论",
                    "ideas": "突出痛点",
                    "sections": [{"title": "相关工作", "content": "已有工作……"}],
                },
                "history": [{"role": "user", "content": "你好"}],
                "max_iterations": 3,
            },
        )
        assert response.status_code == 200
        body = response.json()

        assert body["status"] == "success"
        assert body["data"]["content"] == "最终正文"
        assert body["data"]["iterations"] == 2
        assert body["data"]["stopped_reason"] == "completed"
        assert body["data"]["steps"][0]["tool"] == "draft_expand"

    def test_context_converted_to_writing_context(self, client):
        client.post(
            "/api/v1/agent/chat",
            json={
                "message": "写引言",
                "context": {"topic": "AI 教育", "ideas": "突出痛点"},
            },
        )
        orchestrator = agent_route._orchestrator
        context = orchestrator.calls[0]["context"]

        assert context.topic == "AI 教育"
        assert context.ideas == "突出痛点"

    def test_history_and_max_iterations_forwarded(self, client):
        client.post(
            "/api/v1/agent/chat",
            json={
                "message": "写引言",
                "history": [{"role": "user", "content": "先热身"}],
                "max_iterations": 3,
            },
        )
        call = agent_route._orchestrator.calls[0]
        assert call["history"] == [{"role": "user", "content": "先热身"}]
        assert call["max_iterations"] == 3
        assert call["context"] is None

    def test_empty_message_rejected(self, client):
        response = client.post("/api/v1/agent/chat", json={"message": ""})
        assert response.status_code == 422


class TestAgentChatWebSocket:
    def test_stream_emits_tool_events_then_done(self, client):
        with client.websocket_connect("/api/v1/agent/chat/ws") as ws:
            ws.send_text(json.dumps({"message": "请扩写引言"}))

            received = []
            while True:
                event = ws.receive_json()
                received.append(event)
                if event["type"] == "done":
                    break

        types = [e["type"] for e in received]
        assert types[0] == "tool_call"
        assert "tool_result" in types
        assert types[-1] == "done"

        tokens = "".join(e["content"] for e in received if e["type"] == "token")
        assert tokens == "最终正文"

        done = received[-1]
        assert done["content"] == "最终正文"
        assert done["stopped_reason"] == "completed"
        assert done["steps"][0]["tool"] == "draft_expand"

    def test_bad_payload_reports_error_without_closing(self, client):
        with client.websocket_connect("/api/v1/agent/chat/ws") as ws:
            ws.send_text(json.dumps({"message": ""}))  # 校验失败
            error = ws.receive_json()
            assert error["type"] == "error"

            # 连接仍可用：再发一条合法消息
            ws.send_text(json.dumps({"message": "继续"}))
            first = ws.receive_json()
            assert first["type"] == "tool_call"

    def test_plain_text_message_accepted(self, client):
        with client.websocket_connect("/api/v1/agent/chat/ws") as ws:
            ws.send_text("裸文本消息")
            assert ws.receive_json()["type"] == "tool_call"
            assert agent_route._orchestrator.calls[0]["message"] == "裸文本消息"


class TestSessionPersistence:
    def test_new_session_returned_and_turn_persisted(self, client, store):
        response = client.post("/api/v1/agent/chat", json={"message": "写引言"})
        session_id = response.json()["data"]["session_id"]

        assert session_id
        assert store.session_exists(session_id)
        assert store.get_messages(session_id) == [
            {"role": "user", "content": "写引言"},
            {"role": "assistant", "content": "最终正文"},
        ]

    def test_structured_context_is_persisted(self, client, store):
        response = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "写引言",
                "context": {
                    "topic": "AI 教育",
                    "framework": "引言/方法",
                    "ideas": "突出痛点",
                },
            },
        )
        session_id = response.json()["data"]["session_id"]
        saved = store.get_writing_context(session_id)

        assert saved["topic"] == "AI 教育"
        assert saved["framework"] == "引言/方法"
        assert saved["ideas"] == "突出痛点"

    def test_resume_session_restores_history_and_context(self, client, store):
        first = client.post(
            "/api/v1/agent/chat",
            json={
                "message": "写引言",
                "context": {"topic": "AI 教育", "ideas": "突出痛点"},
            },
        )
        session_id = first.json()["data"]["session_id"]

        client.post(
            "/api/v1/agent/chat",
            json={"message": "继续", "session_id": session_id},
        )

        call = agent_route._orchestrator.calls[-1]
        assert call["history"] == [
            {"role": "user", "content": "写引言"},
            {"role": "assistant", "content": "最终正文"},
        ]
        # 上下文集自库中，无需客户端再传一遍
        assert call["context"].topic == "AI 教育"
        assert call["context"].ideas == "突出痛点"

    def test_unknown_session_returns_404(self, client):
        response = client.post(
            "/api/v1/agent/chat", json={"message": "x", "session_id": "nope"}
        )
        assert response.status_code == 404

    def test_resume_does_not_duplicate_history(self, client, store):
        first = client.post("/api/v1/agent/chat", json={"message": "一"})
        session_id = first.json()["data"]["session_id"]

        client.post(
            "/api/v1/agent/chat",
            json={"message": "二", "session_id": session_id},
        )

        assert [m["content"] for m in store.get_messages(session_id)] == [
            "一",
            "最终正文",
            "二",
            "最终正文",
        ]

    def test_websocket_returns_session_id_and_persists(self, client, store):
        with client.websocket_connect("/api/v1/agent/chat/ws") as ws:
            ws.send_text(json.dumps({"message": "写引言"}))
            while True:
                event = ws.receive_json()
                if event["type"] == "done":
                    break

        session_id = event["session_id"]
        assert store.session_exists(session_id)
        assert store.get_messages(session_id)[0] == {
            "role": "user",
            "content": "写引言",
        }
        assert store.get_messages(session_id)[1] == {
            "role": "assistant",
            "content": "最终正文",
        }


class TestSessionManagement:
    def test_list_sessions(self, client):
        client.post("/api/v1/agent/chat", json={"message": "写引言"})

        body = client.get("/api/v1/agent/sessions").json()

        assert body["status"] == "success"
        assert body["data"]["total"] == 1
        session = body["data"]["sessions"][0]
        assert session["title"] == "写引言"
        assert session["message_count"] == 2

    def test_list_sessions_respects_limit(self, client):
        for i in range(3):
            client.post("/api/v1/agent/chat", json={"message": f"m{i}"})

        body = client.get(
            "/api/v1/agent/sessions", params={"limit": 2}
        ).json()

        assert len(body["data"]["sessions"]) == 2

    def test_get_session_detail(self, client):
        session_id = client.post(
            "/api/v1/agent/chat",
            json={"message": "写引言", "context": {"topic": "AI 教育"}},
        ).json()["data"]["session_id"]

        data = client.get(f"/api/v1/agent/sessions/{session_id}").json()["data"]

        assert data["session_id"] == session_id
        assert data["message_count"] == 2
        assert [m["content"] for m in data["messages"]] == [
            "写引言",
            "最终正文",
        ]
        assert data["context"]["topic"] == "AI 教育"

    def test_get_unknown_session_404(self, client):
        assert client.get("/api/v1/agent/sessions/nope").status_code == 404

    def test_delete_session(self, client, store):
        session_id = client.post(
            "/api/v1/agent/chat", json={"message": "写引言"}
        ).json()["data"]["session_id"]

        response = client.delete(f"/api/v1/agent/sessions/{session_id}")

        assert response.status_code == 200
        assert not store.session_exists(session_id)
        assert client.get("/api/v1/agent/sessions").json()["data"]["total"] == 0

    def test_delete_unknown_session_404(self, client):
        assert (
            client.delete("/api/v1/agent/sessions/nope").status_code == 404
        )

    def test_deleted_session_cannot_be_resumed(self, client):
        session_id = client.post(
            "/api/v1/agent/chat", json={"message": "写引言"}
        ).json()["data"]["session_id"]
        client.delete(f"/api/v1/agent/sessions/{session_id}")

        response = client.post(
            "/api/v1/agent/chat",
            json={"message": "继续", "session_id": session_id},
        )

        assert response.status_code == 404
