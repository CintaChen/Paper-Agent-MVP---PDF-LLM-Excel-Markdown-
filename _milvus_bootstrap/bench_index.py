# -*- coding: utf-8 -*-
"""
索引选型基准测试：不同数据量下 HNSW / IVF_FLAT / FLAT 的表现。

用法（在 E:/kunxuesuo/agent 下）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\bench_index.py

用带簇结构的合成向量（贴近真实 embedding 分布），
以 FLAT 暴力检索结果为标准答案，比较召回率与延迟。
测试库放在 E 盘 storage_data/_bench.db，跑完自动清理。
"""
import os
import time
import shutil
import numpy as np
from pymilvus import MilvusClient, DataType

DB_PATH = r"E:/kunxuesuo/agent/storage_data/_bench2.db"
DIM = 768
N = 3000
N_QUERY = 20
TOP_K = 10
N_CLUSTERS = 25
WARMUP = 3


def make_data(n, dim, seed=42):
    """生成带簇结构的向量，贴近真实 embedding 分布"""
    rng = np.random.default_rng(seed)
    centers = rng.normal(size=(N_CLUSTERS, dim)).astype(np.float32)
    centers /= np.linalg.norm(centers, axis=1, keepdims=True)
    labels = rng.integers(0, N_CLUSTERS, n)
    vecs = centers[labels] + rng.normal(scale=0.35, size=(n, dim)).astype(np.float32)
    vecs = vecs.astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs, labels


def build(client, name, vecs, index_params):
    if client.has_collection(name):
        client.drop_collection(name)
    schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field("id", DataType.INT64, is_primary=True)
    schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIM)
    idx = client.prepare_index_params()
    idx.add_index(field_name="vector", metric_type="COSINE", **index_params)
    client.create_collection(collection_name=name, schema=schema,
                             index_params=idx)
    B = 500
    t0 = time.perf_counter()
    for i in range(0, vecs.shape[0], B):
        batch = vecs[i:i + B]
        rows = [{"id": i + j, "vector": v} for j, v in enumerate(batch)]
        client.insert(collection_name=name, data=rows)
    # 注意：这里不显式 flush。Milvus Lite 在进程内 insert 后即可查，
    # 显式 flush 会触发 WAL 文件删除，在某些受管控环境（回收站不可用）
    # 会抛 safe-delete 错误。真实使用请保留 flush 以保证持久化。
    return time.perf_counter() - t0


def query(client, name, qvecs, params, limit=TOP_K, warmup=WARMUP):
    """先 warmup 再计时，避免把索引首次加载算进延迟"""
    for q in qvecs[:warmup]:
        client.search(collection_name=name, data=[q], limit=limit,
                      search_params=params)
    out = []
    t0 = time.perf_counter()
    for q in qvecs:
        r = client.search(collection_name=name, data=[q], limit=limit,
                          search_params=params)
        out.append([h["id"] for h in r[0]])
    return out, (time.perf_counter() - t0) / len(qvecs) * 1000


def recall_at_k(pred, truth, k=TOP_K):
    tot = 0.0
    for p, t in zip(pred, truth):
        tot += len(set(p[:k]) & set(t[:k])) / k
    return tot / len(pred)


def main():
    print("=" * 66)
    print(f"索引基准测试   N={N}  dim={DIM}  簇数={N_CLUSTERS}")
    print("=" * 66)

    vecs, labels = make_data(N, DIM)
    # 查询向量：取真实点加扰动，保证有明确的最近邻
    rng = np.random.default_rng(7)
    qidx = rng.choice(N, N_QUERY, replace=False)
    qvecs = (vecs[qidx] + rng.normal(scale=0.12, size=(N_QUERY, DIM))
             ).astype(np.float32)
    qvecs /= np.linalg.norm(qvecs, axis=1, keepdims=True)
    print(f"已生成数据：{vecs.shape}，查询 {N_QUERY} 条\n")

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    client = MilvusClient(uri=DB_PATH)
    results = []

    # ---- 1. FLAT 暴力（ground truth）----
    print("[1/4] FLAT 暴力检索（作为标准答案）...")
    try:
        t = build(client, "_b_flat", vecs,
                  {"index_type": "FLAT", "params": {}})
        truth, lat = query(client, "_b_flat", qvecs,
                           {"metric_type": "COSINE", "params": {}})
        print(f"      写入 {t:.1f}s   延迟 {lat:.2f} ms/次")
        results.append(("FLAT (基准)", "-", t, lat, 1.0))
    except Exception as e:
        print(f"      [FAIL] {str(e)[:100]}")
        client = None
        return

    # ---- 2. IVF_FLAT nlist=128（你现在的配置）----
    print("[2/4] IVF_FLAT nlist=128（你当前配置）...")
    for nprobe in (10, 32):
        name = f"_b_ivf{nprobe}"
        try:
            t = build(client, name, vecs,
                      {"index_type": "IVF_FLAT", "params": {"nlist": 128}})
            pred, lat = query(client, name, qvecs,
                              {"metric_type": "COSINE",
                               "params": {"nprobe": nprobe}})
            rc = recall_at_k(pred, truth)
            print(f"      nprobe={nprobe:<3} 写入 {t:.1f}s   "
                  f"延迟 {lat:.2f} ms  召回@{TOP_K} {rc*100:.1f}%")
            results.append((f"IVF_FLAT nlist=128", f"nprobe={nprobe}",
                            t, lat, rc))
        except Exception as e:
            print(f"      [FAIL] nprobe={nprobe}: {str(e)[:100]}")

    # ---- 3. HNSW（关键：验证 Lite 是否支持）----
    print("[3/3] HNSW（验证 Milvus Lite 是否支持）...")
    try:
        t = build(client, "_b_hnsw", vecs,
                  {"index_type": "HNSW",
                   "params": {"M": 16, "efConstruction": 200}})
        for ef in (64, 128):
            pred, lat = query(client, "_b_hnsw", qvecs,
                              {"metric_type": "COSINE", "params": {"ef": ef}})
            rc = recall_at_k(pred, truth)
            print(f"      ef={ef:<3}     写入 {t:.1f}s   "
                  f"延迟 {lat:.2f} ms  召回@{TOP_K} {rc*100:.1f}%")
            results.append((f"HNSW M=16", f"ef={ef}", t, lat, rc))
    except Exception as e:
        print(f"      [FAIL] HNSW 不可用: {str(e)[:160]}")
        print("      -> 若 Lite 不支持 HNSW，请改用 IVF_FLAT 并调大 nlist")

    # 汇总
    print("\n" + "=" * 66)
    print("汇总（召回率越高越好，延迟越低越好）")
    print("=" * 66)
    print(f"  {'索引':<22}{'参数':<12}{'写入':>8}{'延迟':>10}{'召回':>9}")
    print("  " + "-" * 60)
    for name, p, t, lat, rc in results:
        print(f"  {name:<22}{p:<12}{t:>7.1f}s{lat:>9.2f}ms{rc*100:>8.1f}%")
    print("  " + "-" * 60)

    hnsw_ok = any("HNSW" in r[0] for r in results)
    print("\n结论：")
    print(f"  Milvus Lite 支持 HNSW : {'是' if hnsw_ok else '否'}")
    if hnsw_ok:
        best = max((r for r in results if "HNSW" in r[0]), key=lambda x: x[4])
        print(f"  HNSW 最优配置: {best[1]}  召回 {best[4]*100:.1f}%  "
              f"延迟 {best[3]:.2f}ms")
    print("\n注：N=5000 只是抽样验证，真实论文数据量下趋势会更明显。")

    # 清理
    for n in ["_b_flat", "_b_ivf8", "_b_ivf32", "_b_ivf1024", "_b_hnsw"]:
        try:
            if client.has_collection(n):
                client.drop_collection(n)
        except Exception:
            pass
    print("测试集合已清理。")


if __name__ == "__main__":
    main()
