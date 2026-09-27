"""scholarAgent 统一参数规范——所有模块间接口的单一来源

本文件定义了三层参数体系：
1. API 层参数：前端请求参数，带严格约束
2. 内部层参数：后端模块间传递，复用上层约束
3. 配置层参数：环境/基础设施配置（在 config/settings.py）

变更本文件中的默认值时，请同步更新 docs/PARAMS.md。
"""

from pydantic import BaseModel, Field
from typing import Literal, Optional

# ============================================================
# 第一层：API 请求参数（前端直接传，带严格约束）
# ============================================================

class RetrievalAPIParams(BaseModel):
    """检索 API 参数——所有检索入口必须遵守

    用于：
    - api/schemas/request.py 的 SearchRequest
    - rag/retrieve.py 的 HybridRetriever.retrieve()
    """
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="最终返回结果数（经过融合和重排序后）"
    )
    use_bm25: bool = Field(
        default=True,
        description="是否启用 BM25 关键词检索"
    )
    use_vector: bool = Field(
        default=True,
        description="是否启用向量相似度检索"
    )
    use_rerank: bool = Field(
        default=True,
        description="是否启用 Cross-Encoder 重排序"
    )
    rrf_k: int = Field(
        default=60,
        ge=1,
        le=200,
        description="RRF 融合平滑参数（越大排名差异影响越小）"
    )


class ChunkingAPIParams(BaseModel):
    """分块 API 参数

    用于：
    - processors/chunker.py 的 chunk_document()
    - rag/ingest.py 的 IngestPipeline

    警告：修改分块参数后必须重建索引！
    """
    chunk_size: int = Field(
        default=500,
        ge=100,
        le=2000,
        description="每个 chunk 的最大字符数"
    )
    chunk_overlap: int = Field(
        default=50,
        ge=0,
        le=500,
        description="相邻 chunk 之间的重叠字符数"
    )
    min_chunk_length: int = Field(
        default=50,
        ge=10,
        description="小于此长度的 chunk 将被过滤"
    )


class AgentAPIParams(BaseModel):
    """Agent 调用 API 参数

    用于：
    - api/schemas/request.py 的 WritingOutlineRequest 等
    - agent/writing_agent.py 的 WritingAgent
    - agent/style_agent.py 的 StyleAgent
    """
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Agent 检索文献数量（用于构建上下文）"
    )
    temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=2.0,
        description="LLM 温度参数（越高越发散）"
    )
    max_tokens: int = Field(
        default=8192,
        ge=100,
        le=32000,
        description="LLM 最大输出 token 数"
    )
    mode: Literal["polish", "simplify", "academic"] = Field(
        default="polish",
        description="风格优化模式"
    )
    analysis_type: Literal["full", "method", "results", "limitations"] = Field(
        default="full",
        description="论文分析类型"
    )

    @classmethod
    def with_overrides(cls, **overrides) -> "AgentAPIParams":
        """用「可选覆盖」构造参数：值为 None 表示沿用默认值

        Agent 方法签名里 temperature / max_tokens 默认为 None（未指定），
        若原样透传会触发校验错误（None 不是合法数字），必须丢弃 None 项。
        """
        return cls(**{k: v for k, v in overrides.items() if v is not None})


# ============================================================
# 第二层：内部模块参数（后端各层之间传递，复用上层约束）
# ============================================================

class RetrievalConfig(BaseModel):
    """检索引擎内部配置

    由 API 参数 + settings 合并而来，供 rag/retrieve.py 内部使用。
    """
    final_top_k: int = Field(ge=1, le=50, description="最终返回结果数")
    bm25_top_k: int = Field(ge=1, le=100, description="BM25 召回数")
    vector_top_k: int = Field(ge=1, le=100, description="向量召回数")
    rerank_top_k: int = Field(ge=1, le=50, description="重排序后保留数")
    rrf_k: int = Field(ge=1, le=200, description="RRF 平滑参数")
    use_bm25: bool = True
    use_vector: bool = True
    use_rerank: bool = True

    @classmethod
    def from_params(
        cls,
        api: "RetrievalAPIParams",
        bm25_top_k: Optional[int] = None,
        vector_top_k: Optional[int] = None,
        rerank_top_k: Optional[int] = None,
    ) -> "RetrievalConfig":
        """从 API 参数生成内部配置（召回数 >= 最终数）"""
        final = api.top_k
        return cls(
            final_top_k=final,
            bm25_top_k=bm25_top_k or max(final, 10),
            vector_top_k=vector_top_k or max(final, 10),
            rerank_top_k=rerank_top_k or final,
            rrf_k=api.rrf_k,
            use_bm25=api.use_bm25,
            use_vector=api.use_vector,
            use_rerank=api.use_rerank,
        )


class AgentConfig(BaseModel):
    """Agent 内部配置

    供 agent/ 目录下各 Agent 使用，确保 LLM 调用参数一致。
    """
    top_k: int = Field(ge=1, le=20, description="检索文献数")
    temperature: float = Field(ge=0.0, le=2.0, description="LLM 温度")
    max_tokens: int = Field(ge=100, le=32000, description="LLM 最大 token 数")

    @classmethod
    def from_api_params(cls, api_params: AgentAPIParams) -> "AgentConfig":
        """从 API 参数生成 Agent 内部配置"""
        return cls(
            top_k=api_params.top_k,
            temperature=api_params.temperature,
            max_tokens=api_params.max_tokens,
        )


# ============================================================
# 第三层：Settings 扩展（从环境变量读取，覆盖 API 默认值）
# ============================================================

class RetrievalAPISettings(BaseModel):
    """检索 API 的 settings 覆盖值

    当 settings 中定义了对应环境变量时，覆盖 RetrievalAPIParams 的默认值。
    这是可选的——如果 settings 中没有，就使用 RetrievalAPIParams 的默认值。
    """
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    bm25_top_k: Optional[int] = Field(default=None, ge=1, le=100)
    vector_top_k: Optional[int] = Field(default=None, ge=1, le=100)
    rerank_top_k: Optional[int] = Field(default=None, ge=1, le=50)
    rrf_k: Optional[int] = Field(default=None, ge=1, le=200)
    use_bm25: Optional[bool] = None
    use_vector: Optional[bool] = None
    use_rerank: Optional[bool] = None


class AgentAPISettings(BaseModel):
    """Agent API 的 settings 覆盖值"""
    top_k: Optional[int] = Field(default=None, ge=1, le=20)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=100, le=32000)


def build_retrieval_config(
    retrieval_settings: Optional["RetrievalAPISettings"] = None,
) -> "RetrievalConfig":
    """构建检索配置：优先使用 settings 覆盖值，否则使用 API 默认值"""
    from config.settings import settings as app_settings
    s = retrieval_settings or RetrievalAPISettings()
    api = RetrievalAPIParams()

    # 从 settings 读取覆盖值（如果存在）
    bm25_top_k = s.bm25_top_k or app_settings.bm25_top_k
    vector_top_k = s.vector_top_k or app_settings.vector_top_k
    rerank_top_k = s.rerank_top_k or app_settings.rerank_top_k
    final_top_k = s.top_k or api.top_k

    return RetrievalConfig(
        final_top_k=final_top_k,
        bm25_top_k=max(bm25_top_k, final_top_k),
        vector_top_k=max(vector_top_k, final_top_k),
        rerank_top_k=rerank_top_k,
        rrf_k=s.rrf_k or api.rrf_k,
        use_bm25=s.use_bm25 if s.use_bm25 is not None else api.use_bm25,
        use_vector=s.use_vector if s.use_vector is not None else api.use_vector,
        use_rerank=s.use_rerank if s.use_rerank is not None else api.use_rerank,
    )


def build_agent_config(
    agent_settings: Optional["AgentAPISettings"] = None,
) -> "AgentConfig":
    """构建 Agent 配置：优先使用 settings 覆盖值，否则使用 API 默认值"""
    from config.settings import settings as app_settings
    s = agent_settings or AgentAPISettings()
    api = AgentAPIParams()

    return AgentConfig(
        top_k=s.top_k or api.top_k,
        temperature=s.temperature if s.temperature is not None else api.temperature,
        max_tokens=s.max_tokens or api.max_tokens,
    )
