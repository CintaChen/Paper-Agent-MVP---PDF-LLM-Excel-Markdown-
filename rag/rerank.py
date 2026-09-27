"""重排序"""
from typing import Optional
from config.settings import settings
from config.logging import setup_logging
from core.document import SearchResult
from core.llm import LLMClient

logger = setup_logging(__name__)


class Reranker:
    """重排序器"""

    def __init__(self, method: str = "cross_encoder"):
        """
        method: "cross_encoder" | "llm"
        """
        self.method = method
        self.llm_client = None
        self.model = None  # 缓存 CrossEncoder 模型
        self._load_failed = False  # 熔断：模型不可用后不再重试

    def _load_model(self):
        """懒加载 CrossEncoder 模型（只加载一次，失败即熔断）

        模型未下载且网络不可达时，加载会触发 HuggingFace 的多次超时重试
        （实测可阻塞十几分钟）。一旦失败就置位熔断标记，后续检索直接跳过
        重排序，避免每次查询都重复等待。
        """
        if self._load_failed:
            raise RuntimeError("CrossEncoder 模型不可用（已熔断，跳过重排序）")

        if self.model is None:
            try:
                from sentence_transformers import CrossEncoder

                try:
                    # 优先只读本地缓存，避免联网等待
                    self.model = CrossEncoder(
                        settings.rerank_model, local_files_only=True
                    )
                except TypeError:
                    # 旧版本不支持该参数时回退
                    self.model = CrossEncoder(settings.rerank_model)

                logger.info(f"CrossEncoder 模型加载完成: {settings.rerank_model}")
            except Exception as e:
                self._load_failed = True
                logger.warning(
                    f"CrossEncoder 模型加载失败，本进程内不再重试: {e}"
                )
                raise
        return self.model

    def rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int = None,
    ) -> list[SearchResult]:
        """重排序"""
        top_k = top_k or settings.rerank_top_k

        if not results:
            return []

        if self.method == "llm":
            return self._llm_rerank(query, results, top_k)
        else:
            return self._cross_encoder_rerank(query, results, top_k)

    def _cross_encoder_rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """
        Cross-Encoder 重排序
        使用 bge-reranker-v2-m3 等模型
        """
        try:
            model = self._load_model()
            pairs = [(query, r.chunk.text) for r in results]
            scores = model.predict(pairs)

            # 重新排序
            for result, score in zip(results, scores):
                result.score = float(score)
                result.source = "rerank"

            results.sort(key=lambda x: x.score, reverse=True)

            # 更新排名
            for rank, result in enumerate(results[:top_k], 1):
                result.rank = rank

            logger.info(f"Cross-Encoder 重排序完成: {len(results)} → {top_k}")
            return results[:top_k]

        except Exception as e:
            if self._load_failed:
                logger.debug(f"重排序不可用，跳过: {e}")
            else:
                logger.warning(f"Cross-Encoder 重排序失败: {e}，跳过重排序")
            return results[:top_k]

    def _llm_rerank(
        self,
        query: str,
        results: list[SearchResult],
        top_k: int,
    ) -> list[SearchResult]:
        """LLM 重排序"""
        if not self.llm_client:
            self.llm_client = LLMClient()

        # 构建重排序提示词
        context = "\n\n".join(
            f"[文档 {i+1}]\n{r.chunk.text[:500]}"
            for i, r in enumerate(results[:10])
        )

        prompt = f"""请根据以下查询，对文档按相关性排序（最相关排前面）。

查询：{query}

文档：
{context}

请返回排序后的文档编号列表（如：3,1,2,...），只返回编号，不要其他内容。"""

        try:
            response = self.llm_client.chat(
                system_prompt="你是一个专业的文档重排序助手。",
                user_prompt=prompt,
            )
            # 解析排序结果
            order = [
                int(x.strip()) - 1
                for x in response.split(",")
                if x.strip().isdigit()
            ]

            # 重新排列
            reranked = []
            for idx in order:
                if 0 <= idx < len(results):
                    reranked.append(results[idx])

            # 添加未排序的结果
            for r in results:
                if r not in reranked:
                    reranked.append(r)

            # 更新排名
            for rank, result in enumerate(reranked[:top_k], 1):
                result.rank = rank
                result.source = "rerank"

            logger.info(f"LLM 重排序完成: {len(results)} → {top_k}")
            return reranked[:top_k]

        except Exception as e:
            logger.error(f"LLM 重排序失败: {e}")
            return results[:top_k]
