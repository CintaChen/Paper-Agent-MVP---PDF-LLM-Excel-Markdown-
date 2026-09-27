"""Agent 路由"""
import time
from fastapi import APIRouter, HTTPException
from api.schemas.request import (
    WritingOutlineRequest,
    WritingParagraphRequest,
    StyleRequest,
    AnalysisRequest,
)
router = APIRouter()

_writing_agent = None
_style_agent = None
_analysis_agent = None
_metadata_store = None


def get_writing_agent():
    """惰性单例：导入本模块不初始化检索栈与 LLM"""
    global _writing_agent
    if _writing_agent is None:
        from agent.writing_agent import WritingAgent

        _writing_agent = WritingAgent()
    return _writing_agent


def get_style_agent():
    """惰性单例：导入本模块不初始化检索栈与 LLM"""
    global _style_agent
    if _style_agent is None:
        from agent.style_agent import StyleAgent

        _style_agent = StyleAgent()
    return _style_agent


def get_metadata_store():
    """惰性单例：导入本模块不打开 SQLite"""
    global _metadata_store
    if _metadata_store is None:
        from storage.metadata_store import SQLiteStore

        _metadata_store = SQLiteStore()
    return _metadata_store


def get_analysis_agent():
    """惰性单例：导入本模块不初始化分析 Agent"""
    global _analysis_agent
    if _analysis_agent is None:
        from agent.analysis_agent import AnalysisAgent

        _analysis_agent = AnalysisAgent()
    return _analysis_agent


# === 写作 Agent ===

@router.post("/writing/outline")
async def writing_outline(request: WritingOutlineRequest):
    """生成写作大纲"""
    start = time.time()
    try:
        response = get_writing_agent().generate_outline(
            topic=request.topic,
            context_query=request.context_query,
            top_k=request.top_k,
        )
        return {
            "status": "success",
            "data": {
                "topic": request.topic,
                "outline": response,
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/writing/paragraph")
async def writing_paragraph(request: WritingParagraphRequest):
    """段落润色"""
    start = time.time()
    try:
        response = get_writing_agent().polish_paragraph(
            topic=request.topic,
            draft=request.draft,
            context_query=request.context_query,
            top_k=request.top_k,
        )
        return {
            "status": "success",
            "data": {
                "original": request.draft,
                "polished": response,
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === 风格 Agent ===

@router.post("/style/polish")
async def style_polish(request: StyleRequest):
    """风格优化"""
    start = time.time()
    try:
        if request.mode == "simplify":
            response = get_style_agent().simplify(request.text)
        elif request.mode == "academic":
            response = get_style_agent().improve_academic_style(request.text)
        else:
            response = get_style_agent().polish(request.text)

        return {
            "status": "success",
            "data": {
                "original": request.text,
                "optimized": response,
                "mode": request.mode,
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# === 分析 Agent ===

@router.post("/analysis/analyze")
async def analysis_analyze(request: AnalysisRequest):
    """论文分析：结构化抽取研究方法 / 关键发现 / 局限性

    响应结构见 docs/API_DESIGN.md §4.5.4。
    """
    start = time.time()
    try:
        analysis = get_analysis_agent().analyze(
            doc_id=request.doc_id,
            analysis_type=request.analysis_type,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        return {
            "status": "success",
            "data": {
                "doc_id": request.doc_id,
                "analysis": analysis,
            },
            "duration_ms": int((time.time() - start) * 1000),
        }
    except ValueError as e:
        # 文档不存在 / analysis_type 非法
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
