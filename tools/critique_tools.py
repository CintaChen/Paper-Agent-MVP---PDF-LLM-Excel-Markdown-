"""质检类工具

支撑"写的达不到要点就重写"：对生成内容做结构化自评，
主 Agent 据此决定是否重新调用写作工具。
"""
from typing import Any, Optional

from config.logging import setup_logging
from tools.base import Tool

logger = setup_logging(__name__)


_CRITIQUE_SYSTEM_PROMPT = """你是一名严格的学术写作审稿人。
你的任务是判断一段正文是否达到了作者给定的要点与要求。

只输出 JSON，不要输出任何其他内容。JSON 结构：
{
  "passed": true/false,
  "score": 0-10 的整数,
  "issues": ["未达标的点"],
  "suggestions": ["具体修改建议"]
}
"""

_CRITIQUE_USER_PROMPT = """【作者要求 / 要点】
{requirements}

【上下文（框架或思路，可选）】
{context}

【待评审正文】
{content}

请评审正文是否达到要求，按指定 JSON 输出。"""


class SelfCritiqueTool(Tool):
    """自评：检查正文是否覆盖要点、逻辑是否连贯"""

    name = "self_critique"
    description = (
        "评审一段正文是否达到作者要求（要点覆盖、逻辑连贯、有无编造）。"
        "在生成正文后调用；当 passed 为 false 时，应参考 issues 与 suggestions 重新生成。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "待评审的正文",
            },
            "requirements": {
                "type": "string",
                "description": "作者要求或要点清单",
            },
            "context": {
                "type": "string",
                "description": "可选上下文（框架、思路、前文）",
            },
        },
        "required": ["content", "requirements"],
    }

    def __init__(self, llm_client: Any = None):
        self._llm_client = llm_client

    @property
    def llm_client(self):
        if self._llm_client is None:
            from core.llm import LLMClient

            self._llm_client = LLMClient()
        return self._llm_client

    def run(self, content: str, requirements: str, context: str = "") -> dict:
        from rag.tag_extractor import safe_parse_json

        prompt = _CRITIQUE_USER_PROMPT.format(
            requirements=requirements,
            context=context or "（无）",
            content=content,
        )
        raw = self.llm_client.chat(
            system_prompt=_CRITIQUE_SYSTEM_PROMPT,
            user_prompt=prompt,
        )
        parsed = safe_parse_json(raw)
        if not parsed:
            # 解析失败时不武断判定，交由主 Agent 处理
            return {
                "passed": None,
                "parse_error": True,
                "raw": raw,
            }
        return {
            "passed": bool(parsed.get("passed", False)),
            "score": parsed.get("score"),
            "issues": parsed.get("issues", []),
            "suggestions": parsed.get("suggestions", []),
        }
