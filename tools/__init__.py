"""工具层

对外暴露统一的注册表构建入口。所有工具均为惰性依赖：
不调用 run 就不会连接 Milvus / BM25 / LLM。
"""
from typing import Any, Optional

from tools.base import Tool
from tools.registry import ToolRegistry
from tools.rag_tools import RagSearchTool
from tools.skill_tools import StylePolishTool
from tools.writing_tools import DraftExpandTool
from tools.critique_tools import SelfCritiqueTool


def build_default_registry(
    llm_client: Any = None,
    retriever: Any = None,
) -> ToolRegistry:
    """构建默认工具集

    Args:
        llm_client: 共享的 LLM 客户端（不传则各工具惰性自建）
        retriever: 共享的检索器（不传则 rag_search 首次调用时自建）
    """
    return ToolRegistry(
        [
            RagSearchTool(retriever=retriever),
            StylePolishTool(llm_client=llm_client),
            DraftExpandTool(llm_client=llm_client),
            SelfCritiqueTool(llm_client=llm_client),
        ]
    )


__all__ = [
    "Tool",
    "ToolRegistry",
    "RagSearchTool",
    "StylePolishTool",
    "DraftExpandTool",
    "SelfCritiqueTool",
    "build_default_registry",
]
