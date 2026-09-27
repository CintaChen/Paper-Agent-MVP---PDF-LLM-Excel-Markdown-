"""测试 WritingAgent"""
import pytest

from agent.writing_agent import WritingAgent


class FakeLLMClient:
    def __init__(self):
        self.requests = []

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        self.requests.append(user_prompt)
        return "大纲结果"


class FakeRetriever:
    def __init__(self, results=None):
        self.results = results or []
        self.calls = []

    def retrieve(self, query, top_k=None):
        self.calls.append((query, top_k))
        return self.results


class TestWritingAgent:
    def test_generate_outline_uses_retriever(self):
        retriever = FakeRetriever()
        agent = WritingAgent(llm_client=FakeLLMClient(), retriever=retriever)

        response = agent.generate_outline(topic="AI 赋能教育")

        assert response == "大纲结果"
        assert retriever.calls[0][0] == "AI 赋能教育"

    def test_constructing_agent_does_not_build_retriever(self, monkeypatch):
        import agent.base_agent as base_agent

        created = []

        class RecordingRetriever(FakeRetriever):
            def __init__(self, *args, **kwargs):
                created.append(1)
                super().__init__()

        monkeypatch.setattr(base_agent, "HybridRetriever", RecordingRetriever)

        agent = WritingAgent(llm_client=FakeLLMClient())

        assert created == []  # 构造阶段不建检索器
        assert isinstance(agent.retriever, RecordingRetriever)
        assert len(created) == 1
