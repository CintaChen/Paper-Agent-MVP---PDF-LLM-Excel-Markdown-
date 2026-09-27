# -*- coding: utf-8 -*-
"""
改完代码后的验收脚本 —— 直接实例化你自己的 MilvusStore 跑一遍。

用法（在 E:/kunxuesuo/agent 下）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\verify_after_patch.py

它用一个临时集合 _verify_smoke，跑完自动删除，不污染你的 paper_rag。
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.document import Chunk
from core.embedding import EmbeddingClient
from storage.vector_store import MilvusStore

TEMP_COLLECTION = "_verify_smoke"
TEST_TEXTS = [
    "混合检索结合 BM25 与稠密向量，在学术语料上召回率显著提升。",
    "层次化检索先定位文档摘要，再进入段落级检索，降低长文档噪声。",
    "图神经网络用于建模引用网络，可预测论文的长期影响力。",
]


def main():
    print("=" * 60)
    print("验收：MilvusStore 是否真的连上了")
    print("=" * 60)

    # 1. 实例化（这一步就会触发连接）
    print("\n[1/5] 实例化 MilvusStore ...")
    try:
        store = MilvusStore(collection_name=TEMP_COLLECTION)
        print("      连接成功")
    except Exception as e:
        print(f"\n  [FAIL] 连不上 Milvus: {str(e)[:200]}")
        print("\n  请检查：")
        print("    1. storage/vector_store.py 第 36 行是否已改成 uri=settings.milvus_uri")
        print("    2. config/settings.py 是否新增了 milvus_uri 字段")
        print("    3. .env 是否加了 MILVUS_URI=E:/kunxuesuo/agent/storage_data/milvus.db")
        print("\n  改动清单见 _milvus_bootstrap\\MIGRATE.md")
        return 1

    # 2. 清掉上次的残留
    try:
        store.reset()
    except Exception:
        pass

    # 3. 真实 embedding
    print("\n[2/5] 生成向量 ...")
    emb = EmbeddingClient()
    vectors = emb.embed(TEST_TEXTS)
    dim = len(vectors[0])
    print(f"      维度 = {dim}")

    # 4. 建集合 + 写入
    print("\n[3/5] 建集合并写入 ...")
    store.create_collection(dim)
    chunks = [
        Chunk(id=f"v{i}", text=t, page=i + 1, metadata={"doc_id": f"vp00{i}"})
        for i, t in enumerate(TEST_TEXTS, 1)
    ]
    store.insert(chunks, vectors)
    print(f"      当前集合条数 = {store.count()}")

    # 5. 检索
    print("\n[4/5] 语义检索 ...")
    query = "BM25 和向量检索结合效果如何？"
    qv = emb.embed([query])[0]
    results = store.search(qv, top_k=3)

    print(f"      提问: {query}")
    for r in results:
        print(f"        score={r.score:.4f}  rank={r.rank}  "
              f"p{r.chunk.page}  {r.chunk.text[:28]}...")

    if not results:
        print("  [FAIL] 没检索到任何结果")
        store.reset()
        return 1

    top = results[0]
    hit_right = "BM25" in top.chunk.text

    # 6. 清理
    print("\n[5/5] 清理临时集合 ...")
    store.reset()
    print("      已清理，paper_rag 未受影响")

    # 结论
    print("\n" + "=" * 60)
    if hit_right:
        print("  全部通过 —— Milvus 已接上，可以开始导入论文了")
    else:
        print("  链路通了，但最相关的结果没排第一，")
        print("  多半是 IVF_FLAT nlist=128 索引退化，")
        print("  按 MIGRATE.md 第三节改成 HNSW 再试。")
    print("=" * 60)
    print("\n下一步:")
    print("  .venv\\Scripts\\python.exe -m cli.main ingest ./input/papers")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print("\n  [FAIL] 脚本异常：")
        traceback.print_exc()
        print("\n  改动清单见 _milvus_bootstrap\\MIGRATE.md")
        sys.exit(1)
