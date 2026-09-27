"""Embedding 服务封装

针对本地 Ollama 做了两点加固，坑的背景如下：

1. 为什么不再用 OpenAI 兼容端点 /v1/embeddings？
   该请求由 Ollama 的 EmbeddingsMiddleware 用 openai.EmbedRequest 解析，
   这个结构体里没有 keep_alive 字段，Go 的 json 反序列化会**静默丢弃**
   未声明字段（不报错）。于是模型 5 分钟空闲后被卸载，而 Ollama 仍向
   已回收的 llama-server 随机端口转发 /tokenize，返回：
       400 Post "http://127.0.0.1:5xxxx/tokenize": connectex ... refused
   改用原生 /api/embed（**单数**）端点，它认 keep_alive。
   注意别用 /api/embeddings（复数）：字段是 prompt 单条，且返回**未归一化**
   向量（范数 ~22.8），若 Milvus 用 IP 度量会改变检索排序。

2. 即便常驻，Ollama 重启或模型被挤掉时仍可能残留陈旧端口，故加重试。

依赖：仅标准库，不需要 httpx / openai SDK。
"""

import json
import time
import urllib.request
import urllib.error
from typing import Callable, Optional

from config.logging import setup_logging
from config.settings import settings

logger = setup_logging(__name__)

KEEP_ALIVE = 1800     # -1 = 常驻不卸载；改成 300 即恢复 5 分钟自动回收
TIMEOUT = 120       # 单批超时（秒）
MAX_RETRIES = 3     # 命中陈旧端口时的重试次数
RETRY_WAIT = 2.0    # 重试前等待（秒），按次数递增


class EmbeddingClient:
    """Embedding 客户端封装（直连 Ollama 原生 /api/embed）"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        keep_alive: int = KEEP_ALIVE,
    ):
        self.api_key = api_key or settings.emb_api_key or settings.llm_api_key
        self.base_url = base_url or settings.emb_base_url or settings.llm_base_url
        self.model = model or settings.emb_model
        self.keep_alive = keep_alive

        if not self.api_key:
            raise ValueError("缺少 Embedding API Key")

        # http://localhost:11434/v1 -> http://localhost:11434/api/embed
        root = self.base_url.rstrip("/")
        self.endpoint = (root[:-3] if root.endswith("/v1") else root) + "/api/embed"
        logger.info(f"Embedding 客户端初始化: {self.model} @ {self.endpoint}")

    def _warmup(self):
        """预热：确保模型已加载（处理冷启动 400 错误）"""
        payload = json.dumps(
            {"model": self.model, "input": ["warmup"], "keep_alive": self.keep_alive}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp.read()
                logger.info("Embedding 模型预热完成")
        except Exception:
            pass  # 预热失败无所谓，正式请求会重试

    def embed(
        self,
        texts: str | list[str],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        """获取 embedding 向量（自动分批，避免 Ollama llama-server 崩溃）

        Args:
            texts: 单条或多条文本
            on_progress: 每批完成后回调 (已完成条数, 总条数)，用于上报导入进度
        """
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return []

        # 首次调用时预热模型
        if not hasattr(self, "_warmed"):
            self._warmup()
            self._warmed = True

        # 分批处理：每批最多 8 条，避免 tokenize 端口崩溃
        BATCH_SIZE = 8
        total = len(texts)
        all_embeddings = []
        for i in range(0, total, BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            batch_embeddings = self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

            if on_progress is not None:
                try:
                    on_progress(min(i + BATCH_SIZE, total), total)
                except Exception:  # noqa: BLE001 - 进度上报不应影响导入
                    pass

        return all_embeddings

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """单批 embedding 请求（带重试）"""
        payload = json.dumps(
            {"model": self.model, "input": texts, "keep_alive": self.keep_alive}
        ).encode("utf-8")

        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                req = urllib.request.Request(
                    self.endpoint,
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    return json.loads(resp.read().decode("utf-8"))["embeddings"]
            except urllib.error.HTTPError as e:
                # 读取 400 错误的具体内容
                err_body = ""
                try:
                    err_body = e.read().decode("utf-8")[:300]
                except Exception:
                    pass
                last_err = e
                logger.warning(
                    f"Embedding 调用失败（第 {attempt}/{MAX_RETRIES} 次）: HTTP {e.code} - {err_body}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAIT * attempt)
                    self._warmup()
            except Exception as e:
                last_err = e
                logger.warning(
                    f"Embedding 调用失败（第 {attempt}/{MAX_RETRIES} 次）: {e}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_WAIT * attempt)
                    self._warmup()

        logger.error(f"Embedding 调用失败，已重试 {MAX_RETRIES} 次: {last_err}")
        raise last_err

    def embed_one(self, text: str) -> list[float]:
        """获取单个文本的 embedding"""
        return self.embed([text])[0]
