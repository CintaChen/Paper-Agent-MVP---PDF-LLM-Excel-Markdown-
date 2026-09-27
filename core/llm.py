"""LLM 服务封装

支持三种调用形态：
1. chat()          —— 单轮对话（向后兼容，返回字符串）
2. chat_messages() —— 多轮对话 + 工具调用（返回 LLMResponse）
3. chat_stream()   —— 流式对话

工具调用是主 Agent 自主选择子 Agent / 工具的基础能力。
"""
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from openai import OpenAI
from config.settings import settings
from config.logging import setup_logging

logger = setup_logging(__name__)


def _parse_arguments(raw: Any) -> dict:
    """解析工具调用参数（OpenAI 返回的是 JSON 字符串）"""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning(f"工具参数不是合法 JSON，原样返回: {raw}")
        return {"_raw": raw}
    if isinstance(parsed, dict):
        return parsed
    return {"_value": parsed}


@dataclass
class ToolCall:
    """LLM 发起的一次工具调用"""

    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """一次 LLM 调用的归一化结果"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    def as_assistant_message(self) -> dict:
        """转回 OpenAI 消息格式，便于追加进对话历史"""
        message: dict = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(
                            call.arguments, ensure_ascii=False
                        ),
                    },
                }
                for call in self.tool_calls
            ]
        return message


class LLMClient:
    """LLM 客户端封装"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        client: Any = None,
    ):
        self.api_key = api_key or settings.llm_api_key
        self.base_url = base_url or settings.llm_base_url
        self.model = model or settings.llm_model

        if client is not None:
            # 允许注入（便于测试 / 替换后端）
            self.client = client
        elif self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            raise ValueError("缺少 LLM API Key")

        logger.info(f"LLM 客户端初始化: {self.model}")

    # ------------------------------------------------------------------
    # 单轮（向后兼容）
    # ------------------------------------------------------------------
    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """单轮对话，返回文本内容"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat_messages(
            messages, temperature=temperature, max_tokens=max_tokens
        ).content

    # ------------------------------------------------------------------
    # 多轮 + 工具调用
    # ------------------------------------------------------------------
    def chat_messages(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[str] = None,
        temperature: float = None,
        max_tokens: int = None,
    ) -> LLMResponse:
        """多轮对话，可选工具调用

        Args:
            messages: OpenAI 格式的消息列表
            tools: 工具 JSON Schema 列表（见 Tool.to_openai_schema）
            tool_choice: "auto" / "none" / 指定工具名
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                temperature if temperature is not None else settings.llm_temperature
            ),
            "max_tokens": (
                max_tokens if max_tokens is not None else settings.llm_max_tokens
            ),
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        response = self.client.chat.completions.create(**kwargs)
        return self._parse_response(response)

    def _parse_response(self, response: Any) -> LLMResponse:
        """把 OpenAI 响应归一化为 LLMResponse"""
        message = response.choices[0].message
        return LLMResponse(
            content=message.content or "",
            tool_calls=self._parse_tool_calls(message),
            raw=response,
        )

    @staticmethod
    def _parse_tool_calls(message: Any) -> list[ToolCall]:
        raw_calls = getattr(message, "tool_calls", None) or []
        calls = []
        for call in raw_calls:
            calls.append(
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    arguments=_parse_arguments(call.function.arguments),
                )
            )
        return calls

    # ------------------------------------------------------------------
    # 流式
    # ------------------------------------------------------------------
    def chat_stream(self, system_prompt: str, user_prompt: str):
        """流式对话"""
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
