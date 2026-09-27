"""工具协议

所有可被主 Agent 调用的能力（检索、写作、润色、自评、子 Agent）都实现 Tool 接口，
统一暴露为 OpenAI function calling 的 JSON Schema。
"""
from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """工具抽象基类

    子类需定义：
    - name: 工具唯一名称（LLM 通过它调用）
    - description: 给 LLM 看的能力说明（决定 LLM 何时选它）
    - parameters: 参数的 JSON Schema
    - run(): 实际执行逻辑
    """

    name: str = ""
    description: str = ""
    parameters: dict = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    @abstractmethod
    def run(self, **kwargs: Any) -> Any:
        """执行工具，返回 str 或可 JSON 序列化的对象"""
        ...

    def to_openai_schema(self) -> dict:
        """转换为 OpenAI function calling 的 tools 条目"""
        if not self.name:
            raise ValueError(f"{type(self).__name__} 未定义 name")
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
