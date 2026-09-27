"""主 Agent（Orchestrator）

工具调用循环：think → 选工具 → 观察结果 → 判断收敛 → 继续 / 输出。
主 Agent 自主决定调用哪些工具、调用几次，而不是走固定工作流。
"""
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

from config.logging import setup_logging
from core.llm import LLMClient
from agent.prompts import ORCHESTRATOR_SYSTEM_PROMPT
from agent.context import WritingContext
from tools import build_default_registry
from tools.registry import ToolRegistry

logger = setup_logging(__name__)


@dataclass
class ToolStep:
    """一次工具调用的记录（便于调试与展示推理轨迹）"""

    iteration: int
    tool: str
    arguments: dict
    output: str


@dataclass
class OrchestratorResult:
    """主循环结果"""

    content: str
    steps: list[ToolStep] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    iterations: int = 0
    stopped_reason: str = "completed"  # completed | max_iterations


class Orchestrator:
    """主 Agent：自主选择工具完成写作任务"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        registry: ToolRegistry = None,
        system_prompt: str = None,
        max_iterations: int = 8,
        temperature: float = None,
        max_tokens: int = None,
    ):
        self.llm_client = llm_client or LLMClient()
        self.registry = (
            registry
            if registry is not None
            else build_default_registry(llm_client=self.llm_client)
        )
        self.system_prompt = system_prompt or ORCHESTRATOR_SYSTEM_PROMPT
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens

    def run(
        self,
        user_message: str,
        context: Optional[WritingContext | str] = None,
        history: Optional[list[dict]] = None,
        max_iterations: Optional[int] = None,
    ) -> OrchestratorResult:
        """执行一次完整的工具调用循环（消费 run_stream 直至收敛）

        Args:
            user_message: 用户本次请求
            context: 写作上下文（WritingContext 或纯字符串）
            history: 可选的历史消息（OpenAI 格式），用于多轮会话
            max_iterations: 覆盖实例默认的最大迭代次数
        """
        result: Optional[OrchestratorResult] = None
        for event in self.run_stream(
            user_message,
            context=context,
            history=history,
            max_iterations=max_iterations,
        ):
            if event["type"] == "final":
                result = event["result"]
        # run_stream 保证最后必产出 final 事件
        return result

    def run_stream(
        self,
        user_message: str,
        context: Optional[WritingContext | str] = None,
        history: Optional[list[dict]] = None,
        max_iterations: Optional[int] = None,
    ) -> Iterator[dict]:
        """执行工具调用循环，逐步产出事件（供流式接口使用）

        Yields:
            - {"type": "tool_call",   iteration, tool, arguments}
            - {"type": "tool_result", iteration, tool, output}
            - {"type": "final",       result: OrchestratorResult}
        """
        messages = self._build_messages(user_message, context, history)
        tools_schema = self.registry.schemas()
        steps: list[ToolStep] = []
        last_content = ""
        limit = max_iterations or self.max_iterations

        for iteration in range(1, limit + 1):
            response = self.llm_client.chat_messages(
                messages,
                tools=tools_schema,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # 没有工具调用 → 主 Agent 认为可以交付
            if not response.has_tool_calls:
                yield {
                    "type": "final",
                    "result": OrchestratorResult(
                        content=response.content,
                        steps=steps,
                        messages=messages,
                        iterations=iteration,
                        stopped_reason="completed",
                    ),
                }
                return

            if response.content:
                last_content = response.content
            messages.append(response.as_assistant_message())

            for call in response.tool_calls:
                yield {
                    "type": "tool_call",
                    "iteration": iteration,
                    "tool": call.name,
                    "arguments": call.arguments,
                }

                output = self.registry.execute(call.name, call.arguments)
                steps.append(
                    ToolStep(
                        iteration=iteration,
                        tool=call.name,
                        arguments=call.arguments,
                        output=output,
                    )
                )
                logger.info(
                    f"[迭代 {iteration}] 调用工具 {call.name}"
                    f"(参数: {list(call.arguments.keys())})"
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    }
                )

                yield {
                    "type": "tool_result",
                    "iteration": iteration,
                    "tool": call.name,
                    "output": output,
                }

        logger.warning(f"达到最大迭代次数 {limit}，强制结束")
        yield {
            "type": "final",
            "result": OrchestratorResult(
                content=last_content,
                steps=steps,
                messages=messages,
                iterations=limit,
                stopped_reason="max_iterations",
            ),
        }

    def _build_messages(
        self,
        user_message: str,
        context: Optional[WritingContext | str],
        history: Optional[list[dict]],
    ) -> list[dict]:
        """组装初始消息：系统提示 + 写作上下文 + 历史 + 本次请求"""
        messages: list[dict] = [
            {"role": "system", "content": self.system_prompt}
        ]

        context_text = self._render_context(context)
        if context_text:
            messages.append(
                {"role": "system", "content": f"【当前写作上下文】\n{context_text}"}
            )

        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _render_context(context: Optional[WritingContext | str]) -> str:
        if context is None:
            return ""
        if isinstance(context, WritingContext):
            return context.to_prompt()
        return str(context)
