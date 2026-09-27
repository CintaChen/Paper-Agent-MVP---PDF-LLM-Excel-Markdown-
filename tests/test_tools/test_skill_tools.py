"""测试 Skill 类工具（无检索）"""
import pytest

from tools.skill_tools import StylePolishTool


class FakeLLMClient:
    def __init__(self, reply: str = "润色结果"):
        self.reply = reply
        self.calls = []

    def chat(self, system_prompt, user_prompt, temperature=None, max_tokens=None):
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
            }
        )
        return self.reply


class TestStylePolishTool:
    def test_polish_mode(self):
        llm = FakeLLMClient()
        tool = StylePolishTool(llm_client=llm)
        assert tool.run("原句", mode="polish") == "润色结果"
        assert "原句" in llm.calls[0]["user_prompt"]

    def test_academic_mode(self):
        llm = FakeLLMClient()
        tool = StylePolishTool(llm_client=llm)
        tool.run("原句", mode="academic")
        assert "学术" in llm.calls[0]["system_prompt"]

    def test_simplify_mode(self):
        llm = FakeLLMClient()
        tool = StylePolishTool(llm_client=llm)
        tool.run("原句", mode="simplify")
        assert "简化" in llm.calls[0]["user_prompt"]

    def test_invalid_mode_raises(self):
        tool = StylePolishTool(llm_client=FakeLLMClient())
        with pytest.raises(ValueError):
            tool.run("原句", mode="unknown")

    def test_does_not_touch_retriever(self):
        """润色工具不应有任何检索依赖"""
        tool = StylePolishTool(llm_client=FakeLLMClient())
        assert not hasattr(tool, "retriever")
