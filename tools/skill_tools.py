"""Skill 类工具（纯提示词，不依赖检索）

对应"不需要论文素材时"的场景：只改写表达，不引入外部事实。
"""
from typing import Any, Optional

from config.logging import setup_logging
from tools.base import Tool

logger = setup_logging(__name__)


_STYLE_PROMPTS = {
    "polish": """请对以下学术段落进行润色优化。

原文：
{text}

优化要求：
- 使用更正式的学术语言
- 确保句子结构清晰
- 保持原意不变

请输出：
1. 润色后的版本
2. 主要修改说明""",
    "simplify": """请简化以下段落，使其更简洁清晰。

原文：
{text}

要求：
- 去除冗余表达
- 保留核心观点
- 字数控制在原文的 70% 以内""",
    "academic": """请提升以下段落的学术写作规范。

原文：
{text}

优化要求：
1. 使用更正式的学术语言
2. 确保引用规范（如需要，标注 [待引用]）
3. 避免主观表述（如"我认为"→"研究表明"）
4. 确保术语准确

请输出：
1. 优化后的版本
2. 主要修改说明""",
}

_STYLE_SYSTEM_PROMPT = """你是一名专业的学术写作润色专家。
你的任务是帮助优化学术论文的行文表达，使其更符合学术写作规范。

要求：
1. 保持原意不变
2. 使用正式、客观的学术语言
3. 避免口语化表达
4. 句子结构严谨，逻辑清晰
5. 专业术语使用准确
6. 不要编造原文没有的事实或文献
"""


class StylePolishTool(Tool):
    """行文风格 skill：润色 / 简化 / 学术化（无检索）"""

    name = "style_polish"
    description = (
        "对已有文字做表达层面的改写，不引入新的事实或文献。"
        "当用户只要求润色、简化、学术化，或明确不需要参考文献时调用。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "待优化的文本",
            },
            "mode": {
                "type": "string",
                "enum": ["polish", "simplify", "academic"],
                "description": "优化模式：润色 / 简化 / 学术化，默认 polish",
            },
        },
        "required": ["text"],
    }

    def __init__(self, llm_client: Any = None):
        self._llm_client = llm_client

    @property
    def llm_client(self):
        """惰性构造 LLMClient"""
        if self._llm_client is None:
            from core.llm import LLMClient

            self._llm_client = LLMClient()
        return self._llm_client

    def run(self, text: str, mode: str = "polish") -> str:
        if mode not in _STYLE_PROMPTS:
            raise ValueError(
                f"无效的 mode: {mode}，可选 {list(_STYLE_PROMPTS)}"
            )
        prompt = _STYLE_PROMPTS[mode].format(text=text)
        return self.llm_client.chat(
            system_prompt=_STYLE_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
