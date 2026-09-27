"""文档导入流水线"""
import uuid
from pathlib import Path
from typing import Callable, Optional
from config.settings import settings
from config.logging import setup_logging
from core.document import Document, Chunk
from core.embedding import EmbeddingClient
from readers.pdf_reader import PDFReader
from storage.vector_store import MilvusStore
from storage.keyword_store import BM25Store
from storage.metadata_store import SQLiteStore

# 进度回调：(阶段, 百分比 0-100, 文字说明)
ProgressCallback = Callable[[str, int, str], None]

logger = setup_logging(__name__)


class IngestPipeline:
    """文档导入流水线：读取 → 分块 → 向量化 → 存储"""

    def __init__(
        self,
        embedding_client: EmbeddingClient = None,
        vector_store: MilvusStore = None,
        keyword_store: BM25Store = None,
        metadata_store: SQLiteStore = None,
    ):
        self.embedding_client = embedding_client or EmbeddingClient()
        self.vector_store = vector_store or MilvusStore()
        self.keyword_store = keyword_store or BM25Store()
        self.metadata_store = metadata_store or SQLiteStore()
        self.reader = PDFReader()

    def ingest(
        self,
        file_path: str,
        force: bool = False,
        progress: ProgressCallback = None,
    ) -> Optional[Document]:
        """
        导入单个 PDF 文件（支持断点续传）

        Args:
            file_path: PDF 文件路径
            force: 是否强制重新导入（忽略已有状态）
            progress: 进度回调 (阶段, 百分比, 文字说明)
        """

        def emit(stage: str, percent: int, message: str) -> None:
            logger.info(f"[{stage}] {message}")
            if progress is not None:
                try:
                    progress(stage, percent, message)
                except Exception:  # noqa: BLE001 - 进度上报不应中断导入
                    pass

        # 生成 doc_id
        doc_id = self.reader._make_doc_id(file_path)

        # 检查是否已完成（除非强制重导）
        if not force:
            existing_status = self.metadata_store.get_ingest_status(doc_id)
            if existing_status == "completed":
                logger.info(f"跳过已完成论文: {file_path}")
                emit("skipped", 100, "该文件已导入完成，跳过")
                return None

        try:
            # 0. 先登记文档行，确保后续状态更新（UPDATE）有行可改，
            #    中途失败时 "failed" 才能落库、被 retry_failed() 找到
            self.metadata_store.register_document(doc_id, file_path)

            # 1. 读取 PDF
            emit("reading", 5, f"开始解析 PDF：{Path(file_path).name}")
            self.metadata_store.update_ingest_status(doc_id, "reading")
            doc = self.reader.read(file_path)
            emit("reading", 15, f"解析完成：{doc.title}（{doc.total_pages} 页）")

            # 2. 提取内容标签
            emit("tagging", 20, "提取内容标签（PDF 关键词 + LLM）…")
            self.metadata_store.update_ingest_status(doc_id, "tagging")
            from rag.tag_extractor import ContentTagExtractor
            tag_extractor = ContentTagExtractor()
            doc.content_tags = tag_extractor.extract(doc)
            emit("tagging", 35, f"标签提取完成：{len(doc.content_tags)} 个")

            # 3. 父子分块
            emit("chunking", 38, "父子分块…")
            self.metadata_store.update_ingest_status(doc_id, "chunking")
            from processors.chunker import parent_child_chunking
            parents, children = parent_child_chunking(doc)
            emit(
                "chunking",
                45,
                f"分块完成：{len(parents)} 个父块 / {len(children)} 个子块",
            )

            # 4. 向量化
            self.metadata_store.update_ingest_status(doc_id, "embedding")
            if children:
                texts = [c.text for c in children]
                total = len(texts)
                emit("embedding", 48, f"开始向量化 {total} 个片段（Embedding 最耗时）…")

                def on_batch(done: int, all_count: int) -> None:
                    # 向量化占总进度 48% → 88%
                    percent = 48 + int(40 * done / max(all_count, 1))
                    emit("embedding", min(percent, 88), f"向量化 {done}/{all_count}")

                vectors = self.embedding_client.embed(texts, on_progress=on_batch)

                # 5. 存储
                emit("storing", 90, "写入向量库 / 父块 / BM25 索引…")
                dimension = len(vectors[0])
                self.vector_store.create_collection(dimension)
                self.vector_store.insert(children, vectors)
                self.metadata_store.save_parents(parents)
                self.keyword_store.build_index(children)
                self.keyword_store.save_index()
                self.metadata_store.save_document(doc)
                emit("storing", 97, "索引写入完成")

            # 标记完成
            self.metadata_store.update_ingest_status(doc_id, "completed")
            emit("completed", 100, f"导入完成：{doc.title}")
            return doc

        except Exception as e:
            # 标记失败
            error_msg = str(e)[:500]
            self.metadata_store.update_ingest_status(doc_id, "failed", error_msg)
            emit("failed", 0, f"导入失败：{e}")
            logger.error(f"导入失败: {file_path} - {e}")
            raise

    def ingest_directory(
        self,
        dir_path: str,
        force: bool = False,
        progress: ProgressCallback = None,
    ) -> list[Document]:
        """
        批量导入目录（支持断点续传）

        Args:
            dir_path: 目录路径
            force: 是否强制重新导入全部
            progress: 进度回调 (阶段, 百分比, 文字说明)
        """
        dir_path = Path(dir_path)
        if not dir_path.exists():
            raise FileNotFoundError(f"目录不存在: {dir_path}")

        pdf_files = list(dir_path.glob("*.pdf"))
        total_files = len(pdf_files)
        logger.info(f"发现 {total_files} 个 PDF 文件")

        skipped = 0
        success = 0
        failed = 0

        docs = []
        for i, pdf_path in enumerate(pdf_files, 1):
            logger.info(f"[{i}/{total_files}] 处理: {pdf_path.name}")

            # 把「第几篇」与篇内进度合成整体进度
            def per_file(stage: str, percent: int, message: str, index: int = i) -> None:
                if progress is None:
                    return
                overall = int(((index - 1) + percent / 100) * 100 / max(total_files, 1))
                try:
                    progress(stage, min(overall, 100), f"[{index}/{total_files}] {message}")
                except Exception:  # noqa: BLE001
                    pass

            try:
                doc = self.ingest(str(pdf_path), force=force, progress=per_file)
                if doc:
                    docs.append(doc)
                    success += 1
                else:
                    skipped += 1
            except Exception as e:
                failed += 1
                logger.error(f"导入失败: {pdf_path.name} - {e}")
                continue

        logger.info(f"批量导入完成: 成功 {success}, 跳过 {skipped}, 失败 {failed}")
        return docs

    def retry_failed(self) -> list[Document]:
        """重试所有失败的论文"""
        incomplete = self.metadata_store.get_incomplete_docs()
        failed_docs = [d for d in incomplete if d["status"] == "failed"]

        logger.info(f"发现 {len(failed_docs)} 篇失败论文，开始重试")

        docs = []
        for item in failed_docs:
            try:
                doc = self.ingest(item["file_path"], force=True)
                if doc:
                    docs.append(doc)
            except Exception as e:
                logger.error(f"重试失败: {item['file_path']} - {e}")

        return docs

    def reset(self):
        """清空所有数据（向量 / 关键词 / 元数据）

        三者必须一起清：只清向量与关键词，SQLite 里的 `status` 仍是
        `completed`，重新导入会被断点续传整体跳过。
        """
        self.vector_store.reset()
        self.keyword_store.reset()
        self.metadata_store.reset()
        logger.info("已清空所有数据")
