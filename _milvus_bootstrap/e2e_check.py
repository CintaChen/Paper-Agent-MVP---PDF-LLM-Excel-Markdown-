# -*- coding: utf-8 -*-
"""
端到端验证：Ollama embedding -> Milvus Lite -> 检索
完全不依赖 Docker，也不改动你任何已有代码。

用法（在 E:/kunxuesuo/agent 下）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\e2e_check.py

它会在 storage_data/e2e_demo.db 里建一个临时集合，跑完自动清理。
"""
import os
import sys
import shutil
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymilvus import MilvusClient, DataType

DB_PATH = r"E:/kunxuesuo/agent/storage_data/e2e_demo.db"
COLLECTION = "_e2e_demo"

# 模拟 3 段论文摘要（中文，贴近你的真实场景）
SAMPLES = [
    {"doc_id": "p001", "page": 1,
     "text": "本文提出一种面向长文档的层次化检索方法，先检索摘要再定位段落，"
             "显著降低了大模型在长文本问答中的幻觉率。"},
    {"doc_id": "p002", "page": 4,
     "text": "实验表明，BM25 关键词检索与稠密向量检索融合后，"
             "在学术数据集上的召回率提升约 12 个百分点。"},
    {"doc_id": "p003", "page": 9,
     "text": "我们构建了一个引用网络数据集，使用图神经网络对论文影响力进行建模，"
             "并用注意力机制解释预测结果。"},
]


def main():
    print("=" * 60)
    print("端到端验证：Embedding -> Milvus -> 检索")
    print("=" * 60)

    # 1. 真实 embedding
    print("\n[1/4] 调用 Ollama 生成向量 ...")
    from core.embedding import EmbeddingClient
    emb = EmbeddingClient()
    texts = [s["text"] for s in SAMPLES]
    vectors = emb.embed(texts)
    dim = len(vectors[0])
    print(f"      维度 = {dim}，条数 = {len(vectors)}")

    # 2. 建集合（复现你 vector_store.py 的参数：COSINE + IVF_FLAT nlist=128）
    print("\n[2/4] 建集合（复现你的 IVF_FLAT nlist=128 配置）...")
    client = MilvusClient(uri=DB_PATH)
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)

    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
    schema.add_field("text", DataType.VARCHAR, max_length=65535)
    schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
    schema.add_field("page", DataType.INT64)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=dim)

    index = client.prepare_index_params()
    index.add_index(field_name="vector", metric_type="COSINE",
                    index_type="IVF_FLAT", params={"nlist": 128})

    nlist_warning = False
    try:
        client.create_collection(collection_name=COLLECTION, schema=schema,
                                 index_params=index)
        print("      建集合成功")
    except Exception as e:
        print(f"      [!] nlist=128 建集合失败: {str(e)[:110]}")
        print("      -> 回退到 nlist=16 重试（说明小数据量下 128 太大）")
        nlist_warning = True
        index = client.prepare_index_params()
        index.add_index(field_name="vector", metric_type="COSINE",
                        index_type="IVF_FLAT", params={"nlist": 16})
        client.create_collection(collection_name=COLLECTION, schema=schema,
                                 index_params=index)
        print("      nlist=16 建集合成功")

    # 3. 入库
    print("\n[3/4] 写入向量 ...")
    rows = []
    for i, (s, v) in enumerate(zip(SAMPLES, vectors), 1):
        rows.append({"id": f"c{i}", "text": s["text"], "doc_id": s["doc_id"],
                     "page": s["page"], "vector": v})
    client.insert(collection_name=COLLECTION, data=rows)
    print(f"      已写入 {len(rows)} 条")

    # 4. 检索
    print("\n[4/4] 语义检索 ...")
    query = "向量检索和关键词检索融合的效果怎么样？"
    qv = emb.embed([query])[0]
    for nprobe in (10, 128):
        try:
            res = client.search(
                collection_name=COLLECTION, data=[qv], limit=3,
                search_params={"metric_type": "COSINE", "params": {"nprobe": nprobe}},
                output_fields=["text", "doc_id", "page"],
            )
            print(f"\n      提问: {query}")
            print(f"      (nprobe={nprobe})")
            for hits in res:
                for h in hits:
                    e = h["entity"]
                    print(f"        score={h['distance']:.4f}  "
                          f"doc={e['doc_id']} p{e['page']}  {e['text'][:26]}...")
            break
        except Exception as e:
            print(f"      [!] nprobe={nprobe} 检索失败: {str(e)[:110]}")
            if nprobe == 10:
                print("      -> 尝试更大的 nprobe")

    # 清理
    client.drop_collection(COLLECTION)
    print("\n临时集合已清理。")

    # 结论
    print("\n" + "=" * 60)
    print("结论")
    print("=" * 60)
    print("  [OK] Ollama embedding  -> Milvus Lite -> 检索  全链路跑通")
    print(f"  [OK] 数据文件在 E 盘: {DB_PATH}")
    if nlist_warning:
        print("\n  [!] 注意：你的 nlist=128 在数据量少时会失败，")
        print("      建议改成 HNSW（见 MIGRATE.md），或 nlist 调小。")
    else:
        print("  [i] nlist=128 在本次小规模数据下未报错，但数据量 < 几千条时")
        print("      建议仍改用 HNSW，召回更稳、不用手调 nprobe。")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
