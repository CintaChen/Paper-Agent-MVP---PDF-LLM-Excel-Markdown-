"""写作类工具

核心场景：用户给出论文框架与自己的思路，工具按思路扩写。
素材（参考文献片段）作为可选输入由主 Agent 决定是否注入，
不注入时不触发任何检索。
"""
from typing import Any, Optional

from config.logging import setup_logging
from tools.base import Tool

logger = setup_logging(__name__)


_EXPAND_SYSTEM_PROMPT = """你是一名学术论文写作助手。
你的任务是在作者给定的框架和思路下扩写正文，而不是另起炉灶。

铁律：
1. 严格围绕作者提供的思路展开，不得偏离、不得替换作者的观点
2. 有参考素材时，基于素材论述并标注来源（文献标题、页码）；素材不足则如实论述
3. 没有素材时，可以正常论述，但不得编造文献、数据或引用
4. 使用中文学术语体，逻辑连贯，段落之间要有过渡
5. 只输出正文，不要输出解释性说明
"""

_EXPAND_USER_PROMPT = """【论文整体框架】
{framework}

【本节标题】
{section_title}

【作者的思路（必须遵循）】
{user_ideas}
{references_block}{requirements_block}
请按上述思路扩写本节正文。"""


class DraftExpandTool(Tool):
    """按用户思路扩写某一节"""

    name = "draft_expand"
    description = (
        "根据作者给定的论文框架与个人思路，扩写指定章节的正文。"
        "这是写作主任务的核心工具。references 参数可选："
        "若已通过 rag_search 取得素材则传入，没有素材则留空。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "section_title": {
                "type": "string",
                "description": "本节标题",
            },
            "user_ideas": {
                "type": "string",
                "description": "作者对本节的思路、要点、想表达的内容",
            },
            "framework": {
                "type": "string",
                "description": "论文整体框架（可选，用于保持上下文一致）",
            },
            "references": {
                "type": "string",
                "description": "可选的参考文献素材文本（通常来自 rag_search 的结果）",
            },
            "requirements": {
                "type": "string",
                "description": "可选的写作要求（字数、要点清单、风格等）",
            },
        },
        "required": ["section_title", "user_ideas"],
    }

    def __init__(self, llm_client: Any = None):
        self._llm_client = llm_client

    @property
    def llm_client(self):
        if self._llm_client is None:
            from core.llm import LLMClient

            self._llm_client = LLMClient()
        return self._llm_client

    def run(
        self,
        section_title: str,
        user_ideas: str,
        framework: str = "",
        references: str = "",
        requirements: str = "",
    ) -> str:
        references_block = (
            f"\n【参考素材】\n{references}\n" if references else ""
        )
        requirements_block = (
            f"\n【写作要求】\n{requirements}\n" if requirements else ""
        )
        prompt = _EXPAND_USER_PROMPT.format(
            framework=framework or "（未提供）",
            section_title=section_title,
            user_ideas=user_ideas,
            references_block=references_block,
            requirements_block=requirements_block,
        )
        return self.llm_client.chat(
            system_prompt=_EXPAND_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
