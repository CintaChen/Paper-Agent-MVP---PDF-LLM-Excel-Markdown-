"""工具注册表

主 Agent 循环通过注册表：
- 取出全部工具的 JSON Schema 交给 LLM
- 按 LLM 返回的工具名分发执行
"""
import json
from typing import Any, Optional

from config.logging import setup_logging
from tools.base import Tool

logger = setup_logging(__name__)


class ToolRegistry:
    """工具注册表"""

    def __init__(self, tools: Optional[list[Tool]] = None):
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        """注册工具（同名覆盖）"""
        if not tool.name:
            raise ValueError(f"{type(tool).__name__} 未定义 name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def schemas(self) -> list[dict]:
        """全部工具的 JSON Schema"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def execute(self, name: str, arguments: dict = None) -> str:
        """执行工具，统一返回给 LLM 的字符串

        出错不抛异常，而是把错误信息作为工具结果返回，
        让主 Agent 有机会根据错误自行纠正或换用其他工具。
        """
        tool = self.get(name)
        if tool is None:
            return json.dumps(
                {"error": f"未知工具: {name}", "available": self.names()},
                ensure_ascii=False,
            )

        try:
            output = tool.run(**(arguments or {}))
        except TypeError as e:
            logger.warning(f"工具参数错误 {name}: {e}")
            return json.dumps(
                {"error": f"参数错误: {e}"}, ensure_ascii=False
            )
        except Exception as e:  # noqa: BLE001 - 工具失败不应中断主循环
            logger.exception(f"工具执行失败 {name}: {e}")
            return json.dumps(
                {"error": f"工具执行失败: {e}"}, ensure_ascii=False
            )

        if isinstance(output, str):
            return output
        return json.dumps(output, ensure_ascii=False, default=str)
