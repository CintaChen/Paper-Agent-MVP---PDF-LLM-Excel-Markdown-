"""主 Agent 路由（工具化 Orchestrator）

- POST   /api/v1/agent/chat            同步：一次返回完整结果 + 工具轨迹
- WS     /api/v1/agent/chat/ws         流式：先推送工具调用事件，再流式推送最终正文
- GET    /api/v1/agent/sessions        列出写作会话（按最近活跃排序）
- GET    /api/v1/agent/sessions/{id}   会话详情：消息 + 写作上下文
- DELETE /api/v1/agent/sessions/{id}   删除会话及其消息与上下文

Orchestrator 采用惰性单例：导入本模块不会连接 LLM / Milvus / BM25，
只有真正收到请求时才初始化，且各请求共享同一份惰性构建的检索器。
"""
import json
import time
from typing import Iterator, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from config.logging import setup_logging
from api.schemas.request import AgentChatRequest

logger = setup_logging(__name__)
router = APIRouter()

_orchestrator = None
_metadata_store = None

# 每轮最多回灌多少条历史消息，避免长会话撑爆上下文
MAX_HISTORY_MESSAGES = 20


def get_orchestrator():
    """惰性单例：避免导入即初始化 LLM / 工具依赖"""
    global _orchestrator
    if _orchestrator is None:
        from agent.orchestrator import Orchestrator

        _orchestrator = Orchestrator()
    return _orchestrator


def get_metadata_store():
    """惰性单例：避免导入即打开 SQLite"""
    global _metadata_store
    if _metadata_store is None:
        from storage.metadata_store import SQLiteStore

        _metadata_store = SQLiteStore()
    return _metadata_store


def _resolve_session(store, request):
    """确定本次请求的会话、历史消息与写作上下文

    - 传入 session_id：校验存在性，并从库中恢复历史与写作上下文
    - 未传入：新建会话，把请求携带的 history / 结构化 context 落库

    返回 (session_id, history, context)
    """
    from agent.context import WritingContext

    if request.session_id:
        if not store.session_exists(request.session_id):
            raise LookupError(f"会话不存在: {request.session_id}")
        session_id = request.session_id
        history = (
            store.get_messages(session_id, limit=MAX_HISTORY_MESSAGES) or None
        )
        context = WritingContext.from_dict(
            store.get_writing_context(session_id)
        )
    else:
        session_id = store.create_session(title=request.message)
        history = request.history_messages()
        for message in history or []:
            store.append_message(
                session_id, message["role"], message["content"]
            )
        context = WritingContext()

    # 请求显式携带的上下文优先，并持久化，便于下次只凭 session_id 续写
    if request.context is not None:
        context = request.context.to_context()
        store.save_writing_context(session_id, context.to_dict())
    elif (request.context_text or "").strip():
        context = request.context_text

    if isinstance(context, WritingContext) and context.is_empty:
        context = None

    return session_id, history, context


def _persist_turn(
    store, session_id: str, user_message: str, assistant_content: str
) -> None:
    """把本轮问答落库（只存 user / assistant，避免 system 重复注入）"""
    store.append_message(session_id, "user", user_message)
    store.append_message(session_id, "assistant", assistant_content or "")


def _serialize_steps(steps) -> list[dict]:
    """工具轨迹序列化"""
    return [
        {
            "iteration": step.iteration,
            "tool": step.tool,
            "arguments": step.arguments,
            "output": step.output,
        }
        for step in steps
    ]


def _iter_text_chunks(text: str, size: int = 24) -> Iterator[str]:
    """把整段正文切成小块，让前端获得流式体验"""
    for i in range(0, len(text), size):
        yield text[i : i + size]


def _parse_request(raw: str) -> AgentChatRequest:
    """解析 WebSocket 文本帧：支持 JSON 对象或裸文本消息"""
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        payload = {"message": raw}

    if isinstance(payload, str):
        payload = {"message": payload}
    if not isinstance(payload, dict):
        raise ValueError("消息必须是 JSON 对象或纯文本")
    return AgentChatRequest(**payload)


@router.post("/chat")
async def agent_chat(request: AgentChatRequest):
    """主 Agent 同步对话：返回正文、工具轨迹与迭代信息"""
    start = time.time()
    try:
        store = get_metadata_store()
        session_id, history, context = _resolve_session(store, request)

        result = get_orchestrator().run(
            request.message,
            context=context,
            history=history,
            max_iterations=request.max_iterations,
        )

        _persist_turn(store, session_id, request.message, result.content)

        return {
            "status": "success",
            "data": {
                "session_id": session_id,
                "content": result.content,
                "iterations": result.iterations,
                "stopped_reason": result.stopped_reason,
                "steps": _serialize_steps(result.steps),
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001 - 统一转为 HTTP 错误
        logger.exception(f"主 Agent 执行失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/chat/ws")
async def agent_chat_ws(websocket: WebSocket):
    """主 Agent 流式对话

    事件协议（服务端 → 客户端）：
    - {"type": "tool_call",   iteration, tool, arguments}
    - {"type": "tool_result", iteration, tool, output}
    - {"type": "token",       content, done: false}
    - {"type": "done",        content, iterations, stopped_reason, steps, duration_ms}
    - {"type": "error",       message}
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                request = _parse_request(raw)
            except Exception as e:  # noqa: BLE001 - 参数错误不应断开连接
                await websocket.send_json(
                    {"type": "error", "message": f"请求格式错误: {e}"}
                )
                continue

            started = time.time()
            try:
                store = get_metadata_store()
                session_id, history, context = _resolve_session(store, request)
                orchestrator = get_orchestrator()
                final_result = None

                for event in orchestrator.run_stream(
                    request.message,
                    context=context,
                    history=history,
                    max_iterations=request.max_iterations,
                ):
                    if event["type"] == "tool_call":
                        await websocket.send_json(
                            {
                                "type": "tool_call",
                                "iteration": event["iteration"],
                                "tool": event["tool"],
                                "arguments": event["arguments"],
                            }
                        )
                    elif event["type"] == "tool_result":
                        await websocket.send_json(
                            {
                                "type": "tool_result",
                                "iteration": event["iteration"],
                                "tool": event["tool"],
                                "output": event["output"],
                            }
                        )
                    else:
                        final_result = event["result"]

                content = final_result.content if final_result else ""
                for chunk in _iter_text_chunks(content):
                    await websocket.send_json(
                        {"type": "token", "content": chunk, "done": False}
                    )

                _persist_turn(store, session_id, request.message, content)

                await websocket.send_json(
                    {
                        "type": "done",
                        "session_id": session_id,
                        "content": content,
                        "iterations": final_result.iterations if final_result else 0,
                        "stopped_reason": (
                            final_result.stopped_reason
                            if final_result
                            else "completed"
                        ),
                        "steps": (
                            _serialize_steps(final_result.steps)
                            if final_result
                            else []
                        ),
                        "duration_ms": int((time.time() - started) * 1000),
                    }
                )
            except Exception as e:  # noqa: BLE001 - 单次请求失败不断开连接
                logger.exception(f"主 Agent 流式执行失败: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info("主 Agent WebSocket 连接关闭")


# ======================================================================
# 会话管理
# ======================================================================

@router.get("/sessions")
async def list_sessions(limit: int = 50):
    """列出写作会话（按最近活跃排序）"""
    limit = max(1, min(limit, 200))
    try:
        sessions = get_metadata_store().list_sessions(limit=limit)
        return {
            "status": "success",
            "data": {"total": len(sessions), "sessions": sessions},
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f"列出会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, message_limit: int = 200):
    """会话详情：消息 + 写作上下文

    前端刷新页面后可据此恢复整个写作现场，无需重新逐轮问答。
    """
    store = get_metadata_store()
    if not store.session_exists(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    message_limit = max(1, min(message_limit, 1000))
    try:
        return {
            "status": "success",
            "data": {
                "session_id": session_id,
                "message_count": store.count_messages(session_id),
                "messages": store.get_messages(
                    session_id, limit=message_limit
                ),
                "context": store.get_writing_context(session_id) or {},
            },
        }
    except Exception as e:  # noqa: BLE001
        logger.exception(f"读取会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """删除会话及其消息、写作上下文"""
    store = get_metadata_store()
    if not store.session_exists(session_id):
        raise HTTPException(status_code=404, detail=f"会话不存在: {session_id}")

    try:
        store.delete_session(session_id)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "status": "success",
        "message": "会话已删除",
        "data": {"session_id": session_id},
    }
