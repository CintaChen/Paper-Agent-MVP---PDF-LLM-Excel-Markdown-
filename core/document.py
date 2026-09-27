"""文档数据模型"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Chunk(BaseModel):
    """文本块"""
    id: str = Field(..., description="唯一标识")
    text: str = Field(..., description="文本内容")
    page: Optional[int] = Field(None, description="页码")
    start_pos: Optional[int] = Field(None, description="起始位置")
    end_pos: Optional[int] = Field(None, description="结束位置")
    metadata: dict = Field(default_factory=dict, description="元数据")


class ContentTag(BaseModel):
    """内容标签 — 一行一个 tag（domain/topic/methodology）"""
    tag_type: str = Field(..., description="标签类型: domain | topic | methodology")
    value: str = Field(..., description="标签值")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    evidence: str = Field(default="", description="标签依据（原文摘录，不超过 60 字）")
    source: str = Field(default="pdf_keywords", description="来源: pdf_keywords | llm_extracted | manual")
    needs_review: bool = Field(default=False, description="是否需要人工确认")


class Document(BaseModel):
    """文档"""
    id: str = Field(..., description="唯一标识")
    title: str = Field(..., description="标题")
    authors: list[str] = Field(default_factory=list, description="作者")
    year: Optional[str] = Field(None, description="年份")
    journal: Optional[str] = Field(None, description="期刊")
    doi: Optional[str] = Field(None, description="DOI")
    file_path: Optional[str] = Field(None, description="文件路径")
    total_pages: int = Field(0, description="总页数")
    chunks: list[Chunk] = Field(default_factory=list, description="文本块列表")
    content_tags: list[ContentTag] = Field(default_factory=list, description="内容标签列表")
    created_at: datetime = Field(
        default_factory=datetime.now, description="创建时间"
    )
    metadata: dict = Field(default_factory=dict, description="扩展元数据")


class SearchResult(BaseModel):
    """检索结果"""
    chunk: Chunk = Field(..., description="文本块")
    score: float = Field(..., description="相关性分数")
    source: str = Field(..., description="来源: bm25/vector/fusion/rerank")
    rank: int = Field(0, description="排名")
