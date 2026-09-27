"""Agent 基类"""
from typing import Optional
from config.logging import setup_logging
from core.llm import LLMClient
from rag.retrieve import HybridRetriever
from core.document import SearchResult

logger = setup_logging(__name__)


class BaseAgent:
    """Agent 基类"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        retriever: HybridRetriever = None,
        system_prompt: str = "",
    ):
        self.llm_client = llm_client or LLMClient()
        self._retriever = retriever
        self.system_prompt = system_prompt

    @property
    def retriever(self) -> HybridRetriever:
        """惰性构造检索器

        纯润色 / 纯改写场景不会调用 retrieve()，也就不应为此连接 Milvus、
        加载 BM25 索引、打开 SQLite。首次真正检索时才构造。
        """
        if self._retriever is None:
            self._retriever = HybridRetriever()
        return self._retriever

    def retrieve(self, query: str, top_k: int = None) -> list[SearchResult]:
        """检索相关文档"""
        return self.retriever.retrieve(query, top_k=top_k)

    def build_context(self, results: list[SearchResult]) -> str:
        """构建上下文（显示真实来源）"""
        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results, 1):
            # 🆕 从 metadata 获取真实标题
            doc_title = result.chunk.metadata.get("doc_title", "未知文献")
            page = result.chunk.page
            source = result.chunk.metadata.get("source", "unknown")

            context_parts.append(
                f"[片段 {i}] (来源: {doc_title}, 第 {page} 页)\n{result.chunk.text}"
            )

        return "\n\n".join(context_parts)

    def chat(self, user_prompt: str, context: str = "", temperature: float = None, max_tokens: int = None) -> str:
        """调用 LLM

        Args:
            user_prompt: 用户提示词
            context: 参考上下文
            temperature: LLM 温度（可选，覆盖默认值）
            max_tokens: LLM 最大 token（可选，覆盖默认值）
        """
        if context:
            full_prompt = f"参考内容：\n{context}\n\n{user_prompt}"
        else:
            full_prompt = user_prompt

        return self.llm_client.chat(
            system_prompt=self.system_prompt,
            user_prompt=full_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
