"""WebSocket 路由"""
import json
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_retriever = None
_llm_client = None


def get_retriever():
    """惰性单例：导入本模块不连接 Milvus / BM25"""
    global _retriever
    if _retriever is None:
        from rag.retrieve import HybridRetriever

        _retriever = HybridRetriever()
    return _retriever


def get_llm_client():
    """惰性单例：导入本模块不初始化 LLM"""
    global _llm_client
    if _llm_client is None:
        from core.llm import LLMClient

        _llm_client = LLMClient()
    return _llm_client


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """WebSocket 聊天（流式输出）"""
    await websocket.accept()
    session_id = f"session_{int(time.time())}"

    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            message = json.loads(data)
            user_message = message.get("message", "")

            # 检索相关文档
            results = get_retriever().retrieve(user_message, top_k=5)
            context = "\n\n".join(r.chunk.text[:500] for r in results)

            # 构建提示词
            system_prompt = """你是一名专业的学术论文写作助手。
根据用户提供的文献内容回答问题。"""

            user_prompt = f"""参考内容：
{context}

用户问题：{user_message}"""

            # 流式调用 LLM
            full_response = ""
            for token in get_llm_client().chat_stream(system_prompt, user_prompt):
                full_response += token
                await websocket.send_json({
                    "type": "token",
                    "content": token,
                    "done": False,
                })

            # 发送完成信号
            await websocket.send_json({
                "type": "done",
                "session_id": session_id,
                "duration_ms": 0,
            })

    except WebSocketDisconnect:
        pass
