"""测试 StyleAgent：纯润色不得触发检索栈初始化"""
import pytest

from agent.style_agent import StyleAgent


class FakeLLMClient:
    def __init__(self):
        self.requests = []

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        self.requests.append(user_prompt)
        return "润色结果"


@pytest.fixture
def forbid_retriever(monkeypatch):
    """任何 HybridRetriever 构造都视为失败"""
    import agent.base_agent as base_agent

    def _boom(*args, **kwargs):
        raise AssertionError("纯润色不应构造 HybridRetriever")

    monkeypatch.setattr(base_agent, "HybridRetriever", _boom)


class TestStyleAgentLazyRetriever:
    def test_polish_does_not_touch_retriever(self, forbid_retriever):
        agent = StyleAgent(llm_client=FakeLLMClient())
        assert agent.polish("待润色的段落") == "润色结果"

    def test_constructing_agent_does_not_build_retriever(self, monkeypatch):
        import agent.base_agent as base_agent

        created = []

        class FakeRetriever:
            def __init__(self):
                created.append(1)

            def retrieve(self, query, top_k=None):
                return []

        monkeypatch.setattr(base_agent, "HybridRetriever", FakeRetriever)

        agent = StyleAgent(llm_client=FakeLLMClient())
        assert created == []  # 仅构造 Agent 不建检索器

        assert agent.retrieve("查询") == []
        assert len(created) == 1

        agent.retrieve("再查一次")
        assert len(created) == 1  # 复用同一实例

    def test_injected_retriever_is_used(self):
        sentinel = object()
        agent = StyleAgent(llm_client=FakeLLMClient(), retriever=sentinel)
        assert agent.retriever is sentinel
