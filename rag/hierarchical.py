"""层次化检索（预留）"""
from typing import Optional
from config.logging import setup_logging
from core.document import SearchResult

logger = setup_logging(__name__)


def hierarchical_retrieve(
    query: str,
    coarse_retriever,
    fine_retriever,
    reranker,
    coarse_top_k: int = 50,
    fine_top_k: int = 10,
) -> list[SearchResult]:
    """
    层次化检索：先粗筛后精筛
    - 粗筛：快速召回大量候选（如向量检索 top-50）
    - 精筛：对候选进行精细重排序（如 Cross-Encoder）

    适用于大批量论文场景（>1000篇）
    """
    # 第一步：粗筛
    logger.info(f"层次化检索 - 粗筛: top-{coarse_top_k}")
    coarse_results = coarse_retriever(query, top_k=coarse_top_k)

    if not coarse_results:
        return []

    # 第二步：精筛
    logger.info(f"层次化检索 - 精筛: {len(coarse_results)} → top-{fine_top_k}")
    final_results = reranker.rerank(query, coarse_results, top_k=fine_top_k)

    return final_results
