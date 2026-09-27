# -*- coding: utf-8 -*-
"""
探测脚本：确认 Ollama embedding 能出向量、维度是多少。

用法（在 E:/kunxuesuo/agent 下）：
    .venv\\Scripts\\python.exe _milvus_bootstrap\\probe_embedding.py

维度必须和你建 Milvus 集合时用的 dim 一致，否则入库会报错。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.embedding import EmbeddingClient


def main():
    print("正在用项目自带的 EmbeddingClient 调 Ollama ...")
    try:
        client = EmbeddingClient()
    except Exception as e:
        print(f"  [FAIL] 客户端初始化失败: {e}")
        return

    print(f"  模型: {client.model}")
    print(f"  地址: {client.base_url}")

    try:
        vecs = client.embed(["第一段测试文本。", "第二段测试文本。"])
    except Exception as e:
        print(f"  [FAIL] 调用失败: {e}")
        print("\n  排查方向：")
        print("    1. Ollama 是否在运行（任务管理器看 ollama app.exe）")
        print("    2. 模型是否已拉取： ollama pull nomic-embed-text")
        print("    3. .env 里 EMB_BASE_URL 是否是 http://localhost:11434/v1")
        return

    dim = len(vecs[0])
    print(f"  [OK]  成功，条数={len(vecs)}，维度={dim}")
    print(f"  [OK]  前 5 个分量: {[round(x, 5) for x in vecs[0][:5]]}")

    print("\n" + "=" * 50)
    print(f"  建集合时 dim 必须填: {dim}")
    print("=" * 50)

    known = {768: "nomic-embed-text / bge-base-zh",
             1024: "bge-large-zh / bge-m3",
             1536: "text-embedding-3-small"}
    if dim in known:
        print(f"  该维度常见于: {known[dim]}")
    print("\n  如果你换 embedding 模型，必须重建集合（维度不可改）。")


if __name__ == "__main__":
    main()
