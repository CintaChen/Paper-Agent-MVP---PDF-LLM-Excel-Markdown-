"""API 请求/响应模型

所有请求模型继承自 config/params.py 的参数约束，
确保前后端参数一致、有范围校验。
"""
from pydantic import BaseModel, Field
from typing import Literal, Optional
from config.params import (
    RetrievalAPIParams,
    AgentAPIParams,
)


# ============================================================
# 导入相关请求
# ============================================================

class IngestFileRequest(BaseModel):
    file_path: str


class IngestDirectoryRequest(BaseModel):
    dir_path: str
    recursive: bool = False


# ============================================================
# 检索请求（继承 RetrievalAPIParams 的约束）
# ============================================================

class SearchRequest(RetrievalAPIParams):
    """混合检索请求

    继承自 RetrievalAPIParams：
    - top_k: 1-50，默认 10
    - use_bm25: 默认 True
    - use_vector: 默认 True
    - use_rerank: 默认 True
    - rrf_k: 1-200，默认 60
    """
    query: str = Field(..., min_length=1, description="检索查询文本")
    filters: Optional[dict] = None


# ============================================================
# Agent 请求（继承 AgentAPIParams 的约束）
# ============================================================

class WritingOutlineRequest(AgentAPIParams):
    """写作大纲请求

    继承自 AgentAPIParams：
    - top_k: 1-20，默认 5
    - temperature: 0-2，默认 0.2
    - max_tokens: 100-32000，默认 8192
    """
    topic: str = Field(..., min_length=1, description="研究主题")
    context_query: Optional[str] = None
    # top_k 覆盖为写作场景的更合理默认值
    top_k: int = Field(default=5, ge=1, le=20, description="检索文献数量")


class WritingParagraphRequest(AgentAPIParams):
    """段落润色请求"""
    topic: str = Field(..., min_length=1, description="段落主题")
    draft: str = ""
    context_query: Optional[str] = None
    top_k: int = Field(default=3, ge=1, le=20, description="检索文献数量")


class StyleRequest(AgentAPIParams):
    """风格优化请求

    继承自 AgentAPIParams：
    - mode: Literal["polish", "simplify", "academic"]
    """
    text: str = Field(..., min_length=1, description="待优化文本")
    # mode 已在 AgentAPIParams 中约束


class AnalysisRequest(AgentAPIParams):
    """论文分析请求

    继承自 AgentAPIParams：
    - analysis_type: Literal["full", "method", "results", "limitations"]
    """
    doc_id: str = Field(..., min_length=1, description="文档 ID")


# ============================================================
# 主 Agent（Orchestrator）请求
# ============================================================

class SectionRequest(BaseModel):
    """已完成章节"""
    title: str = Field(..., min_length=1, description="章节标题")
    content: str = Field(default="", description="章节正文")


class WritingContextRequest(BaseModel):
    """写作上下文（框架 / 思路 / 已完成章节）

    保证主 Agent 扩写后续章节时能看到全篇脉络，避免跑偏。
    """
    topic: str = Field(default="", description="论文主题")
    framework: str = Field(default="", description="整体框架")
    ideas: str = Field(default="", description="作者的思路（必须遵循）")
    requirements: str = Field(default="", description="写作要求")
    sections: list[SectionRequest] = Field(
        default_factory=list, description="已完成章节"
    )

    def to_context(self):
        """转换为 agent.context.WritingContext"""
        from agent.context import WritingContext

        context = WritingContext(
            topic=self.topic,
            framework=self.framework,
            ideas=self.ideas,
            requirements=self.requirements,
        )
        for section in self.sections:
            context.add_section(section.title, section.content)
        return context


class ChatMessage(BaseModel):
    """历史消息（OpenAI 消息格式子集）"""
    role: Literal["user", "assistant"] = Field(..., description="角色")
    content: str = Field(..., description="内容")


class AgentChatRequest(BaseModel):
    """主 Agent 对话请求

    上下文二选一：
    - context: 结构化写作上下文（推荐）
    - context_text: 纯文本上下文
    """
    message: str = Field(..., min_length=1, description="用户本次请求")
    session_id: Optional[str] = Field(
        default=None,
        description=(
            "会话 ID。传入则续接该会话（自动恢复历史与写作上下文）；"
            "不传则新建会话，并在响应中返回新 ID。"
        ),
    )
    context: Optional[WritingContextRequest] = Field(
        default=None, description="结构化写作上下文"
    )
    context_text: Optional[str] = Field(
        default=None, description="纯文本上下文（与 context 二选一）"
    )
    history: list[ChatMessage] = Field(
        default_factory=list, description="历史消息，用于多轮会话"
    )
    max_iterations: Optional[int] = Field(
        default=None, ge=1, le=20, description="最大工具调用轮数"
    )

    def build_context(self):
        """构建上下文对象（无上下文时返回 None）"""
        if self.context is not None:
            return self.context.to_context()
        return self.context_text or None

    def history_messages(self) -> Optional[list[dict]]:
        """历史消息转为 OpenAI 格式（空则返回 None）"""
        if not self.history:
            return None
        return [message.model_dump() for message in self.history]


# ============================================================
# 响应模型
# ============================================================

class AgentResponse(BaseModel):
    status: str = "success"
    data: Optional[dict] = None
    message: str = ""
    duration_ms: int = 0


def make_response(data: dict, message: str = "") -> dict:
    """统一构造成功响应"""
    return AgentResponse(status="success", data=data, message=message).model_dump()


def make_error(message: str, code: str = "ERROR", details: dict = None) -> dict:
    """统一构造错误响应"""
    return {
        "status": "error",
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }
