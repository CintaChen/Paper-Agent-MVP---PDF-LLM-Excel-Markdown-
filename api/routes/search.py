"""检索路由"""
import time
from fastapi import APIRouter, HTTPException
from api.schemas.request import SearchRequest

router = APIRouter()

_retriever = None


def get_retriever():
    """惰性单例：导入本模块不连接 Milvus / BM25"""
    global _retriever
    if _retriever is None:
        from rag.retrieve import HybridRetriever

        _retriever = HybridRetriever()
    return _retriever


@router.post("")
async def search(request: SearchRequest):
    """混合检索"""
    start = time.time()
    try:
        results = get_retriever().retrieve(
            query=request.query,
            top_k=request.top_k,
            use_bm25=request.use_bm25,
            use_vector=request.use_vector,
            use_rerank=request.use_rerank,
        )

        return {
            "status": "success",
            "data": {
                "query": request.query,
                "results": [
                    {
                        "chunk": {
                            "id": r.chunk.id,
                            "text": r.chunk.text,
                            "page": r.chunk.page,
                            "metadata": r.chunk.metadata,
                        },
                        "score": r.score,
                        "source": r.source,
                        "rank": r.rank,
                    }
                    for r in results
                ],
                "total_found": len(results),
                "duration_ms": int((time.time() - start) * 1000),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/vector")
async def vector_search(request: SearchRequest):
    """仅向量检索"""
    start = time.time()
    try:
        results = get_retriever().retrieve(
            query=request.query,
            top_k=request.top_k,
            use_bm25=False,
            use_vector=True,
            use_rerank=False,
        )

        return {
            "status": "success",
            "data": {
                "query": request.query,
                "results": [
                    {
                        "chunk": {
                            "id": r.chunk.id,
                            "text": r.chunk.text,
                            "page": r.chunk.page,
                        },
                        "score": r.score,
                        "source": r.source,
                        "rank": r.rank,
                    }
                    for r in results
                ],
                "duration_ms": int((time.time() - start) * 1000),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/keyword")
async def keyword_search(request: SearchRequest):
    """仅关键词检索"""
    start = time.time()
    try:
        results = get_retriever().retrieve(
            query=request.query,
            top_k=request.top_k,
            use_bm25=True,
            use_vector=False,
            use_rerank=False,
        )

        return {
            "status": "success",
            "data": {
                "query": request.query,
                "results": [
                    {
                        "chunk": {
                            "id": r.chunk.id,
                            "text": r.chunk.text,
                            "page": r.chunk.page,
                        },
                        "score": r.score,
                        "source": r.source,
                        "rank": r.rank,
                    }
                    for r in results
                ],
                "duration_ms": int((time.time() - start) * 1000),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
