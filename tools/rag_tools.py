"""检索类工具

检索器惰性加载：只有主 Agent 真正调用 rag_search 时才连接 Milvus / 加载 BM25，
纯润色、纯改写场景不会触发任何检索栈初始化。
"""
from typing import Any, Optional

from config.logging import setup_logging
from tools.base import Tool

logger = setup_logging(__name__)


class RagSearchTool(Tool):
    """混合检索工具：BM25 + 向量 + RRF + 重排序"""

    name = "rag_search"
    description = (
        "在本地论文库中检索与查询相关的原文片段。"
        "当需要真实的文献依据、引用、方法细节或数据支撑时调用；"
        "仅做语言润色、按用户思路改写而无需外部事实时不要调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "检索查询词，尽量具体（研究主题、方法名、术语）",
            },
            "top_k": {
                "type": "integer",
                "description": "返回片段数量，默认 5",
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["query"],
    }

    def __init__(self, retriever: Any = None):
        self._retriever = retriever

    @property
    def retriever(self):
        """惰性构造 HybridRetriever"""
        if self._retriever is None:
            from rag.retrieve import HybridRetriever

            self._retriever = HybridRetriever()
        return self._retriever

    # 单个片段与整次返回的字符上限，避免父文档扩展后挤爆上下文
    MAX_SNIPPET_CHARS = 1200
    MAX_TOTAL_CHARS = 12000

    def run(self, query: str, top_k: int = 5) -> dict:
        results = self.retriever.retrieve(query, top_k=top_k)

        snippets = []
        used = 0
        truncated = False
        for r in results:
            text = r.chunk.text or ""
            if len(text) > self.MAX_SNIPPET_CHARS:
                text = text[: self.MAX_SNIPPET_CHARS] + "…"
                truncated = True
            if used + len(text) > self.MAX_TOTAL_CHARS:
                truncated = True
                break
            snippets.append(
                {
                    "title": r.chunk.metadata.get("doc_title", "未知文献"),
                    "page": r.chunk.page,
                    "score": round(float(r.score), 4),
                    "text": text,
                }
            )
            used += len(text)

        return {
            "query": query,
            "count": len(results),
            "returned": len(snippets),
            "truncated": truncated,
            "results": snippets,
        }
