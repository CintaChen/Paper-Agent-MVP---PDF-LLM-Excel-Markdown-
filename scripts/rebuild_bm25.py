"""从 Milvus 重建 BM25 索引

用途：
    BM25 索引与向量库不同步时（例如历史版本中 chunk_map 被逐篇覆盖，
    导致倒排索引里大部分 chunk_id 在 chunk_map 中查不到），
    从 Milvus 读回全部 child 重新构建 BM25，**无需重新 embedding**。

用法（在项目根目录执行）：
    python scripts/rebuild_bm25.py
"""
import sys
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.logging import setup_logging  # noqa: E402
from core.document import Chunk  # noqa: E402
from storage.keyword_store import BM25Store  # noqa: E402
from storage.vector_store import MilvusStore  # noqa: E402

logger = setup_logging("rebuild_bm25")

BATCH_SIZE = 1000
OUTPUT_FIELDS = ["text", "doc_id", "doc_title", "parent_id", "page"]


def iter_rows(client, collection: str, batch_size: int = BATCH_SIZE) -> Iterator[dict]:
    """分页读取 Milvus 中的全部记录"""
    offset = 0
    while True:
        rows = client.query(
            collection_name=collection,
            filter="page >= 0",
            output_fields=OUTPUT_FIELDS,
            limit=batch_size,
            offset=offset,
        )
        if not rows:
            return
        yield from rows
        if len(rows) < batch_size:
            return
        offset += len(rows)


def main() -> int:
    vector_store = MilvusStore()
    collection = vector_store.collection_name

    if not vector_store.client.has_collection(collection):
        logger.error(f"集合不存在，请先导入论文: {collection}")
        return 1

    total = vector_store.count()
    logger.info(f"开始重建 BM25 索引，向量库共 {total} 个 chunk")

    bm25 = BM25Store()
    bm25.reset()

    batch: list[Chunk] = []
    processed = 0
    for row in iter_rows(vector_store.client, collection):
        batch.append(
            Chunk(
                id=row["id"],
                text=row.get("text") or "",
                page=row.get("page"),
                metadata={
                    "doc_id": row.get("doc_id", ""),
                    "doc_title": row.get("doc_title", ""),
                    "parent_id": row.get("parent_id", ""),
                    "type": "child",
                },
            )
        )
        if len(batch) >= BATCH_SIZE:
            bm25.build_index(batch)
            processed += len(batch)
            batch = []

    if batch:
        bm25.build_index(batch)
        processed += len(batch)

    if processed == 0:
        logger.warning("向量库为空，未写入索引")
        return 1

    bm25.save_index()

    docs = {c.metadata.get("doc_id") for c in bm25.chunk_map.values()}
    logger.info(
        f"重建完成: 读取 {processed} 个 chunk, "
        f"索引 {bm25.total_docs} 个文档, "
        f"{len(bm25.index)} 个词项, 覆盖 {len(docs)} 篇论文"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
