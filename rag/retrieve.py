"""混合检索入口

使用 config/params.py 中的 RetrievalConfig 统一管理参数，
避免裸 top_k 在不同层级含义不一致的问题。
"""
from typing import Optional
from config.settings import settings
from config.params import RetrievalAPIParams, RetrievalConfig
from config.logging import setup_logging
from core.document import SearchResult
from core.embedding import EmbeddingClient
from storage.vector_store import MilvusStore
from storage.keyword_store import BM25Store
from storage.metadata_store import SQLiteStore
from rag.fusion import reciprocal_rank_fusion
from rag.rerank import Reranker

logger = setup_logging(__name__)


class HybridRetriever:
    """混合检索器：BM25 + 向量 + RRF + 重排序"""

    def __init__(
        self,
        embedding_client: EmbeddingClient = None,
        vector_store: MilvusStore = None,
        keyword_store: BM25Store = None,
        reranker: Reranker = None,
        metadata_store: SQLiteStore = None,
    ):
        self.embedding_client = embedding_client or EmbeddingClient()
        self.vector_store = vector_store or MilvusStore()
        self.keyword_store = keyword_store or BM25Store()
        self.keyword_store.load_index()
        self.reranker = reranker or Reranker()
        self.metadata_store = metadata_store or SQLiteStore()

    def retrieve(
        self,
        query: str,
        top_k: int = None,
        use_bm25: bool = True,
        use_vector: bool = True,
        use_rerank: bool = None,
        rrf_k: int = None,
        use_parent: bool = True,
    ) -> list[SearchResult]:
        """
        混合检索

        参数通过 RetrievalConfig 统一管理，各 top_k 语义明确：
        - final_top_k: 最终返回数
        - bm25_top_k / vector_top_k: 各源召回数
        - rerank_top_k: 重排序后保留数

        Args:
            query: 查询文本
            top_k: 最终返回结果数（覆盖 config 默认值）
            use_bm25: 是否使用 BM25
            use_vector: 是否使用向量检索
            use_rerank: 是否使用重排序
            rrf_k: RRF 平滑参数（覆盖 config 默认值）
            use_parent: 是否扩展为父文档
        """
        # 构建 API 参数（校验约束）
        api_params = RetrievalAPIParams(
            top_k=top_k or settings.retrieve_top_k,
            use_bm25=use_bm25,
            use_vector=use_vector,
            use_rerank=use_rerank if use_rerank is not None else settings.use_rerank,
            rrf_k=rrf_k or settings.rrf_k,
        )

        # 构建内部配置（自动推导各层 top_k）
        config = RetrievalConfig.from_params(api_params)

        bm25_results = []
        vector_results = []

        # 1. BM25 关键词检索
        if config.use_bm25:
            try:
                bm25_results = self.keyword_store.search(
                    query, top_k=config.bm25_top_k
                )
                logger.info(f"BM25 检索: {len(bm25_results)} 个结果")
            except Exception as e:
                logger.warning(f"BM25 检索失败: {e}")

        # 2. 向量检索
        if config.use_vector:
            try:
                query_vector = self.embedding_client.embed_one(query)
                vector_results = self.vector_store.search(
                    query_vector, top_k=config.vector_top_k
                )
                logger.info(f"向量检索: {len(vector_results)} 个结果")
            except Exception as e:
                logger.warning(f"向量检索失败: {e}")

        # 3. 融合
        if bm25_results and vector_results:
            fused_results = reciprocal_rank_fusion(
                bm25_results, vector_results, k=config.rrf_k
            )
        elif bm25_results:
            fused_results = bm25_results
        elif vector_results:
            fused_results = vector_results
        else:
            return []

        # 4. 重排序
        if config.use_rerank and fused_results:
            try:
                fused_results = self.reranker.rerank(
                    query, fused_results, top_k=config.rerank_top_k
                )
            except Exception as e:
                logger.warning(f"重排序失败: {e}")

        # 5. 🆕 父文档扩展
        if use_parent:
            fused_results = self._expand_to_parents(fused_results)

        return fused_results[: config.final_top_k]

    def _expand_to_parents(self, results: list[SearchResult]) -> list[SearchResult]:
        """将 Child 结果扩展为 Parent 结果

        - 同一 Parent 只保留一次（去重）
        - 无 parent_id 或 Parent 缺失时**降级保留 Child**：
          旧版直接丢弃这些结果，会导致「检索命中了却返回空」。
        """
        expanded = []
        seen_parents = set()

        for result in results:
            parent_id = result.chunk.metadata.get("parent_id")
            if not parent_id:
                expanded.append(result)
                continue

            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

            # 从 SQLite 读取完整 Parent
            parent = self.metadata_store.get_parent(parent_id)
            if parent:
                expanded.append(SearchResult(
                    chunk=parent,
                    score=result.score,
                    source="parent_expanded",
                    rank=result.rank,
                ))
            else:
                logger.warning(f"Parent 不存在，降级为 Child: {parent_id}")
                expanded.append(result)

        return expanded

    def reset(self):
        """清空数据"""
        self.vector_store.reset()
        self.keyword_store.reset()
