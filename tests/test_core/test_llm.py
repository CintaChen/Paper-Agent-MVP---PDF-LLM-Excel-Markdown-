"""测试 LLM 工具调用解析"""
from core.llm import LLMClient, LLMResponse, ToolCall


# ============================================================
# 伪造 OpenAI 响应对象
# ============================================================

class FakeFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, id: str, name: str, arguments: str):
        self.id = id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeChoice:
    def __init__(self, message):
        self.message = message


class FakeResponse:
    def __init__(self, message):
        self.choices = [FakeChoice(message)]


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class FakeChat:
    def __init__(self, responses):
        self.completions = FakeCompletions(responses)


class FakeOpenAI:
    def __init__(self, responses):
        self.chat = FakeChat(responses)


def make_client(responses):
    return LLMClient(client=FakeOpenAI(responses))


# ============================================================
# 测试
# ============================================================

class TestLLMToolCalling:
    def test_chat_returns_content(self):
        client = make_client([FakeResponse(FakeMessage(content="你好"))])
        assert client.chat("sys", "hi") == "你好"

    def test_parse_tool_calls(self):
        response = FakeResponse(
            FakeMessage(
                content=None,
                tool_calls=[
                    FakeToolCall("call_1", "rag_search", '{"query": "AI"}')
                ],
            )
        )
        client = make_client([response])

        out = client.chat_messages(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "rag_search"}}],
        )

        assert out.has_tool_calls
        assert out.tool_calls[0].id == "call_1"
        assert out.tool_calls[0].name == "rag_search"
        assert out.tool_calls[0].arguments == {"query": "AI"}

    def test_no_tool_calls(self):
        client = make_client([FakeResponse(FakeMessage(content="正文"))])
        out = client.chat_messages([{"role": "user", "content": "hi"}])
        assert not out.has_tool_calls
        assert out.content == "正文"

    def test_invalid_arguments_kept_raw(self):
        response = FakeResponse(
            FakeMessage(
                content=None,
                tool_calls=[FakeToolCall("c", "t", "{bad json")],
            )
        )
        client = make_client([response])
        out = client.chat_messages([{"role": "user", "content": "hi"}])
        assert out.tool_calls[0].arguments == {"_raw": "{bad json"}

    def test_tools_passed_to_api_only_when_present(self):
        client = make_client(
            [
                FakeResponse(FakeMessage(content="a")),
                FakeResponse(FakeMessage(content="b")),
            ]
        )
        client.chat_messages([{"role": "user", "content": "hi"}])
        client.chat_messages(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "x"}}],
        )

        kwargs = client.client.chat.completions.calls
        assert "tools" not in kwargs[0]
        assert kwargs[1]["tools"][0]["function"]["name"] == "x"


class TestLLMResponse:
    def test_as_assistant_message_with_tool_calls(self):
        response = LLMResponse(
            content="",
            tool_calls=[ToolCall(id="c1", name="rag_search", arguments={"query": "AI"})],
        )
        message = response.as_assistant_message()
        assert message["role"] == "assistant"
        assert message["content"] is None
        assert message["tool_calls"][0]["id"] == "c1"
        assert message["tool_calls"][0]["function"]["name"] == "rag_search"

    def test_as_assistant_message_plain(self):
        response = LLMResponse(content="结果")
        message = response.as_assistant_message()
        assert message == {"role": "assistant", "content": "结果"}
