"""测试主 Agent 的事件流（run_stream）与 run 的复用关系"""
from agent.context import WritingContext
from agent.orchestrator import Orchestrator
from core.llm import LLMResponse, ToolCall
from tools.base import Tool
from tools.registry import ToolRegistry


class FakeLLMClient:
    """按顺序返回预设响应，并记录每次请求的 messages"""

    def __init__(self, responses):
        self._responses = list(responses)
        self.requests = []

    def chat_messages(
        self, messages, tools=None, tool_choice=None, temperature=None, max_tokens=None
    ):
        self.requests.append({"messages": list(messages), "tools": tools})
        return self._responses.pop(0)


class RecordingTool(Tool):
    name = "draft_expand"
    description = "记录调用参数的写作工具"
    parameters = {"type": "object", "properties": {}}

    def __init__(self):
        self.calls = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        return "生成的正文"


def _tool_call_response(call_id="c1"):
    return LLMResponse(
        content="",
        tool_calls=[
            ToolCall(
                id=call_id,
                name="draft_expand",
                arguments={"section_title": "引言", "user_ideas": "先说背景"},
            )
        ],
    )


class TestRunStream:
    def test_event_sequence(self):
        llm = FakeLLMClient([_tool_call_response(), LLMResponse(content="最终正文")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([RecordingTool()]))

        events = list(orch.run_stream("帮我写引言"))
        types = [e["type"] for e in events]

        assert types == ["tool_call", "tool_result", "final"]

        tool_call = events[0]
        assert tool_call["tool"] == "draft_expand"
        assert tool_call["iteration"] == 1
        assert tool_call["arguments"]["section_title"] == "引言"

        tool_result = events[1]
        assert tool_result["tool"] == "draft_expand"
        assert tool_result["output"] == "生成的正文"

        final = events[2]["result"]
        assert final.content == "最终正文"
        assert final.stopped_reason == "completed"
        assert final.iterations == 2
        assert len(final.steps) == 1

    def test_direct_answer_yields_only_final(self):
        llm = FakeLLMClient([LLMResponse(content="直接回答")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([]))

        events = list(orch.run_stream("你好"))
        assert [e["type"] for e in events] == ["final"]
        assert events[0]["result"].content == "直接回答"

    def test_max_iterations_override(self):
        responses = [_tool_call_response(f"c{i}") for i in range(5)]
        llm = FakeLLMClient(responses)
        orch = Orchestrator(
            llm_client=llm,
            registry=ToolRegistry([RecordingTool()]),
            max_iterations=8,
        )

        events = list(orch.run_stream("x", max_iterations=2))
        final = events[-1]["result"]

        assert final.stopped_reason == "max_iterations"
        assert final.iterations == 2
        assert len(final.steps) == 2
        # 仅消费了 2 次 LLM 响应
        assert len(llm.requests) == 2

    def test_context_and_history_injected(self):
        llm = FakeLLMClient([LLMResponse(content="ok")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([]))
        context = WritingContext(topic="AI 教育", ideas="强调个性化学习")
        history = [
            {"role": "user", "content": "先写引言"},
            {"role": "assistant", "content": "好的"},
        ]

        list(orch.run_stream("写方法", context=context, history=history))

        messages = llm.requests[0]["messages"]
        system_joined = "\n".join(
            m["content"] for m in messages if m["role"] == "system"
        )
        assert "AI 教育" in system_joined
        assert "强调个性化学习" in system_joined
        # 历史消息保留，且本次请求位于最后
        assert {"role": "user", "content": "先写引言"} in messages
        assert {"role": "assistant", "content": "好的"} in messages
        assert messages[-1] == {"role": "user", "content": "写方法"}


class TestRunUsesStream:
    def test_run_returns_final_result(self):
        llm = FakeLLMClient([_tool_call_response(), LLMResponse(content="最终正文")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([RecordingTool()]))

        result = orch.run("帮我写引言")

        assert result.content == "最终正文"
        assert result.stopped_reason == "completed"
        assert result.iterations == 2
        assert result.steps[0].tool == "draft_expand"

    def test_run_honors_max_iterations_param(self):
        responses = [_tool_call_response(f"c{i}") for i in range(5)]
        llm = FakeLLMClient(responses)
        orch = Orchestrator(
            llm_client=llm,
            registry=ToolRegistry([RecordingTool()]),
            max_iterations=8,
        )

        result = orch.run("x", max_iterations=2)
        assert result.stopped_reason == "max_iterations"
        assert result.iterations == 2
