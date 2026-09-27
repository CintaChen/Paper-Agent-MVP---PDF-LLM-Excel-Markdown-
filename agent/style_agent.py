"""行文风格 Agent

使用 config/params.py 中的 AgentConfig 统一管理 LLM 调用参数。
"""
from typing import Optional
from config.logging import setup_logging
from config.params import AgentAPIParams, AgentConfig
from core.llm import LLMClient
from rag.retrieve import HybridRetriever
from agent.base_agent import BaseAgent
from agent.prompts import STYLE_SYSTEM_PROMPT

logger = setup_logging(__name__)


class StyleAgent(BaseAgent):
    """行文风格 Agent：优化论文表达"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        retriever: HybridRetriever = None,
    ):
        super().__init__(
            llm_client=llm_client,
            retriever=retriever,
            system_prompt=STYLE_SYSTEM_PROMPT,
        )

    def _get_config(self, temperature: float = None, max_tokens: int = None) -> AgentConfig:
        """获取统一 Agent 配置（未指定的参数沿用默认值）"""
        return AgentConfig.from_api_params(
            AgentAPIParams.with_overrides(
                temperature=temperature, max_tokens=max_tokens
            )
        )

    def polish(self, text: str, temperature: float = None, max_tokens: int = None) -> str:
        """润色优化"""
        from agent.prompts import STYLE_POLISH_PROMPT

        config = self._get_config(temperature, max_tokens)
        prompt = STYLE_POLISH_PROMPT.format(text=text)
        response = self.chat(prompt, temperature=config.temperature, max_tokens=config.max_tokens)
        return response

    def simplify(self, text: str, temperature: float = None, max_tokens: int = None) -> str:
        """简化表达"""
        from agent.prompts import STYLE_SIMPLIFY_PROMPT

        config = self._get_config(temperature, max_tokens)
        prompt = STYLE_SIMPLIFY_PROMPT.format(text=text)
        response = self.chat(prompt, temperature=config.temperature, max_tokens=config.max_tokens)
        return response

    def improve_academic_style(self, text: str, temperature: float = None, max_tokens: int = None) -> str:
        """提升学术风格"""
        config = self._get_config(temperature, max_tokens)

        prompt = f"""请提升以下段落的学术写作规范。

原文：
{text}

优化要求：
1. 使用更正式的学术语言
2. 确保引用规范（如需要，标注 [待引用]）
3. 避免主观表述（如"我认为"→"研究表明"）
4. 确保术语准确

请输出：
1. 优化后的版本
2. 主要修改说明"""

        response = self.chat(prompt, temperature=config.temperature, max_tokens=config.max_tokens)
        return response
