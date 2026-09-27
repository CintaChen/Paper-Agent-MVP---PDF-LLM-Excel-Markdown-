"""PDF 导入任务：后台执行 + 进度事件流

导入一篇论文通常要几十秒到几分钟（Embedding 占大头），同步等待期间前端毫无反馈。
这里把导入放到后台线程执行，用「事件列表 + Condition」暴露进度：
- HTTP 侧可轮询快照（GET /ingest/tasks/{id}）
- WebSocket 侧可消费流式文字（WS /ingest/ws/{id}）

并发约束：Milvus Lite 不支持并发写，因此所有导入任务串行执行，
后来的任务会先上报「排队中」再等待。
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from config.logging import setup_logging

logger = setup_logging(__name__)

MAX_TASKS = 50  # 内存中保留的最近任务数
MAX_EVENTS = 2000  # 单个任务最多保留的事件数
STREAM_TIMEOUT = 15.0  # 等待新事件的超时（秒）

# 串行化导入：Milvus Lite 同时只允许一个进程/写入流
_ingest_lock = threading.Lock()


@dataclass
class IngestEvent:
    seq: int
    stage: str
    percent: int
    message: str
    level: str = "info"

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "stage": self.stage,
            "percent": self.percent,
            "message": self.message,
            "level": self.level,
        }


@dataclass
class IngestTask:
    id: str
    filename: str
    file_path: str
    status: str = "running"  # running | completed | failed | skipped
    stage: str = "pending"
    percent: int = 0
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    events: list[IngestEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._seq = 0
        self.condition = threading.Condition()

    # ------------------------------------------------------------------
    # 事件写入（由导入线程调用）
    # ------------------------------------------------------------------
    def append(self, stage: str, percent: int, message: str, level: str = "info") -> None:
        with self.condition:
            self._seq += 1
            self.stage = stage
            self.percent = max(0, min(int(percent), 100))
            self.events.append(
                IngestEvent(self._seq, stage, self.percent, message, level)
            )
            if len(self.events) > MAX_EVENTS:
                del self.events[: len(self.events) - MAX_EVENTS]
            self.condition.notify_all()

    def finish(self, status: str, result: dict = None, error: str = None) -> None:
        with self.condition:
            self.status = status
            self.result = result
            self.error = error
            self.finished_at = time.time()
            if status == "completed":
                self.stage, self.percent = "completed", 100
            elif status == "skipped":
                self.stage, self.percent = "skipped", 100
            else:
                self.stage = "failed"
            self.condition.notify_all()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    @property
    def is_finished(self) -> bool:
        return self.status in ("completed", "failed", "skipped")

    def snapshot(self, since: int = 0) -> dict:
        with self.condition:
            return {
                "task_id": self.id,
                "filename": self.filename,
                "file_path": self.file_path,
                "status": self.status,
                "stage": self.stage,
                "percent": self.percent,
                "error": self.error,
                "result": self.result,
                "created_at": self.created_at,
                "finished_at": self.finished_at,
                "events": [
                    event.to_dict() for event in self.events if event.seq > since
                ],
            }

    def wait_events(self, since: int, timeout: float = STREAM_TIMEOUT) -> list[IngestEvent]:
        """等待 since 之后的新事件；已结束则立即返回剩余事件"""
        with self.condition:
            if not self.is_finished and self._seq <= since:
                self.condition.wait(timeout)
            return [event for event in self.events if event.seq > since]


class IngestTaskManager:
    """进程内任务表"""

    def __init__(self) -> None:
        self._tasks: dict[str, IngestTask] = {}
        self._lock = threading.Lock()

    def create(self, filename: str, file_path: str) -> IngestTask:
        task = IngestTask(
            id=uuid.uuid4().hex[:16], filename=filename, file_path=file_path
        )
        with self._lock:
            self._tasks[task.id] = task
            if len(self._tasks) > MAX_TASKS:
                ordered = sorted(self._tasks.values(), key=lambda item: item.created_at)
                for stale in ordered[: len(self._tasks) - MAX_TASKS]:
                    self._tasks.pop(stale.id, None)
        return task

    def get(self, task_id: str) -> Optional[IngestTask]:
        return self._tasks.get(task_id)

    def list(self, limit: int = 20) -> list[dict]:
        with self._lock:
            ordered = sorted(
                self._tasks.values(), key=lambda item: item.created_at, reverse=True
            )
            return [task.snapshot() for task in ordered[:limit]]

    def run(self, task: IngestTask, runner: Callable[[Callable], object]) -> None:
        """在后台线程执行 runner(progress_callback)"""
        thread = threading.Thread(
            target=self._execute,
            args=(task, runner),
            daemon=True,
            name=f"ingest-{task.id}",
        )
        thread.start()

    @staticmethod
    def _execute(task: IngestTask, runner: Callable[[Callable], object]) -> None:
        if not _ingest_lock.acquire(blocking=False):
            task.append("queued", 0, "已有导入任务在执行，排队等待…")
            _ingest_lock.acquire()

        try:
            def progress(stage: str, percent: int, message: str) -> None:
                task.append(stage, percent, message)

            doc = runner(progress)

            if doc is None:
                # 断点续传：该论文此前已导入完成
                task.append("skipped", 100, "该文件已导入完成，跳过")
                task.finish("skipped", result={"skipped": True})
            else:
                task.finish(
                    "completed",
                    result={
                        "id": doc.id,
                        "title": doc.title,
                        "total_pages": doc.total_pages,
                        "chunk_count": len(doc.chunks),
                    },
                )
        except Exception as e:  # noqa: BLE001 - 失败要写回任务而非抛到线程外
            logger.exception(f"导入任务失败: {task.filename}")
            task.append("failed", task.percent, f"导入失败：{e}", level="error")
            task.finish("failed", error=str(e))
        finally:
            _ingest_lock.release()


manager = IngestTaskManager()
