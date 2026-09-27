"""导入路由

- POST /file              同步导入服务器本地文件
- POST /directory         同步批量导入目录
- POST /upload            异步上传导入：立即返回 task_id
- GET  /tasks             最近导入任务列表
- GET  /tasks/{task_id}   导入任务快照（轮询兜底）
- WS   /ws/{task_id}      订阅导入进度：进度条 + 流式文字
"""
import asyncio
import os
import time
from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from config.logging import setup_logging
from config.settings import settings
from api.ingest_tasks import STREAM_TIMEOUT, manager
from api.schemas.request import IngestDirectoryRequest, IngestFileRequest

logger = setup_logging(__name__)
router = APIRouter()

_pipeline = None


def get_pipeline():
    """惰性单例：导入本模块不连接 Milvus / 加载索引"""
    global _pipeline
    if _pipeline is None:
        from rag.ingest import IngestPipeline

        _pipeline = IngestPipeline()
    return _pipeline


@router.post("/file")
async def ingest_file(request: IngestFileRequest):
    """导入单个 PDF 文件"""
    start = time.time()
    try:
        doc = get_pipeline().ingest(request.file_path)
        # ingest() 对已完成的论文返回 None（断点续传），此处不能直接取属性
        if doc is None:
            return {
                "status": "success",
                "data": {"file_path": request.file_path, "skipped": True},
                "message": "该文件已导入完成，已跳过",
                "duration_ms": int((time.time() - start) * 1000),
            }
        return {
            "status": "success",
            "data": {
                "id": doc.id,
                "title": doc.title,
                "total_pages": doc.total_pages,
                "chunk_count": len(doc.chunks),
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/directory")
async def ingest_directory(request: IngestDirectoryRequest):
    """批量导入目录"""
    start = time.time()
    try:
        docs = get_pipeline().ingest_directory(request.dir_path)
        return {
            "status": "success",
            "data": {
                "total_files": len(docs),
                "success_count": len(docs),
                "failed_count": 0,
                "documents": [
                    {"id": d.id, "title": d.title, "status": "success"}
                    for d in docs
                ],
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def ingest_upload(file: UploadFile = File(...)):
    """上传 PDF 并**异步**导入，立即返回 task_id

    导入耗时较长（Embedding 占大头），放到后台线程执行；
    进度通过 `WS /api/v1/ingest/ws/{task_id}` 流式推送，
    也可用 `GET /api/v1/ingest/tasks/{task_id}` 轮询。
    """
    filename = os.path.basename(file.filename or "")
    if not filename:
        raise HTTPException(status_code=400, detail="缺少文件名")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    upload_dir = Path(settings.input_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = upload_dir / filename

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    upload_path.write_bytes(content)

    task = manager.create(filename, str(upload_path))
    # 线程内构造流水线：避免在事件循环线程里连接 Milvus
    manager.run(
        task,
        lambda progress: get_pipeline().ingest(str(upload_path), progress=progress),
    )

    return {
        "status": "success",
        "data": {
            "task_id": task.id,
            "filename": filename,
            "file_size": len(content),
            "file_path": str(upload_path),
        },
    }


@router.get("/tasks")
async def list_ingest_tasks(limit: int = 20):
    """最近的导入任务"""
    limit = max(1, min(limit, 100))
    return {"status": "success", "data": {"tasks": manager.list(limit)}}


@router.get("/tasks/{task_id}")
async def get_ingest_task(task_id: str):
    """导入任务快照（含已产生的事件）"""
    task = manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"任务不存在: {task_id}")
    return {"status": "success", "data": task.snapshot()}


@router.websocket("/ws/{task_id}")
async def ingest_progress_ws(websocket: WebSocket, task_id: str):
    """导入进度事件流

    服务端 → 客户端：
    - {"type": "progress", seq, stage, percent, message, level}
    - {"type": "done", status, percent, result, error, task_id, filename}
    """
    task = manager.get(task_id)
    if task is None:
        await websocket.close(code=4404, reason="任务不存在")
        return

    await websocket.accept()
    since = 0
    try:
        while True:
            events = await asyncio.to_thread(
                task.wait_events, since, STREAM_TIMEOUT
            )
            for event in events:
                since = event.seq
                await websocket.send_json({"type": "progress", **event.to_dict()})

            if task.is_finished:
                # 收尾：补齐剩余事件后发送 done
                for event in task.snapshot(since=since)["events"]:
                    since = event["seq"]
                    await websocket.send_json({"type": "progress", **event})

                final = task.snapshot()
                final.pop("events", None)
                await websocket.send_json({"type": "done", **final})
                break
    except WebSocketDisconnect:
        logger.info(f"导入进度订阅断开: {task_id}")
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001 - 连接可能已关闭
            pass
