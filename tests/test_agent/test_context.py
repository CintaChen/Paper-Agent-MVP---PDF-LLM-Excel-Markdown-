"""测试写作上下文的序列化（会话持久化的基础）"""
from agent.context import WritingContext


class TestSerialization:
    def test_to_dict(self):
        context = WritingContext(
            topic="AI", framework="F", ideas="I", requirements="R"
        )
        context.add_section("引言", "正文")

        assert context.to_dict() == {
            "topic": "AI",
            "framework": "F",
            "ideas": "I",
            "requirements": "R",
            "sections": [{"title": "引言", "content": "正文"}],
        }

    def test_roundtrip_preserves_prompt(self):
        context = WritingContext(topic="AI", ideas="I")
        context.add_section("引言", "正文")

        restored = WritingContext.from_dict(context.to_dict())

        assert restored.topic == "AI"
        assert restored.ideas == "I"
        assert [s.title for s in restored.sections] == ["引言"]
        assert restored.to_prompt() == context.to_prompt()

    def test_from_dict_none_and_empty(self):
        assert WritingContext.from_dict(None).is_empty
        assert WritingContext.from_dict({}).is_empty
        assert WritingContext.from_dict({"sections": []}).is_empty

    def test_from_dict_skips_bad_sections(self):
        context = WritingContext.from_dict(
            {
                "topic": "T",
                "sections": ["坏数据", {"title": "A", "content": "B"}],
            }
        )

        assert [s.title for s in context.sections] == ["A"]


class TestIsEmpty:
    def test_empty_by_default(self):
        assert WritingContext().is_empty

    def test_non_empty_when_any_field_set(self):
        assert not WritingContext(topic="T").is_empty
        assert not WritingContext(framework="F").is_empty
        assert not WritingContext(ideas="I").is_empty
        assert not WritingContext(requirements="R").is_empty

    def test_non_empty_when_section_added(self):
        context = WritingContext()
        context.add_section("A", "B")
        assert not context.is_empty
