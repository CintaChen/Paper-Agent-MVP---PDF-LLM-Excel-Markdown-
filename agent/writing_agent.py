"""写作思路 Agent

使用 config/params.py 中的 AgentConfig 统一管理 LLM 调用参数，
确保所有 Agent 的 temperature、max_tokens 等参数一致且可维护。
"""
from typing import Optional
from config.logging import setup_logging
from config.params import AgentAPIParams, AgentConfig
from core.llm import LLMClient
from rag.retrieve import HybridRetriever
from agent.base_agent import BaseAgent
from agent.prompts import WRITING_SYSTEM_PROMPT

logger = setup_logging(__name__)


class WritingAgent(BaseAgent):
    """写作思路 Agent：帮助用户梳理论文写作思路"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        retriever: HybridRetriever = None,
    ):
        super().__init__(
            llm_client=llm_client,
            retriever=retriever,
            system_prompt=WRITING_SYSTEM_PROMPT,
        )

    def generate_outline(
        self,
        topic: str,
        context_query: str = None,
        top_k: int = 5,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """
        生成写作大纲

        Args:
            topic: 研究主题
            context_query: 用于检索相关文献的查询词（默认使用 topic）
            top_k: 检索文献数量
            temperature: LLM 温度（覆盖默认值）
            max_tokens: LLM 最大 token（覆盖默认值）
        """
        from agent.prompts import WRITING_OUTLINE_PROMPT

        # 使用 AgentConfig 统一参数（未指定的参数沿用默认值）
        api_params = AgentAPIParams.with_overrides(
            top_k=top_k, temperature=temperature, max_tokens=max_tokens
        )
        agent_config = AgentConfig.from_api_params(api_params)

        # 检索相关文献
        query = context_query or topic
        results = self.retrieve(query, top_k=agent_config.top_k)
        context = self.build_context(results)

        # 构建提示词
        prompt = WRITING_OUTLINE_PROMPT.format(
            topic=topic,
            context=context if context else "暂无相关文献",
        )

        # 调用 LLM（使用统一参数）
        response = self.chat(prompt, temperature=agent_config.temperature, max_tokens=agent_config.max_tokens)
        return response

    def polish_paragraph(
        self,
        topic: str,
        draft: str = "",
        context_query: str = None,
        top_k: int = 3,
        temperature: float = None,
        max_tokens: int = None,
    ) -> str:
        """
        润色段落

        Args:
            topic: 段落主题
            draft: 当前草稿
            context_query: 检索查询词
            top_k: 检索文献数量
            temperature: LLM 温度
            max_tokens: LLM 最大 token
        """
        from agent.prompts import WRITING_PARAGRAPH_PROMPT

        api_params = AgentAPIParams.with_overrides(
            top_k=top_k, temperature=temperature, max_tokens=max_tokens
        )
        agent_config = AgentConfig.from_api_params(api_params)

        query = context_query or topic
        results = self.retrieve(query, top_k=agent_config.top_k)
        context = self.build_context(results)

        prompt = WRITING_PARAGRAPH_PROMPT.format(
            topic=topic,
            context=context if context else "暂无相关文献",
            draft=draft if draft else "（无草稿，请从零撰写）",
        )

        response = self.chat(prompt, temperature=agent_config.temperature, max_tokens=agent_config.max_tokens)
        return response
