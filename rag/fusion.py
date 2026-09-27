"""融合策略"""
from typing import Optional
from collections import defaultdict
from config.settings import settings
from config.logging import setup_logging
from core.document import SearchResult

logger = setup_logging(__name__)


def reciprocal_rank_fusion(
    bm25_results: list[SearchResult],
    vector_results: list[SearchResult],
    k: int = None,
) -> list[SearchResult]:
    """
    RRF（倒数排名融合）
    公式: score = Σ(1 / (k + rank))
    """
    k = k or settings.rrf_k
    scores = defaultdict(float)
    chunk_map = {}

    # BM25 结果融合
    for result in bm25_results:
        chunk_id = result.chunk.id
        scores[chunk_id] += 1.0 / (k + result.rank)
        chunk_map[chunk_id] = result.chunk

    # 向量结果融合
    for result in vector_results:
        chunk_id = result.chunk.id
        scores[chunk_id] += 1.0 / (k + result.rank)
        if chunk_id not in chunk_map:
            chunk_map[chunk_id] = result.chunk

    # 排序
    sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for rank, (chunk_id, score) in enumerate(sorted_chunks, 1):
        results.append(
            SearchResult(
                chunk=chunk_map[chunk_id],
                score=score,
                source="fusion",
                rank=rank,
            )
        )

    logger.info(
        f"RRF 融合: BM25({len(bm25_results)}) + Vector({len(vector_results)}) "
        f"→ {len(results)} 个结果"
    )
    return results


def weighted_fusion(
    bm25_results: list[SearchResult],
    vector_results: list[SearchResult],
    bm25_weight: float = 0.3,
    vector_weight: float = 0.7,
) -> list[SearchResult]:
    """加权融合"""
    scores = defaultdict(float)
    chunk_map = {}

    # 归一化 BM25 分数
    if bm25_results:
        max_bm25 = max(r.score for r in bm25_results) or 1
        for result in bm25_results:
            chunk_id = result.chunk.id
            scores[chunk_id] += bm25_weight * (result.score / max_bm25)
            chunk_map[chunk_id] = result.chunk

    # 归一化向量分数
    if vector_results:
        max_vec = max(r.score for r in vector_results) or 1
        for result in vector_results:
            chunk_id = result.chunk.id
            scores[chunk_id] += vector_weight * (result.score / max_vec)
            if chunk_id not in chunk_map:
                chunk_map[chunk_id] = result.chunk

    sorted_chunks = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for rank, (chunk_id, score) in enumerate(sorted_chunks, 1):
        results.append(
            SearchResult(
                chunk=chunk_map[chunk_id],
                score=score,
                source="fusion",
                rank=rank,
            )
        )

    return results
