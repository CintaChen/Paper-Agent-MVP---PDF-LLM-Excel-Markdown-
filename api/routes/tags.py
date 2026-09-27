"""标签管理路由"""
import time
from fastapi import APIRouter, HTTPException
from typing import Optional
from config.logging import setup_logging
from core.document import ContentTag

logger = setup_logging(__name__)
router = APIRouter()

_store = None


def get_store():
    """惰性单例：导入本模块不打开 SQLite"""
    global _store
    if _store is None:
        from storage.metadata_store import SQLiteStore

        _store = SQLiteStore()
    return _store


# 注意：静态路径（/stats、/search）必须注册在 /{doc_id} 之前。
# Starlette 按注册顺序匹配，/{doc_id} 会吞掉所有单段路径。
@router.get("/stats")
async def get_tag_stats():
    """标签统计（领域分布、主题热度）"""
    conn = get_store().conn
    cursor = conn.cursor()

    # 领域分布
    cursor.execute("""
        SELECT value, COUNT(*) as cnt, AVG(confidence) as avg_conf
        FROM content_tags WHERE tag_type = 'domain'
        GROUP BY value ORDER BY cnt DESC
    """)
    domains = [{"value": r["value"], "count": r["cnt"], "avg_confidence": round(r["avg_conf"], 2)} for r in cursor.fetchall()]

    # 主题热度（top 20）
    cursor.execute("""
        SELECT value, COUNT(*) as cnt
        FROM content_tags WHERE tag_type = 'topic'
        GROUP BY value ORDER BY cnt DESC LIMIT 20
    """)
    topics = [{"value": r["value"], "count": r["cnt"]} for r in cursor.fetchall()]

    # 方法论分布
    cursor.execute("""
        SELECT value, COUNT(*) as cnt
        FROM content_tags WHERE tag_type = 'methodology'
        GROUP BY value ORDER BY cnt DESC
    """)
    methodologies = [{"value": r["value"], "count": r["cnt"]} for r in cursor.fetchall()]

    # 来源统计
    cursor.execute("""
        SELECT source, COUNT(*) as cnt
        FROM content_tags GROUP BY source
    """)
    sources = [{"source": r["source"], "count": r["cnt"]} for r in cursor.fetchall()]

    return {
        "status": "success",
        "data": {
            "domains": domains,
            "topics": topics,
            "methodologies": methodologies,
            "sources": sources,
        },
    }


@router.get("/search")
async def search_by_tag(
    tag_type: str,
    value: str,
    limit: int = 20,
):
    """按标签搜索论文"""
    conn = get_store().conn
    cursor = conn.cursor()

    if tag_type not in {"domain", "topic", "methodology"}:
        raise HTTPException(status_code=400, detail=f"无效的 tag_type: {tag_type}")

    cursor.execute("""
        SELECT DISTINCT d.id, d.title, d.authors, d.year, ct.confidence, ct.source
        FROM content_tags ct
        JOIN documents d ON ct.doc_id = d.id
        WHERE ct.tag_type = ? AND ct.value LIKE ?
        ORDER BY ct.confidence DESC
        LIMIT ?
    """, (tag_type, f"%{value}%", limit))

    results = []
    for r in cursor.fetchall():
        results.append({
            "doc_id": r["id"],
            "title": r["title"],
            "authors": r["authors"],
            "year": r["year"],
            "confidence": r["confidence"],
            "source": r["source"],
        })

    return {
        "status": "success",
        "data": {
            "tag_type": tag_type,
            "query": value,
            "results": results,
            "total": len(results),
        },
    }


@router.get("/{doc_id}")
async def get_tags(doc_id: str):
    """获取论文的内容标签"""
    doc = get_store().get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 按 tag_type 分组
    tags_by_type = {}
    for tag in doc.content_tags:
        if tag.tag_type not in tags_by_type:
            tags_by_type[tag.tag_type] = []
        tags_by_type[tag.tag_type].append({
            "value": tag.value,
            "confidence": tag.confidence,
            "evidence": tag.evidence,
            "source": tag.source,
            "needs_review": tag.needs_review,
        })

    return {
        "status": "success",
        "data": {
            "doc_id": doc_id,
            "title": doc.title,
            "tags": tags_by_type,
            "total": len(doc.content_tags),
        },
    }


@router.put("/{doc_id}")
async def update_tags(doc_id: str, tags: list[dict]):
    """人工修正标签

    请求体格式：
    [
      {"tag_type": "domain", "value": "自然语言处理", "confidence": 1.0, "evidence": "...", "source": "manual", "needs_review": false}
    ]
    """
    doc = get_store().get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    # 验证输入
    valid_types = {"domain", "topic", "methodology"}
    new_tags = []
    for tag_data in tags:
        if tag_data.get("tag_type") not in valid_types:
            raise HTTPException(status_code=400, detail=f"无效的 tag_type: {tag_data.get('tag_type')}")
        new_tags.append(ContentTag(
            tag_type=tag_data["tag_type"],
            value=tag_data["value"],
            confidence=tag_data.get("confidence", 1.0),
            evidence=tag_data.get("evidence", ""),
            source="manual",
            needs_review=False,
        ))

    # 更新数据库
    doc.content_tags = new_tags
    get_store().save_document(doc)

    return {
        "status": "success",
        "message": f"已更新 {len(new_tags)} 个标签",
    }
