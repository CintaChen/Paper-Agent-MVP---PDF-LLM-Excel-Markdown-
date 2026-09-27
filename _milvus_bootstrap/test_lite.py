# -*- coding: utf-8 -*-
"""
验证脚本：在你的项目里，Milvus 到底能不能连上。

用法（在 E:/kunxuesuo/agent 目录下执行）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\test_lite.py

本脚本只做只读探测 + 写入临时集合，不会碰你任何已有数据。
"""
import sys
import traceback
from pathlib import Path

DB_PATH = Path(r"E:/kunxuesuo/agent/storage_data/milvus_lite.db")
TEST_COLLECTION = "_bootstrap_smoke_test"
DIM = 8

ok = lambda m: print(f"  [OK]   {m}")
bad = lambda m: print(f"  [FAIL] {m}")
info = lambda m: print(f"  [..]   {m}")


def section(title):
    print("\n" + "=" * 58)
    print(title)
    print("=" * 58)


def test_a_milvusclient():
    """路径 A：新版 MilvusClient + 本地文件（推荐做法）"""
    section("A. MilvusClient 连本地文件（Milvus Lite）")
    try:
        from pymilvus import MilvusClient, DataType
    except Exception as e:
        bad(f"导入失败: {e}")
        return False

    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        client = MilvusClient(uri=str(DB_PATH))
        ok(f"连接成功 -> {DB_PATH}")

        if client.has_collection(TEST_COLLECTION):
            client.drop_collection(TEST_COLLECTION)
            info("已清理上次测试的临时集合")

        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("id", DataType.VARCHAR, max_length=64, is_primary=True)
        schema.add_field("text", DataType.VARCHAR, max_length=65535)
        schema.add_field("doc_id", DataType.VARCHAR, max_length=64)
        schema.add_field("page", DataType.INT64)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=DIM)

        index = client.prepare_index_params()
        index.add_index(
            field_name="vector",
            metric_type="COSINE",
            index_type="IVF_FLAT",
            params={"nlist": 16},
        )
        client.create_collection(
            collection_name=TEST_COLLECTION, schema=schema, index_params=index
        )
        ok(f"建集合成功（字段 id/text/doc_id/page/vector，COSINE + IVF_FLAT）")

        rows = [
            {"id": "c1", "text": " transformer 在长文本上的注意力改进",
             "doc_id": "p001", "page": 3,
             "vector": [0.9, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]},
            {"id": "c2", "text": " 基于 BERT 的中文分词评测",
             "doc_id": "p002", "page": 7,
             "vector": [0.1, 0.85, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0]},
            {"id": "c3", "text": " 图神经网络在引用网络中的应用",
             "doc_id": "p003", "page": 12,
             "vector": [0.0, 0.0, 0.2, 0.8, 0.0, 0.0, 0.0, 0.0]},
        ]
        client.insert(collection_name=TEST_COLLECTION, data=rows)
        ok("写入 3 条向量")

        res = client.search(
            collection_name=TEST_COLLECTION,
            data=[[0.88, 0.12, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]],
            limit=2,
            output_fields=["text", "doc_id", "page"],
        )
        for hits in res:
            for h in hits:
                e = h["entity"]
                ok(f"命中 id={h['id']} score={h['distance']:.4f} "
                   f"p{e['page']} {e['text'].strip()[:24]}")

        client.drop_collection(TEST_COLLECTION)
        info("临时集合已清理")
        return True
    except Exception:
        bad("MilvusClient 路径失败：")
        traceback.print_exc()
        return False


def test_b_legacy_orm():
    """路径 B：你现有代码用的老式 connections.connect，能否改成 uri 连 Lite"""
    section("B. 老式 connections.connect + uri（最小改动方案）")
    try:
        from pymilvus import (
            connections, Collection, FieldSchema, CollectionSchema,
            DataType, utility,
        )
    except Exception as e:
        bad(f"导入失败: {e}")
        return False

    alias = "lite_probe"
    try:
        connections.connect(alias=alias, uri=str(DB_PATH))
        ok("connections.connect(uri=...) 成功 —— 你只需改这一行")

        name = TEST_COLLECTION + "_orm"
        if utility.has_collection(name, using=alias):
            utility.drop_collection(name, using=alias)

        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR,
                        is_primary=True, max_length=64),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
            FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="page", dtype=DataType.INT64),
            FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=DIM),
        ]
        schema = CollectionSchema(fields=fields, description="smoke test")
        col = Collection(name=name, schema=schema, using=alias)
        col.create_index(
            field_name="vector",
            index_params={"metric_type": "COSINE",
                          "index_type": "IVF_FLAT", "params": {"nlist": 16}},
        )
        ok("Collection / Index 创建成功（与 vector_store.py 同款写法）")

        col.insert([
            ["c1", "c2"],
            ["注意力机制综述", "引用网络分析"],
            ["p001", "p003"],
            [3, 12],
            [[0.9, 0.1, 0, 0, 0, 0, 0, 0], [0, 0, 0.2, 0.8, 0, 0, 0, 0]],
        ])
        col.flush()
        ok(f"写入成功，num_entities = {col.num_entities}")

        col.load()
        hits = col.search(
            data=[[0.9, 0.1, 0, 0, 0, 0, 0, 0]],
            anns_field="vector",
            param={"metric_type": "COSINE", "params": {"nprobe": 8}},
            limit=2,
            output_fields=["text", "doc_id", "page"],
        )
        for rank, h in enumerate(hits[0], 1):
            ok(f"命中 id={h.id} score={h.score:.4f} {h.entity.get('text')}")

        utility.drop_collection(name, using=alias)
        info("临时集合已清理")
        return True
    except Exception:
        bad("老式 API 连 Lite 失败：")
        traceback.print_exc()
        return False
    finally:
        try:
            connections.disconnect(alias)
        except Exception:
            pass


def test_c_server():
    """路径 C：Docker Milvus 服务是否可达"""
    section("C. Docker Milvus 服务（localhost:19530）可达性")
    import socket
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("localhost", 19530))
        ok("19530 端口已通，Milvus 服务在跑")
        s.close()
        return True
    except Exception as e:
        bad(f"连不上 19530：{e}")
        info("Docker Desktop 未启动，或 Milvus 容器未运行")
        return False


if __name__ == "__main__":
    print(f"Python: {sys.version.split()[0]}")
    import pymilvus
    print(f"pymilvus: {pymilvus.__version__}")
    print(f"目标数据文件: {DB_PATH}")

    ra = test_a_milvusclient()
    rb = test_b_legacy_orm()
    rc = test_c_server()

    section("结论")
    print(f"  A 新版 MilvusClient + Lite : {'可 用' if ra else '不可用'}")
    print(f"  B 老式 API + uri 改一行    : {'可 用' if rb else '不可用'}")
    print(f"  C Docker 服务已就绪        : {'是' if rc else '否'}")

    if ra or rb:
        print("\n  -> 不用 Docker 也能跑，数据落在 E 盘：")
        print(f"     {DB_PATH}")
    elif not rc:
        print("\n  -> 需要启动 Docker Desktop，或改用 Zilliz Cloud 托管。")
