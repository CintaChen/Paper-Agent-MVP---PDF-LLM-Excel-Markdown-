"""测试主 Agent 工具调用循环"""
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


class TestOrchestrator:
    def test_no_tool_call_returns_directly(self):
        llm = FakeLLMClient([LLMResponse(content="直接回答")])
        orch = Orchestrator(
            llm_client=llm,
            registry=ToolRegistry([RecordingTool()]),
        )
        result = orch.run("你好")

        assert result.content == "直接回答"
        assert result.iterations == 1
        assert result.stopped_reason == "completed"
        assert result.steps == []

    def test_calls_tool_then_finishes(self):
        tool = RecordingTool()
        llm = FakeLLMClient(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(
                            id="c1",
                            name="draft_expand",
                            arguments={"section_title": "引言", "user_ideas": "先说背景"},
                        )
                    ],
                ),
                LLMResponse(content="最终正文"),
            ]
        )
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([tool]))
        result = orch.run("帮我写引言")

        assert result.content == "最终正文"
        assert result.iterations == 2
        assert result.stopped_reason == "completed"
        assert len(result.steps) == 1
        assert result.steps[0].tool == "draft_expand"
        assert result.steps[0].output == "生成的正文"
        assert tool.calls[0]["section_title"] == "引言"

    def test_tool_result_fed_back_to_llm(self):
        llm = FakeLLMClient(
            [
                LLMResponse(
                    content="",
                    tool_calls=[
                        ToolCall(id="c1", name="draft_expand", arguments={})
                    ],
                ),
                LLMResponse(content="done"),
            ]
        )
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([RecordingTool()]))
        orch.run("x")

        second_messages = llm.requests[1]["messages"]
        tool_messages = [m for m in second_messages if m["role"] == "tool"]
        assert tool_messages[0]["tool_call_id"] == "c1"
        assert tool_messages[0]["content"] == "生成的正文"

    def test_max_iterations_guard(self):
        tool = RecordingTool()
        responses = [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id=f"c{i}", name="draft_expand", arguments={})],
            )
            for i in range(5)
        ]
        llm = FakeLLMClient(responses)
        orch = Orchestrator(
            llm_client=llm,
            registry=ToolRegistry([tool]),
            max_iterations=3,
        )
        result = orch.run("x")

        assert result.stopped_reason == "max_iterations"
        assert result.iterations == 3
        assert len(result.steps) == 3

    def test_writing_context_injected(self):
        llm = FakeLLMClient([LLMResponse(content="ok")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([]))
        context = WritingContext(
            topic="AI 教育",
            framework="引言 / 方法 / 结论",
            ideas="强调个性化学习",
        )
        orch.run("写引言", context=context)

        system_messages = [
            m["content"] for m in llm.requests[0]["messages"] if m["role"] == "system"
        ]
        joined = "\n".join(system_messages)
        assert "AI 教育" in joined
        assert "强调个性化学习" in joined

    def test_previous_sections_visible(self):
        llm = FakeLLMClient([LLMResponse(content="ok")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([]))
        context = WritingContext(topic="T")
        context.add_section("引言", "引言正文内容")
        orch.run("写方法", context=context)

        joined = "\n".join(
            m["content"] for m in llm.requests[0]["messages"] if m["role"] == "system"
        )
        assert "引言正文内容" in joined

    def test_tools_schema_passed_to_llm(self):
        llm = FakeLLMClient([LLMResponse(content="ok")])
        orch = Orchestrator(llm_client=llm, registry=ToolRegistry([RecordingTool()]))
        orch.run("x")

        assert llm.requests[0]["tools"][0]["function"]["name"] == "draft_expand"

    def test_default_registry_and_lazy_retriever(self):
        """默认工具集齐全，且未调用 rag_search 时不初始化检索器"""
        llm = FakeLLMClient([LLMResponse(content="ok")])
        orch = Orchestrator(llm_client=llm)

        assert set(orch.registry.names()) == {
            "rag_search",
            "style_polish",
            "draft_expand",
            "self_critique",
        }
        assert orch.registry.get("rag_search")._retriever is None
