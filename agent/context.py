"""写作上下文

保证"作者看得见"的同时，也让主 Agent 在扩写后续章节时能看见
框架、思路与已完成正文，从而维持全篇逻辑连贯。
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Section:
    """已完成的章节"""

    title: str
    content: str


@dataclass
class WritingContext:
    """论文写作上下文"""

    topic: str = ""
    framework: str = ""
    ideas: str = ""
    requirements: str = ""
    sections: list[Section] = field(default_factory=list)

    def add_section(self, title: str, content: str) -> None:
        """记录一节已完成正文"""
        self.sections.append(Section(title=title, content=content))

    def to_prompt(self, recent_sections: int = 2) -> str:
        """序列化为可注入主 Agent 的上下文字符串

        最近 recent_sections 节保留全文（保证衔接），更早的只保留标题（控制长度）。
        """
        parts: list[str] = []

        if self.topic:
            parts.append(f"【论文主题】\n{self.topic}")
        if self.framework:
            parts.append(f"【整体框架】\n{self.framework}")
        if self.ideas:
            parts.append(f"【作者的思路】\n{self.ideas}")
        if self.requirements:
            parts.append(f"【写作要求】\n{self.requirements}")

        if self.sections:
            recent = self.sections[-recent_sections:]
            earlier = self.sections[:-recent_sections]

            if earlier:
                titles = "、".join(s.title for s in earlier)
                parts.append(f"【已完成章节（仅标题）】\n{titles}")

            for section in recent:
                parts.append(
                    f"【已完成章节：{section.title}】\n{section.content}"
                )

        return "\n\n".join(parts)

    @property
    def is_empty(self) -> bool:
        """是否没有任何有效内容"""
        return not any(
            [
                self.topic,
                self.framework,
                self.ideas,
                self.requirements,
                self.sections,
            ]
        )

    def to_dict(self) -> dict:
        """序列化为可落库的字典"""
        return {
            "topic": self.topic,
            "framework": self.framework,
            "ideas": self.ideas,
            "requirements": self.requirements,
            "sections": [
                {"title": section.title, "content": section.content}
                for section in self.sections
            ],
        }

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "WritingContext":
        """从落库字典还原（None / 空则返回空上下文）"""
        if not data:
            return cls()

        context = cls(
            topic=data.get("topic", "") or "",
            framework=data.get("framework", "") or "",
            ideas=data.get("ideas", "") or "",
            requirements=data.get("requirements", "") or "",
        )
        for item in data.get("sections") or []:
            if isinstance(item, dict):
                context.add_section(
                    item.get("title", "") or "",
                    item.get("content", "") or "",
                )
        return context
