"""验证路由模块的惰性初始化

导入任何路由模块都不应构造重量级依赖（Milvus / BM25 / SQLite / LLM），
否则 uvicorn 一启动就会连接数据库，且无法在测试中挂载 api.app。
"""
import importlib

import pytest

LAZY_MODULES = [
    "api.routes.search",
    "api.routes.websocket",
    "api.routes.ingest",
    "api.routes.documents",
    "api.routes.tags",
    "api.routes.agents",
    "api.routes.agent",
]

# 这些类型一旦作为模块属性出现，就说明导入触发了重量级初始化
HEAVY_TYPES = {
    "HybridRetriever",
    "IngestPipeline",
    "SQLiteStore",
    "WritingAgent",
    "StyleAgent",
    "LLMClient",
    "Orchestrator",
    "MilvusStore",
    "BM25Store",
    "EmbeddingClient",
}


@pytest.mark.parametrize("module_name", LAZY_MODULES)
def test_import_does_not_construct_dependencies(module_name):
    module = importlib.import_module(module_name)
    for attr in dir(module):
        value = getattr(module, attr)
        assert type(value).__name__ not in HEAVY_TYPES, (
            f"{module_name}.{attr} 在导入时被构造为 {type(value).__name__}"
        )


def test_retriever_is_lazy_singleton(monkeypatch):
    import rag.retrieve

    module = importlib.import_module("api.routes.search")
    monkeypatch.setattr(module, "_retriever", None)

    created = []

    class FakeRetriever:
        def __init__(self):
            created.append(1)

    monkeypatch.setattr(rag.retrieve, "HybridRetriever", FakeRetriever)

    assert created == []  # 未调用 getter 前不构造
    assert module.get_retriever() is module.get_retriever()
    assert len(created) == 1


def test_pipeline_is_lazy_singleton(monkeypatch):
    import rag.ingest

    module = importlib.import_module("api.routes.ingest")
    monkeypatch.setattr(module, "_pipeline", None)

    created = []

    class FakePipeline:
        def __init__(self):
            created.append(1)

    monkeypatch.setattr(rag.ingest, "IngestPipeline", FakePipeline)

    assert created == []
    assert module.get_pipeline() is module.get_pipeline()
    assert len(created) == 1


def test_metadata_store_is_lazy_singleton(monkeypatch):
    import storage.metadata_store

    module = importlib.import_module("api.routes.documents")
    monkeypatch.setattr(module, "_metadata_store", None)

    created = []

    class FakeStore:
        def __init__(self):
            created.append(1)

    monkeypatch.setattr(storage.metadata_store, "SQLiteStore", FakeStore)

    assert created == []
    assert module.get_metadata_store() is module.get_metadata_store()
    assert len(created) == 1


def test_llm_client_is_lazy_singleton(monkeypatch):
    import core.llm

    module = importlib.import_module("api.routes.websocket")
    monkeypatch.setattr(module, "_llm_client", None)

    created = []

    class FakeClient:
        def __init__(self):
            created.append(1)

    monkeypatch.setattr(core.llm, "LLMClient", FakeClient)

    assert created == []
    assert module.get_llm_client() is module.get_llm_client()
    assert len(created) == 1
